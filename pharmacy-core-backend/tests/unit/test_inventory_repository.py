"""InventoryRepository — the SQL behind the capital calculation.

The repository makes no judgements. What it must get right is the split between the
capital view and the cover view, the handling of bad data, and the fact that "stock
age unknown" is not the same as "stock age zero".
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.supplier import Supplier
from app.repositories.inventory_repository import InventoryRepository

pytestmark = pytest.mark.unit


AS_OF = date(2026, 6, 30)


@pytest.fixture
def repository(db_session) -> InventoryRepository:
    return InventoryRepository(db_session)


@pytest.fixture
def build(db_session):
    """Make medicines, batches and receipts one fact at a time.

    Deliberately not a fixed scenario: each test states only what it needs, so a
    failure points at one rule rather than at a shared fixture everything depends on.
    """

    supplier = Supplier(name="Acme Distributors", phone="9000000000")
    db_session.add(supplier)
    db_session.flush()

    class Builder:
        def medicine(self, name: str) -> Medicine:
            medicine = Medicine(
                name=name,
                normalized_name=name.lower(),
                mrp=Decimal("50.00"),
                hsn_code="30049099",
                manufacturer="Generic Pharma",
            )
            db_session.add(medicine)
            db_session.flush()
            return medicine

        def batch(
            self,
            medicine: Medicine,
            *,
            units: int,
            cost: str,
            expires_in_days: int = 365,
            number: str | None = None,
        ) -> Batch:
            batch = Batch(
                medicine_id=medicine.id,
                batch_number=number or f"B{medicine.id}-{units}",
                expiry_date=AS_OF + timedelta(days=expires_in_days),
                quantity=units,
                cost_price=Decimal(cost),
            )
            db_session.add(batch)
            db_session.flush()
            return batch

        def receive(self, batch: Batch, *, days_ago: int) -> None:
            """Record that ``batch`` arrived on a purchase ``days_ago``."""

            purchase = Purchase(
                supplier_id=supplier.id,
                purchase_date=AS_OF - timedelta(days=days_ago),
                invoice_number=f"INV-{days_ago}-{batch.id}",
                total_amount=Decimal("100.00"),
            )
            db_session.add(purchase)
            db_session.flush()
            db_session.add(
                PurchaseItem(
                    purchase_id=purchase.id,
                    medicine_id=batch.medicine_id,
                    batch_id=batch.id,
                    quantity=max(batch.quantity, 1),
                    unit_cost=batch.cost_price,
                    line_total=batch.cost_price * max(batch.quantity, 1),
                )
            )
            db_session.flush()

    return Builder()


def only(rows):
    assert len(rows) == 1, f"expected one row, got {len(rows)}"
    return rows[0]


# ---------------------------------------------------------------------------
# Stock and value
# ---------------------------------------------------------------------------


def test_an_empty_database_returns_nothing(repository):
    assert repository.stock_by_medicine(as_of=AS_OF) == []


def test_stock_and_value_come_from_quantity_times_cost(repository, build, db_session):
    medicine = build.medicine("Paracetamol 500")
    build.batch(medicine, units=100, cost="20.00")
    db_session.commit()

    row = only(repository.stock_by_medicine(as_of=AS_OF))

    assert row.stock_quantity == 100
    assert row.inventory_value == Decimal("2000.00")


def test_batches_of_one_medicine_are_summed(repository, build, db_session):
    """Two deliveries at different prices. The value is the sum, not a re-pricing at
    either batch's cost."""

    medicine = build.medicine("Paracetamol 500")
    build.batch(medicine, units=100, cost="20.00", number="P1")
    build.batch(medicine, units=50, cost="30.00", number="P2")
    db_session.commit()

    row = only(repository.stock_by_medicine(as_of=AS_OF))

    assert row.stock_quantity == 150
    assert row.inventory_value == Decimal("3500.00")


def test_medicines_are_kept_separate(repository, build, db_session):
    build.batch(build.medicine("Paracetamol 500"), units=100, cost="20.00")
    build.batch(build.medicine("Amoxicillin 250"), units=40, cost="50.00")
    db_session.commit()

    rows = repository.stock_by_medicine(as_of=AS_OF)

    assert [r.stock_quantity for r in rows] == [100, 40]


