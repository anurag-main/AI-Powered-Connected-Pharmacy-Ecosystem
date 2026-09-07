"""The business data tool and the parallel executor that drives it.

The tool opens its own database session rather than receiving one, so these tests
exercise the real ``SessionLocal`` path — pointed at the temp SQLite file by
``conftest``, not at MySQL.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.ai.schemas.business_query import BusinessQuery, Dimension, Metric
from app.ai.tools import business_tools
from app.ai.tools.business_tools import (
    BUSINESS_TOOLS,
    execute_business_query,
    get_business_metrics,
    query_business_data,
)
from app.core.time_range import Period
from tests.factories import EXPECTED

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------


def test_a_summary_query_returns_the_repository_figures(seeded_app_db):
    result = execute_business_query(BusinessQuery(metric=Metric.SALES))

    assert result["total_sales"] == EXPECTED["sales"]["total_sales"]
    assert result["total_orders"] == EXPECTED["sales"]["total_orders"]


@pytest.mark.parametrize("metric", list(Metric))
def test_every_metric_is_reachable_through_the_tool(seeded_app_db, metric):
    result = execute_business_query(BusinessQuery(metric=metric))

    assert isinstance(result, dict) and result


def test_a_breakdown_query_returns_ranked_rows(seeded_app_db):
    query = BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT, limit=1)

    result = execute_business_query(query)

    assert result["rows"] == [
        {"label": "Crocin 500", "value": 100.0, "quantity": 5}
    ]


def test_a_date_filtered_query_reaches_the_repository(seeded_app_db):
    query = BusinessQuery(
        metric=Metric.SALES,
        period=Period.CUSTOM,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
    )

    result = execute_business_query(query)

    assert result["total_sales"] == 100.0
    assert result["period"] == "2026-08-01"


def test_a_named_period_resolves_against_a_supplied_date(seeded_app_db):
    """as_of is threaded through so a test never depends on the real clock."""

    query = BusinessQuery(metric=Metric.SALES, period=Period.LAST_MONTH)

    result = execute_business_query(query, as_of=date(2026, 9, 16))

    # The scenario's sales are in August, which is "last month" from mid-September.
    assert result["total_sales"] == EXPECTED["sales"]["total_sales"]
    assert result["period"] == "2026-08-01 to 2026-08-31"


# ---------------------------------------------------------------------------
# The tool surface the model sees
# ---------------------------------------------------------------------------


def test_exactly_one_tool_is_exposed():
    """One parameterised entry point, not five zero-argument ones."""

    assert len(BUSINESS_TOOLS) == 1
    assert BUSINESS_TOOLS[0].name == "query_business_data"


def test_the_tool_accepts_structured_arguments():
    """The old tools took nothing, so no question about a period or a ranking could
    be expressed at all."""

    args = query_business_data.args

    assert {"metric", "dimension", "period", "sort", "limit"} <= set(args)


def test_the_tool_runs_a_valid_query(seeded_app_db):
    result = query_business_data.invoke({"metric": "sales"})

    assert result["total_sales"] == EXPECTED["sales"]["total_sales"]


def test_the_tool_runs_a_breakdown(seeded_app_db):
    result = query_business_data.invoke(
        {"metric": "sales", "dimension": "product", "limit": 2}
    )

    assert len(result["rows"]) == 2


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"metric": "inventory"}, "metric does not exist"),
        ({"metric": "sales", "dimension": "category"}, "dimension does not exist"),
        ({"metric": "sales", "dimension": "supplier"}, "unsupported combination"),
        ({"metric": "sales", "dimension": "product", "limit": 999999}, "limit too large"),
        ({"metric": "sales", "dimension": "product", "limit": 0}, "limit too small"),
        ({"metric": "expiry", "period": "last_month"}, "expiry takes no period"),
        ({"metric": "sales", "period": "custom"}, "custom needs dates"),
        ({"metric": "sales; DROP TABLE sales"}, "injection attempt"),
    ],
)
def test_the_tool_rejects_invalid_arguments(arguments, reason):
    """Validation happens before any database work, so a bad call costs nothing."""

    with pytest.raises(ValidationError):
        query_business_data.invoke(arguments)


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


def test_several_queries_run_and_are_keyed_separately(seeded_app_db):
    queries = [
        BusinessQuery(metric=Metric.SALES),
        BusinessQuery(metric=Metric.MARGIN),
    ]

    metrics = get_business_metrics(queries)

    assert set(metrics) == {"sales", "margin"}
    assert metrics["sales"]["total_sales"] == EXPECTED["sales"]["total_sales"]
    assert metrics["margin"]["cogs"] == EXPECTED["margin"]["cogs"]


def test_a_summary_and_a_breakdown_of_the_same_metric_coexist(seeded_app_db):
    """Keying by metric name alone would let the second overwrite the first, and the
    analyzer would answer "top products" with an overall total."""

    queries = [
        BusinessQuery(metric=Metric.SALES),
        BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT),
    ]

    metrics = get_business_metrics(queries)

    assert set(metrics) == {"sales", "sales_by_product"}
    assert "total_sales" in metrics["sales"]
    assert "rows" in metrics["sales_by_product"]


def test_all_five_metrics_run_concurrently(seeded_app_db):
    metrics = get_business_metrics([BusinessQuery(metric=m) for m in Metric])

    assert set(metrics) == {m.value for m in Metric}
    assert not any("error" in value for value in metrics.values())


def test_an_empty_plan_fetches_nothing():
    """An off-topic question produces an empty plan; that is not an error."""

    assert get_business_metrics([]) == {}


def test_one_failing_query_does_not_lose_the_others(seeded_app_db, monkeypatch):
    """Per-query failure isolation keeps a partial outage honest instead of total."""

    original = business_tools.execute_business_query

    def flaky(query, **kwargs):
        if query.metric is Metric.MARGIN:
            raise RuntimeError("margin query exploded")
        return original(query, **kwargs)

    monkeypatch.setattr(business_tools, "execute_business_query", flaky)

    metrics = get_business_metrics(
        [BusinessQuery(metric=Metric.SALES), BusinessQuery(metric=Metric.MARGIN)]
    )

    assert metrics["margin"] == {"error": "margin query exploded"}
    assert metrics["sales"]["total_sales"] == EXPECTED["sales"]["total_sales"]


def test_a_total_database_outage_reports_errors_rather_than_crashing(
    seeded_app_db, monkeypatch
):
    def dead(query, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(business_tools, "execute_business_query", dead)

    metrics = get_business_metrics(
        [BusinessQuery(metric=Metric.SALES), BusinessQuery(metric=Metric.EXPIRY)]
    )

    assert metrics == {
        "sales": {"error": "database is down"},
        "expiry": {"error": "database is down"},
    }


def test_queries_return_zeroed_metrics_on_an_empty_database(db_session):
    metrics = get_business_metrics(
        [BusinessQuery(metric=Metric.SALES), BusinessQuery(metric=Metric.MARGIN)]
    )

    assert metrics["sales"]["total_orders"] == 0
    assert metrics["margin"]["revenue"] == 0.0
