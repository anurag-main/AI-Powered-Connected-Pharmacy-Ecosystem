"""The BI graph end to end: memory → plan → fetch → analyze → reflect → persist.

These tests cross real boundaries — the compiled LangGraph, the checkpointer, the
thread pool, and SQLite — with only the LLM and the vector store faked. They are the
tests that catch a wiring break between two nodes that each pass in isolation.

``get_business_graph()`` is ``lru_cache``d, so its ``MemorySaver`` survives across
tests; every test therefore uses the ``thread_id`` fixture for a unique conversation.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.ai.graphs.business_graph import MAX_REFLECTIONS, get_business_graph
from app.ai.schemas.business_analysis import BusinessAnalysis
from app.ai.schemas.memory import MemoryExtraction, MemoryFact
from app.ai.schemas.business_query import BusinessQuery, Dimension, Metric, PlannerOutput
from app.ai.schemas.reflection import ReflectionOutput
from tests.factories import EXPECTED

pytestmark = pytest.mark.integration


def run_graph(question: str, thread_id: str) -> dict:
    return get_business_graph().invoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": thread_id}},
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_a_sales_question_completes_and_answers(seeded_app_db, fake_llm, thread_id):
    state = run_graph("What were total sales?", thread_id)

    assert [q.metric.value for q in state["plan"]] == ["sales"]
    assert state["business_metrics"]["sales"]["total_sales"] == (
        EXPECTED["sales"]["total_sales"]
    )
    assert state["answer"]
    assert 0.0 <= state["confidence"] <= 1.0


def test_the_plan_and_the_fetched_metrics_stay_in_step(
    seeded_app_db, fake_llm, thread_id
):
    """The planner/fetcher contract: everything planned is fetched, and nothing else.

    This is the single most valuable assertion in the file — it is what breaks if
    someone changes the plan format on one side only.
    """

    fake_llm.responses[PlannerOutput] = PlannerOutput(queries=[BusinessQuery(metric=Metric.SALES), BusinessQuery(metric=Metric.MARGIN), BusinessQuery(metric=Metric.EXPIRY)])

    state = run_graph("How healthy is the business?", thread_id)

    assert set(state["business_metrics"]) == {q.key() for q in state["plan"]}


def test_the_answer_is_recorded_once_in_the_transcript(
    seeded_app_db, fake_llm, thread_id
):
    """The analyzer reruns on each reflection cycle; only the finalizer writes."""

    state = run_graph("What were total sales?", thread_id)

    ai_messages = [m for m in state["messages"] if isinstance(m, AIMessage)]
    assert len(ai_messages) == 1
    assert ai_messages[0].content == state["answer"]


def test_conversation_history_carries_across_turns(seeded_app_db, fake_llm, thread_id):
    """Same thread id must accumulate the conversation via the checkpointer."""

    run_graph("What were total sales?", thread_id)
    state = run_graph("And my margin?", thread_id)

    human_turns = [m.content for m in state["messages"] if isinstance(m, HumanMessage)]
    assert human_turns == ["What were total sales?", "And my margin?"]


def test_separate_threads_do_not_share_history(seeded_app_db, fake_llm, thread_id):
    run_graph("What were total sales?", f"{thread_id}-a")
    state = run_graph("What were total sales?", f"{thread_id}-b")

    human_turns = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    assert len(human_turns) == 1


# ---------------------------------------------------------------------------
# Off-topic
# ---------------------------------------------------------------------------


def test_an_off_topic_question_fetches_no_business_data(
    seeded_app_db, fake_llm, thread_id
):
    """The intended behaviour per PLANNER_SYSTEM_PROMPT: out-of-domain input yields
    an empty capability list, so no tool runs and no metric is invented.

    The refusal *wording* is the model's job and is not asserted here — with a fake
    LLM that would only be testing the fake. It is covered by the golden set's
    real-LLM mode.
    """

    fake_llm.responses[PlannerOutput] = PlannerOutput(queries=[])

    state = run_graph("What is the capital of France?", thread_id)

    assert state["plan"] == []
    assert state["business_metrics"] == {}
    assert state["answer"], "the graph must still produce an answer, not crash"


# ---------------------------------------------------------------------------
# Reflection loop
# ---------------------------------------------------------------------------


def test_reflection_fetches_the_missing_capability_and_then_finishes(
    seeded_app_db, fake_llm, thread_id
):
    """First pass: reflector says margin is missing. Second pass: satisfied."""

    verdicts = iter(
        [
            ReflectionOutput(
                sufficient=False,
                missing_queries=[BusinessQuery(metric=Metric.MARGIN)],
                reason="Profitability needs cost data.",
            ),
            ReflectionOutput(
                sufficient=True, missing_queries=[], reason="Complete."
            ),
        ]
    )
    fake_llm.responses[ReflectionOutput] = lambda _messages: next(verdicts)

    state = run_graph("Is my business profitable?", thread_id)

    assert {q.metric.value for q in state["plan"]} == {"sales", "margin"}
    assert set(state["business_metrics"]) == {"sales", "margin"}
    assert state["reflection_count"] == 2


def test_a_permanently_unsatisfied_reflector_still_terminates(
    seeded_app_db, fake_llm, thread_id
):
    """The bounded-loop guarantee under the worst case: the reflector never accepts
    the answer. The cap must stop it and the graph must still return."""

    def never_satisfied(_messages):
        return ReflectionOutput(
            sufficient=False,
            missing_queries=[
                BusinessQuery(metric=Metric.MARGIN),
                BusinessQuery(metric=Metric.EXPIRY),
                BusinessQuery(metric=Metric.RETURNS),
                BusinessQuery(metric=Metric.PURCHASES),
            ],
            reason="Still not enough.",
        )

    fake_llm.responses[ReflectionOutput] = never_satisfied

    state = run_graph("Is my business profitable?", thread_id)

    assert state["reflection_count"] <= MAX_REFLECTIONS
    assert state["answer"]


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


def test_extracted_memories_are_persisted_for_the_thread(
    seeded_app_db, fake_llm, fake_memory, thread_id
):
    fake_llm.responses[MemoryExtraction] = MemoryExtraction(
        memories=[
            MemoryFact(fact="The pharmacy is in Pune.", category="business", confidence=0.9)
        ]
    )

    run_graph("We are based in Pune. What were sales?", thread_id)

    assert [doc.page_content for doc in fake_memory.documents] == [
        "The pharmacy is in Pune."
    ]
    assert fake_memory.documents[0].metadata["thread_id"] == thread_id


def test_a_persisted_memory_is_retrieved_on_the_next_turn(
    seeded_app_db, fake_llm, fake_memory, thread_id
):
    fake_llm.responses[MemoryExtraction] = MemoryExtraction(
        memories=[
            MemoryFact(fact="The pharmacy is in Pune.", category="business", confidence=0.9)
        ]
    )
    run_graph("We are based in Pune.", thread_id)

    # Nothing new to store on the second turn.
    fake_llm.responses[MemoryExtraction] = MemoryExtraction(memories=[])
    state = run_graph("Where are we located?", thread_id)

    assert [doc.page_content for doc in state["retrieved_memories"]] == [
        "The pharmacy is in Pune."
    ]


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_an_llm_outage_propagates_rather_than_faking_success(
    seeded_app_db, fake_llm, thread_id
):
    """If the provider is down the caller must learn about it. Swallowing the error
    and returning a cheerful empty analysis would be the worst possible behaviour —
    a confident answer built on nothing.

    This pins current behaviour: the exception escapes the graph. Whether that should
    become a structured degraded response is a design decision for a later milestone;
    the test exists so the choice is made deliberately.
    """

    fake_llm.error = RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        run_graph("What were total sales?", thread_id)


def test_a_database_outage_yields_error_metrics_not_a_crash(
    seeded_app_db, fake_llm, thread_id, monkeypatch
):
    """Per-tool isolation carried through the whole graph: the run completes, and the
    failure is visible in the metrics rather than silently absent."""

    from app.ai.tools import business_tools

    def dead(query, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(business_tools, "execute_business_query", dead)

    state = run_graph("What were total sales?", thread_id)

    assert state["business_metrics"]["sales"] == {"error": "database is down"}
    assert state["answer"], "a tool outage must still produce an answer"


def test_an_empty_database_completes_with_zeroed_metrics(
    db_session, fake_llm, thread_id
):
    """A brand-new pharmacy with no data at all must not break the agent."""

    state = run_graph("What were total sales?", thread_id)

    assert state["business_metrics"]["sales"]["total_orders"] == 0
    assert state["answer"]


def test_an_analysis_the_model_is_unsure_of_keeps_its_low_confidence(
    seeded_app_db, fake_llm, thread_id
):
    """Confidence must reach the caller untouched — it is the signal a UI would use
    to warn the pharmacist not to act on the answer."""

    fake_llm.responses[BusinessAnalysis] = BusinessAnalysis(
        summary="I cannot ground this in the available data.",
        key_insights=[],
        recommendations=[],
        confidence=0.0,
    )

    state = run_graph("Which supplier is slowest?", thread_id)

    assert state["confidence"] == 0.0
