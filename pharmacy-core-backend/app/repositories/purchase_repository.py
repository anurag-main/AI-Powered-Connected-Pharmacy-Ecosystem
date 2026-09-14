"""Storage layer for the Goods Receipt domain.

THE COMMIT BOUNDARY IS NOT HERE
-------------------------------
Every other write repository in this project commits inside its own ``add()``
method. That is fine for a single-table insert and fatal for this one: a goods
receipt writes suppliers, purchases, batches and purchase_items, and a commit in
the middle would leave a purchase header pointing at batches that were never
created if the next statement failed.

So this repository never calls ``commit()``. It ``flush()``es where it needs a
generated id, and ``GoodsReceiptService`` owns the single ``with db.begin():``
block that commits or rolls back all of it. This is the Unit of Work pattern the
medicine repository docstring predicted we would need.

``flush()`` vs ``commit()`` is the idea worth taking away: flush sends the INSERT
to MySQL and gets the auto-increment id back, but the transaction is still open
and still reversible. Commit is the point of no return.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.supplier import Supplier


class PurchaseRepository:
    """SQL access for goods receipts. Reads and writes; never commits."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -----------------------------------------------------------------
    # Suppliers
    # -----------------------------------------------------------------

    def get_supplier(self, supplier_id: int) -> Supplier | None:
        """Primary-key lookup. ``None`` when the id does not exist."""
        return self.db.get(Supplier, supplier_id)

    def find_supplier_by_name(self, name: str) -> Supplier | None:
        """Case-insensitive match on the vendor name.

        Matching with ``LOWER()`` here is what stops "Sun Pharma", "sun pharma"
        and "SUN PHARMA" becoming three vendors, which would split every
        purchase-trend report three ways.
        """
        stmt = select(Supplier).where(func.lower(Supplier.name) == name.strip().lower())
        return self.db.scalars(stmt).first()

    def create_supplier(self, *, name: str) -> Supplier:
        """Insert a vendor and flush so the caller gets its id. No commit."""
        supplier = Supplier(name=name.strip())
        self.db.add(supplier)
        self.db.flush()
        return supplier

    def list_suppliers(self) -> list[Supplier]:
        """Every vendor, alphabetically -- this feeds a picker, not a report."""
        stmt = select(Supplier).order_by(Supplier.name)
        return list(self.db.scalars(stmt).all())

    # -----------------------------------------------------------------
    # Medicines (read-only here -- this domain never creates one)
    # -----------------------------------------------------------------

    def medicines_by_ids(self, medicine_ids: list[int]) -> dict[int, Medicine]:
        """Load every referenced medicine in ONE query, keyed by id.

        Deliberately not a lookup per line. A 20-line invoice would otherwise
        issue 20 round trips before doing any work -- the N+1 problem, and the
        easiest performance bug in the codebase to introduce by accident.
        """
        if not medicine_ids:
            return {}
        stmt = select(Medicine).where(Medicine.id.in_(set(medicine_ids)))
        return {row.id: row for row in self.db.scalars(stmt).all()}

    # -----------------------------------------------------------------
    # Batches
    # -----------------------------------------------------------------

    def find_batch(self, *, medicine_id: int, batch_number: str) -> Batch | None:
        """The existing shelf batch with this number, if there is one.

        Matched case-insensitively for the same reason as supplier names:
        "ab123" and "AB123" printed on the same carton are one physical batch.
        """
        stmt = select(Batch).where(
            Batch.medicine_id == medicine_id,
            func.lower(Batch.batch_number) == batch_number.lower(),
        )
        return self.db.scalars(stmt).first()

    def create_batch(
        self,
        *,
        medicine_id: int,
        batch_number: str,
        expiry_date: date,
        quantity: int,
        cost_price: Decimal,
    ) -> Batch:
        """Insert a new physical batch and flush for its id. No commit."""
        batch = Batch(
            medicine_id=medicine_id,
            batch_number=batch_number,
            expiry_date=expiry_date,
            quantity=quantity,
            cost_price=cost_price,
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    # -----------------------------------------------------------------
    # Purchases
    # -----------------------------------------------------------------

    def create_purchase(
        self,
        *,
        supplier_id: int,
        purchase_date: date,
        invoice_number: str | None,
        total_amount: Decimal,
    ) -> Purchase:
        """Insert the invoice header and flush for its id. No commit."""
        purchase = Purchase(
            supplier_id=supplier_id,
            purchase_date=purchase_date,
            invoice_number=invoice_number,
            total_amount=total_amount,
        )
        self.db.add(purchase)
        self.db.flush()
        return purchase

    def create_purchase_item(
        self,
        *,
        purchase_id: int,
        medicine_id: int,
        batch_id: int,
        quantity: int,
        unit_cost: Decimal,
        line_total: Decimal,
    ) -> PurchaseItem:
        """Insert one invoice line. No flush needed -- nothing references its id."""
        item = PurchaseItem(
            purchase_id=purchase_id,
            medicine_id=medicine_id,
            batch_id=batch_id,
            quantity=quantity,
            unit_cost=unit_cost,
            line_total=line_total,
        )
        self.db.add(item)
        return item

    def recent_purchases(self, *, limit: int) -> list[tuple[Purchase, str, int]]:
        """The most recent receipts as ``(purchase, supplier_name, line_count)``.

        One query with a join and a grouped count, rather than loading each
        purchase and asking it how many lines it has. Ordered by id descending
        rather than by date: two receipts entered on the same day should still
        come back newest-first, and ``purchase_date`` alone cannot express that.
        """
        line_count = func.count(PurchaseItem.id).label("line_count")
        stmt = (
            select(Purchase, Supplier.name, line_count)
            .join(Supplier, Supplier.id == Purchase.supplier_id)
            .outerjoin(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
            .group_by(Purchase.id, Supplier.name)
            .order_by(Purchase.id.desc())
            .limit(limit)
        )
        return [(row[0], row[1], row[2]) for row in self.db.execute(stmt).all()]

    def purchase_detail(
        self, purchase_id: int
    ) -> tuple[Purchase, str, list[tuple[PurchaseItem, Medicine, Batch | None]]] | None:
        """One receipt with its lines, or ``None`` if the id does not exist."""
        header = self.db.get(Purchase, purchase_id)
        if header is None:
            return None

        supplier = self.db.get(Supplier, header.supplier_id)
        supplier_name = supplier.name if supplier is not None else "(unknown supplier)"

        stmt = (
            select(PurchaseItem, Medicine, Batch)
            .join(Medicine, Medicine.id == PurchaseItem.medicine_id)
            .outerjoin(Batch, Batch.id == PurchaseItem.batch_id)
            .where(PurchaseItem.purchase_id == purchase_id)
            .order_by(PurchaseItem.id)
        )
        lines = [(row[0], row[1], row[2]) for row in self.db.execute(stmt).all()]
        return header, supplier_name, lines
