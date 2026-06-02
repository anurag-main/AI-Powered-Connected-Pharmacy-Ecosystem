"""LangGraph node — persist_sale.

THE node that mutates the database. Writes a complete sale in ONE atomic
transaction touching 4 tables:

    1. customers   — find by phone, or INSERT if new
    2. sales       — INSERT one header row
    3. sale_items  — INSERT N line rows (one per priced item)
    4. batches     — UPDATE quantity = quantity - sold (one per priced item)

The transaction is wrapped in `with db.begin():` — if ANY step raises,
SQLAlchemy issues a ROLLBACK and the DB looks as if nothing happened.

Analogy (kid-level):
    Mom takes the bundle of finished notebook pages and does FOUR things
    together: add the kid to the address book if new, write a fresh bill,
    copy every page into the bill ledger, and walk to the storeroom to
    subtract the sold candy from the boxes. If anything interrupts her
    halfway, she tears up everything she wrote. Either all four happen,
    or none of them happen. That all-or-nothing guarantee = a transaction.

Why this node uses ORM models directly (not the Phase 2 repositories):
    The Phase 2 repos commit inside each .add() method — fine for single-
    table writes, fatal here. Multi-table writes need ONE commit boundary,
    owned by the caller (this node). This is the Unit of Work pattern.

What happens on failure:
    - Bad input (missing priced_items or total_amount) → soft error, no DB call
    - Insufficient stock at write time → rollback, soft error returned
    - Network blip / SQL error          → rollback, soft error returned
    Either way, state.sale_id is NOT set if we failed. Downstream consumers
    must check both state["sale_id"] and state["errors"].

Sale_id is the new invoice ID — returned to the caller so they can show
"Invoice #42" to the pharmacist.
"""
from decimal import Decimal

from sqlalchemy import select

from app.ai.state.billing_state import BillingState
from app.core.database import SessionLocal
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.sale import Sale
from app.models.sale_item import SaleItem


def persist_sale(state: BillingState) -> dict:
    """Atomically write a Sale + its line items + decrement batch stock."""

    # ----- Guard 1: must have priced items to record -----
    priced_items = state.get("priced_items")
    if not priced_items:
        return {"errors": ["persist_sale: no priced_items to record"]}

    # ----- Guard 2: must have a total to put on the header -----
    total_amount = state.get("total_amount")
    if total_amount is None:
        return {"errors": ["persist_sale: total_amount missing from state"]}

    # ----- Pull optional customer info (may be None for walk-in sales) -----
    extracted = state.get("extracted_intent") or {}
    customer_phone = extracted.get("customer_phone")
    customer_name = extracted.get("customer_name")

    with SessionLocal() as db:
        try:
            # ============================================================
            # TRANSACTION START — `with db.begin():` is the commit boundary.
            # If we leave this block normally → SQLAlchemy commits.
            # If we leave it by raising      → SQLAlchemy rolls back.
            # ============================================================
            with db.begin():

                # ------------------------------------------------------------
                # STEP 1 — find or create the customer (only if phone given)
                # ------------------------------------------------------------
                customer_id: int | None = None
                if customer_phone:
                    stmt = select(Customer).where(Customer.phone == customer_phone)
                    customer = db.scalars(stmt).first()
                    if customer is None:
                        customer = Customer(phone=customer_phone, name=customer_name)
                        db.add(customer)
                        # flush() pushes the INSERT to the DB and populates customer.id,
                        # WITHOUT committing. That ID is needed for the sales FK below.
                        db.flush()
                    customer_id = customer.id

                # ------------------------------------------------------------
                # STEP 2 — INSERT the Sale row (the invoice header)
                # ------------------------------------------------------------
                sale = Sale(
                    customer_id=customer_id,
                    total_amount=Decimal(str(total_amount)),
                )
                db.add(sale)
                db.flush()  # populates sale.id; needed for the sale_items FK

                # ------------------------------------------------------------
                # STEP 3 — for each priced_item:
                #   3a. Re-check stock and decrement the batch
                #   3b. INSERT a sale_items row (with frozen unit_price/line_total)
                # ------------------------------------------------------------
                for item in priced_items:
                    batch = db.get(Batch, item["batch_id"])
                    if batch is None:
                        # Should never happen — select_batch already verified.
                        # But defensive checks are cheap and save audit headaches.
                        raise RuntimeError(
                            f"persist_sale: batch_id={item['batch_id']} vanished"
                        )

                    # Final stock check INSIDE the transaction — protects against
                    # concurrent sales between select_batch and now.
                    if batch.quantity < item["quantity"]:
                        raise RuntimeError(
                            f"persist_sale: insufficient stock in batch "
                            f"{batch.batch_number!r}: need {item['quantity']}, "
                            f"have {batch.quantity}"
                        )

                    # Decrement stock (the UPDATE batches statement).
                    batch.quantity -= item["quantity"]

                    # Insert the line.
                    sale_item = SaleItem(
                        sale_id=sale.id,
                        medicine_id=item["medicine_id"],
                        batch_id=item["batch_id"],
                        quantity=item["quantity"],
                        unit_price=Decimal(str(item["unit_price"])),
                        line_total=Decimal(str(item["line_total"])),
                    )
                    db.add(sale_item)

                # If we reach this line, the `with db.begin():` block exits
                # normally and SQLAlchemy commits the transaction.
                sale_id = sale.id

            # We're outside the `with db.begin():` block now — the transaction
            # has been committed. Safe to read sale.id even after commit
            # because we captured it above.
            return {"sale_id": sale_id, "errors": []}

        except Exception as e:  # noqa: BLE001 — we want to surface ANY DB failure
            # The `with db.begin():` block already rolled back if we got here
            # by raising INSIDE it. This catch turns the exception into a
            # graph-level soft error.
            return {
                "errors": [f"persist_sale failed: {type(e).__name__}: {e}"],
            }


