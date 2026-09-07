"""BusinessQuery validation — the boundary between the model and the database.

This is the security-relevant layer. Anything the LLM can express has to pass through
here, so these tests are as much about what is *impossible* as what is allowed.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.ai.schemas.business_query import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SUPPORTED_DIMENSIONS,
    BusinessQuery,
    Dimension,
    Metric,
    PlannerOutput,
    SortDirection,
)
from app.core.time_range import Period

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_a_bare_metric_is_a_valid_all_time_summary():
    """"What are my total sales?" must stay the simplest possible query."""

    query = BusinessQuery(metric=Metric.SALES)

    assert query.dimension is None
    assert query.period is Period.ALL_TIME
    assert query.limit == DEFAULT_LIMIT
    assert query.sort is SortDirection.DESC


def test_the_metric_is_required():
    with pytest.raises(ValidationError):
        BusinessQuery()


# ---------------------------------------------------------------------------
# What cannot be expressed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "revenue",                       # a plausible synonym that is not a metric
        "inventory",                     # a concept with no data source
        "sales; DROP TABLE sales",       # injection attempt
        "sales OR 1=1",
        "",
    ],
)
def test_an_unknown_metric_is_rejected(value):
    """The metric is an enum, so a crafted string cannot reach the repository."""

    with pytest.raises(ValidationError):
        BusinessQuery(metric=value)


@pytest.mark.parametrize(
    "value",
    [
        "category",                      # genuinely does not exist in the schema
        "region",
        "customer",
        "medicines.name",                # a column reference
        "(SELECT 1)",                    # a subquery
        "1; DELETE FROM sales",
    ],
)
def test_an_unknown_dimension_is_rejected(value):
    with pytest.raises(ValidationError):
        BusinessQuery(metric=Metric.SALES, dimension=value)


def test_category_is_deliberately_not_a_dimension():
    """The database has no category column; advertising one would let the planner
    promise a breakdown the repository cannot produce."""

    assert "category" not in {d.value for d in Dimension}


# ---------------------------------------------------------------------------
# Metric / dimension compatibility
# ---------------------------------------------------------------------------


def test_sales_cannot_be_broken_down_by_supplier():
    """There is no join from a sale to a supplier: a sale points at a batch, and a
    batch does not record which purchase created it."""

    with pytest.raises(ValidationError, match="cannot be broken down by"):
        BusinessQuery(metric=Metric.SALES, dimension=Dimension.SUPPLIER)


def test_purchases_cannot_be_broken_down_by_product():
    with pytest.raises(ValidationError, match="cannot be broken down by"):
        BusinessQuery(metric=Metric.PURCHASES, dimension=Dimension.PRODUCT)


def test_margin_cannot_be_broken_down_by_day():
    with pytest.raises(ValidationError, match="cannot be broken down by"):
        BusinessQuery(metric=Metric.MARGIN, dimension=Dimension.DAY)


def test_the_error_names_the_supported_dimensions():
    """A planner retrying after a validation error needs to be told what IS allowed."""

    with pytest.raises(ValidationError, match="manufacturer"):
        BusinessQuery(metric=Metric.MARGIN, dimension=Dimension.DAY)


@pytest.mark.parametrize(
    ("metric", "dimension"),
    [
        (metric, dimension)
        for metric, dimensions in SUPPORTED_DIMENSIONS.items()
        for dimension in dimensions
    ],
)
def test_every_advertised_combination_validates(metric, dimension):
    assert BusinessQuery(metric=metric, dimension=dimension).dimension is dimension


def test_every_metric_has_a_dimension_entry():
    """A metric missing from the table would raise a KeyError during validation."""

    assert set(SUPPORTED_DIMENSIONS) == set(Metric)


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------


def test_a_named_period_needs_no_dates():
    query = BusinessQuery(metric=Metric.SALES, period=Period.LAST_MONTH)

    assert query.period is Period.LAST_MONTH


def test_custom_requires_both_dates():
    with pytest.raises(ValidationError, match="requires both start_date and end_date"):
        BusinessQuery(
            metric=Metric.SALES, period=Period.CUSTOM, start_date=date(2026, 1, 1)
        )


def test_custom_rejects_a_reversed_range():
    with pytest.raises(ValidationError, match="is after end_date"):
        BusinessQuery(
            metric=Metric.SALES,
            period=Period.CUSTOM,
            start_date=date(2026, 3, 31),
            end_date=date(2026, 1, 1),
        )


def test_dates_without_a_custom_period_are_rejected():
    """Ambiguous input: does last_month win, or the dates? Rejecting beats guessing —
    a guess produces a confident answer to a question nobody asked.
    """

    with pytest.raises(ValidationError, match="only valid with period='custom'"):
        BusinessQuery(
            metric=Metric.SALES,
            period=Period.LAST_MONTH,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )


def test_expiry_rejects_a_time_period():
    """Expiry is a snapshot of stock on hand. "Expired stock last month" has no
    agreed meaning, and inventing one would be a silent lie."""

    with pytest.raises(ValidationError, match="does not support a time period"):
        BusinessQuery(metric=Metric.EXPIRY, period=Period.LAST_MONTH)


def test_expiry_accepts_all_time():
    assert BusinessQuery(metric=Metric.EXPIRY).period is Period.ALL_TIME


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


def test_an_excessive_limit_is_rejected():
    """A model asking for a million rows must not be able to."""

    with pytest.raises(ValidationError):
        BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT, limit=1_000_000)


@pytest.mark.parametrize("limit", [0, -1, -100])
def test_a_non_positive_limit_is_rejected(limit):
    with pytest.raises(ValidationError):
        BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT, limit=limit)


def test_the_maximum_limit_is_accepted():
    query = BusinessQuery(
        metric=Metric.SALES, dimension=Dimension.PRODUCT, limit=MAX_LIMIT
    )

    assert query.limit == MAX_LIMIT


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------


def test_the_date_range_is_resolved_from_the_period():
    query = BusinessQuery(metric=Metric.SALES, period=Period.LAST_MONTH)

    result = query.date_range(as_of=date(2026, 9, 16))

    assert result.start == date(2026, 8, 1)
    assert result.end == date(2026, 8, 31)


def test_distinct_questions_get_distinct_keys():
    """Two results must not collide in the metrics dict, or one silently replaces
    the other and the analyzer answers with the wrong data."""

    keys = {
        BusinessQuery(metric=Metric.SALES).key(),
        BusinessQuery(metric=Metric.SALES, period=Period.LAST_MONTH).key(),
        BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT).key(),
        BusinessQuery(
            metric=Metric.SALES, dimension=Dimension.PRODUCT, period=Period.LAST_MONTH
        ).key(),
        BusinessQuery(metric=Metric.MARGIN).key(),
    }

    assert len(keys) == 5


def test_the_key_is_readable():
    query = BusinessQuery(
        metric=Metric.SALES, dimension=Dimension.PRODUCT, period=Period.LAST_MONTH
    )

    assert query.key() == "sales_by_product_last_month"


def test_the_key_is_stable_for_the_same_question():
    first = BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT)
    second = BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT)

    assert first.key() == second.key()


def test_describe_reports_shape_without_data():
    """Used in logs, so it must never carry figures."""

    text = BusinessQuery(
        metric=Metric.SALES, dimension=Dimension.PRODUCT, period=Period.LAST_MONTH
    ).describe()

    assert "sales" in text and "product" in text and "last_month" in text


# ---------------------------------------------------------------------------
# PlannerOutput
# ---------------------------------------------------------------------------


def test_an_empty_plan_is_valid():
    """How the planner says "this question is not about business data"."""

    assert PlannerOutput().queries == []


def test_a_plan_holds_several_queries():
    plan = PlannerOutput(
        queries=[
            BusinessQuery(metric=Metric.SALES),
            BusinessQuery(metric=Metric.MARGIN),
        ]
    )

    assert [q.metric for q in plan.queries] == [Metric.SALES, Metric.MARGIN]


def test_one_invalid_query_rejects_the_whole_plan():
    """Partial acceptance would run some queries and silently drop others, producing
    an answer built on data the planner did not intend."""

    with pytest.raises(ValidationError):
        PlannerOutput(
            queries=[
                {"metric": "sales"},
                {"metric": "sales", "dimension": "category"},
            ]
        )
