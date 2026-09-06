"""BusinessRepository — the SQL the BI agent's answers are ultimately built from.

Every expectation is the hand-computed value documented in ``tests/factories.py``.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.repositories.business_repository import BusinessRepository
from tests.factories import EXPECTED

pytestmark = pytest.mark.unit


@pytest.fixture
def repository(seeded_db) -> BusinessRepository:
    return BusinessRepository(seeded_db)


@pytest.fixture
def empty_repository(db_session) -> BusinessRepository:
    return BusinessRepository(db_session)


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------


def test_sales_summary_totals(repository):
    result = repository.get_sales_summary()

    assert result["total_sales"] == EXPECTED["sales"]["total_sales"]
    assert result["total_orders"] == EXPECTED["sales"]["total_orders"]
    assert result["average_order_value"] == EXPECTED["sales"]["average_order_value"]


def test_sales_summary_latest_sale_is_the_most_recent(repository):
    result = repository.get_sales_summary()

    # S2 was sold on 2026-08-02, one day after S1.
    assert result["latest_sale"] == datetime(2026, 8, 2, 11, 0, 0)


def test_sales_summary_on_empty_database(empty_repository):
    """No sales must yield zeros, not a division-by-zero."""

    result = empty_repository.get_sales_summary()

    assert result["total_sales"] == 0.0
    assert result["total_orders"] == 0
    assert result["average_order_value"] == 0
    assert result["latest_sale"] is None


# ---------------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------------


def test_purchase_summary_totals(repository):
    result = repository.get_purchase_summary()

    expected = EXPECTED["purchases"]
    assert result["total_purchase"] == expected["total_purchase"]
    assert result["total_purchase_orders"] == expected["total_purchase_orders"]
    assert result["average_purchase_value"] == expected["average_purchase_value"]


def test_purchase_summary_on_empty_database(empty_repository):
    result = empty_repository.get_purchase_summary()

    assert result["total_purchase"] == 0.0
    assert result["total_purchase_orders"] == 0
    assert result["average_purchase_value"] == 0


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------


def test_return_summary_splits_sales_and_purchase_returns(repository):
    result = repository.get_return_summary()

    expected = EXPECTED["returns"]
    assert result["total_returns"] == expected["total_returns"]
    assert result["total_return_amount"] == expected["total_return_amount"]
    assert result["sales_return_count"] == expected["sales_return_count"]
    assert result["sales_return_amount"] == expected["sales_return_amount"]
    assert result["purchase_return_count"] == expected["purchase_return_count"]
    assert result["purchase_return_amount"] == expected["purchase_return_amount"]


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


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------


def test_expiry_summary_counts_only_expired_batches(repository):
    """Two of the three seeded batches expire in 2027 and must be excluded."""

    result = repository.get_expiry_summary()

    assert result["expired_batches"] == EXPECTED["expiry"]["expired_batches"]
    # 20 units x 10.00 cost = 200.00 of stock already lost.
    assert result["expiry_loss"] == EXPECTED["expiry"]["expiry_loss"]


def test_expiry_summary_on_empty_database(empty_repository):
    result = empty_repository.get_expiry_summary()

    assert result["expired_batches"] == 0
    assert result["expiry_loss"] == 0.0


# ---------------------------------------------------------------------------
# Margin
# ---------------------------------------------------------------------------


def test_margin_summary_uses_batch_cost_for_cogs(repository):
    """COGS must come from the batch actually sold, not from a flat assumption.

    5 x Crocin at 10.00 cost + 2 x Dolo at 12.00 cost = 74.00.
    """

    result = repository.get_margin_summary()

    expected = EXPECTED["margin"]
    assert result["revenue"] == expected["revenue"]
    assert result["cogs"] == expected["cogs"]
    assert result["gross_profit"] == expected["gross_profit"]
    assert result["profit_margin_percent"] == expected["profit_margin_percent"]


def test_margin_gross_profit_reconciles(repository):
    result = repository.get_margin_summary()

    assert result["gross_profit"] == result["revenue"] - result["cogs"]


def test_margin_summary_on_empty_database(empty_repository):
    """Zero revenue must not divide by zero when computing the margin percentage."""

    result = empty_repository.get_margin_summary()

    assert result["revenue"] == 0.0
    assert result["cogs"] == 0.0
    assert result["gross_profit"] == 0.0
    assert result["profit_margin_percent"] == 0


# ---------------------------------------------------------------------------
# Known gaps — current behaviour, pinned so a later milestone changes it knowingly
# ---------------------------------------------------------------------------


@pytest.mark.known_gap
def test_no_summary_method_accepts_a_date_range(repository):
    """Documents audit finding B3: the repository is date-blind.

    Every "last month" / "today" question therefore returns the all-time figure.
    Milestone 4 adds date parameters; this test will then be replaced by real
    date-filtering tests rather than deleted quietly.
    """

    import inspect

    summary_methods = [
        repository.get_sales_summary,
        repository.get_purchase_summary,
        repository.get_return_summary,
        repository.get_expiry_summary,
        repository.get_margin_summary,
    ]

    for method in summary_methods:
        parameters = set(inspect.signature(method).parameters)
        assert parameters == set(), (
            f"{method.__name__} now takes {parameters}. Date filtering has landed — "
            "replace this known-gap test with real date-range assertions."
        )


@pytest.mark.known_gap
def test_repository_exposes_no_grouping_or_ranking(repository):
    """Documents audit finding B10: no top-N / breakdown capability exists.

    "Top-selling medicines" and "which supplier" are unanswerable, not merely
    sometimes-wrong. Milestone 4 adds grouping.
    """

    public_methods = {
        name for name in dir(repository) if not name.startswith("_") and name != "db"
    }

    assert public_methods == {
        "get_sales_summary",
        "get_purchase_summary",
        "get_return_summary",
        "get_expiry_summary",
        "get_margin_summary",
    }, "BusinessRepository gained a method — update this gap test to match."
