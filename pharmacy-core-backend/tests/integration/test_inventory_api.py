"""The three inventory endpoints, end to end through FastAPI.

FastAPI -> agent service -> graph/tool -> InventoryRiskService -> DemandService ->
repositories -> the test database. Only the LLM is faked.

The properties worth protecting here are the same three the expiry dashboard
protects, plus one that is specific to this agent:

  * /report calls no model at all - it must stay fast and free
  * /explain describes the SAME query it was given, never one a planner chose
  * the summary counts survive a filter and a limit, or every card on the dashboard lies
  * the report never leaks an expiry date, or this screen becomes the expiry screen
"""

from __future__ import annotations

import pytest

from app.ai.graphs.inventory_graph import AGENT_VERSION
from app.ai.schemas.inventory_analysis import InventoryAnalysis
from app.ai.schemas.inventory_query import InventoryRiskQuery
from tests.factories import INVENTORY_TOTAL_AT_RISK, INVENTORY_TOTAL_VALUE

pytestmark = pytest.mark.integration

REPORT = "/api/v1/inventory/report"
EXPLAIN = "/api/v1/inventory/explain"
ANALYZE = "/api/v1/inventory/analyze"


@pytest.fixture
def explain_llm(fake_llm):
    """Only the analyst is scripted.

    Deliberately NO InventoryRiskQuery response: if anything reaches the planner
    during an /explain call, the fake raises and the test fails. That is the
    assertion.
    """

    fake_llm.responses[InventoryAnalysis] = InventoryAnalysis(
        summary="Two medicines are dead stock.", confidence=0.85
    )
    return fake_llm


@pytest.fixture
def analyze_llm(fake_llm):
    """Both nodes scripted, for the full chat flow."""

    fake_llm.responses[InventoryRiskQuery] = InventoryRiskQuery(limit=100)
    fake_llm.responses[InventoryAnalysis] = InventoryAnalysis(
        summary="Rs 62,750 of capital is at risk.", confidence=0.8
    )
    return fake_llm


def names(body) -> set[str]:
    return {item["medicine_name"] for item in body["items"]}


# ---------------------------------------------------------------------------
# /report - deterministic
# ---------------------------------------------------------------------------


def test_the_report_returns_the_computed_figures(client, inventory_app_db):
    response = client.post(REPORT, json={"limit": 100})

    assert response.status_code == 200
    body = response.json()

    assert body["medicines_reviewed"] == 6
    assert body["medicines_without_stock"] == 1
    assert body["total_inventory_value"] == INVENTORY_TOTAL_VALUE
    assert body["total_capital_at_risk"] == INVENTORY_TOTAL_AT_RISK


def test_the_report_calls_no_model(client, inventory_app_db, fake_llm):
    """`fake_llm` is scripted with nothing, so any model call raises.

    This is the whole point of the endpoint: the table costs nothing to render, and
    the business calculation does not depend on the LLM being reachable.
    """

    response = client.post(REPORT, json={})

    assert response.status_code == 200
    assert fake_llm.calls == []


def test_defaults_apply_when_the_body_is_empty(client, inventory_app_db):
    response = client.post(REPORT, json={})

    assert response.status_code == 200
    body = response.json()

    assert body["target_cover_days"] == 60
    assert len(body["items"]) <= 10  # the default limit


def test_every_medicine_is_ranked_worst_first(client, inventory_app_db):
    response = client.post(REPORT, json={"limit": 100})

    levels = [item["risk_level"] for item in response.json()["items"]]

    assert levels == ["dead", "dead", "critical", "medium", "healthy", "healthy"]


def test_the_report_carries_the_reasons_behind_each_level(client, inventory_app_db):
    body = client.post(REPORT, json={"limit": 100}).json()

    amoxicillin = next(i for i in body["items"] if i["medicine_name"] == "Amoxicillin 250")

    assert "never sold" in amoxicillin["risk_reasons"]
    assert amoxicillin["capital_at_risk"] == 25_000.00


def test_the_report_never_exposes_an_expiry_date(client, inventory_app_db):
    """The boundary with the expiry agent. Ibuprofen holds 40 expired units and the
    report must describe them as a count, never as a date."""

    body = client.post(REPORT, json={"limit": 100}).json()

    ibuprofen = next(i for i in body["items"] if i["medicine_name"] == "Ibuprofen 400")

    assert ibuprofen["stock_quantity"] == 100
    assert ibuprofen["sellable_quantity"] == 60
    assert "40 unit(s) no longer sellable" in ibuprofen["risk_reasons"]
    assert not any("expir" in r.lower() for r in ibuprofen["risk_reasons"])


def test_unknown_values_are_null_not_zero(client, inventory_app_db):
    """A never-sold medicine has no cover figure, and Ibuprofen's expired batch has
    no purchase line. Both must come back as null - zero would be a claim."""

    body = client.post(REPORT, json={"limit": 100}).json()

    amoxicillin = next(i for i in body["items"] if i["medicine_name"] == "Amoxicillin 250")

    assert amoxicillin["days_of_cover"] is None
    assert amoxicillin["last_sale_date"] is None
    assert amoxicillin["days_since_last_sale"] is None
    assert amoxicillin["ever_sold"] is False


