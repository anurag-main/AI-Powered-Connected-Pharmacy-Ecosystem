"""LangGraph node — select_batch.

For each item in state['resolved_items'], picks the FEFO-winning Batch:
the soonest-expiring batch of that medicine that (a) isn't expired and
(b) still has stock. Writes enriched items to state['batched_items'].

Items with no usable batch (expired, empty, or insufficient quantity)
are reported via state['errors'] and are NOT in batched_items.

Analogy (kid-level):
    Sanjay, the storeroom manager, takes each notebook page Priya stickered.
    For each candy on the page, he checks every box of that candy on the
    shelves. He throws out expired boxes and skips empty ones. From what's
    left, he picks the box that goes bad SOONEST and writes its batch
    number on the page. If the soonest-expiring box doesn't have enough
    candy, the page goes on the "out of stock" pile.

Why we re-use repo.select_fefo from Phase 2:
    The SQL is already correct and uses the (medicine_id, expiry_date)
    composite index — single B-tree seek per item. No need to write new
    SQL just because we're in a LangGraph node.

Future enhancement (not in this step):
    If the FEFO winner has 3 strips but the order needs 5, today we
    error. The senior move is "multi-batch split" — take 3 from batch A
    and 2 from the next-earliest batch B. That's a step 3.5+ refactor.
"""
from app.ai.state.billing_state import BillingState
from app.core.database import SessionLocal
from app.repositories.sqlalchemy_batch_repository import SQLAlchemyBatchRepository


def select_batch(state: BillingState) -> dict:
    """Pick a FEFO-winning Batch for each resolved item."""

    # YOUR JOB 1 — pull resolved_items out of state
    # state["resolved_items"] is a list of dicts like:
    #     [{"name": "Crocin 500mg", "quantity": 2, "unit": "strip", "medicine_id": 5}, ...]
    # Use state.get("resolved_items") so a missing key returns None.
    # Write 1 line below:
    #     resolved_items = state.get("resolved_items")
    
    resolved_items =state.get("resolved_items")


    # YOUR JOB 2 — guard: nothing to pick batches for
    # If resolved_items is None / empty, return:
    #     {"errors": ["select_batch: no resolved_items to pick batches for"]}
    # Write the guard below (2–3 lines):
    if not resolved_items : 
        return  {
            "errors": [
                "select_batch: no resolved_items to pick batches for"
            ]
        }

    # YOUR JOB 3 — initialize accumulator lists
    # Write 2 lines below:
    #     batched_items: list[dict] = []
    #     errors: list[str] = []
    batched_items: list[dict] = []
    errors: list[str] = []


    # YOUR JOB 4 — open a DB session and a repository
    # Same pattern as resolve_medicine. The loop in YOUR JOB 5 must live
    # INSIDE this with-block.
    # Pattern:
    #     with SessionLocal() as db:
    #         repo = SQLAlchemyBatchRepository(db)
    #         ...
    with SessionLocal() as db:
        repo = SQLAlchemyBatchRepository(db)

        # JOB 5
        for item in resolved_items:

            batch = repo.select_fefo(
                item["medicine_id"]
            )

            if batch is None:
                errors.append(
                    f"No stocked, unexpired batch found for {item['name']!r}"
                )
                continue

            if batch.quantity < item["quantity"]:
                errors.append(
                    f"Insufficient stock for {item['name']!r}: "
                    f"need {item['quantity']}, "
                    f"only {batch.quantity} in batch {batch.batch_number!r}"
                )
                continue

            batched_items.append(
                {
                    **item,
                    "batch_id": batch.id,
                    "batch_number": batch.batch_number,
                    "expiry_date": batch.expiry_date.isoformat(),
                }
            )

    return {"batched_items": batched_items, "errors": errors}


# ============================================================================
# End-to-end smoke test — runs against your REAL local MySQL.
# Run with:
#     cd c:\ai-pharmacy-ecosystem\pharmacy-core-backend
#     .\venv\Scripts\Activate.ps1
#     python -m app.ai.nodes.select_batch
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

    # Step A — peek at the data so the test adapts to whatever's in your DB.
    with _SessionLocal() as _db:
        _meds = _MedRepo(_db).list_all()
        if _meds:
            _batches = _BatchRepo(_db).list_for_medicine(_meds[0].id)
        else:
            _batches = []

    if not _meds:
        print("!! No medicines in DB. Insert one via the FastAPI Swagger UI first.")
        raise SystemExit(1)

    if not _batches:
        print(f"!! No batches for medicine_id={_meds[0].id} ({_meds[0].name!r}).")
        print("   Insert a batch via Swagger UI: POST /batches with a non-expired")
        print("   expiry_date and quantity > 0, then re-run this test.")
        raise SystemExit(1)

    print(f"Found {len(_meds)} medicine(s) and {len(_batches)} batch(es) for the first one.")
    print(f"First medicine : id={_meds[0].id}  name={_meds[0].name!r}")
    print(f"First batch    : id={_batches[0].id}  expiry={_batches[0].expiry_date}  qty={_batches[0].quantity}\n")

    # Step B — build a known-resolved state and a deliberately-bad one.
    target_qty = min(_batches[0].quantity, 2) if _batches[0].quantity > 0 else 1
    too_many_qty = _batches[0].quantity + 1000  # guaranteed insufficient

    test_state: BillingState = {
        "resolved_items": [
            {
                "name": _meds[0].name,
                "quantity": target_qty,
                "unit": "strip",
                "medicine_id": _meds[0].id,
            },
        ]
    }

    insufficient_state: BillingState = {
        "resolved_items": [
            {
                "name": _meds[0].name,
                "quantity": too_many_qty,
                "unit": "strip",
                "medicine_id": _meds[0].id,
            },
        ]
    }

    print("========== Test 1: a fulfillable order ==========")
    print(f"Asking for {target_qty} of {_meds[0].name!r}")
    try:
        out = select_batch(test_state)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except NotImplementedError as e:
        print(f"NotImplementedError → {e}\n(fill in YOUR JOBs first)")
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__} → {e}")

    print("\n========== Test 2: order too large (insufficient stock) ==========")
    print(f"Asking for {too_many_qty} (more than any single batch has)")
    try:
        out = select_batch(insufficient_state)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except NotImplementedError:
        print("(skipped — implement YOUR JOBs first)")
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__} → {e}")

    print("\n========== Test 3: empty-state guard ==========")
    try:
        out = select_batch({})  # type: ignore[arg-type]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except NotImplementedError:
        print("(skipped — implement YOUR JOBs first)")
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__} → {e}")
