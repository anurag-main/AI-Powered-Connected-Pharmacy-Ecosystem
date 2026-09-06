"""Deterministic test data.

One fixed scenario, small enough that every expected metric can be worked out by
hand and written into the test as a literal. No randomness, no `faker`: a test that
computes its own expectation cannot catch a bug in the code that computes it.

THE SCENARIO
------------
Medicines
    M1  Crocin 500   MRP 20.00
    M2  Dolo 650     MRP 30.00

Batches
    B1  M1  qty 100  cost 10.00  expires 2027-01-01   (usable)
    B2  M2  qty  50  cost 12.00  expires 2027-06-01   (usable)
    B3  M1  qty  20  cost 10.00  expires 2020-01-01   (EXPIRED)

Sales
    S1  100.00   line: 5 x M1 from B1 @ 20.00
    S2   60.00   line: 2 x M2 from B2 @ 30.00

Purchases (supplier SUP1)
    P1  300.00
    P2  100.00

Returns
    R1  sales     20.00
    R2  purchase  50.00
    R3  sales     10.00

DERIVED EXPECTATIONS (hand-computed — these are the assertions)
    sales     total 160.00 · orders 2 · avg 80.00
    purchases total 400.00 · orders 2 · avg 200.00
    returns   count 3 · total 80.00 · sales 2/30.00 · purchase 1/50.00
    expiry    expired_batches 1 · expiry_loss 200.00      (20 x 10.00)
    margin    revenue 160.00 · cogs 74.00 (5x10 + 2x12)
              gross_profit 86.00 · margin 53.75%

Every money value is binary-exact as a float, so SQLite's lack of native DECIMAL
cannot introduce rounding noise into an assertion.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.returns import Return
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.supplier import Supplier

# Expected values, exported so tests and the evaluation harness agree on one source
# of truth. If the scenario above changes, this changes with it.
EXPECTED = {
    "sales": {
        "total_sales": 160.00,
        "total_orders": 2,
        "average_order_value": 80.00,
    },
    "purchases": {
        "total_purchase": 400.00,
        "total_purchase_orders": 2,
        "average_purchase_value": 200.00,
    },
    "returns": {
        "total_returns": 3,
        "total_return_amount": 80.00,
        "sales_return_count": 2,
        "sales_return_amount": 30.00,
        "purchase_return_count": 1,
        "purchase_return_amount": 50.00,
    },
    "expiry": {
        "expired_batches": 1,
        "expiry_loss": 200.00,
    },
    "margin": {
        "revenue": 160.00,
        "cogs": 74.00,
        "gross_profit": 86.00,
        "profit_margin_percent": 53.75,
    },
}


def seed_scenario(db: Session) -> dict[str, object]:
    """Insert the scenario above and return the created rows by key."""

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
    db.add_all([crocin, dolo])
    db.flush()

    usable_crocin = Batch(
        medicine_id=crocin.id,
        batch_number="B1",
        expiry_date=date(2027, 1, 1),
        quantity=100,
        cost_price=Decimal("10.00"),
    )
    usable_dolo = Batch(
        medicine_id=dolo.id,
        batch_number="B2",
        expiry_date=date(2027, 6, 1),
        quantity=50,
        cost_price=Decimal("12.00"),
    )
    expired_crocin = Batch(
        medicine_id=crocin.id,
        batch_number="B3",
        expiry_date=date(2020, 1, 1),
        quantity=20,
        cost_price=Decimal("10.00"),
    )
    db.add_all([usable_crocin, usable_dolo, expired_crocin])
    db.flush()

    sale_one = Sale(
        customer_id=None,
        total_amount=Decimal("100.00"),
        sold_at=datetime(2026, 8, 1, 10, 0, 0),
    )
    sale_two = Sale(
        customer_id=None,
        total_amount=Decimal("60.00"),
        sold_at=datetime(2026, 8, 2, 11, 0, 0),
    )
    db.add_all([sale_one, sale_two])
    db.flush()

    db.add_all(
        [
            SaleItem(
                sale_id=sale_one.id,
                medicine_id=crocin.id,
                batch_id=usable_crocin.id,
                quantity=5,
                unit_price=Decimal("20.00"),
                line_total=Decimal("100.00"),
            ),
            SaleItem(
                sale_id=sale_two.id,
                medicine_id=dolo.id,
                batch_id=usable_dolo.id,
                quantity=2,
                unit_price=Decimal("30.00"),
                line_total=Decimal("60.00"),
            ),
        ]
    )

    supplier = Supplier(name="Acme Distributors", phone="9999999999")
    db.add(supplier)
    db.flush()

    db.add_all(
        [
            Purchase(
                supplier_id=supplier.id,
                purchase_date=date(2026, 7, 1),
                invoice_number="INV-1",
                total_amount=Decimal("300.00"),
            ),
            Purchase(
                supplier_id=supplier.id,
                purchase_date=date(2026, 7, 15),
                invoice_number="INV-2",
                total_amount=Decimal("100.00"),
            ),
        ]
    )

    db.add_all(
        [
            Return(
                return_type="sales",
                medicine_id=crocin.id,
                batch_id=usable_crocin.id,
                sale_id=sale_one.id,
                quantity=1,
                amount=Decimal("20.00"),
                reason="damaged strip",
                returned_at=datetime(2026, 8, 3, 9, 0, 0),
            ),
            Return(
                return_type="purchase",
                medicine_id=dolo.id,
                batch_id=usable_dolo.id,
                supplier_id=supplier.id,
                quantity=2,
                amount=Decimal("50.00"),
                reason="short expiry on arrival",
                returned_at=datetime(2026, 8, 4, 9, 0, 0),
            ),
            Return(
                return_type="sales",
                medicine_id=dolo.id,
                batch_id=usable_dolo.id,
                sale_id=sale_two.id,
                quantity=1,
                amount=Decimal("10.00"),
                reason="wrong item",
                returned_at=datetime(2026, 8, 5, 9, 0, 0),
            ),
        ]
    )

    db.commit()

    return {
        "crocin": crocin,
        "dolo": dolo,
        "usable_crocin_batch": usable_crocin,
        "usable_dolo_batch": usable_dolo,
        "expired_crocin_batch": expired_crocin,
        "sale_one": sale_one,
        "sale_two": sale_two,
        "supplier": supplier,
    }