# ---------------------------------------------------------------------------
# /report - filtering, sorting, limiting
# ---------------------------------------------------------------------------


def test_filtering_by_risk_level(client, inventory_app_db):
    body = client.post(REPORT, json={"risk_level": "dead", "limit": 100}).json()

    assert names(body) == {"Amoxicillin 250", "Cough Syrup 100ml"}


def test_filtering_by_capital_floor(client, inventory_app_db):
    body = client.post(REPORT, json={"min_capital_at_risk": 20000, "limit": 100}).json()

    assert names(body) == {"Amoxicillin 250", "Cetirizine 10"}


def test_filtering_by_medicine(client, inventory_app_db):
    body = client.post(REPORT, json={"medicine_id": 1, "limit": 100}).json()

    assert len(body["items"]) == 1
    assert body["items"][0]["medicine_id"] == 1


def test_a_filter_that_matches_nothing_returns_an_empty_list_not_an_error(
    client, inventory_app_db
):
    response = client.post(REPORT, json={"min_capital_at_risk": 10_000_000})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["items_matching_filter"] == 0


def test_sorting_by_capital_ignores_the_risk_level(client, inventory_app_db):
    """Cetirizine holds the most money but is only critical; the dead items rank
    above it under the default sort and below it under this one."""

    body = client.post(
        REPORT, json={"sort": "capital_at_risk", "limit": 100}
    ).json()

    assert [i["medicine_name"] for i in body["items"]][:2] == [
        "Cetirizine 10",
        "Amoxicillin 250",
    ]


def test_sorting_by_cover_puts_unmeasurable_medicines_last(client, inventory_app_db):
    """A medicine with no sales has no cover figure. It must not outrank a medicine
    that actually has 400 days of it."""

    body = client.post(REPORT, json={"sort": "days_of_cover", "limit": 100}).json()
    ordered = [i["medicine_name"] for i in body["items"]]

    assert ordered[0] == "Cetirizine 10", "400 days of cover"
    assert ordered.index("Amoxicillin 250") > ordered.index("Vitamin C 500")


def test_sorting_by_stock_age_puts_the_oldest_first(client, inventory_app_db):
    body = client.post(REPORT, json={"sort": "stock_age", "limit": 100}).json()

    assert body["items"][0]["medicine_name"] == "Amoxicillin 250"
    assert body["items"][0]["stock_age_days"] == 300


def test_the_limit_truncates_the_list(client, inventory_app_db):
    body = client.post(REPORT, json={"limit": 2}).json()

    assert len(body["items"]) == 2


def test_the_counts_survive_a_limit(client, inventory_app_db):
    """The whole reason counts_by_risk exists. Counting rows in the response would
    cap every summary card at the limit."""

    body = client.post(REPORT, json={"limit": 1}).json()

    assert len(body["items"]) == 1
    assert body["counts_by_risk"] == {
        "dead": 2,
        "critical": 1,
        "high": 0,
        "medium": 1,
        "healthy": 2,
    }


def test_the_totals_survive_a_filter(client, inventory_app_db):
    """Filtered to dead stock, the shop-level KPIs must still describe the shop. A
    dashboard filtered to one level should not claim the shop holds Rs 27,400."""

    body = client.post(REPORT, json={"risk_level": "dead", "limit": 100}).json()

    assert body["total_inventory_value"] == INVENTORY_TOTAL_VALUE
    assert body["total_capital_at_risk"] == INVENTORY_TOTAL_AT_RISK
    assert body["items_matching_filter"] == 2
    assert body["medicines_reviewed"] == 6


def test_the_filtered_view_states_its_own_subtotal(client, inventory_app_db):
    """Found by a real round trip: asked to describe a filtered report, the model
    added the visible rows up itself and got the wrong number. Adding is not its job,
    so the subtotal is computed here and handed to it.

    It is taken before `limit`, so a truncated table still reports the full subtotal
    for what matched.
    """

    body = client.post(REPORT, json={"risk_level": "dead", "limit": 1}).json()

    assert len(body["items"]) == 1, "truncated by the limit"
    assert body["items_matching_filter"] == 2
    assert body["capital_at_risk_in_view"] == 27_400.00, "both dead medicines"
    assert body["total_capital_at_risk"] == INVENTORY_TOTAL_AT_RISK


def test_an_unfiltered_view_subtotal_equals_the_shop_total(client, inventory_app_db):
    body = client.post(REPORT, json={"limit": 100}).json()

    assert body["capital_at_risk_in_view"] == body["total_capital_at_risk"]


def test_a_shorter_target_cover_creates_more_excess(client, inventory_app_db):
    at_sixty = client.post(REPORT, json={"target_cover_days": 60, "limit": 100}).json()
    at_thirty = client.post(REPORT, json={"target_cover_days": 30, "limit": 100}).json()

    assert at_thirty["total_capital_at_risk"] > at_sixty["total_capital_at_risk"]
    assert at_thirty["target_cover_days"] == 30


