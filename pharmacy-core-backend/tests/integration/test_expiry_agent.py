"""The Expiry Risk Agent end to end: planner → fetcher → analyzer, and over HTTP.

Only the LLM is faked. The graph, the repository, the risk maths and SQLite are real,
so these tests catch a wiring break between two pieces that each pass alone.

The single most important assertion in this file is that the LLM cannot change a
number. Everything else the agent does is replaceable; that property is the reason it
exists rather than being a prompt over an expiry report.
"""

from __future__ import annotations

import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.ai.graphs.expiry_graph import AGENT_VERSION, get_expiry_graph
from app.ai.schemas.expiry_analysis import ExpiryAnalysis
from app.ai.schemas.expiry_query import ExpiryRiskQuery, RiskLevel

pytestmark = pytest.mark.integration

ENDPOINT = "/api/v1/expiry/analyze"


@pytest.fixture
def expiry_llm(fake_llm):
    """The fake, scripted for this agent's two schemas."""

    fake_llm.responses[ExpiryRiskQuery] = ExpiryRiskQuery(window_days=365, limit=100)
    fake_llm.responses[ExpiryAnalysis] = ExpiryAnalysis(
        summary="Four batches carry excess stock; the expired cough syrup is the worst.",
        confidence=0.9,
    )
    return fake_llm


def run_graph(question: str, thread_id: str) -> dict:
    return get_expiry_graph().invoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": thread_id}},
    )


def by_batch(report) -> dict:
    return {item.batch_number: item for item in report.items}


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


def test_the_agent_answers_an_expiry_question(expiry_app_db, expiry_llm, thread_id):
    state = run_graph("Which medicines are expiring soon?", thread_id)

    assert state["answer"]
    assert 0.0 <= state["confidence"] <= 1.0
    assert state["report"].total_batches_reviewed == 6


def test_the_planned_query_drives_the_report(expiry_app_db, expiry_llm, thread_id):
    """The planner/fetcher contract — what breaks if one side changes alone."""

    expiry_llm.responses[ExpiryRiskQuery] = ExpiryRiskQuery(window_days=7, limit=100)

    state = run_graph("What expires this week?", thread_id)

    assert state["query"].window_days == 7
    assert state["report"].window_days == 7
    assert set(by_batch(state["report"])) == {"P1", "C1"}


def test_a_risk_level_filter_reaches_the_report(expiry_app_db, expiry_llm, thread_id):
    expiry_llm.responses[ExpiryRiskQuery] = ExpiryRiskQuery(
        window_days=365, risk_level=RiskLevel.CRITICAL, limit=100
    )

    state = run_graph("Any critical expiry risks?", thread_id)

    assert set(by_batch(state["report"])) == {"P1"}


def test_the_answer_is_recorded_once_in_the_transcript(expiry_app_db, expiry_llm, thread_id):
    state = run_graph("What is expiring?", thread_id)

    ai_messages = [m for m in state["messages"] if isinstance(m, AIMessage)]
    assert len(ai_messages) == 1
    assert ai_messages[0].content == state["answer"]


def test_conversation_history_carries_across_turns(expiry_app_db, expiry_llm, thread_id):
    run_graph("What is expiring?", thread_id)
    state = run_graph("And which is worst?", thread_id)

    questions = [m.content for m in state["messages"] if isinstance(m, HumanMessage)]
    assert questions == ["What is expiring?", "And which is worst?"]


def test_separate_threads_do_not_share_history(expiry_app_db, expiry_llm, thread_id):
    run_graph("What is expiring?", f"{thread_id}-a")
    state = run_graph("What is expiring?", f"{thread_id}-b")

    questions = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    assert len(questions) == 1


# ---------------------------------------------------------------------------
# The property that matters: the model cannot alter the numbers
# ---------------------------------------------------------------------------


def test_the_model_cannot_change_the_computed_figures(expiry_app_db, expiry_llm, thread_id):
    """The whole design in one test.

    The fake analyst returns prose full of invented numbers. The structured report is
    untouched by it, so the API still returns the real, computed values and a caller
    can check the prose against them.
    """

    expiry_llm.responses[ExpiryAnalysis] = ExpiryAnalysis(
        summary="Nothing much is at risk, maybe 3 units worth about 12 rupees.",
        confidence=0.99,
    )

    state = run_graph("What is at risk?", thread_id)
    report = state["report"]

    assert report.total_value_at_risk == 4000.00
    assert report.total_at_risk == 5
    assert by_batch(report)["P2"].potential_excess == 170
    assert by_batch(report)["P2"].value_at_risk == 1700.00


def test_the_analyst_is_given_the_real_report(expiry_app_db, expiry_llm, thread_id):
    """If the figures never reach the prompt the model is answering from nothing, and
    any number in its reply is invented."""

    run_graph("What is at risk?", thread_id)

    prompt = expiry_llm.calls_for(ExpiryAnalysis)[0].messages[-1].content
    assert "potential_excess" in prompt
    assert "170" in prompt
    assert "value_at_risk" in prompt


