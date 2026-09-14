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
from app.models.purchase_item import PurchaseItem
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


# ===========================================================================
# Expiry-risk scenario
# ===========================================================================
#
# Separate from seed_scenario() on purpose: the BI tests pin exact figures against
# that data, and bending it to also serve expiry would break 100+ assertions for no
# gain.
#
# Everything here is relative to an `as_of` the caller passes in, so no test depends
# on the day it runs.
#
# THE SCENARIO (as_of = D)
# ------------------------
# PARACETAMOL — sells 2/day (180 units over the 90-day lookback)
#   P1  expires D+5    30 units   cost 10.00   FEFO first
#   P2  expires D+20  200 units   cost 10.00   FEFO second
#
#   P1: 5 days x 2/day = 10 units of demand available, has 30  -> sells 10, excess 20
#   P2: 20 days x 2/day = 40 total demand, 10 already taken by P1
#       -> 30 available, has 200 -> sells 30, excess 170
#
#   This is the FEFO point: P2's excess is large *because* P1 is consuming the
#   early demand. Split the demand evenly instead and you would get both wrong.
#
# AMOXICILLIN — never sold at all
#   A1  expires D+10   50 units   cost 20.00
#   -> no history, demand 0, excess 50, value at risk 1000.00
#
# VITAMIN C — sells 10/day (900 over the lookback), tiny batch
#   V1  expires D+15   40 units   cost 5.00
#   -> 15 days x 10/day = 150 demand, has 40 -> sells all 40, excess 0, LOW
#   This is the batch a naive "expires soon" report would flag and shouldn't.
#
# COUGH SYRUP — already expired
#   C1  expired D-10   25 units   cost 40.00
#   -> cannot sell, excess 25, value at risk 1000.00, EXPIRED
#
# FAR-FUTURE STOCK — outside every window
#   Z1  expires D+300  100 units  cost 1.00
# ===========================================================================

EXPIRY_EXPECTED = {
    "paracetamol_near": {"excess": 20, "value_at_risk": 200.00, "risk": "critical"},
    "paracetamol_bulk": {"excess": 170, "value_at_risk": 1700.00, "risk": "high"},
    "amoxicillin": {"excess": 50, "value_at_risk": 1000.00, "risk": "high"},
    "vitamin_c": {"excess": 0, "value_at_risk": 0.00, "risk": "low"},
    "cough_syrup": {"excess": 25, "value_at_risk": 1000.00, "risk": "expired"},
}


def seed_expiry_scenario(db: Session, as_of: date) -> dict[str, object]:
    """Insert the expiry scenario above, relative to ``as_of``."""

    from datetime import timedelta

    def medicine(name: str, mrp: str, maker: str) -> Medicine:
        return Medicine(
            name=name,
            normalized_name=name.lower(),
            mrp=Decimal(mrp),
            hsn_code="30049099",
            manufacturer=maker,
        )

    paracetamol = medicine("Paracetamol 500", "15.00", "Generic Pharma")
    amoxicillin = medicine("Amoxicillin 250", "40.00", "Generic Pharma")
    vitamin_c = medicine("Vitamin C 500", "8.00", "Wellness Labs")
    cough_syrup = medicine("Cough Syrup 100ml", "70.00", "Wellness Labs")
    far_future = medicine("Cetirizine 10", "5.00", "Generic Pharma")

    db.add_all([paracetamol, amoxicillin, vitamin_c, cough_syrup, far_future])
    db.flush()

    def batch(med: Medicine, number: str, days: int, qty: int, cost: str) -> Batch:
        return Batch(
            medicine_id=med.id,
            batch_number=number,
            expiry_date=as_of + timedelta(days=days),
            quantity=qty,
            cost_price=Decimal(cost),
        )

    batches = {
        "P1": batch(paracetamol, "P1", 5, 30, "10.00"),
        "P2": batch(paracetamol, "P2", 20, 200, "10.00"),
        "A1": batch(amoxicillin, "A1", 10, 50, "20.00"),
        "V1": batch(vitamin_c, "V1", 15, 40, "5.00"),
        "C1": batch(cough_syrup, "C1", -10, 25, "40.00"),
        "Z1": batch(far_future, "Z1", 300, 100, "1.00"),
    }
    db.add_all(list(batches.values()))
    db.flush()

    # Sales history inside the 90-day lookback. One sale per medicine carrying the
    # whole volume keeps the fixture small; the service only reads summed quantity.
    def sell(med: Medicine, from_batch: Batch, units: int, days_ago: int) -> None:
        sale = Sale(
            customer_id=None,
            total_amount=Decimal(units) * med.mrp,
            sold_at=datetime.combine(as_of - timedelta(days=days_ago), datetime.min.time()),
        )
        db.add(sale)
        db.flush()
        db.add(
            SaleItem(
                sale_id=sale.id,
                medicine_id=med.id,
                batch_id=from_batch.id,
                quantity=units,
                unit_price=med.mrp,
                line_total=Decimal(units) * med.mrp,
            )
        )

    # 180 units over 90 days = 2/day.
    sell(paracetamol, batches["P1"], 180, days_ago=30)
    # 900 units over 90 days = 10/day.
    sell(vitamin_c, batches["V1"], 900, days_ago=30)
    # Cough syrup sold once, but long before the lookback window opens: it has
    # history, yet zero recent demand. A different case from "never sold".
    sell(cough_syrup, batches["C1"], 50, days_ago=200)
    # Amoxicillin: deliberately never sold.

    db.commit()

    return {
        "paracetamol": paracetamol,
        "amoxicillin": amoxicillin,
        "vitamin_c": vitamin_c,
        "cough_syrup": cough_syrup,
        "far_future": far_future,
        "batches": batches,
    }


