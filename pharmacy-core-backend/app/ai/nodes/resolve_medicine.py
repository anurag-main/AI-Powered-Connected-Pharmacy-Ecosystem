"""LangGraph node — resolve_medicine.

Takes each item from state['extracted_intent'].items and finds the matching
Medicine row in the database. Enriches each item with a `medicine_id` and
writes the result to state['resolved_items'].

Items whose name cannot be found are reported via state['errors'] and are
NOT included in resolved_items (downstream nodes will not try to bill them).

Analogy (kid-level):
    Priya, the inventory clerk, takes each notebook page Rohit filled.
    She walks to the shelves, finds the candy by name, and writes the
    SKU number on the page. If a page asks for a candy that isn't on
    any shelf, that page goes on the "can't find" pile and mom is told.

Why we open a NEW SessionLocal() inside the node:
    FastAPI's Depends(get_db) gives endpoints a per-request session.
    LangGraph nodes have no such injection mechanism, so we manage the
    session lifecycle ourselves via `with SessionLocal() as db:` — the
    context manager guarantees the connection returns to the pool even
    if a lookup raises.

Why we don't crash on a missing medicine:
    A real pharmacist might say "give me Vitamin Q" — a typo or an
    unstocked item. We collect that as a soft error and let the rest of
    the order proceed. The graph (step 3.8) will decide whether to abort
    or partial-fulfill based on state['errors'].
"""
from app.ai.state.billing_state import BillingState
from app.core.database import SessionLocal
from app.repositories.sqlalchemy_medicine_repository import SQLAlchemyMedicineRepository
from app.services.medicine_service import normalize_medicine_name


def resolve_medicine(state: BillingState) -> dict:
    """Resolve each extracted item's name to a Medicine row id."""

    # YOUR JOB 1 — pull extracted_intent out of state
    # state["extracted_intent"] is a dict shaped like:
    #     {"items": [...], "customer_name": ..., "customer_phone": ...}
    # Use state.get("extracted_intent") so a missing key returns None.
    # Write 1 line below:
    #     extracted = state.get("extracted_intent")
    
    extracted =state.get("extracted_intent")

    # YOUR JOB 2 — guard: bail out if no items to resolve
    # Two conditions count as "nothing to resolve":
    #   (a) extracted is None / falsy (the LLM node didn't run or returned nothing)
    #   (b) extracted["items"] is missing or empty
    # In either case, return: {"errors": ["resolve_medicine: no items to resolve"]}
    # Write the guard below (2–3 lines):
    if not extracted or not extracted.get("items"):
        return {
            "errors": ["resolve_medicine: no items to resolve"]
        }

    # YOUR JOB 3 — initialize two accumulator lists
    # We'll fill these as we walk through items.
    # Write 2 lines below:
    #     resolved_items: list[dict] = []
    #     errors: list[str] = []
    resolved_items: list[dict] = []
    errors: list[str] = []

    # YOUR JOB 4 — open a DB session and a repository
    # Use the context manager form so the connection is returned even on errors.
    # Pattern:
    #     with SessionLocal() as db:
    #         repo = SQLAlchemyMedicineRepository(db)
    #         ...  (your loop goes inside this block)
    # Write the `with` line + repo construction below:
    


    # YOUR JOB 5 — loop over extracted["items"], resolve each one
    # For each item dict:
    #   a. normalize the name:    normalized = normalize_medicine_name(item["name"])
    #   b. look it up:            medicine = repo.find_by_normalized_name(normalized)
    #   c. if not found:          errors.append(f"Medicine not found: {item['name']!r}")
    #                             continue
    #   d. if found, append an enriched dict to resolved_items:
    #          resolved_items.append({**item, "medicine_id": medicine.id})
    #
    # IMPORTANT: this loop MUST be INSIDE the `with SessionLocal() as db:` block
    # from YOUR JOB 4 — once the `with` block exits, the session is closed and
    # the repo cannot run any more queries.
    # Write the loop below (5–6 lines):
    with SessionLocal() as db:
        repo = SQLAlchemyMedicineRepository(db)

        for item in extracted["items"]:
            normalized = normalize_medicine_name(item["name"])
            medicine = repo.find_by_normalized_name(normalized)

            if medicine is None:
                errors.append(f"Medicine not found: {item['name']!r}")
                continue

            resolved_items.append({**item, "medicine_id": medicine.id})

    # YOUR JOB 6 — return the state update
    # Return both keys so downstream nodes have a consistent view.
    # Note: this overwrites any existing `errors` from prior nodes. That's OK
    # for now — we'll switch to an additive reducer pattern when the graph is
    # compiled in step 3.8.
    return {"resolved_items": resolved_items, "errors": errors}


# ============================================================================
# End-to-end smoke test — runs against your REAL local MySQL.
# Run with:
#     cd c:\ai-pharmacy-ecosystem\pharmacy-core-backend
#     .\venv\Scripts\Activate.ps1
#     python -m app.ai.nodes.resolve_medicine
# ============================================================================

if __name__ == "__main__":
    import json

    from app.core.database import SessionLocal as _SessionLocal
    from app.repositories.sqlalchemy_medicine_repository import (
        SQLAlchemyMedicineRepository as _Repo,
    )

    # Step A — peek at what's actually in the DB so the test adapts to your data.
    with _SessionLocal() as _db:
        _all = _Repo(_db).list_all()

    if not _all:
        print("!! No medicines in DB. Insert at least one via POST /medicines first")
        print("   (e.g. through the FastAPI Swagger UI at http://127.0.0.1:8000/docs)")
        raise SystemExit(1)

    print(f"Found {len(_all)} medicines in DB. First few:")
    for m in _all[:5]:
        print(f"  id={m.id:<3}  name={m.name!r}")

    # Step B — pick a real name from the DB + add a fake one to test the error path.
    known_name = _all[0].name
    print(f"\nTest case will use known medicine: {known_name!r}")
    print("Also testing an UNKNOWN medicine to exercise the error path.\n")

    test_state: BillingState = {
        "extracted_intent": {
            "items": [
                {"name": known_name, "quantity": 2, "unit": "strip"},
                {"name": "Unicorn Dust 999mg", "quantity": 1, "unit": "tube"},  # not in DB
            ],
            "customer_name": "Test User",
            "customer_phone": "9999999999",
        }
    }

    print("========== Calling resolve_medicine ==========")
    try:
        output = resolve_medicine(test_state)
        print("OUTPUT:")
        print(json.dumps(output, indent=2, ensure_ascii=False))
    except NotImplementedError as e:
        print(f"OUTPUT: NotImplementedError → {e}")
        print("(fill in YOUR JOB markers in resolve_medicine.py, then re-run)")
    except Exception as e:  # noqa: BLE001
        print(f"OUTPUT: {type(e).__name__} → {e}")

    # Step C — the empty-extracted-intent guard.
    print("\n========== Empty-intent guard test ==========")
    try:
        guard_output = resolve_medicine({})  # type: ignore[arg-type]
        print("OUTPUT:")
        print(json.dumps(guard_output, indent=2, ensure_ascii=False))
    except NotImplementedError:
        print("(skipped — implement YOUR JOBs first)")
    except Exception as e:  # noqa: BLE001
        print(f"OUTPUT: {type(e).__name__} → {e}")