# ---------------------------------------------------------------------------
# /report - validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"risk_level": "catastrophic"},
        {"risk_level": "expired"},
        {"limit": 0},
        {"limit": -5},
        {"limit": 100_000},
        {"target_cover_days": 1},
        {"target_cover_days": 400},
        {"min_capital_at_risk": -1},
        {"medicine_id": 0},
        {"sort": "cost_price DESC"},
    ],
    ids=[
        "invented risk level",
        "the expiry agent's risk level",
        "zero limit",
        "negative limit",
        "unbounded limit",
        "target cover too short",
        "target cover too long",
        "negative capital floor",
        "zero medicine id",
        "a column name as a sort",
    ],
)
def test_an_invalid_query_is_rejected_with_422(client, inventory_app_db, body):
    assert client.post(REPORT, json=body).status_code == 422


def test_a_validation_error_does_not_leak_sql_or_internals(client, inventory_app_db):
    response = client.post(REPORT, json={"sort": "1; DROP TABLE batches"})

    assert response.status_code == 422
    assert "Traceback" not in response.text
    assert "SELECT" not in response.text.upper()


# ---------------------------------------------------------------------------
# /report - empty and degenerate
# ---------------------------------------------------------------------------


def test_an_empty_database_returns_an_empty_report(client, db_session):
    response = client.post(REPORT, json={})

    assert response.status_code == 200
    body = response.json()

    assert body["items"] == []
    assert body["medicines_reviewed"] == 0
    assert body["total_capital_at_risk"] == 0.0
    assert body["notes"] == ["No medicine currently holds stock."]


def test_a_database_failure_is_not_reported_as_success(
    client, inventory_app_db, monkeypatch
):
    """The failure mode that matters most: a broken query must never come back as an
    empty-but-successful report, which a dashboard would render as 'nothing at risk'.
    """

    from app.repositories import inventory_repository

    def explode(*args, **kwargs):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(
        inventory_repository.InventoryRepository, "stock_by_medicine", explode
    )

    with pytest.raises(RuntimeError):
        client.post(REPORT, json={})


# ---------------------------------------------------------------------------
# /explain
# ---------------------------------------------------------------------------


def test_explain_returns_prose_for_the_given_query(client, inventory_app_db, explain_llm):
    response = client.post(EXPLAIN, json={"risk_level": "dead"})

    assert response.status_code == 200
    body = response.json()

    assert body["answer"] == "Two medicines are dead stock."
    assert body["confidence"] == 0.85
    assert body["agent_version"] == AGENT_VERSION


def test_explain_skips_the_planner(client, inventory_app_db, explain_llm):
    """`explain_llm` scripts no InventoryRiskQuery, so reaching the planner raises.

    This is what guarantees the prose describes the rows on screen rather than a
    target cover the model picked for itself.
    """

    response = client.post(EXPLAIN, json={"target_cover_days": 30})

    assert response.status_code == 200


def test_explain_carries_no_figures_of_its_own(client, inventory_app_db, explain_llm):
    """The dashboard already holds the numbers from /report. Duplicating them here
    would create two sources of truth for one screen."""

    body = client.post(EXPLAIN, json={}).json()

    assert set(body) == {"answer", "confidence", "execution_time_ms", "agent_version"}


def test_explain_rejects_an_invalid_query_before_calling_the_model(
    client, inventory_app_db, explain_llm
):
    response = client.post(EXPLAIN, json={"risk_level": "catastrophic"})

    assert response.status_code == 422
    assert explain_llm.calls == []


# ---------------------------------------------------------------------------
# /analyze
# ---------------------------------------------------------------------------


def test_analyze_answers_a_question_and_returns_the_data(
    client, inventory_app_db, analyze_llm
):
    response = client.post(
        ANALYZE,
        json={"question": "Which medicines are dead stock?", "thread_id": "t-inv-1"},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["answer"] == "Rs 62,750 of capital is at risk."
    assert body["medicines_reviewed"] == 6
    assert body["total_capital_at_risk"] == INVENTORY_TOTAL_AT_RISK
    assert len(body["items"]) == 6
    assert body["agent_version"] == AGENT_VERSION


def test_analyze_runs_the_planner(client, inventory_app_db, analyze_llm):
    """The one endpoint that does. It is the only one where the parameters have to
    be inferred from a sentence."""

    client.post(
        ANALYZE,
        json={"question": "Where is my money stuck?", "thread_id": "t-inv-2"},
    )

    assert analyze_llm.call_count(InventoryRiskQuery) == 1
    assert analyze_llm.call_count(InventoryAnalysis) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"question": "hi", "thread_id": "t"},
        {"question": "", "thread_id": "t"},
        {"question": "x" * 501, "thread_id": "t"},
        {"question": "What is overstocked?"},
        {"thread_id": "t"},
    ],
    ids=["too short", "empty", "too long", "no thread id", "no question"],
)
def test_analyze_rejects_a_malformed_request(client, inventory_app_db, body):
    assert client.post(ANALYZE, json=body).status_code == 422