# ===========================================================================
# Inventory-risk scenario
# ===========================================================================
#
# Separate from the other two on purpose. The expiry scenario is built around
# expiry dates and has no purchase history at all, so it cannot exercise stock age
# or capital at risk; bending it to serve both would break the expiry assertions for
# no gain.
#
# Everything is relative to an `as_of` the caller passes in, so no test depends on
# the day it runs.
#
# THE SCENARIO (as_of = D)
# ------------------------
# PARACETAMOL   100 units @ 20  sold 900 over 90d  received D-45
#   10/day, 10 days of cover, target 600 -> no excess          -> HEALTHY
#
# AMOXICILLIN   500 units @ 50  NEVER SOLD         received D-300
#   no velocity, no cover figure, Rs 25,000 all stuck          -> DEAD
#
# CETIRIZINE    400 units @ 100 sold 90 over 90d   received D-120
#   1/day, 400 days of cover, 340 excess = Rs 34,000           -> CRITICAL
#
# COUGH SYRUP    60 units @ 40  sold 50, 200d ago  received D-210
#   has history but none recent -> Rs 2,400 stuck              -> DEAD
#
# VITAMIN C     150 units @ 15  sold 90 over 90d   received D-60
#   1/day, 150 days of cover, 90 excess = Rs 1,350             -> MEDIUM
#
# IBUPROFEN   60 live + 40 expired @ 10  sold 90 over 90d  received D-30
#   60 sellable at 1/day = 60 days cover, target 60 -> no excess -> HEALTHY
#   The expired 40 count as capital but not as cover. No purchase line for the
#   expired batch, deliberately.
#
# DOMPERIDONE     0 units @ 15  never sold
#   No capital tied up -> excluded from items, counted separately
# ===========================================================================

INVENTORY_EXPECTED = {
    "Paracetamol 500": {"risk": "healthy", "capital_at_risk": 0.00},
    "Amoxicillin 250": {"risk": "dead", "capital_at_risk": 25_000.00},
    "Cetirizine 10": {"risk": "critical", "capital_at_risk": 34_000.00},
    "Cough Syrup 100ml": {"risk": "dead", "capital_at_risk": 2_400.00},
    "Vitamin C 500": {"risk": "medium", "capital_at_risk": 1_350.00},
    "Ibuprofen 400": {"risk": "healthy", "capital_at_risk": 0.00},
}

INVENTORY_TOTAL_VALUE = 72_650.00
INVENTORY_TOTAL_AT_RISK = 62_750.00