def test_rows_come_back_ordered_by_medicine_id(repository, build, db_session):
    """A stable order, so a ranking built on top cannot flap between runs."""

    for name in ("Zinc 50", "Aspirin 75", "Metformin 500"):
        build.batch(build.medicine(name), units=10, cost="5.00")
    db_session.commit()

    ids = [r.medicine_id for r in repository.stock_by_medicine(as_of=AS_OF)]

    assert ids == sorted(ids)


def test_zero_cost_is_allowed_and_values_at_nothing(repository, build, db_session):
    """cost_price is NOT NULL but has no CHECK, so a free sample is representable."""

    medicine = build.medicine("Sample Sachet")
    build.batch(medicine, units=100, cost="0.00")
    db_session.commit()

    row = only(repository.stock_by_medicine(as_of=AS_OF))

    assert row.stock_quantity == 100
    assert row.inventory_value == Decimal("0.00")


# ---------------------------------------------------------------------------
# Zero and negative stock
# ---------------------------------------------------------------------------


def test_a_medicine_with_no_stock_is_left_out(repository, build, db_session):
    """No capital is tied up in it, so it is not inventory risk. The service reports
    how many were left out rather than presenting this as the whole catalogue."""

    build.batch(build.medicine("Domperidone 10"), units=0, cost="15.00")
    db_session.commit()

    assert repository.stock_by_medicine(as_of=AS_OF) == []


def test_a_medicine_with_no_batches_at_all_is_left_out(repository, build, db_session):
    build.medicine("Never Stocked")
    db_session.commit()

    assert repository.stock_by_medicine(as_of=AS_OF) == []


def test_a_negative_batch_is_excluded_from_the_totals(repository, build, db_session):
    """Letting -20 cancel a real 100 would understate capital that is physically on
    the shelf. The column has no CHECK constraint, so this is reachable."""

    medicine = build.medicine("Paracetamol 500")
    build.batch(medicine, units=100, cost="20.00", number="GOOD")
    build.batch(medicine, units=-20, cost="20.00", number="BAD")
    db_session.commit()

    row = only(repository.stock_by_medicine(as_of=AS_OF))

    assert row.stock_quantity == 100, "the negative batch did not cancel the good one"
    assert row.inventory_value == Decimal("2000.00")


def test_a_negative_batch_is_counted_so_it_can_be_reported(repository, build, db_session):
    """Excluded from the arithmetic, but not hidden — that would bury the defect."""

    medicine = build.medicine("Paracetamol 500")
    build.batch(medicine, units=100, cost="20.00", number="GOOD")
    build.batch(medicine, units=-20, cost="20.00", number="BAD")
    db_session.commit()

    assert only(repository.stock_by_medicine(as_of=AS_OF)).negative_batch_count == 1


def test_a_medicine_whose_only_batch_is_negative_is_left_out(
    repository, build, db_session
):
    build.batch(build.medicine("Broken Record"), units=-5, cost="20.00")
    db_session.commit()

    assert repository.stock_by_medicine(as_of=AS_OF) == []


# ---------------------------------------------------------------------------
# Capital view vs cover view
# ---------------------------------------------------------------------------


def test_expired_stock_counts_as_capital_but_not_as_cover(repository, build, db_session):
    """Money already spent, and it cannot satisfy a day of demand. One number cannot
    be both, so the repository returns both."""

    medicine = build.medicine("Ibuprofen 400")
    build.batch(medicine, units=60, cost="10.00", expires_in_days=200, number="LIVE")
    build.batch(medicine, units=40, cost="10.00", expires_in_days=-5, number="DEAD")
    db_session.commit()

    row = only(repository.stock_by_medicine(as_of=AS_OF))

    assert row.stock_quantity == 100
    assert row.inventory_value == Decimal("1000.00")
    assert row.sellable_quantity == 60
    assert row.sellable_value == Decimal("600.00")


def test_a_batch_expiring_today_is_not_sellable(repository, build, db_session):
    """The boundary is ``expiry_date > as_of``, matching the reorder repository. Stock
    that expires today cannot be relied on as cover."""

    medicine = build.medicine("Ibuprofen 400")
    build.batch(medicine, units=50, cost="10.00", expires_in_days=0)
    db_session.commit()

    row = only(repository.stock_by_medicine(as_of=AS_OF))

    assert row.stock_quantity == 50
    assert row.sellable_quantity == 0


