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
from app.ai.schemas.planner import PlannerOutput
from app.ai.schemas.reflection import ReflectionOutput
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


def test_planner_returns_the_capabilities_it_selected(fake_llm):
    fake_llm.responses[PlannerOutput] = PlannerOutput(tasks=["sales", "margin"])
    state = {"messages": [HumanMessage(content="What is my profit margin?")]}

    result = business_planner(state)

    assert result["plan"] == ["sales", "margin"]


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

    fake_llm.responses[PlannerOutput] = PlannerOutput(tasks=[])
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


def test_fetcher_retrieves_exactly_the_planned_capabilities(seeded_app_db):
    result = business_fetcher({"plan": ["sales", "expiry"]})

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
        "plan": ["sales"],
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
    assert result["plan"] == ["sales"]


def test_reflector_retries_and_extends_the_plan_when_data_is_missing(fake_llm):
    fake_llm.responses[ReflectionOutput] = ReflectionOutput(
        sufficient=False,
        missing_tasks=["margin"],
        reason="Profitability needs cost data.",
    )

    result = business_reflector(_reflector_state())

    assert result["retry"] is True
    assert result["plan"] == ["sales", "margin"]


def test_reflector_discards_capabilities_the_model_invented(fake_llm):
    """An LLM asking for a tool that does not exist must not reach the fetcher,
    where it would raise ValueError and fail the whole turn."""

    fake_llm.responses[ReflectionOutput] = ReflectionOutput(
        sufficient=False,
        missing_tasks=["customer_demographics", "weather"],
        reason="Needs more context.",
    )

    result = business_reflector(_reflector_state())

    assert result["plan"] == ["sales"]
    assert result["retry"] is False, "no real capability to fetch, so no retry"


def test_reflector_does_not_refetch_an_already_planned_capability(fake_llm):
    """Re-running an identical fetch changes nothing and burns a reflection cycle."""

    fake_llm.responses[ReflectionOutput] = ReflectionOutput(
        sufficient=False,
        missing_tasks=["sales"],
        reason="Wants sales again.",
    )

    result = business_reflector(_reflector_state(plan=["sales"]))

    assert result["plan"] == ["sales"]
    assert result["retry"] is False


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


@pytest.mark.known_gap
def test_memory_is_not_visible_from_a_different_conversation(fake_memory):
    """Documents audit finding B1 — the critical one.

    Memories are written and read filtered by ``thread_id``, so a new conversation
    recalls nothing from any previous one. "Long-term memory" is really same-thread
    scratch memory. Milestone 5 introduces a user/business identity; when it lands,
    this expectation inverts and the test is rewritten to assert recall.
    """

    memory_persistor(
        {"memories": [MemoryFact(fact="Located in Pune.", category="business", confidence=0.9)]},
        _config("conversation-one"),
    )

    result = memory_retriever(
        {"messages": [HumanMessage(content="Where are we located?")]},
        _config("conversation-two"),
    )

    assert result["retrieved_memories"] == [], (
        "Cross-conversation recall now works — B1 is fixed. Replace this gap test "
        "with an assertion that the fact IS recalled."
    )


@pytest.mark.known_gap
def test_memory_persistor_saves_regardless_of_confidence(fake_memory):
    """Documents audit finding B4: there is no write gate.

    A fact the extractor itself is barely confident about is stored as durable truth.
    Milestone 5 adds a threshold.
    """

    low_confidence = MemoryFact(
        fact="The user might prefer evening deliveries.",
        category="preference",
        confidence=0.1,
    )

    memory_persistor({"memories": [low_confidence]}, _config("conv-1"))

    assert len(fake_memory.documents) == 1, (
        "A confidence gate now exists — replace this gap test with threshold tests."
    )
