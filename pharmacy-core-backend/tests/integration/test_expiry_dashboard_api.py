"""The two dashboard endpoints: /report and /explain.

These exist because a dashboard has filters, not a question. The properties worth
protecting here are:

  * /report calls no model at all — it must stay fast and free
  * /explain describes the SAME query it was given, never one a planner chose
  * the summary counts survive a `limit`, or every card on the dashboard lies
"""

from __future__ import annotations

import pytest

from app.ai.graphs.expiry_graph import AGENT_VERSION
from app.ai.schemas.expiry_analysis import ExpiryAnalysis
from app.ai.schemas.expiry_query import ExpiryRiskQuery

pytestmark = pytest.mark.integration

REPORT = "/api/v1/expiry/report"
EXPLAIN = "/api/v1/expiry/explain"


@pytest.fixture
def explain_llm(fake_llm):
    """Only the analyst is scripted.

    Deliberately NO ExpiryRiskQuery response: if anything reaches the planner during
    an /explain call, the fake raises and the test fails. That is the assertion.
    """

    fake_llm.responses[ExpiryAnalysis] = ExpiryAnalysis(
        summary="Four batches carry excess stock.", confidence=0.85
    )
    return fake_llm


# ---------------------------------------------------------------------------
# /report — deterministic
# ---------------------------------------------------------------------------


def test_the_report_endpoint_returns_the_computed_figures(client, expiry_app_db):
    response = client.post(REPORT, json={"window_days": 90, "limit": 100})

    assert response.status_code == 200
    body = response.json()

    assert body["total_batches_reviewed"] == 5
    assert body["total_at_risk"] == 4
    assert body["total_value_at_risk"] == 3900.0
    assert {item["batch_number"] for item in body["items"]} == {
        "P1",
        "P2",
        "A1",
        "V1",
        "C1",
    }


def test_the_report_endpoint_calls_no_model(client, expiry_app_db, fake_llm):
    """`fake_llm` is scripted with nothing, so any model call raises.

    This is the whole point of the endpoint: the table costs nothing to render.
    """

    response = client.post(REPORT, json={"window_days": 90})

    assert response.status_code == 200
    assert fake_llm.calls == []


def test_defaults_apply_when_the_body_is_empty(client, expiry_app_db):
    response = client.post(REPORT, json={})

    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 90
    assert len(body["items"]) <= 10  # the default limit


def test_the_filters_actually_narrow_the_result(client, expiry_app_db):
    week = client.post(REPORT, json={"window_days": 7}).json()

    assert {item["batch_number"] for item in week["items"]} == {"P1", "C1"}


def test_a_risk_level_filter_reaches_the_report(client, expiry_app_db):
    critical = client.post(
        REPORT, json={"window_days": 90, "risk_level": "critical"}
    ).json()

    assert {item["batch_number"] for item in critical["items"]} == {"P1"}
    assert all(item["risk_level"] == "critical" for item in critical["items"])


def test_items_come_back_ranked(client, expiry_app_db):
    body = client.post(REPORT, json={"window_days": 90, "limit": 100}).json()

    assert body["items"][0]["batch_number"] == "C1"  # expired outranks everything


# ---------------------------------------------------------------------------
# Summary counts — the reason they are computed server-side
# ---------------------------------------------------------------------------


def test_counts_cover_every_risk_level(client, expiry_app_db):
    counts = client.post(REPORT, json={"window_days": 90}).json()["counts_by_risk"]

    assert set(counts) == {"expired", "critical", "high", "medium", "low"}


def test_counts_survive_a_limit(client, expiry_app_db):
    """The bug this prevents: counting rows in React instead of batches in the data.

    Ask for the top 1 and the table has one row - but four batches are still at
    risk, and the summary card has to say so.
    """

    full = client.post(REPORT, json={"window_days": 90, "limit": 100}).json()
    limited = client.post(REPORT, json={"window_days": 90, "limit": 1}).json()

    assert len(limited["items"]) == 1
    assert limited["counts_by_risk"] == full["counts_by_risk"]
    assert limited["total_at_risk"] == full["total_at_risk"]
    assert limited["total_value_at_risk"] == full["total_value_at_risk"]


