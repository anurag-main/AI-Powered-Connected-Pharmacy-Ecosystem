"""LangGraph node — compute_pricing.

For each item in state['batched_items'], looks up the Medicine's MRP from
the DATABASE (never trusting the client), computes line_total = mrp × quantity,
and sums all line_totals into total_amount.

Writes:
    state['priced_items']  — same items enriched with unit_price + line_total
    state['total_amount']  — grand total (float; precise Decimal math done internally)

Analogy (kid-level):
    Meera, the cashier, takes each notebook page. She walks to the candy
    jar, reads the printed price tag (set by mom, NEVER by the kid), and
    multiplies it by the quantity. She writes the per-page cost on the
    page, then adds up every page's cost into the grand total.

Why we look up MRP from the DB (not from the LLM, not from the request body):
    The #1 rule of money math: never trust client-supplied prices. An
    attacker can tamper with anything coming from the network. The ONLY
    trustworthy price source is our own DB, set by an admin / pharmacy
    owner. This is OWASP "Business Logic — Insecure Pricing" territory.

Why Decimal for the math:
    Python float is binary IEEE-754. `0.1 + 0.2` is `0.30000000000000004`.
    Harmless for a temperature reading; catastrophic for an invoice. We
    use Decimal internally and round to 2 decimal places (paise precision),
    then cast to float only at the state boundary because dicts in
    LangGraph state get serialized to JSON downstream.

Future enhancement:
    GST / tax calculation isn't modeled yet. Real Indian pharmacies need
    HSN-code-driven GST per line item. That's a Phase 5+ refinement.
"""
from decimal import ROUND_HALF_UP, Decimal

from app.ai.state.billing_state import BillingState
from app.core.database import SessionLocal
from app.repositories.sqlalchemy_medicine_repository import SQLAlchemyMedicineRepository


# Two-decimal quantum: ₹.01 (paise) — what we round every money value to.
_PAISE = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    """Round a Decimal to 2 places, banker's-safe (ROUND_HALF_UP)."""
    return value.quantize(_PAISE, rounding=ROUND_HALF_UP)


def compute_pricing(state: BillingState) -> dict:
    """Look up MRP per item, compute line_total, sum to total_amount."""

    # YOUR JOB 1 — pull batched_items out of state
    # state["batched_items"] is the output of select_batch — each item already
    # carries medicine_id, batch_id, batch_number, expiry_date.
    # Use state.get("batched_items") so a missing key returns None.
    # Write 1 line below:
    #     batched_items = state.get("batched_items")
    
    batched_items = state.get("batched_items")


    # YOUR JOB 2 — guard: nothing to price
    # If batched_items is None / empty, return:
    #     {"errors": ["compute_pricing: no batched_items to price"]}
    # Write 2-3 lines below:
    if not batched_items :
        return {
            "errors": [
                "compute_pricing: no batched_items to price"
            ]
        }
        

    # YOUR JOB 3 — initialize accumulators
    # priced_items: list[dict] = []
    # total_amount: Decimal = Decimal("0")
    # (We start total as Decimal "0" — adding Decimals stays exact. Mixing
    #  Decimal + float would explode with a TypeError.)
    # Write 2 lines below:
    priced_items: list[dict] = []
    total_amount: Decimal = Decimal("0")

    with SessionLocal() as db:
        med_repo = SQLAlchemyMedicineRepository(db)

        for item in batched_items:
            medicine = med_repo.get_by_id(item["medicine_id"])

            if medicine is None:
                continue

            unit_price = _round_money(Decimal(str(medicine.mrp)))
            line_total = _round_money(unit_price * Decimal(item["quantity"]))

            priced_items.append({
                **item,
                "unit_price": float(unit_price),
                "line_total": float(line_total),
            })

            total_amount += line_total

    return {
        "priced_items": priced_items,
        "total_amount": float(total_amount),
    }


# ============================================================================
# End-to-end smoke test — runs against your REAL local MySQL.
# Run with:
#     cd c:\ai-pharmacy-ecosystem\pharmacy-core-backend
#     .\venv\Scripts\Activate.ps1
#     python -m app.ai.nodes.compute_pricing
# ============================================================================

if __name__ == "__main__":
    import json

    from app.core.database import SessionLocal as _SessionLocal
    from app.repositories.sqlalchemy_medicine_repository import (
        SQLAlchemyMedicineRepository as _MedRepo,
    )

    with _SessionLocal() as _db:
        _meds = _MedRepo(_db).list_all()

    if not _meds:
        print("!! No medicines in DB.")
        raise SystemExit(1)

    target = _meds[0]
    print(f"Using medicine: id={target.id}  name={target.name!r}  mrp={target.mrp}\n")

    # Pretend select_batch already enriched the items — that's the input shape
    # this node consumes in real graph runs.
    test_state: BillingState = {
        "batched_items": [
            {
                "name": target.name,
                "quantity": 2,
                "unit": "strip",
                "medicine_id": target.id,
                "batch_id": 6,
                "batch_number": "SEED-EARLY",
                "expiry_date": "2026-08-30",
            },
            # If you have a second medicine in DB, add a second entry to exercise the sum.
        ]
    }

    print(f"========== Test 1: price 2 × {target.name!r} ==========")
    print(f"Expected: unit_price={target.mrp}, line_total={target.mrp * 2}, total_amount={target.mrp * 2}")
    try:
        out = compute_pricing(test_state)
        print("OUTPUT:")
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except NotImplementedError as e:
        print(f"NotImplementedError → {e}\n(fill in YOUR JOBs first)")
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__} → {e}")

    print("\n========== Test 2: empty-state guard ==========")
    try:
        out = compute_pricing({})  # type: ignore[arg-type]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except NotImplementedError:
        print("(skipped — implement YOUR JOBs first)")
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__} → {e}")
