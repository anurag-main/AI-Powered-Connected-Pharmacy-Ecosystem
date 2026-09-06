"""The HTTP boundary: request → router → service → graph → response.

Covers the contract the frontend would depend on, and FastAPI's validation edge,
which is the cheapest place to reject a bad request — before any DB or LLM cost.
"""

from __future__ import annotations

import pytest

from app.ai.schemas.business_analysis import BusinessAnalysis

pytestmark = pytest.mark.integration

ENDPOINT = "/api/v1/business/analyze"


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_analyze_returns_the_full_response_contract(
    client, seeded_app_db, fake_llm, thread_id
):
    fake_llm.responses[BusinessAnalysis] = BusinessAnalysis(
        summary="Total sales are 160.00 across 2 orders.",
        key_insights=[],
        recommendations=[],
        confidence=0.92,
    )

    response = client.post(
        ENDPOINT,
        json={"question": "What were total sales?", "thread_id": thread_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Total sales are 160.00 across 2 orders."
    assert body["confidence"] == 0.92
    assert set(body) == {"answer", "confidence", "execution_time_ms", "agent_version"}


def test_analyze_reports_a_measured_execution_time(
    client, seeded_app_db, fake_llm, thread_id
):
    response = client.post(
        ENDPOINT,
        json={"question": "What were total sales?", "thread_id": thread_id},
    )

    assert response.json()["execution_time_ms"] >= 0


def test_the_same_thread_id_continues_a_conversation(
    client, seeded_app_db, fake_llm, thread_id
):
    first = client.post(
        ENDPOINT, json={"question": "What were total sales?", "thread_id": thread_id}
    )
    second = client.post(
        ENDPOINT, json={"question": "And the margin?", "thread_id": thread_id}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    # Two turns on one thread means the analyzer saw a growing transcript.
    analyzer_calls = fake_llm.calls_for(BusinessAnalysis)
    assert len(analyzer_calls[-1].messages) > len(analyzer_calls[0].messages)


# ---------------------------------------------------------------------------
# Validation — rejected before any database or LLM work happens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"thread_id": "t-1"}, "question missing"),
        ({"question": "What were total sales?"}, "thread_id missing"),
        ({"question": "hi", "thread_id": "t-1"}, "question below min_length"),
        ({"question": "x" * 501, "thread_id": "t-1"}, "question above max_length"),
        ({"question": "What were sales?", "thread_id": ""}, "empty thread_id"),
        ({"question": "What were sales?", "thread_id": "x" * 101}, "thread_id too long"),
    ],
)
def test_invalid_requests_are_rejected_with_422(client, fake_llm, payload, reason):
    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 422, reason
    assert fake_llm.calls == [], "validation must happen before any LLM call"


def test_a_malformed_body_is_rejected(client, fake_llm):
    response = client.post(ENDPOINT, content="not json")

    assert response.status_code == 422
    assert fake_llm.calls == []


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_an_llm_outage_does_not_return_a_fake_success(
    client, seeded_app_db, fake_llm, thread_id
):
    """The important half of this assertion is the negative one: the endpoint must
    never answer 200 with an empty or invented analysis when the provider failed.

    Current behaviour is an unhandled exception surfacing as a server error. That is
    honest but crude — there is no error contract and no structured detail for the
    client. Recorded here rather than fixed, since adding one is a behaviour change
    and this milestone is infrastructure only.
    """

    fake_llm.error = RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        client.post(
            ENDPOINT,
            json={"question": "What were total sales?", "thread_id": thread_id},
        )


def test_an_empty_database_still_answers(client, db_session, fake_llm, thread_id):
    response = client.post(
        ENDPOINT,
        json={"question": "What were total sales?", "thread_id": thread_id},
    )

    assert response.status_code == 200
    assert response.json()["answer"]


# ---------------------------------------------------------------------------
# Known gaps
# ---------------------------------------------------------------------------


@pytest.mark.known_gap
def test_agent_version_is_a_service_default_not_agent_state(
    client, seeded_app_db, fake_llm, thread_id
):
    """``agent_version`` and ``execution_time_ms`` are declared on ``BusinessState``
    but written by no node, so the service's fallback is always what ships.

    Harmless today, misleading later: the field looks like it reports the agent's own
    version. Milestone 3 (state cleanup) either populates it or removes it.
    """

    response = client.post(
        ENDPOINT,
        json={"question": "What were total sales?", "thread_id": thread_id},
    )

    assert response.json()["agent_version"] == "business-agent-v1", (
        "a node now sets agent_version — remove this gap test."
    )