def seed_inventory_scenario(db: Session, as_of: date) -> dict[str, object]:
    """Insert the inventory scenario above, relative to ``as_of``."""

    from datetime import timedelta

    supplier = Supplier(name="Acme Distributors", phone="9000000000")
    db.add(supplier)
    db.flush()

    def medicine(name: str, mrp: str) -> Medicine:
        row = Medicine(
            name=name,
            normalized_name=name.lower(),
            mrp=Decimal(mrp),
            hsn_code="30049099",
            manufacturer="Generic Pharma",
        )
        db.add(row)
        db.flush()
        return row

    def batch(
        med: Medicine,
        number: str,
        *,
        units: int,
        cost: str,
        expires_in: int = 365,
        received: int | None = None,
    ) -> Batch:
        row = Batch(
            medicine_id=med.id,
            batch_number=number,
            expiry_date=as_of + timedelta(days=expires_in),
            quantity=units,
            cost_price=Decimal(cost),
        )
        db.add(row)
        db.flush()

        if received is not None:
            purchase = Purchase(
                supplier_id=supplier.id,
                purchase_date=as_of - timedelta(days=received),
                invoice_number=f"INV-{number}",
                total_amount=Decimal(cost) * max(units, 1),
            )
            db.add(purchase)
            db.flush()
            db.add(
                PurchaseItem(
                    purchase_id=purchase.id,
                    medicine_id=med.id,
                    batch_id=row.id,
                    quantity=max(units, 1),
                    unit_cost=Decimal(cost),
                    line_total=Decimal(cost) * max(units, 1),
                )
            )
            db.flush()

        return row

    def sell(med: Medicine, from_batch: Batch, units: int, days_ago: int) -> None:
        sale = Sale(
            customer_id=None,
            total_amount=Decimal(units) * med.mrp,
            sold_at=datetime.combine(
                as_of - timedelta(days=days_ago), datetime.min.time()
            ),
        )
        db.add(sale)
        db.flush()
        db.add(
            SaleItem(
                sale_id=sale.id,
                medicine_id=med.id,
                batch_id=from_batch.id,
                quantity=units,
                unit_price=med.mrp,
                line_total=Decimal(units) * med.mrp,
            )
        )
        db.flush()

    paracetamol = medicine("Paracetamol 500", "30.00")
    p1 = batch(paracetamol, "IP1", units=100, cost="20.00", received=45)
    sell(paracetamol, p1, 900, days_ago=30)

    amoxicillin = medicine("Amoxicillin 250", "80.00")
    batch(amoxicillin, "IA1", units=500, cost="50.00", received=300)

    cetirizine = medicine("Cetirizine 10", "150.00")
    c1 = batch(cetirizine, "IC1", units=400, cost="100.00", received=120)
    sell(cetirizine, c1, 90, days_ago=30)

    cough = medicine("Cough Syrup 100ml", "70.00")
    s1 = batch(cough, "IS1", units=60, cost="40.00", received=210)
    sell(cough, s1, 50, days_ago=200)

    vitamin_c = medicine("Vitamin C 500", "25.00")
    v1 = batch(vitamin_c, "IV1", units=150, cost="15.00", received=60)
    sell(vitamin_c, v1, 90, days_ago=30)

    ibuprofen = medicine("Ibuprofen 400", "18.00")
    i1 = batch(ibuprofen, "II1", units=60, cost="10.00", expires_in=200, received=30)
    # Expired, and with no purchase line - so it contributes capital but neither
    # cover nor stock age.
    batch(ibuprofen, "II2", units=40, cost="10.00", expires_in=-5)
    sell(ibuprofen, i1, 90, days_ago=30)

    domperidone = medicine("Domperidone 10", "12.00")
    batch(domperidone, "ID1", units=0, cost="15.00")

    db.commit()

    return {
        "paracetamol": paracetamol,
        "amoxicillin": amoxicillin,
        "cetirizine": cetirizine,
        "cough_syrup": cough,
        "vitamin_c": vitamin_c,
        "ibuprofen": ibuprofen,
        "domperidone": domperidone,
        "supplier": supplier,
    }
