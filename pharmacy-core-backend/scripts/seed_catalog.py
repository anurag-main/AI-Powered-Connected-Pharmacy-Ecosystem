"""Seed a starter medicine catalog so voice billing finds real medicines.

Inserts ~10 common medicines (each with a price + a valid 8-digit HSN code) and
one non-expired, in-stock batch per medicine. Without this the catalog only has
'Crocin 500mg' and spoken items like 'Paracetamol 500mg' come back 'not found'.

Idempotent: re-runs skip medicines whose normalized name already exists, and skip
batches whose batch_number already exists for that medicine. Safe to run anytime.

Run with:
    cd c:\\ai-pharmacy-ecosystem\\pharmacy-core-backend
    .\\venv\\Scripts\\Activate.ps1
    python -m scripts.seed_catalog
"""
from datetime import date, timedelta
from decimal import Decimal

from app.core.database import SessionLocal
from app.repositories.sqlalchemy_batch_repository import SQLAlchemyBatchRepository
from app.repositories.sqlalchemy_medicine_repository import SQLAlchemyMedicineRepository
from app.services.medicine_service import normalize_medicine_name

# HSN 30049099 = "medicaments, for retail sale" — valid 8-digit code for all these demo items.
_HSN = "30049099"

# (name, mrp, manufacturer, stock_qty). Names are the canonical spelling the catalog
# stores; speak them this way for an exact match (matching is lowercase-exact for now).
_CATALOG = [
    ("Paracetamol 500mg", Decimal("15.00"), "Cipla", 200),
    ("Crocin 500mg", Decimal("25.50"), "GSK", 150),
    ("Mtac B 500mg", Decimal("30.00"), "Ipca", 120),
    ("Azithromycin 500mg", Decimal("75.00"), "Cipla", 80),
    ("Amoxicillin 500mg", Decimal("45.00"), "Sun Pharma", 90),
    ("Cetirizine 10mg", Decimal("20.00"), "Dr Reddy", 160),
    ("Pantoprazole 40mg", Decimal("55.00"), "Alkem", 100),
    ("ORS Powder", Decimal("22.00"), "FDC", 140),
    ("Benadryl Cough Syrup", Decimal("110.00"), "J&J", 60),
    ("Volini Gel", Decimal("95.00"), "Sun Pharma", 70),
]


def main() -> int:
    today = date.today()
    expiry = today + timedelta(days=540)  # ~18 months out — comfortably unexpired

    added_meds = skipped_meds = added_batches = skipped_batches = 0

    with SessionLocal() as db:
        med_repo = SQLAlchemyMedicineRepository(db)
        batch_repo = SQLAlchemyBatchRepository(db)

        for name, mrp, manufacturer, qty in _CATALOG:
            normalized = normalize_medicine_name(name)
            existing = med_repo.find_by_normalized_name(normalized)

            if existing is not None:
                medicine = existing
                print(f"  SKIP medicine  id={medicine.id:<3} {name!r} (already exists)")
                skipped_meds += 1
            else:
                medicine = med_repo.add(
                    name=name,
                    mrp=float(mrp),
                    hsn_code=_HSN,
                    manufacturer=manufacturer,
                )
                print(f"  ADD  medicine  id={medicine.id:<3} {name!r}  mrp={mrp}")
                added_meds += 1

            # One in-stock batch per medicine. Skip if this batch_number already exists.
            batch_number = f"SEED-{normalized.replace(' ', '-').upper()}"
            existing_numbers = {b.batch_number for b in batch_repo.list_for_medicine(medicine.id)}
            if batch_number in existing_numbers:
                print(f"       SKIP batch  {batch_number!r} (already exists)")
                skipped_batches += 1
                continue

            batch = batch_repo.add(
                medicine_id=medicine.id,
                batch_number=batch_number,
                expiry_date=expiry,
                quantity=qty,
                cost_price=(mrp * Decimal("0.6")).quantize(Decimal("0.01")),
            )
            print(f"       ADD  batch   id={batch.id:<3} {batch_number!r}  qty={qty}  exp={expiry}")
            added_batches += 1

    print(
        f"\nDone. Medicines: +{added_meds} added, {skipped_meds} skipped. "
        f"Batches: +{added_batches} added, {skipped_batches} skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