def test_counts_match_the_items_when_nothing_is_truncated(client, expiry_app_db):
    body = client.post(REPORT, json={"window_days": 90, "limit": 100}).json()

    tally: dict[str, int] = {}
    for item in body["items"]:
        tally[item["risk_level"]] = tally.get(item["risk_level"], 0) + 1

    non_zero = {k: v for k, v in body["counts_by_risk"].items() if v}
    assert non_zero == tally


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"window_days": 0},
        {"window_days": 400},
        {"limit": 0},
        {"limit": 5000},
        {"risk_level": "catastrophic"},
        {"medicine_id": 0},
        {"window_days": "soon"},
    ],
)
def test_out_of_range_queries_are_rejected(client, expiry_app_db, body):
    assert client.post(REPORT, json=body).status_code == 422


def test_an_unknown_field_cannot_smuggle_anything_through(client, expiry_app_db):
    """Pydantic ignores unknown keys here; what matters is that it changes nothing."""

    plain = client.post(REPORT, json={"window_days": 7}).json()
    spiked = client.post(
        REPORT, json={"window_days": 7, "order_by": "1; DROP TABLE batches"}
    ).json()

    assert spiked["items"] == plain["items"]


# ---------------------------------------------------------------------------
# /explain
# ---------------------------------------------------------------------------


def test_explain_returns_prose_for_the_given_query(client, expiry_app_db, explain_llm):
    response = client.post(EXPLAIN, json={"window_days": 30})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Four batches carry excess stock."
    assert body["confidence"] == 0.85
    assert body["agent_version"] == AGENT_VERSION


def test_explain_skips_the_planner(client, expiry_app_db, explain_llm):
    """The planner is never scripted, so reaching it would raise.

    Beyond saving a call, this is what stops the prose describing a 90-day window
    while the table on screen shows 7 days.
    """

    assert client.post(EXPLAIN, json={"window_days": 7}).status_code == 200

    schemas = [call.schema for call in explain_llm.calls]
    assert ExpiryRiskQuery not in schemas
    assert schemas == [ExpiryAnalysis]


def test_explain_is_given_the_report_for_the_query_it_was_sent(
    client, expiry_app_db, explain_llm
):
    """A 7-day window must not hand the analyst the 90-day report."""

    client.post(EXPLAIN, json={"window_days": 7})

    prompt = explain_llm.calls[-1].messages[-1].content
    assert '"window_days": 7' in prompt
    assert "P1" in prompt  # in the 7-day window
    assert "A1" not in prompt  # 10 days out, correctly absent


def test_explain_carries_no_figures_of_its_own(client, expiry_app_db, explain_llm):
    """One source of truth per screen: the numbers come from /report."""

    body = client.post(EXPLAIN, json={"window_days": 90}).json()

    assert set(body) == {"answer", "confidence", "execution_time_ms", "agent_version"}


def test_explain_rejects_the_same_bad_queries_as_report(
    client, expiry_app_db, explain_llm
):
    assert client.post(EXPLAIN, json={"window_days": 400}).status_code == 422


def test_an_llm_outage_does_not_fake_an_explanation(
    client, expiry_app_db, fake_llm
):
    fake_llm.error = RuntimeError("provider is down")

    with pytest.raises(RuntimeError):
        client.post(EXPLAIN, json={"window_days": 30})


def test_the_table_still_loads_when_the_model_is_down(client, expiry_app_db, fake_llm):
    """The reason the dashboard makes two calls instead of one.

    An LLM outage costs the pharmacist the summary paragraph, not the report.
    """

    fake_llm.error = RuntimeError("provider is down")

    response = client.post(REPORT, json={"window_days": 90})

    assert response.status_code == 200
    assert response.json()["total_at_risk"] == 4
