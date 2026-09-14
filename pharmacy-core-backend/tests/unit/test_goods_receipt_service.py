"""Unit tests for GoodsReceiptService -- the rules, and the transaction boundary.

WHAT THESE TESTS ARE FOR
------------------------
This service is the only writer of stock in the system. Every other component
either reads batches or decrements them. A bug here does not produce a wrong
number on a screen -- it produces wrong stock, which then silently feeds the
expiry agent, the inventory agent, the reorder agent and FEFO selection at the
billing counter. So the rules are asserted individually, and the atomicity is
asserted by counting rows after a deliberate failure.

The scenario is built inline rather than from the shared factory. The shared
scenarios are tuned for the expiry and inventory assertions and would drag their
expectations into tests that are about something else entirely.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.time_range import today
from app.exceptions import (
    BatchConflictError,
    InvalidGoodsReceiptError,
    MedicineNotFoundError,
    SupplierNotFoundError,
)
from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.supplier import Supplier
from app.schemas.purchase import GoodsReceiptCreate, GoodsReceiptLine
from app.services.goods_receipt_service import GoodsReceiptService


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


@pytest.fixture
def receipt_db(db_session):
    """Two medicines and one supplier. No batches -- stock starts empty.

    Starting with no stock is deliberate: it means every batch these tests see
    was created by the service under test, not inherited from a fixture.
    """
    crocin = Medicine(
        name="Crocin 500",
        normalized_name="crocin 500",
        mrp=Decimal("20.00"),
        hsn_code="30049099",
        manufacturer="GSK",
    )
    dolo = Medicine(
        name="Dolo 650",
        normalized_name="dolo 650",
        mrp=Decimal("30.00"),
        hsn_code="30049099",
        manufacturer="Micro Labs",
    )
    supplier = Supplier(name="Sun Pharma", phone="022000000")
    db_session.add_all([crocin, dolo, supplier])
    db_session.commit()
    return db_session


@pytest.fixture
def service(receipt_db) -> GoodsReceiptService:
    return GoodsReceiptService(receipt_db)


@pytest.fixture
def ids(receipt_db) -> dict[str, int]:
    crocin = receipt_db.scalars(
        select(Medicine).where(Medicine.normalized_name == "crocin 500")
    ).one()
    dolo = receipt_db.scalars(
        select(Medicine).where(Medicine.normalized_name == "dolo 650")
    ).one()
    supplier = receipt_db.scalars(select(Supplier)).one()
    return {"crocin": crocin.id, "dolo": dolo.id, "supplier": supplier.id}


def future() -> date:
    """An expiry comfortably in the future, relative to the real today.

    Relative rather than a literal like 2027-06-30: a hard-coded date turns every
    one of these tests into a time bomb that starts failing on a particular day.
    """
    return today() + timedelta(days=365)


def line(medicine_id: int, **overrides) -> GoodsReceiptLine:
    defaults = {
        "medicine_id": medicine_id,
        "batch_number": "B-001",
        "expiry_date": future(),
        "quantity": 100,
        "unit_cost": 10.00,
    }
    defaults.update(overrides)
    return GoodsReceiptLine(**defaults)


def receipt(**overrides) -> GoodsReceiptCreate:
    defaults = {"supplier_name": "Sun Pharma", "lines": []}
    defaults.update(overrides)
    return GoodsReceiptCreate(**defaults)


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_receipt_creates_batch_purchase_and_line(service, receipt_db, ids):
    """One receipt writes all four tables and the stock actually appears."""
    result = service.record_receipt(
        receipt(supplier_id=ids["supplier"], supplier_name=None, lines=[line(ids["crocin"])])
    )

    assert result.total_amount == 1000.00
    assert result.total_units == 100
    assert result.lines[0].batch_created is True

    batch = receipt_db.scalars(select(Batch)).one()
    assert batch.quantity == 100
    assert batch.cost_price == Decimal("10.00")

    purchase = receipt_db.scalars(select(Purchase)).one()
    assert purchase.total_amount == Decimal("1000.00")

    item = receipt_db.scalars(select(PurchaseItem)).one()
    assert item.batch_id == batch.id
    assert item.line_total == Decimal("1000.00")


def test_total_is_computed_from_lines_not_accepted_from_client(service, ids):
    """The invoice total is the sum the SERVER worked out.

    There is deliberately no field on the input schema for a client-supplied
    total, so the only way to get this wrong is for the service to stop summing.
    """
    result = service.record_receipt(
        receipt(
            lines=[
                line(ids["crocin"], batch_number="A", quantity=3, unit_cost=10.00),
                line(ids["dolo"], batch_number="B", quantity=2, unit_cost=12.50),
            ]
        )
    )
    assert result.total_amount == 55.00  # 3*10 + 2*12.5
    assert result.total_units == 5


def test_money_does_not_drift_on_repeating_decimals(service, ids):
    """Three lines of 0.1 must total 0.30, not 0.30000000000000004.

    The reason ``_money`` exists. A float sum here would reach the DECIMAL(10,2)
    column as a value the pharmacist never typed.
    """
    result = service.record_receipt(
        receipt(
            lines=[
                line(ids["crocin"], batch_number="A", quantity=1, unit_cost=0.10),
                line(ids["crocin"], batch_number="B", quantity=1, unit_cost=0.10),
                line(ids["dolo"], batch_number="C", quantity=1, unit_cost=0.10),
            ]
        )
    )
    assert result.total_amount == 0.30


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


def test_supplier_matched_case_insensitively_not_duplicated(service, receipt_db, ids):
    """"SUN PHARMA" and "Sun Pharma" are one vendor, not two."""
    service.record_receipt(receipt(supplier_name="SUN PHARMA", lines=[line(ids["crocin"])]))

    count = receipt_db.scalar(select(func.count()).select_from(Supplier))
    assert count == 1


def test_unknown_supplier_name_creates_the_vendor(service, receipt_db, ids):
    """A name that is not on file is a new vendor, not an error."""
    result = service.record_receipt(
        receipt(supplier_name="Medlife Distributors", lines=[line(ids["crocin"])])
    )
    assert result.supplier_name == "Medlife Distributors"
    assert receipt_db.scalar(select(func.count()).select_from(Supplier)) == 2


def test_unknown_supplier_id_is_an_error(service, ids):
    """An id, unlike a name, is a reference to something that should exist."""
    with pytest.raises(SupplierNotFoundError):
        service.record_receipt(
            receipt(supplier_id=999_999, supplier_name=None, lines=[line(ids["crocin"])])
        )


def test_supplier_required(service, ids):
    with pytest.raises(InvalidGoodsReceiptError, match="either supplier_id or supplier_name"):
        service.record_receipt(receipt(supplier_name=None, lines=[line(ids["crocin"])]))


def test_supplier_id_and_name_together_rejected(service, ids):
    """Both fields invites a request where the two disagree."""
    with pytest.raises(InvalidGoodsReceiptError, match="not both"):
        service.record_receipt(
            receipt(supplier_id=ids["supplier"], supplier_name="Cipla", lines=[line(ids["crocin"])])
        )


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def test_expired_stock_cannot_be_received(service, ids):
    """Receiving expired stock would poison FEFO and the expiry agent."""
    with pytest.raises(InvalidGoodsReceiptError, match="not in the future"):
        service.record_receipt(
            receipt(lines=[line(ids["crocin"], expiry_date=today() - timedelta(days=1))])
        )


def test_expiry_of_today_is_rejected(service, ids):
    """Today is not "in the future" -- stock expiring today cannot be sold."""
    with pytest.raises(InvalidGoodsReceiptError, match="not in the future"):
        service.record_receipt(receipt(lines=[line(ids["crocin"], expiry_date=today())]))


def test_cost_above_mrp_is_rejected(service, ids):
    """Crocin MRP is 20.00; you never buy above the legal retail price.

    This is the cheapest catch for the misplaced decimal point that would
    otherwise multiply the shop's recorded inventory value by a hundred.
    """
    with pytest.raises(InvalidGoodsReceiptError, match="exceeds its MRP"):
        service.record_receipt(receipt(lines=[line(ids["crocin"], unit_cost=2000.00)]))


def test_cost_exactly_at_mrp_is_allowed(service, ids):
    """The rule is "above MRP", not "at or above" -- zero margin is legal."""
    result = service.record_receipt(receipt(lines=[line(ids["crocin"], unit_cost=20.00)]))
    assert result.lines[0].unit_cost == 20.00


def test_unknown_medicine_is_an_error_not_an_insert(service, receipt_db, ids):
    """A receipt never invents a catalogue entry."""
    with pytest.raises(MedicineNotFoundError):
        service.record_receipt(receipt(lines=[line(999_999)]))

    assert receipt_db.scalar(select(func.count()).select_from(Medicine)) == 2


def test_future_purchase_date_is_rejected(service, ids):
    with pytest.raises(InvalidGoodsReceiptError, match="in the future"):
        service.record_receipt(
            receipt(purchase_date=today() + timedelta(days=1), lines=[line(ids["crocin"])])
        )


def test_same_batch_twice_in_one_receipt_is_rejected(service, ids):
    """Ambiguous: double-entry, or two real cartons? Refusing beats doubling."""
    with pytest.raises(InvalidGoodsReceiptError, match="more than once"):
        service.record_receipt(
            receipt(
                lines=[
                    line(ids["crocin"], batch_number="B-1"),
                    line(ids["crocin"], batch_number="b-1"),
                ]
            )
        )


# ---------------------------------------------------------------------------
# Top-up vs create
# ---------------------------------------------------------------------------


def test_same_batch_number_tops_up_rather_than_duplicating(service, receipt_db, ids):
    """Two deliveries of one carton are one batch row with more units in it.

    A second row would be equally valid to FEFO, equally counted by the inventory
    agent, and impossible to reconcile against one physical box on the shelf.
    """
    service.record_receipt(receipt(lines=[line(ids["crocin"], quantity=100)]))
    result = service.record_receipt(receipt(lines=[line(ids["crocin"], quantity=60)]))

    assert result.lines[0].batch_created is False

    batch = receipt_db.scalars(select(Batch)).one()  # .one() asserts there is exactly one
    assert batch.quantity == 160


def test_top_up_matches_batch_number_case_insensitively(service, receipt_db, ids):
    service.record_receipt(receipt(lines=[line(ids["crocin"], batch_number="AB123")]))
    service.record_receipt(receipt(lines=[line(ids["crocin"], batch_number="ab123")]))

    batch = receipt_db.scalars(select(Batch)).one()
    assert batch.quantity == 200


def test_top_up_with_different_expiry_is_a_conflict(service, ids):
    """Taking either date would silently restate the shelf life of real tablets."""
    service.record_receipt(receipt(lines=[line(ids["crocin"])]))

    with pytest.raises(BatchConflictError, match="One of the two is wrong"):
        service.record_receipt(
            receipt(lines=[line(ids["crocin"], expiry_date=future() + timedelta(days=30))])
        )


def test_top_up_with_different_cost_is_a_conflict(service, ids):
    """Averaging would restate the value of stock already counted, invisibly."""
    service.record_receipt(receipt(lines=[line(ids["crocin"], unit_cost=10.00)]))

    with pytest.raises(BatchConflictError, match="Weighted-average costing is not supported"):
        service.record_receipt(receipt(lines=[line(ids["crocin"], unit_cost=12.00)]))


def test_same_batch_number_on_a_different_medicine_is_a_separate_batch(
    service, receipt_db, ids
):
    """Batch numbers are only unique per medicine, never globally."""
    service.record_receipt(receipt(lines=[line(ids["crocin"], batch_number="SHARED")]))
    service.record_receipt(receipt(lines=[line(ids["dolo"], batch_number="SHARED")]))

    assert receipt_db.scalar(select(func.count()).select_from(Batch)) == 2


# ---------------------------------------------------------------------------
# Atomicity -- the reason this service owns the commit boundary
# ---------------------------------------------------------------------------


def test_a_failing_line_writes_nothing_at_all(service, receipt_db, ids):
    """Line 1 is perfectly valid. Line 2 is expired. Neither may survive.

    This is the test that would catch a future refactor moving ``commit()`` back
    into the repository, which is where every other write repository in this
    project still keeps it.
    """
    with pytest.raises(InvalidGoodsReceiptError):
        service.record_receipt(
            receipt(
                lines=[
                    line(ids["crocin"], batch_number="GOOD"),
                    line(ids["dolo"], batch_number="BAD", expiry_date=today() - timedelta(days=1)),
                ]
            )
        )

    assert receipt_db.scalar(select(func.count()).select_from(Batch)) == 0
    assert receipt_db.scalar(select(func.count()).select_from(Purchase)) == 0
    assert receipt_db.scalar(select(func.count()).select_from(PurchaseItem)) == 0


def test_a_conflicting_batch_writes_nothing(service, receipt_db, ids):
    """A conflict on line 2 must not leave line 1's batch or the header behind.

    Note what this actually exercises: the PRE-FLIGHT check catches the conflict
    before the transaction opens, so nothing was written to roll back. That is
    the design -- a user typo should not cost row locks on the batches table.
    The mid-transaction re-check is covered separately below.
    """
    service.record_receipt(receipt(lines=[line(ids["dolo"], batch_number="EXISTING")]))
    purchases_before = receipt_db.scalar(select(func.count()).select_from(Purchase))

    with pytest.raises(BatchConflictError):
        service.record_receipt(
            receipt(
                lines=[
                    line(ids["crocin"], batch_number="NEW-ONE"),
                    # 12.00 differs from the 10.00 on the shelf, and is still
                    # under Dolo's MRP of 30.00 -- so this reaches the conflict
                    # rule rather than tripping the MRP rule first.
                    line(ids["dolo"], batch_number="EXISTING", unit_cost=12.00),
                ]
            )
        )

    assert receipt_db.scalar(select(func.count()).select_from(Purchase)) == purchases_before
    assert (
        receipt_db.scalar(
            select(func.count()).select_from(Batch).where(Batch.batch_number == "NEW-ONE")
        )
        == 0
    )


def test_a_race_detected_inside_the_transaction_rolls_back(service, receipt_db, ids, monkeypatch):
    """Simulate another request creating the same batch after our pre-flight check.

    This is the only way the mid-transaction re-check in ``_upsert_batch`` can
    fire in real life, and it is the one path where a conflict is found AFTER the
    purchase header has already been inserted. Without the re-check, a race would
    silently top up a batch whose cost basis disagrees with the invoice.

    ``find_batch`` is patched to report "nothing on the shelf" the first time
    (the pre-flight check) and the conflicting batch every time after.
    """
    service.record_receipt(receipt(lines=[line(ids["dolo"], batch_number="RACED")]))
    purchases_before = receipt_db.scalar(select(func.count()).select_from(Purchase))

    real_find_batch = service.repository.find_batch
    calls = {"n": 0}

    def racing_find_batch(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # pre-flight sees a clear shelf
        return real_find_batch(**kwargs)  # the transaction sees the conflict

    monkeypatch.setattr(service.repository, "find_batch", racing_find_batch)

    with pytest.raises(BatchConflictError):
        service.record_receipt(
            receipt(lines=[line(ids["dolo"], batch_number="RACED", unit_cost=12.00)])
        )

    assert calls["n"] >= 2, "the re-check inside the transaction did not run"
    assert receipt_db.scalar(select(func.count()).select_from(Purchase)) == purchases_before


# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------


def test_recent_receipts_are_newest_first(service, ids):
    first = service.record_receipt(receipt(lines=[line(ids["crocin"], batch_number="R1")]))
    second = service.record_receipt(receipt(lines=[line(ids["dolo"], batch_number="R2")]))

    rows = service.recent_receipts(limit=10)
    assert [r.purchase_id for r in rows] == [second.purchase_id, first.purchase_id]
    assert rows[0].line_count == 1


def test_recent_receipts_limit_is_bounded(service, ids):
    """A caller asking for 10_000 gets the cap, not a table scan."""
    service.record_receipt(receipt(lines=[line(ids["crocin"])]))
    assert len(service.recent_receipts(limit=10_000)) <= 50


def test_receipt_detail_returns_lines(service, ids):
    created = service.record_receipt(
        receipt(
            lines=[
                line(ids["crocin"], batch_number="D1", quantity=5, unit_cost=10.00),
                line(ids["dolo"], batch_number="D2", quantity=2, unit_cost=12.00),
            ]
        )
    )

    detail = service.receipt_detail(created.purchase_id)
    assert detail is not None
    assert detail.total_amount == 74.00
    assert detail.total_units == 7
    assert [line_out.medicine_name for line_out in detail.lines] == ["Crocin 500", "Dolo 650"]


def test_receipt_detail_missing_id_is_none_not_an_exception(service):
    """The router turns ``None`` into a 404; the service does not raise for it."""
    assert service.receipt_detail(999_999) is None


def test_list_suppliers_is_alphabetical(service, receipt_db, ids):
    service.record_receipt(receipt(supplier_name="Cipla", lines=[line(ids["crocin"])]))
    names = [s.name for s in service.list_suppliers()]
    assert names == sorted(names)