def test_a_batch_expiring_tomorrow_is_still_sellable(repository, build, db_session):
    medicine = build.medicine("Ibuprofen 400")
    build.batch(medicine, units=50, cost="10.00", expires_in_days=1)
    db_session.commit()

    assert only(repository.stock_by_medicine(as_of=AS_OF)).sellable_quantity == 50


def test_a_medicine_holding_only_expired_stock_still_appears(
    repository, build, db_session
):
    """It has zero cover and real capital. Dropping it would hide the worst case."""

    medicine = build.medicine("Expired Everything")
    build.batch(medicine, units=80, cost="25.00", expires_in_days=-30)
    db_session.commit()

    row = only(repository.stock_by_medicine(as_of=AS_OF))

    assert row.stock_quantity == 80
    assert row.inventory_value == Decimal("2000.00")
    assert row.sellable_quantity == 0


# ---------------------------------------------------------------------------
# Stock age
# ---------------------------------------------------------------------------


def test_the_receipt_date_comes_from_the_purchase(repository, build, db_session):
    medicine = build.medicine("Paracetamol 500")
    batch = build.batch(medicine, units=100, cost="20.00")
    build.receive(batch, days_ago=45)
    db_session.commit()

    receipts = repository.oldest_receipt_by_medicine()

    assert receipts[medicine.id] == AS_OF - timedelta(days=45)


def test_the_oldest_receipt_wins(repository, build, db_session):
    """Two deliveries still on the shelf. The capital went out with the first one."""

    medicine = build.medicine("Paracetamol 500")
    first = build.batch(medicine, units=100, cost="20.00", number="OLD")
    second = build.batch(medicine, units=50, cost="20.00", number="NEW")
    build.receive(first, days_ago=200)
    build.receive(second, days_ago=10)
    db_session.commit()

    receipts = repository.oldest_receipt_by_medicine()

    assert receipts[medicine.id] == AS_OF - timedelta(days=200)


def test_a_sold_out_batch_does_not_age_the_medicine(repository, build, db_session):
    """The question is how long the money *currently* tied up has been tied up. A
    batch that sold out years ago is not tied up in anything."""

    medicine = build.medicine("Paracetamol 500")
    sold_out = build.batch(medicine, units=0, cost="20.00", number="GONE")
    on_hand = build.batch(medicine, units=100, cost="20.00", number="HERE")
    build.receive(sold_out, days_ago=900)
    build.receive(on_hand, days_ago=30)
    db_session.commit()

    receipts = repository.oldest_receipt_by_medicine()

    assert receipts[medicine.id] == AS_OF - timedelta(days=30)


def test_a_batch_with_no_purchase_line_has_no_receipt_date(
    repository, build, db_session
):
    """purchase_items.batch_id is nullable, so this is reachable. Absent must mean
    unknown — the service reports None, never zero."""

    medicine = build.medicine("Paracetamol 500")
    build.batch(medicine, units=100, cost="20.00")
    db_session.commit()

    assert medicine.id not in repository.oldest_receipt_by_medicine()


def test_receipts_can_be_restricted_to_specific_medicines(repository, build, db_session):
    first = build.medicine("Paracetamol 500")
    second = build.medicine("Amoxicillin 250")
    build.receive(build.batch(first, units=100, cost="20.00"), days_ago=45)
    build.receive(build.batch(second, units=100, cost="20.00"), days_ago=45)
    db_session.commit()

    receipts = repository.oldest_receipt_by_medicine(medicine_ids=[second.id])

    assert set(receipts) == {second.id}


def test_receipts_on_an_empty_database_are_empty(repository):
    assert repository.oldest_receipt_by_medicine() == {}


# ---------------------------------------------------------------------------
# Catalogue size
# ---------------------------------------------------------------------------


def test_medicines_are_counted_whether_stocked_or_not(repository, build, db_session):
    build.batch(build.medicine("Stocked"), units=10, cost="5.00")
    build.medicine("Unstocked")
    db_session.commit()

    assert repository.count_medicines() == 2


def test_counting_an_empty_catalogue(repository):
    assert repository.count_medicines() == 0
