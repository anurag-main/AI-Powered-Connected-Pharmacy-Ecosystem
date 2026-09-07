"""BusinessRepository — the SQL the BI agent's answers are ultimately built from.

Every expectation is the hand-computed value documented in ``tests/factories.py``.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.ai.schemas.business_query import (
    BusinessQuery,
    Dimension,
    Metric,
    SortDirection,
)
from app.core.time_range import DateRange
from app.repositories.business_repository import BusinessRepository
from tests.factories import EXPECTED

pytestmark = pytest.mark.unit


@pytest.fixture
def repository(seeded_db) -> BusinessRepository:
    return BusinessRepository(seeded_db)


@pytest.fixture
def empty_repository(db_session) -> BusinessRepository:
    return BusinessRepository(db_session)


ALL_TIME = DateRange(None, None)

# The scenario's transactions: sales 2026-08-01 and 08-02, purchases 2026-07-01 and
# 07-15, returns 2026-08-03/04/05.
AUGUST = DateRange(date(2026, 8, 1), date(2026, 8, 31))
JULY = DateRange(date(2026, 7, 1), date(2026, 7, 31))


# ---------------------------------------------------------------------------
# Summaries — unchanged behaviour with no date range
# ---------------------------------------------------------------------------


def test_sales_summary_totals(repository):
    result = repository.get_sales_summary()

    assert result["total_sales"] == EXPECTED["sales"]["total_sales"]
    assert result["total_orders"] == EXPECTED["sales"]["total_orders"]
    assert result["average_order_value"] == EXPECTED["sales"]["average_order_value"]


def test_sales_summary_latest_sale_is_the_most_recent(repository):
    assert repository.get_sales_summary()["latest_sale"] == datetime(2026, 8, 2, 11, 0)


def test_sales_summary_on_empty_database(empty_repository):
    """No sales must yield zeros, not a division-by-zero."""

    result = empty_repository.get_sales_summary()

    assert result["total_sales"] == 0.0
    assert result["total_orders"] == 0
    assert result["average_order_value"] == 0
    assert result["latest_sale"] is None


def test_purchase_summary_totals(repository):
    result = repository.get_purchase_summary()

    expected = EXPECTED["purchases"]
    assert result["total_purchase"] == expected["total_purchase"]
    assert result["total_purchase_orders"] == expected["total_purchase_orders"]
    assert result["average_purchase_value"] == expected["average_purchase_value"]


def test_return_summary_splits_sales_and_purchase_returns(repository):
    result = repository.get_return_summary()

    expected = EXPECTED["returns"]
    for field, value in expected.items():
        assert result[field] == value, field


def test_return_split_amounts_sum_to_the_total(repository):
    """A split that does not reconcile to the total is a silent reporting bug."""

    result = repository.get_return_summary()

    assert (
        result["sales_return_amount"] + result["purchase_return_amount"]
        == result["total_return_amount"]
    )
    assert (
        result["sales_return_count"] + result["purchase_return_count"]
        == result["total_returns"]
    )


def test_expiry_summary_counts_only_expired_batches(repository):
    """Two of the three seeded batches expire in 2027 and must be excluded."""

    result = repository.get_expiry_summary()

    assert result["expired_batches"] == EXPECTED["expiry"]["expired_batches"]
    assert result["expiry_loss"] == EXPECTED["expiry"]["expiry_loss"]


def test_margin_summary_uses_batch_cost_for_cogs(repository):
    """COGS must come from the batch actually sold, not a flat assumption.

    5 x Crocin at 10.00 cost + 2 x Dolo at 12.00 cost = 74.00.
    """

    result = repository.get_margin_summary()

    for field, value in EXPECTED["margin"].items():
        assert result[field] == value, field


def test_margin_gross_profit_reconciles(repository):
    result = repository.get_margin_summary()

    assert result["gross_profit"] == result["revenue"] - result["cogs"]


def test_margin_summary_on_empty_database(empty_repository):
    """Zero revenue must not divide by zero when computing the percentage."""

    result = empty_repository.get_margin_summary()

    assert result["revenue"] == 0.0
    assert result["profit_margin_percent"] == 0


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------


def test_sales_filtered_to_a_period_containing_everything(repository):
    assert (
        repository.get_sales_summary(AUGUST)["total_sales"]
        == EXPECTED["sales"]["total_sales"]
    )


def test_sales_filtered_to_a_period_containing_nothing(repository):
    """A valid query with no matching rows: zeros, not an error and not all-time."""

    result = repository.get_sales_summary(JULY)

    assert result["total_sales"] == 0.0
    assert result["total_orders"] == 0
    assert result["latest_sale"] is None


def test_sales_filtered_to_a_single_day(repository):
    """Sale one only: 100.00 on 2026-08-01."""

    one_day = DateRange(date(2026, 8, 1), date(2026, 8, 1))

    result = repository.get_sales_summary(one_day)

    assert result["total_sales"] == 100.00
    assert result["total_orders"] == 1


def test_the_last_day_of_a_range_is_included(repository):
    """The off-by-one that a `<= end` predicate would cause.

    Sale two is at 2026-08-02 **11:00**. A range ending on 08-02 compared with
    `sold_at <= 2026-08-02 00:00:00` would silently drop it. The repository uses an
    exclusive upper bound of 08-03 00:00 instead, so the whole day counts.
    """

    through_the_second = DateRange(date(2026, 8, 1), date(2026, 8, 2))

    result = repository.get_sales_summary(through_the_second)

    assert result["total_orders"] == 2, "a sale at 11:00 on the end date was dropped"
    assert result["total_sales"] == 160.00


def test_the_first_day_of_a_range_is_included(repository):
    result = repository.get_sales_summary(DateRange(date(2026, 8, 2), date(2026, 8, 2)))

    assert result["total_orders"] == 1
    assert result["total_sales"] == 60.00


def test_purchases_filter_on_a_date_column(repository):
    """purchase_date is a Date, not a DateTime — inclusive on both ends."""

    result = repository.get_purchase_summary(DateRange(date(2026, 7, 1), date(2026, 7, 1)))

    assert result["total_purchase"] == 300.00
    assert result["total_purchase_orders"] == 1


def test_purchases_across_the_whole_month(repository):
    result = repository.get_purchase_summary(JULY)

    assert result["total_purchase"] == EXPECTED["purchases"]["total_purchase"]


def test_returns_filtered_by_period(repository):
    """Only the 2026-08-03 sales return of 20.00 falls in this window."""

    result = repository.get_return_summary(
        DateRange(date(2026, 8, 3), date(2026, 8, 3))
    )

    assert result["total_returns"] == 1
    assert result["sales_return_amount"] == 20.00
    assert result["purchase_return_count"] == 0


def test_margin_filtered_by_period(repository):
    """The margin filter applies to the parent sale's date, via the join."""

    result = repository.get_margin_summary(
        DateRange(date(2026, 8, 1), date(2026, 8, 1))
    )

    # Sale one only: 100.00 revenue, 5 x 10.00 cost.
    assert result["revenue"] == 100.00
    assert result["cogs"] == 50.00
    assert result["gross_profit"] == 50.00


