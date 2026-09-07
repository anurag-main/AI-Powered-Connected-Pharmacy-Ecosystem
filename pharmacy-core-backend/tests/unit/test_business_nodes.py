"""The BI nodes in isolation.

Each node is a plain function over state, which makes it the cheapest useful place
to test. The interesting logic is not the LLM call — it is what each node does with
the answer: the reflector discarding invented capabilities, the planner resetting the
per-turn budget, the finalizer writing exactly one message.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from app.ai.graphs.business_graph import MAX_REFLECTIONS, should_retry
from app.ai.nodes.business_analyzer import business_analyzer
from app.ai.nodes.business_fetcher import business_fetcher
from app.ai.nodes.business_finalizer import business_finalizer
from app.ai.nodes.business_planner import business_planner
from app.ai.nodes.business_reflector import business_reflector
from app.ai.nodes.memory_extractor import memory_extractor
from app.ai.nodes.memory_persistor import memory_persistor
from app.ai.nodes.memory_retriever import memory_retriever
from app.ai.schemas.business_analysis import BusinessAnalysis
from app.ai.schemas.memory import MemoryExtraction, MemoryFact
from app.ai.schemas.business_query import (
    BusinessQuery,
    Dimension,
    Metric,
    PlannerOutput,
)
from app.ai.schemas.reflection import ReflectionOutput
from app.ai.memory.memory_repository import MemoryScope
from app.ai.utils.message_utils import get_latest_user_message
from tests.factories import EXPECTED

pytestmark = pytest.mark.unit


def _config(thread: str) -> dict:
    return {"configurable": {"thread_id": thread}}


# ---------------------------------------------------------------------------
# message_utils
# ---------------------------------------------------------------------------


def test_latest_user_message_ignores_assistant_turns():
    state = {
        "messages": [
            HumanMessage(content="first question"),
            AIMessage(content="an answer"),
            HumanMessage(content="second question"),
            AIMessage(content="another answer"),
        ]
    }

    assert get_latest_user_message(state) == "second question"


def test_latest_user_message_raises_when_there_is_no_user_turn():
    with pytest.raises(ValueError, match="No HumanMessage"):
        get_latest_user_message({"messages": [AIMessage(content="hi")]})


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def test_planner_returns_the_queries_it_selected(fake_llm):
    queries = [BusinessQuery(metric=Metric.SALES), BusinessQuery(metric=Metric.MARGIN)]
    fake_llm.responses[PlannerOutput] = PlannerOutput(queries=queries)
    state = {"messages": [HumanMessage(content="What is my profit margin?")]}

    result = business_planner(state)

    assert [q.metric for q in result["plan"]] == [Metric.SALES, Metric.MARGIN]


def test_planner_carries_period_and_ranking_through(fake_llm):
    """The whole point of the structured plan: the period and the ranking travel
    with the metric instead of being lost between nodes."""

    fake_llm.responses[PlannerOutput] = PlannerOutput(
        queries=[
            BusinessQuery(
                metric=Metric.SALES,
                dimension=Dimension.PRODUCT,
                period="last_month",
                limit=5,
            )
        ]
    )
    state = {"messages": [HumanMessage(content="Top 5 products last month?")]}

    query = business_planner(state)["plan"][0]

    assert query.dimension is Dimension.PRODUCT
    assert query.period.value == "last_month"
    assert query.limit == 5


def test_planner_resets_the_reflection_budget_each_turn(fake_llm):
    """reflection_count is checkpointed, so turn 2 would inherit turn 1's count and
    could skip reflection entirely. The planner must zero it."""

    state = {
        "messages": [HumanMessage(content="What are my sales?")],
        "reflection_count": 2,
    }

    result = business_planner(state)

    assert result["reflection_count"] == 0


def test_planner_can_return_an_empty_plan(fake_llm):
    """An off-topic question is meant to produce no capabilities at all."""

    fake_llm.responses[PlannerOutput] = PlannerOutput(queries=[])
    state = {"messages": [HumanMessage(content="What's the weather?")]}

    assert business_planner(state)["plan"] == []


def test_planner_is_asked_about_the_latest_question_only(fake_llm):
    state = {
        "messages": [
            HumanMessage(content="old question about returns"),
            AIMessage(content="old answer"),
            HumanMessage(content="new question about expiry"),
        ]
    }

    business_planner(state)

    prompt = fake_llm.calls_for(PlannerOutput)[0].messages[-1].content
    assert prompt == "new question about expiry"


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


def test_fetcher_retrieves_exactly_the_planned_queries(seeded_app_db):
    plan = [BusinessQuery(metric=Metric.SALES), BusinessQuery(metric=Metric.EXPIRY)]

    result = business_fetcher({"plan": plan})

    assert set(result["business_metrics"]) == {"sales", "expiry"}
    assert (
        result["business_metrics"]["sales"]["total_sales"]
        == EXPECTED["sales"]["total_sales"]
    )


def test_fetcher_on_an_empty_plan_returns_no_metrics(seeded_app_db):
    assert business_fetcher({"plan": []})["business_metrics"] == {}


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


def test_analyzer_reports_the_summary_and_confidence(fake_llm):
    fake_llm.responses[BusinessAnalysis] = BusinessAnalysis(
        summary="Sales totalled 160.00.",
        key_insights=[],
        recommendations=[],
        confidence=0.85,
    )
    state = {
        "messages": [HumanMessage(content="What are my sales?")],
        "business_metrics": {"sales": {"total_sales": 160.0}},
    }

    result = business_analyzer(state)

    assert result["answer"] == "Sales totalled 160.00."
    assert result["confidence"] == 0.85


def test_analyzer_is_given_the_fetched_metrics(fake_llm):
    """The metrics must actually reach the prompt — otherwise the model is answering
    from nothing and any number it produces is invented."""

    state = {
        "messages": [HumanMessage(content="What are my sales?")],
        "business_metrics": {"sales": {"total_sales": 160.0}},
    }

    business_analyzer(state)

    prompt = fake_llm.calls_for(BusinessAnalysis)[0].messages[-1].content
    assert "total_sales" in prompt
    assert "160.0" in prompt


def test_analyzer_includes_retrieved_memories_when_present(fake_llm):
    state = {
        "messages": [HumanMessage(content="What are my sales?")],
        "business_metrics": {},
        "retrieved_memories": [
            Document(page_content="The pharmacy is located in Pune.")
        ],
    }

    business_analyzer(state)

    prompt = fake_llm.calls_for(BusinessAnalysis)[0].messages[-1].content
    assert "Retrieved Long-Term Memories" in prompt
    assert "located in Pune" in prompt


def test_analyzer_omits_the_memory_section_when_there_are_none(fake_llm):
    state = {
        "messages": [HumanMessage(content="What are my sales?")],
        "business_metrics": {},
        "retrieved_memories": [],
    }

    business_analyzer(state)

    prompt = fake_llm.calls_for(BusinessAnalysis)[0].messages[-1].content
    assert "Retrieved Long-Term Memories" not in prompt


# ---------------------------------------------------------------------------
# Reflector
# ---------------------------------------------------------------------------


def _reflector_state(**overrides) -> dict:
    state = {
        "messages": [HumanMessage(content="What are my sales?")],
        "plan": [BusinessQuery(metric=Metric.SALES)],
        "business_metrics": {"sales": {"total_sales": 160.0}},
        "answer": "Sales totalled 160.00.",
        "reflection_count": 0,
    }
    state.update(overrides)
    return state


def test_reflector_finishes_when_the_data_is_sufficient(fake_llm):
    result = business_reflector(_reflector_state())

    assert result["retry"] is False
    assert result["reflection_count"] == 1
    assert [q.metric for q in result["plan"]] == [Metric.SALES]


def test_reflector_retries_and_extends_the_plan_when_data_is_missing(fake_llm):
    fake_llm.responses[ReflectionOutput] = ReflectionOutput(
        sufficient=False,
        missing_queries=[BusinessQuery(metric=Metric.MARGIN)],
        reason="Profitability needs cost data.",
    )

    result = business_reflector(_reflector_state())

    assert result["retry"] is True
    assert [q.metric for q in result["plan"]] == [Metric.SALES, Metric.MARGIN]


def test_a_query_the_model_invents_cannot_be_constructed():
    """The reflector no longer needs to filter invented capabilities by hand.

    A nonexistent metric or dimension fails Pydantic validation before it can reach
    the node at all, so the filtering moved from a hand-maintained allowlist to the
    type itself.
    """

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReflectionOutput(
            sufficient=False,
            missing_queries=[{"metric": "customer_demographics"}],
            reason="Needs more context.",
        )


def test_reflector_does_not_refetch_an_already_planned_capability(fake_llm):
    """Re-running an identical fetch changes nothing and burns a reflection cycle."""

    fake_llm.responses[ReflectionOutput] = ReflectionOutput(
        sufficient=False,
        missing_queries=[BusinessQuery(metric=Metric.SALES)],
        reason="Wants sales again.",
    )

    result = business_reflector(_reflector_state())

    assert len(result["plan"]) == 1
    assert result["retry"] is False


def test_reflector_treats_a_different_period_as_a_new_query(fake_llm):
    """Same metric, different window, is genuinely new data — the query key is what
    distinguishes them, not the metric name."""

    fake_llm.responses[ReflectionOutput] = ReflectionOutput(
        sufficient=False,
        missing_queries=[BusinessQuery(metric=Metric.SALES, period="last_month")],
        reason="Needs the previous period to compare.",
    )

    result = business_reflector(_reflector_state())

    assert len(result["plan"]) == 2
    assert result["retry"] is True


def test_reflector_increments_the_count_it_was_given(fake_llm):
    result = business_reflector(_reflector_state(reflection_count=1))

    assert result["reflection_count"] == 2


# ---------------------------------------------------------------------------
# Loop guard
# ---------------------------------------------------------------------------


def test_should_retry_loops_while_under_the_cap():
    assert should_retry({"retry": True, "reflection_count": 0}) == "retry"
    assert should_retry({"retry": True, "reflection_count": 1}) == "retry"


def test_should_retry_stops_at_the_cap_even_when_still_unsatisfied():
    """The bounded-loop guarantee: an unsatisfied reflector cannot spin forever."""

    assert should_retry({"retry": True, "reflection_count": MAX_REFLECTIONS}) == "finish"
    assert (
        should_retry({"retry": True, "reflection_count": MAX_REFLECTIONS + 5})
        == "finish"
    )


def test_should_retry_finishes_when_satisfied():
    assert should_retry({"retry": False, "reflection_count": 0}) == "finish"


# ---------------------------------------------------------------------------
# Finalizer
# ---------------------------------------------------------------------------


def test_finalizer_appends_exactly_one_assistant_message():
    """The analyzer reruns on every reflection cycle; only the finalizer writes to
    the transcript, so a turn must produce exactly one AI message."""

    result = business_finalizer({"answer": "Sales totalled 160.00."})

    assert len(result["messages"]) == 1
    message = result["messages"][0]
    assert isinstance(message, AIMessage)
    assert message.content == "Sales totalled 160.00."


# ---------------------------------------------------------------------------
# Memory nodes
# ---------------------------------------------------------------------------


def test_memory_extractor_returns_the_extracted_facts(fake_llm):
    fact = MemoryFact(fact="The pharmacy is in Pune.", category="business", confidence=0.9)
    fake_llm.responses[MemoryExtraction] = MemoryExtraction(memories=[fact])

    result = memory_extractor({"messages": [HumanMessage(content="We are in Pune.")]})

    assert result["memories"] == [fact]


def test_memory_persistor_saves_each_fact_against_the_thread(fake_memory):
    facts = [
        MemoryFact(fact="Located in Pune.", category="business", confidence=0.9),
        MemoryFact(fact="Prefers 100-unit packs.", category="preference", confidence=0.8),
    ]

    memory_persistor({"memories": facts}, _config("conv-1"))

    assert [doc.page_content for doc in fake_memory.documents] == [
        "Located in Pune.",
        "Prefers 100-unit packs.",
    ]
    assert all(doc.metadata["thread_id"] == "conv-1" for doc in fake_memory.documents)


def test_memory_persistor_handles_nothing_worth_remembering(fake_memory):
    memory_persistor({"memories": []}, _config("conv-1"))

    assert fake_memory.documents == []


def test_memory_retriever_returns_facts_from_the_same_conversation(fake_memory):
    memory_persistor(
        {"memories": [MemoryFact(fact="Located in Pune.", category="business", confidence=0.9)]},
        _config("conv-1"),
    )

    result = memory_retriever(
        {"messages": [HumanMessage(content="Where are we located?")]},
        _config("conv-1"),
    )

    assert [doc.page_content for doc in result["retrieved_memories"]] == [
        "Located in Pune."
    ]


def test_memory_is_isolated_between_conversations(fake_memory):
    """Scope isolation — the property the whole memory design turns on.

    A fact learned in one conversation must be invisible from another. Previously
    this was pinned as a known gap; it is now an explicit guarantee, enforced by
    tagging on write AND filtering on read, so a mistake at either end cannot leak
    one pharmacist's conversation into another's.
    """

    memory_persistor(
        {
            "memories": [
                MemoryFact(
                    fact="The pharmacy operates from Pune.",
                    category="business",
                    confidence=0.9,
                )
            ]
        },
        _config("conversation-one"),
    )

    result = memory_retriever(
        {"messages": [HumanMessage(content="Where are we located?")]},
        _config("conversation-two"),
    )

    assert result["retrieved_memories"] == [], (
        "a memory from conversation-one surfaced in conversation-two"
    )


def test_memory_is_visible_within_its_own_conversation(fake_memory):
    """The other half of isolation: scoping must not break normal recall."""

    memory_persistor(
        {
            "memories": [
                MemoryFact(
                    fact="The pharmacy operates from Pune.",
                    category="business",
                    confidence=0.9,
                )
            ]
        },
        _config("conversation-one"),
    )

    result = memory_retriever(
        {"messages": [HumanMessage(content="Where are we located?")]},
        _config("conversation-one"),
    )

    assert [doc.page_content for doc in result["retrieved_memories"]] == [
        "The pharmacy operates from Pune."
    ]


def test_writes_are_tagged_with_their_scope(fake_memory):
    """Read filtering alone would put one scope's rows in another's result set and
    rely on a query parameter to hide them."""

    memory_persistor(
        {
            "memories": [
                MemoryFact(
                    fact="The owner wants monthly reports.",
                    category="preference",
                    confidence=0.9,
                )
            ]
        },
        _config("conv-42"),
    )

    assert fake_memory.documents[0].metadata["thread_id"] == "conv-42"


# ---------------------------------------------------------------------------
# Memory write policy, applied by the node
# ---------------------------------------------------------------------------


def test_a_low_confidence_memory_is_not_persisted(fake_memory):
    """B4 fixed. The extractor proposes; the node decides.

    The QA pass saw an off-topic remark stored at confidence 0.7. It is now refused.
    """

    memory_persistor(
        {
            "memories": [
                MemoryFact(
                    fact="The user might prefer evening deliveries.",
                    category="preference",
                    confidence=0.1,
                )
            ]
        },
        _config("conv-1"),
    )

    assert fake_memory.documents == []


def test_a_memory_in_a_disallowed_category_is_not_persisted(fake_memory):
    memory_persistor(
        {
            "memories": [
                MemoryFact(
                    fact="The election is coming up soon.",
                    category="opinion",
                    confidence=0.95,
                )
            ]
        },
        _config("conv-1"),
    )

    assert fake_memory.documents == []


def test_a_duplicate_memory_is_not_stored_twice(fake_memory):
    """B5 fixed. Restating a stored fact must not create a second document."""

    fact = MemoryFact(
        fact="The pharmacy operates from Pune.", category="business", confidence=0.9
    )

    memory_persistor({"memories": [fact]}, _config("conv-1"))
    memory_persistor({"memories": [fact]}, _config("conv-1"))

    assert len(fake_memory.documents) == 1


def test_the_same_fact_can_be_stored_in_two_different_conversations(fake_memory):
    """Deduplication is per scope. Two conversations each keeping their own copy is
    correct — they cannot read each other's."""

    fact = MemoryFact(
        fact="The pharmacy operates from Pune.", category="business", confidence=0.9
    )

    memory_persistor({"memories": [fact]}, _config("conv-1"))
    memory_persistor({"memories": [fact]}, _config("conv-2"))

    assert len(fake_memory.documents) == 2


def test_a_good_memory_still_gets_through(fake_memory):
    """The gates must not be so tight that nothing is ever remembered."""

    memory_persistor(
        {
            "memories": [
                MemoryFact(
                    fact="The owner wants to cut expiry losses this year.",
                    category="goal",
                    confidence=0.9,
                )
            ]
        },
        _config("conv-1"),
    )

    assert len(fake_memory.documents) == 1


def test_the_persistor_reports_what_it_stored_and_refused(fake_memory, caplog):
    """Observability for a silent decision: a gate that drops data without saying so
    is indistinguishable from a broken gate."""

    import logging

    with caplog.at_level(logging.INFO):
        memory_persistor(
            {
                "memories": [
                    MemoryFact(fact="The pharmacy is in Pune.", category="business", confidence=0.9),
                    MemoryFact(fact="The election is soon.", category="opinion", confidence=0.9),
                ]
            },
            _config("conv-1"),
        )

    record = [r for r in caplog.records if r.getMessage() == "memory_persisted"][-1]
    assert record.proposed == 2
    assert record.stored == 1
    assert record.rejected == 1