# ============================================================================
# End-to-end smoke test — runs against your REAL local MySQL.
# WARNING: this test actually writes to the DB. It uses a known test phone
# (9999999999) so re-runs won't create duplicate customers — but EVERY run
# decrements batch stock and creates a new Sale row. Watch your batch qty.
#
# Run with:
#     cd c:\ai-pharmacy-ecosystem\pharmacy-core-backend
#     .\venv\Scripts\Activate.ps1
#     python -m app.ai.nodes.persist_sale
# ============================================================================

if __name__ == "__main__":
    import json

    from app.core.database import SessionLocal as _SessionLocal
    from app.repositories.sqlalchemy_batch_repository import (
        SQLAlchemyBatchRepository as _BatchRepo,
    )
    from app.repositories.sqlalchemy_medicine_repository import (
        SQLAlchemyMedicineRepository as _MedRepo,
    )

    # ----- Discover what's in the DB so the test adapts -----
    with _SessionLocal() as _db:
        _meds = _MedRepo(_db).list_all()
        if _meds:
            _winner_batch = _BatchRepo(_db).select_fefo(_meds[0].id)
        else:
            _winner_batch = None

    if not _meds:
        print("!! No medicines in DB.")
        raise SystemExit(1)
    if _winner_batch is None:
        print("!! No usable batch (FEFO returned None). Run scripts.seed_test_batch first.")
        raise SystemExit(1)

    target_med = _meds[0]
    print(f"Target medicine : id={target_med.id}  name={target_med.name!r}  mrp={target_med.mrp}")
    print(f"FEFO batch      : id={_winner_batch.id}  number={_winner_batch.batch_number!r}  qty BEFORE={_winner_batch.quantity}\n")

    # Build a state as if extract_intent → resolve_medicine → select_batch →
    # compute_pricing had all already run.
    unit_price = float(target_med.mrp)
    qty = 1
    test_state: BillingState = {
        "extracted_intent": {
            "items": [{"name": target_med.name, "quantity": qty, "unit": "strip"}],
            "customer_name": "Smoke Test User",
            "customer_phone": "9999999999",
        },
        "priced_items": [
            {
                "name": target_med.name,
                "quantity": qty,
                "unit": "strip",
                "medicine_id": target_med.id,
                "batch_id": _winner_batch.id,
                "batch_number": _winner_batch.batch_number,
                "expiry_date": _winner_batch.expiry_date.isoformat(),
                "unit_price": unit_price,
                "line_total": unit_price * qty,
            },
        ],
        "total_amount": unit_price * qty,
    }

    print("========== Test 1: writes a real sale to DB ==========")
    try:
        out = persist_sale(test_state)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__} → {e}")

    # ----- Verify the side effects -----
    with _SessionLocal() as _db:
        _after_batch = _BatchRepo(_db).get_by_id(_winner_batch.id)
        print(f"\nBatch qty AFTER : {_after_batch.quantity if _after_batch else 'NULL'} "
              f"(should be {_winner_batch.quantity - qty})")

    print("\n========== Test 2: empty-input guard ==========")
    try:
        out = persist_sale({})  # type: ignore[arg-type]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__} → {e}")

    print("\n========== Test 3: insufficient stock -> atomic rollback ==========")
    over_qty_state: BillingState = {
        "extracted_intent": {"items": [], "customer_name": None, "customer_phone": None},
        "priced_items": [
            {**test_state["priced_items"][0], "quantity": 999_999},  # impossibly large
        ],
        "total_amount": 999_999.0,
    }
    try:
        out = persist_sale(over_qty_state)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__} → {e}")

    # Confirm the rollback worked — batch qty should NOT have changed in Test 3.
    with _SessionLocal() as _db:
        _after_rollback = _BatchRepo(_db).get_by_id(_winner_batch.id)
        print(f"\nBatch qty AFTER rollback test: {_after_rollback.quantity if _after_rollback else 'NULL'}")
        print("(should equal the value after Test 1 — Test 3 should have rolled back)")