def test_margin_on_a_period_with_no_sales(repository):
    result = repository.get_margin_summary(JULY)

    assert result["revenue"] == 0.0
    assert result["profit_margin_percent"] == 0


def test_every_summary_reports_the_period_it_measured(repository):
    """Without this the analyzer cannot tell the user what was actually measured —
    the root cause of the QA pass's mislabelled 'last month' figure."""

    assert repository.get_sales_summary(AUGUST)["period"] == "2026-08-01 to 2026-08-31"
    assert repository.get_sales_summary()["period"] == "all time"
    assert repository.get_expiry_summary()["period"] == "stock as at today"


# ---------------------------------------------------------------------------
# Breakdowns — grouping and ranking
# ---------------------------------------------------------------------------


def test_sales_by_product_ranked_descending(repository):
    query = BusinessQuery(
        metric=Metric.SALES, dimension=Dimension.PRODUCT, sort=SortDirection.DESC
    )

    rows = repository.run(query)["rows"]

    assert [row["label"] for row in rows] == ["Crocin 500", "Dolo 650"]
    assert rows[0]["value"] == 100.00
    assert rows[0]["quantity"] == 5
    assert rows[1]["value"] == 60.00


def test_sales_by_product_ranked_ascending(repository):
    """'Lowest-selling' is the same query with the sort flipped, not a new one."""

    query = BusinessQuery(
        metric=Metric.SALES, dimension=Dimension.PRODUCT, sort=SortDirection.ASC
    )

    rows = repository.run(query)["rows"]

    assert [row["label"] for row in rows] == ["Dolo 650", "Crocin 500"]


