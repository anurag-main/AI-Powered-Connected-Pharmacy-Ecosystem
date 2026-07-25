"""Seed ~3 months of realistic pharmacy operations for the BI Agent.

Populates suppliers, medicines, batches, purchases (+items), sales (+items),
customers and returns with coherent, FK-safe, financially realistic data.

WHAT IT PRODUCES
    - 10 real suppliers, 100 real medicines
    - ~200 batches (mix of expired / expiring-soon / long-dated)
    - 80 purchase invoices (3-10 items each) over the last 90 days
    - ~400-460 sales (1-6 items each), weekday/weekend/low-day variation
    - 20 sales-returns + 10 purchase-returns

DESIGN NOTES
    - DESTRUCTIVE: wipes the business tables first (reverse-FK order) so re-runs
      give a clean, coherent dataset. Run only against a DEV database.
    - Money is Decimal, 2dp. Batch cost_price = 65-92% of MRP (=> 8-35% margin).
    - Sales only draw from NON-expired batches with stock (FEFO), decrementing
      batch.quantity. Expired batches keep their stock -> measurable expiry loss.
    - Derived metrics (gross profit, margin, valuation, trends) are NOT stored —
      they are SQL aggregates over these rows. We only store the raw facts.
    - Deterministic: fixed RNG seed, so every run yields the same dataset.

PREREQUISITE
    The suppliers/purchases/purchase_items/returns tables must exist first
    (register the models in app/models/__init__.py, then `alembic upgrade head`).

RUN
    cd c:\\ai-pharmacy-ecosystem\\pharmacy-core-backend
    .\\venv\\Scripts\\Activate.ps1
    python -m scripts.seed_business_data
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete

from app.core.database import SessionLocal
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.reorder_request import ReorderRequest
from app.models.returns import Return
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.supplier import Supplier

RNG = random.Random(42)  # deterministic

TODAY = date.today()
NOW = datetime.now()


# ---------------------------------------------------------------------------
# Reference data — real names, not placeholders
# ---------------------------------------------------------------------------

SUPPLIERS = [
    "Sun Pharma", "Cipla", "Dr. Reddy's", "Abbott", "Mankind",
    "Alkem", "Glenmark", "Lupin", "Torrent", "Zydus",
]

# (name, manufacturer, mrp, hsn_code)
MEDICINES = [
    ("Paracetamol 500mg", "Micro Labs", 30, "30049099"),
    ("Dolo 650", "Micro Labs", 32, "30049099"),
    ("Crocin Advance 500mg", "GSK", 28, "30049099"),
    ("Calpol 250 Suspension", "GSK", 75, "30049099"),
    ("Azithromycin 500mg", "Cipla", 85, "30042010"),
    ("Amoxicillin 500mg", "Cipla", 95, "30041020"),
    ("Augmentin 625 Duo", "GSK", 190, "30041020"),
    ("Cetirizine 10mg", "Dr. Reddy's", 25, "30049099"),
    ("Levocetirizine 5mg", "Sun Pharma", 45, "30049099"),
    ("Montair LC", "Cipla", 210, "30049099"),
    ("Pantoprazole 40mg", "Sun Pharma", 110, "30049099"),
    ("Pan D", "Alkem", 135, "30049099"),
    ("Omeprazole 20mg", "Dr. Reddy's", 70, "30049099"),
    ("Rabeprazole 20mg", "Zydus", 95, "30049099"),
    ("Metformin 500mg", "USV", 40, "30049099"),
    ("Metformin 1000mg", "USV", 65, "30049099"),
    ("Glimepiride 2mg", "Sanofi", 78, "30049099"),
    ("Telmisartan 40mg", "Glenmark", 95, "30049099"),
    ("Telma 40", "Glenmark", 120, "30049099"),
    ("Amlodipine 5mg", "Cipla", 38, "30049099"),
    ("Amlong 5mg", "Micro Labs", 52, "30049099"),
    ("Atorvastatin 10mg", "Zydus", 88, "30049099"),
    ("Rosuvastatin 10mg", "Sun Pharma", 130, "30049099"),
    ("Ecosprin 75", "USV", 12, "30049099"),
    ("Clopidogrel 75mg", "Sun Pharma", 95, "30049099"),
    ("Vitamin D3 60000 IU", "Mankind", 45, "21069099"),
    ("Calcium + Vitamin D3", "Abbott", 120, "21069099"),
    ("Shelcal 500", "Torrent", 135, "21069099"),
    ("ORS Powder", "Cipla", 22, "30049099"),
    ("Zinc Sulphate 20mg", "Alkem", 30, "30049099"),
    ("Benadryl Cough Syrup", "Johnson & Johnson", 110, "30049099"),
    ("Ascoril LS Syrup", "Glenmark", 130, "30049099"),
    ("Insulin Glargine", "Sanofi", 850, "30043900"),
    ("Human Mixtard 30/70", "Novo Nordisk", 165, "30043900"),
    ("Multivitamin Tablets", "Abbott", 95, "21069099"),
    ("Becosules Capsules", "Pfizer", 45, "21069099"),
    ("Neurobion Forte", "Merck", 42, "21069099"),
    ("Thyronorm 50mcg", "Abbott", 130, "30049099"),
    ("Eltroxin 100mcg", "GSK", 145, "30049099"),
    ("Ibuprofen 400mg", "Abbott", 35, "30049099"),
    ("Combiflam", "Sanofi", 44, "30049099"),
    ("Diclofenac 50mg", "Novartis", 30, "30049099"),
    ("Volini Gel", "Sun Pharma", 145, "30049099"),
    ("Moov Cream", "Reckitt", 95, "30049099"),
    ("Aceclofenac 100mg", "Ipca", 55, "30049099"),
    ("Zerodol SP", "Ipca", 105, "30049099"),
    ("Nimesulide 100mg", "Dr. Reddy's", 40, "30049099"),
    ("Domperidone 10mg", "Cipla", 48, "30049099"),
    ("Ondansetron 4mg", "Alkem", 60, "30049099"),
    ("Rantac 150", "JB Chemicals", 30, "30049099"),
    ("Digene Gel", "Abbott", 130, "30049099"),
    ("Gelusil MPS", "Pfizer", 95, "30049099"),
    ("Cyclopam Tablet", "Indoco", 40, "30049099"),
    ("Meftal Spas", "Blue Cross", 45, "30049099"),
    ("Drotin M", "Walter Bushnell", 60, "30049099"),
    ("Ciprofloxacin 500mg", "Cipla", 65, "30042010"),
    ("Ofloxacin 200mg", "Cipla", 55, "30042010"),
    ("Norflox 400", "Cipla", 60, "30042010"),
    ("Metronidazole 400mg", "JB Chemicals", 35, "30042000"),
    ("Doxycycline 100mg", "Sun Pharma", 70, "30042010"),
    ("Cefixime 200mg", "Lupin", 120, "30042010"),
    ("Taxim O 200", "Alkem", 135, "30042010"),
    ("Clavam 625", "Alkem", 195, "30041020"),
    ("Monocef Injection", "Aristo", 55, "30042010"),
    ("Dexamethasone 0.5mg", "Zydus", 25, "30049099"),
    ("Prednisolone 10mg", "Wyeth", 40, "30049099"),
    ("Wysolone 10mg", "Pfizer", 55, "30049099"),
    ("Montek LC Kid", "Sun Pharma", 155, "30049099"),
    ("Allegra 120mg", "Sanofi", 190, "30049099"),
    ("Sinarest Tablet", "Centaur", 75, "30049099"),
    ("Cheston Cold", "Cipla", 65, "30049099"),
    ("Vicks Action 500", "Procter & Gamble", 45, "30049099"),
    ("Otrivin Nasal Spray", "GSK", 105, "30049099"),
    ("Nasivion Drops", "Merck", 60, "30049099"),
    ("Betadine Gargle", "Win-Medicare", 110, "30049099"),
    ("Betadine Ointment", "Win-Medicare", 95, "30049099"),
    ("Soframycin Cream", "Sanofi", 45, "30049099"),
    ("Neosporin Powder", "GSK", 85, "30049099"),
    ("Dettol Antiseptic", "Reckitt", 85, "34029099"),
    ("Savlon Antiseptic", "ITC", 75, "34029099"),
    ("Liv 52 Tablets", "Himalaya", 140, "30049099"),
    ("Cypon Syrup", "Geno Pharma", 95, "30049099"),
    ("Zincovit Tablets", "Apex", 105, "21069099"),
    ("Supradyn Daily", "Bayer", 115, "21069099"),
    ("Revital H", "Sun Pharma", 260, "21069099"),
    ("Cremaffin Plus Syrup", "Abbott", 185, "30049099"),
    ("Duphalac Syrup", "Abbott", 285, "30049099"),
    ("Isabgol Husk", "Telophase", 210, "21069099"),
    ("Unienzyme Tablets", "Torrent", 95, "30049099"),
    ("Aristozyme Syrup", "Aristo", 105, "30049099"),
    ("Sporlac Sachet", "Uni-Sankyo", 30, "30049099"),
    ("Enterogermina", "Sanofi", 145, "30049099"),
    ("Electral Powder", "FDC", 22, "30049099"),
    ("Pediasure Vanilla", "Abbott", 480, "21069099"),
    ("Protinex Powder", "Danone", 520, "21069099"),
    ("Glucon-D", "Zydus", 130, "21069099"),
    ("Himalaya Septilin", "Himalaya", 130, "30049099"),
    ("Ashwagandha Tablets", "Dabur", 210, "21069099"),
    ("Chyawanprash", "Dabur", 320, "21069099"),
    ("Grilinctus Syrup", "Franco-Indian", 115, "30049099"),
]

FIRST_NAMES = [
    "Anurag", "Priya", "Rahul", "Sneha", "Amit", "Pooja", "Vikram", "Neha",
    "Suresh", "Kavita", "Ramesh", "Anjali", "Deepak", "Meera", "Sanjay",
    "Divya", "Arjun", "Shweta", "Manoj", "Rekha", "Nitin", "Swati",
]
LAST_NAMES = [
    "Bhosale", "Sharma", "Patil", "Deshmukh", "Verma", "Joshi", "Nair",
    "Reddy", "Gupta", "Kulkarni", "Iyer", "Mehta", "Shah", "Rao",
]

SALES_RETURN_REASONS = ["Damaged strip", "Wrong medicine", "Customer cancelled", "Expired stock"]
PURCHASE_RETURN_REASONS = ["Expired stock", "Supplier replacement", "Damaged strip", "Wrong medicine"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def money(x) -> Decimal:
    """Round any numeric to 2-decimal Decimal (paise). Never FLOAT for money."""
    return Decimal(f"{float(x):.2f}")


def batch_number() -> str:
    """Realistic-looking pharma batch code, e.g. 'AX2451B'."""
    letters = "".join(RNG.choice("ABCDEFGHJKLMNPQRTUVWXYZ") for _ in range(2))
    return f"{letters}{RNG.randint(1000, 9999)}{RNG.choice('ABCDEF')}"


def normalize(name: str) -> str:
    """Mirror app.services.medicine_service.normalize_medicine_name."""
    return name.lower().strip()


# ---------------------------------------------------------------------------
# Wipe (reverse-FK order) so re-runs are clean
# ---------------------------------------------------------------------------

def wipe(db) -> None:
    for model in (
        Return, SaleItem, Sale, PurchaseItem, Purchase,
        ReorderRequest, Batch, Customer, Medicine, Supplier,
    ):
        db.execute(delete(model))
    db.commit()


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def make_suppliers(db) -> list[Supplier]:
    rows = [Supplier(name=n, phone=f"022{RNG.randint(10000000, 99999999)}") for n in SUPPLIERS]
    db.add_all(rows)
    db.flush()
    return rows


def make_medicines(db) -> list[Medicine]:
    rows = [
        Medicine(name=n, normalized_name=normalize(n), mrp=money(mrp),
                 hsn_code=hsn, manufacturer=mfr)
        for (n, mfr, mrp, hsn) in MEDICINES
    ]
    db.add_all(rows)
    db.flush()
    return rows


def make_batches(db, medicines: list[Medicine]) -> list[Batch]:
    """1-4 batches per medicine (~200 total) with a controlled expiry mix."""
    batches: list[Batch] = []
    for med in medicines:
        for _ in range(RNG.randint(1, 4)):
            cost = money(float(med.mrp) * RNG.uniform(0.65, 0.92))
            batches.append(Batch(
                medicine_id=med.id,
                batch_number=batch_number(),
                expiry_date=TODAY,               # placeholder; assigned below
                quantity=RNG.randint(10, 300),
                cost_price=cost,
            ))

    # Assign the required expiry mix across all batches.
    RNG.shuffle(batches)
    n_expired = RNG.randint(15, 25)             # already expired
    n_soon = 10                                  # expiring within 30 days
    for i, b in enumerate(batches):
        if i < n_expired:
            b.expiry_date = TODAY - timedelta(days=RNG.randint(5, 180))
        elif i < n_expired + n_soon:
            b.expiry_date = TODAY + timedelta(days=RNG.randint(5, 30))
        else:
            b.expiry_date = TODAY + timedelta(days=RNG.randint(180, 540))

    db.add_all(batches)
    db.flush()
    return batches


def make_customers(db) -> list[Customer]:
    rows, seen = [], set()
    for _ in range(40):
        phone = "9" + "".join(str(RNG.randint(0, 9)) for _ in range(9))
        if phone in seen:
            continue
        seen.add(phone)
        name = f"{RNG.choice(FIRST_NAMES)} {RNG.choice(LAST_NAMES)}"
        rows.append(Customer(name=name, phone=phone))
    db.add_all(rows)
    db.flush()
    return rows


def make_purchases(db, suppliers, medicines, batches) -> None:
    """80 invoices, 3-10 lines each, spread over the last 90 days."""
    batches_by_med: dict[int, list[Batch]] = {}
    for b in batches:
        batches_by_med.setdefault(b.medicine_id, []).append(b)

    for i in range(80):
        supplier = RNG.choice(suppliers)
        pdate = TODAY - timedelta(days=RNG.randint(0, 90))
        purchase = Purchase(
            supplier_id=supplier.id,
            purchase_date=pdate,
            invoice_number=f"{supplier.name[:3].upper()}/25-26/{1000 + i}",
            total_amount=money(0),
        )
        db.add(purchase)
        db.flush()

        total = Decimal("0")
        for med in RNG.sample(medicines, RNG.randint(3, 10)):
            qty = RNG.randint(20, 300)
            unit_cost = money(float(med.mrp) * RNG.uniform(0.65, 0.90))
            line_total = money(unit_cost * qty)
            total += line_total
            linked = batches_by_med.get(med.id)
            db.add(PurchaseItem(
                purchase_id=purchase.id,
                medicine_id=med.id,
                batch_id=(RNG.choice(linked).id if linked else None),
                quantity=qty,
                unit_cost=unit_cost,
                line_total=line_total,
            ))
        purchase.total_amount = money(total)   # invariant: header == sum(lines)
    db.flush()


def make_sales(db, medicines, batches, customers):
    """~450 sales over 90 days; sell FEFO from non-expired, in-stock batches."""
    batches_by_med: dict[int, list[Batch]] = {}
    for b in batches:
        batches_by_med.setdefault(b.medicine_id, []).append(b)

    # Popularity skew -> creates fast movers vs slow movers for BI.
    weights = {m.id: RNG.choice([1, 1, 1, 2, 3, 8, 15]) for m in medicines}

    def sellable_batch(med_id: int) -> Batch | None:
        avail = [b for b in batches_by_med.get(med_id, [])
                 if b.quantity > 0 and b.expiry_date > TODAY]
        return min(avail, key=lambda b: b.expiry_date) if avail else None

    sales_with_items: list[tuple[Sale, list[dict]]] = []

    for day_offset in range(90, -1, -1):
        d = TODAY - timedelta(days=day_offset)
        weekend = d.weekday() >= 5
        if RNG.random() < 0.08:
            n_sales = RNG.randint(1, 2)               # occasional low day
        elif weekend:
            n_sales = RNG.randint(7, 11)              # busier weekends
        else:
            n_sales = RNG.randint(3, 6)               # normal weekday

        for _ in range(n_sales):
            sold_at = datetime(d.year, d.month, d.day,
                               RNG.randint(9, 21), RNG.randint(0, 59))
            customer = RNG.choice(customers) if RNG.random() < 0.6 else None
            sale = Sale(customer_id=(customer.id if customer else None),
                        total_amount=money(0), sold_at=sold_at)
            db.add(sale)
            db.flush()

            candidates = [m for m in medicines if sellable_batch(m.id)]
            if not candidates:
                continue
            k = min(RNG.randint(1, 6), len(candidates))
            picks = RNG.choices(candidates, weights=[weights[m.id] for m in candidates], k=k)

            total = Decimal("0")
            items_info: list[dict] = []
            seen_meds: set[int] = set()
            for med in picks:
                if med.id in seen_meds:
                    continue
                seen_meds.add(med.id)
                batch = sellable_batch(med.id)
                if batch is None:
                    continue
                qty = min(RNG.randint(1, 5), batch.quantity)
                unit_price = money(med.mrp)
                line_total = money(unit_price * qty)
                batch.quantity -= qty
                total += line_total
                db.add(SaleItem(
                    sale_id=sale.id, medicine_id=med.id, batch_id=batch.id,
                    quantity=qty, unit_price=unit_price, line_total=line_total,
                ))
                items_info.append({
                    "medicine_id": med.id, "batch_id": batch.id,
                    "quantity": qty, "unit_price": unit_price,
                })

            if not items_info:
                db.delete(sale)
                continue
            sale.total_amount = money(total)          # invariant: header == sum(lines)
            sales_with_items.append((sale, items_info))
    db.flush()
    return sales_with_items, batches_by_med


def make_returns(db, sales_with_items, suppliers, batches):
    """20 sales-returns + 10 purchase-returns, satisfying the CHECK constraints."""
    # --- sales returns: customer -> pharmacy (sale_id set, supplier_id null) ---
    for sale, items in RNG.sample(sales_with_items, min(20, len(sales_with_items))):
        it = RNG.choice(items)
        qty = RNG.randint(1, it["quantity"])
        db.add(Return(
            return_type="sales",
            medicine_id=it["medicine_id"],
            batch_id=it["batch_id"],
            sale_id=sale.id,
            supplier_id=None,
            quantity=qty,
            amount=money(it["unit_price"] * qty),
            reason=RNG.choice(SALES_RETURN_REASONS),
            returned_at=sale.sold_at + timedelta(days=RNG.randint(1, 7)),
        ))

    # --- purchase returns: pharmacy -> supplier (supplier_id set, sale_id null) ---
    expired = [b for b in batches if b.expiry_date <= TODAY and b.quantity > 0]
    pool = expired if expired else batches
    for _ in range(10):
        b = RNG.choice(pool)
        med = next(m for m in db.query(Medicine).filter(Medicine.id == b.medicine_id))
        qty = RNG.randint(1, max(1, min(b.quantity, 20)))
        db.add(Return(
            return_type="purchase",
            medicine_id=b.medicine_id,
            batch_id=b.id,
            sale_id=None,
            supplier_id=RNG.choice(suppliers).id,
            quantity=qty,
            amount=money(b.cost_price * qty),
            reason=RNG.choice(PURCHASE_RETURN_REASONS),
            returned_at=NOW - timedelta(days=RNG.randint(1, 90)),
        ))
    db.flush()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    with SessionLocal() as db:
        print("Wiping existing business data (reverse-FK order)...")
        wipe(db)

        suppliers = make_suppliers(db)
        medicines = make_medicines(db)
        batches = make_batches(db, medicines)
        customers = make_customers(db)
        make_purchases(db, suppliers, medicines, batches)
        sales_with_items, _ = make_sales(db, medicines, batches, customers)
        make_returns(db, sales_with_items, suppliers, batches)

        db.commit()

        # ---- summary ----
        n_pi = db.query(PurchaseItem).count()
        n_si = db.query(SaleItem).count()
        expired_loss = sum(
            float(b.cost_price) * b.quantity
            for b in batches if b.expiry_date <= TODAY and b.quantity > 0
        )
        gross_sales = sum(float(s.total_amount) for s, _ in sales_with_items)
        print("\n================= SEED COMPLETE =================")
        print(f"  suppliers      : {len(suppliers)}")
        print(f"  medicines      : {len(medicines)}")
        print(f"  batches        : {len(batches)}")
        print(f"  customers      : {len(customers)}")
        print(f"  purchases      : {db.query(Purchase).count()}  (items: {n_pi})")
        print(f"  sales          : {len(sales_with_items)}  (items: {n_si})")
        print(f"  returns        : {db.query(Return).count()}")
        print(f"  gross sales    : Rs {gross_sales:,.2f}")
        print(f"  expiry loss    : Rs {expired_loss:,.2f}")
        print("================================================")


if __name__ == "__main__":
    main()
