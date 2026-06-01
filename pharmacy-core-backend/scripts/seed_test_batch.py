"""Seed test batches for the FIRST medicine in the database.

Why this file exists:
    Phase 2 built the Batch model + repository, but we never built a `/batches`
    FastAPI router (the LangGraph will write batches via repository code, not
    HTTP). So to test step 3.4 (`select_batch` FEFO node) we need a way to put
    batch rows into the DB. This script does it directly via the repository.

How to run:
    cd c:\\ai-pharmacy-ecosystem\\pharmacy-core-backend
    .\\venv\\Scripts\\Activate.ps1
    python -m scripts.seed_test_batch

What it does:
    Inserts up to 3 test batches for the first medicine in the DB, each with
    a different expiry date. This is deliberate — it lets you SEE FEFO at work:
    the soonest-expiring batch should win the `select_fefo` query.

Idempotent:
    Re-runs are safe. If a batch with the same `batch_number` already exists
    for that medicine, that batch is skipped (no duplicate insert, no crash).
"""
from datetime import date, timedelta
from decimal import Decimal

from app.core.database import SessionLocal
from app.repositories.sqlalchemy_batch_repository import SQLAlchemyBatchRepository
from app.repositories.sqlalchemy_medicine_repository import SQLAlchemyMedicineRepository


# The three test batches we want to seed. Different expiries → FEFO has something to choose between.
_BATCH_SPECS = [
    {
        "batch_number": "SEED-EARLY",
        "days_until_expiry": 90,        # ~3 months out — FEFO WINNER
        "quantity": 25,
        "cost_price": Decimal("18.00"),
    },
    {
        "batch_number": "SEED-MID",
        "days_until_expiry": 300,       # ~10 months out
        "quantity": 100,
        "cost_price": Decimal("20.00"),
    },
    {
        "batch_number": "SEED-LATE",
        "days_until_expiry": 600,       # ~20 months out
        "quantity": 50,
        "cost_price": Decimal("22.00"),
    },
]


def main() -> int:
    today = date.today()
    print(f"Today (Python-side): {today}\n")

    with SessionLocal() as db:
        # Pick the target medicine: first one in the DB.
        meds = SQLAlchemyMedicineRepository(db).list_all()
        if not meds:
            print("!! No medicines in DB. Add one via Swagger UI (POST /medicines) first.")
            return 1

        target = meds[0]
        print(f"Target medicine: id={target.id}  name={target.name!r}\n")

        batch_repo = SQLAlchemyBatchRepository(db)

        # Read existing batches once — used to skip duplicates.
        existing_numbers = {b.batch_number for b in batch_repo.list_for_medicine(target.id)}

        inserted = 0
        skipped = 0
        for spec in _BATCH_SPECS:
            number = spec["batch_number"]
            if number in existing_numbers:
                print(f"  SKIP  batch_number={number!r}  (already exists for this medicine)")
                skipped += 1
                continue

            batch = batch_repo.add(
                medicine_id=target.id,
                batch_number=number,
                expiry_date=today + timedelta(days=spec["days_until_expiry"]),
                quantity=spec["quantity"],
                cost_price=spec["cost_price"],
            )
            print(
                f"  ADD   id={batch.id}  number={batch.batch_number!r}  "
                f"expires={batch.expiry_date}  qty={batch.quantity}"
            )
            inserted += 1

        print(f"\nInserted {inserted} batch(es), skipped {skipped} duplicate(s).")

        # Show the FEFO winner so you know what to expect when select_batch runs.
        winner = batch_repo.select_fefo(target.id)
        if winner is None:
            print(
                "!! select_fefo() returned None — that means no batch passed the filters "
                "(expired OR quantity 0). Check the inserted dates / quantities."
            )
            return 2

        print("\nFEFO winner for this medicine:")
        print(
            f"  id={winner.id}  number={winner.batch_number!r}  "
            f"expires={winner.expiry_date}  qty={winner.quantity}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