def test_limit_restricts_the_number_of_rows(repository):
    query = BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT, limit=1)

    rows = repository.run(query)["rows"]

    assert len(rows) == 1
    assert rows[0]["label"] == "Crocin 500", "the limit must keep the TOP row"


def test_sales_by_manufacturer(repository):
    query = BusinessQuery(metric=Metric.SALES, dimension=Dimension.MANUFACTURER)

    rows = repository.run(query)["rows"]

    assert {row["label"] for row in rows} == {"GSK", "Micro Labs"}


def test_sales_by_day_is_ordered_chronologically(repository):
    """A daily series must come back in time order, not ranked by value.

    Day two took less than day one, so a value-ranked result would put 08-02 first
    and silently destroy the trend the user asked to see.
    """

    query = BusinessQuery(
        metric=Metric.SALES, dimension=Dimension.DAY, sort=SortDirection.ASC
    )

    rows = repository.run(query)["rows"]

    assert [row["label"] for row in rows] == ["2026-08-01", "2026-08-02"]
    assert [row["value"] for row in rows] == [100.00, 60.00]


def test_sales_by_day_descending_is_most_recent_first(repository):
    query = BusinessQuery(
        metric=Metric.SALES, dimension=Dimension.DAY, sort=SortDirection.DESC
    )

    rows = repository.run(query)["rows"]

    assert [row["label"] for row in rows] == ["2026-08-02", "2026-08-01"]


def test_sales_by_month(repository):
    rows = repository.run(
        BusinessQuery(metric=Metric.SALES, dimension=Dimension.MONTH)
    )["rows"]

    assert len(rows) == 1
    assert rows[0]["label"] == "2026-08"
    assert rows[0]["value"] == 160.00


def test_purchases_by_supplier(repository):
    rows = repository.run(
        BusinessQuery(metric=Metric.PURCHASES, dimension=Dimension.SUPPLIER)
    )["rows"]

    assert len(rows) == 1
    assert rows[0]["label"] == "Acme Distributors"
    assert rows[0]["value"] == 400.00
    assert rows[0]["quantity"] == 2


def test_returns_by_product(repository):
    """Both return directions count toward a product's total.

    Dolo appears twice in the scenario: a 50.00 purchase return and a 10.00 sales
    return. The breakdown groups by product, not by direction, so it is 60.00.
    """

    rows = repository.run(
        BusinessQuery(metric=Metric.RETURNS, dimension=Dimension.PRODUCT)
    )["rows"]

    by_label = {row["label"]: row["value"] for row in rows}
    assert by_label == {"Crocin 500": 20.00, "Dolo 650": 60.00}


def test_margin_by_product(repository):
    """Crocin: 100.00 revenue - 50.00 cost = 50.00. Dolo: 60.00 - 24.00 = 36.00."""

    rows = repository.run(
        BusinessQuery(metric=Metric.MARGIN, dimension=Dimension.PRODUCT)
    )["rows"]

    by_label = {row["label"]: row["value"] for row in rows}
    assert by_label == {"Crocin 500": 50.00, "Dolo 650": 36.00}