def test_the_analyst_receives_the_data_caveats(expiry_app_db, expiry_llm, thread_id):
    """The notes are how "no sales history" reaches the user instead of being
    silently presented as zero demand."""

    run_graph("What is at risk?", thread_id)

    prompt = expiry_llm.calls_for(ExpiryAnalysis)[0].messages[-1].content
    assert "No sales history at all" in prompt
    assert "not a forecast" in prompt


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def test_the_endpoint_returns_prose_and_structured_data(
    client, expiry_app_db, expiry_llm, thread_id
):
    response = client.post(
        ENDPOINT,
        json={"question": "Which medicines are expiring soon?", "thread_id": thread_id},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["answer"]
    assert body["agent_version"] == AGENT_VERSION
    assert body["total_value_at_risk"] == 4000.00
    assert body["items"], "the structured items travel with the prose"
    assert body["notes"]


def test_the_response_items_carry_every_computed_field(
    client, expiry_app_db, expiry_llm, thread_id
):
    """A caller must be able to render a table without parsing the sentence."""

    response = client.post(
        ENDPOINT, json={"question": "What is expiring?", "thread_id": thread_id}
    )
    item = response.json()["items"][0]

    assert {
        "batch_number",
        "medicine_name",
        "days_to_expiry",
        "stock_quantity",
        "estimated_demand",
        "potential_excess",
        "value_at_risk",
        "risk_level",
        "priority_score",
        "reasons",
        "recommendation",
    } <= set(item)


def test_items_come_back_ranked(client, expiry_app_db, expiry_llm, thread_id):
    response = client.post(
        ENDPOINT, json={"question": "What should I act on?", "thread_id": thread_id}
    )
    levels = [item["risk_level"] for item in response.json()["items"]]

    assert levels[0] == "expired"
    assert levels == sorted(
        levels, key=lambda level: ["expired", "critical", "high", "medium", "low"].index(level)
    )


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"thread_id": "t-1"}, "question missing"),
        ({"question": "What expires?"}, "thread_id missing"),
        ({"question": "hi", "thread_id": "t-1"}, "question too short"),
        ({"question": "x" * 501, "thread_id": "t-1"}, "question too long"),
        ({"question": "What expires?", "thread_id": ""}, "empty thread_id"),
    ],
)
def test_invalid_requests_are_rejected_before_any_work(
    client, expiry_llm, payload, reason
):
    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 422, reason
    assert expiry_llm.calls == [], "validation must precede any LLM call"


# ---------------------------------------------------------------------------
# Empty and degraded cases
# ---------------------------------------------------------------------------


def test_nothing_at_risk_is_reported_honestly(client, db_session, expiry_llm, thread_id):
    """An empty database must produce "nothing is at risk", not a manufactured concern."""

    response = client.post(
        ENDPOINT, json={"question": "What is expiring?", "thread_id": thread_id}
    )
    body = response.json()

    assert response.status_code == 200
    assert body["items"] == []
    assert body["total_at_risk"] == 0
    assert body["total_value_at_risk"] == 0.0
    assert any("No batches expire" in note for note in body["notes"])


def test_an_llm_outage_does_not_return_a_fake_success(
    client, expiry_app_db, expiry_llm, thread_id
):
    """Same contract as the BI agent: never a cheerful 200 built on nothing."""

    expiry_llm.error = RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        client.post(
            ENDPOINT, json={"question": "What is expiring?", "thread_id": thread_id}
        )


def test_a_database_failure_surfaces(client, expiry_app_db, expiry_llm, thread_id, monkeypatch):
    from app.ai.tools import expiry_tools

    def dead(*_args, **_kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(expiry_tools, "run_expiry_risk", dead)

    with pytest.raises(RuntimeError, match="database is down"):
        client.post(
            ENDPOINT, json={"question": "What is expiring?", "thread_id": thread_id}
        )


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


def test_a_request_yields_a_followable_trace(
    client, expiry_app_db, expiry_llm, thread_id, caplog
):
    from app.core.middleware import REQUEST_ID_HEADER

    with caplog.at_level(logging.INFO):
        response = client.post(
            ENDPOINT, json={"question": "What is expiring?", "thread_id": thread_id}
        )

    request_id = response.headers[REQUEST_ID_HEADER]
    events = [record.getMessage() for record in caplog.records]

    assert "ai_run_started" in events
    assert "ai_run_completed" in events

    nodes = {r.node for r in caplog.records if r.getMessage() == "node_completed"}
    assert {"planner", "fetcher", "analyzer"} <= nodes

    tools = {r.tool for r in caplog.records if r.getMessage() == "tool_completed"}
    assert "expiry_risk" in tools

    agents = {
        r.agent for r in caplog.records if r.getMessage() == "ai_run_started"
    }
    assert agents == {"expiry"}, "the run must be attributed to this agent"

    run_lines = [
        r
        for r in caplog.records
        if r.getMessage() in {"ai_run_started", "node_completed", "tool_completed"}
    ]
    assert {r.request_id for r in run_lines} == {request_id}
    assert len({r.run_id for r in run_lines}) == 1


def test_logs_do_not_leak_stock_levels_or_money(
    client, expiry_app_db, expiry_llm, thread_id, caplog
):
    """The report is commercially sensitive; logs get shape, not contents."""

    with caplog.at_level(logging.DEBUG):
        client.post(
            ENDPOINT, json={"question": "What is expiring?", "thread_id": thread_id}
        )

    blob = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)

    assert "Paracetamol" not in blob
    assert "1700" not in blob