def test_expiry_by_product(repository):
    """Only the expired Crocin batch: 20 units at 10.00."""

    rows = repository.run(
        BusinessQuery(metric=Metric.EXPIRY, dimension=Dimension.PRODUCT)
    )["rows"]

    assert len(rows) == 1
    assert rows[0]["label"] == "Crocin 500"
    assert rows[0]["value"] == 200.00


def test_breakdown_combining_a_date_range_and_ranking(repository):
    """The combined query the roadmap calls for: top N, by product, over a period."""

    query = BusinessQuery(
        metric=Metric.SALES,
        dimension=Dimension.PRODUCT,
        period="custom",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
        limit=5,
    )

    result = repository.run(query)

    assert result["rows"] == [
        {"label": "Crocin 500", "value": 100.00, "quantity": 5}
    ], "only sale one is in range, so only Crocin appears"


def test_breakdown_over_a_period_with_no_data_returns_no_rows(repository):
    """An empty result is a real answer, distinct from a failure."""

    query = BusinessQuery(
        metric=Metric.SALES,
        dimension=Dimension.PRODUCT,
        period="custom",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    )

    assert repository.run(query)["rows"] == []


def test_breakdown_on_an_empty_database(empty_repository):
    rows = empty_repository.run(
        BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT)
    )["rows"]

    assert rows == []


def test_breakdown_reports_its_dimension_and_period(repository):
    result = repository.run(
        BusinessQuery(metric=Metric.SALES, dimension=Dimension.PRODUCT)
    )

    assert result["dimension"] == "product"
    assert result["period"] == "all time"


# ---------------------------------------------------------------------------
# run() dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metric", list(Metric))
def test_every_metric_has_a_working_summary(repository, metric):
    """No metric may be reachable by the planner without an implementation."""

    result = repository.run(BusinessQuery(metric=metric))

    assert isinstance(result, dict) and result, metric


@pytest.mark.parametrize(
    ("metric", "dimension"),
    [
        (Metric.SALES, Dimension.PRODUCT),
        (Metric.SALES, Dimension.MANUFACTURER),
        (Metric.SALES, Dimension.DAY),
        (Metric.SALES, Dimension.MONTH),
        (Metric.PURCHASES, Dimension.SUPPLIER),
        (Metric.PURCHASES, Dimension.DAY),
        (Metric.PURCHASES, Dimension.MONTH),
        (Metric.RETURNS, Dimension.PRODUCT),
        (Metric.RETURNS, Dimension.MANUFACTURER),
        (Metric.RETURNS, Dimension.DAY),
        (Metric.RETURNS, Dimension.MONTH),
        (Metric.MARGIN, Dimension.PRODUCT),
        (Metric.MARGIN, Dimension.MANUFACTURER),
        (Metric.EXPIRY, Dimension.PRODUCT),
        (Metric.EXPIRY, Dimension.MANUFACTURER),
    ],
)
def test_every_advertised_breakdown_actually_executes(repository, metric, dimension):
    """SUPPORTED_DIMENSIONS is what the planner is told it may ask for.

    Any pair the schema advertises but the repository cannot build would be a
    validation error at runtime for a question the planner was encouraged to produce.
    """

    result = repository.run(BusinessQuery(metric=metric, dimension=dimension))

    assert "rows" in result


# ---------------------------------------------------------------------------
# Known gaps that remain
# ---------------------------------------------------------------------------


@pytest.mark.known_gap
def test_there_is_still_no_category_dimension():
    """Medicines have name, manufacturer, hsn_code and mrp — no category column.

    "Sales by category" is therefore unanswerable, and Dimension deliberately omits
    it rather than advertising a breakdown the repository cannot produce. Adding it
    needs a schema change and a migration, not a repository change.
    """

    assert not hasattr(Dimension, "CATEGORY"), (
        "A category dimension exists now — add the column, the breakdown, and "
        "real tests, then delete this gap test."
    )
