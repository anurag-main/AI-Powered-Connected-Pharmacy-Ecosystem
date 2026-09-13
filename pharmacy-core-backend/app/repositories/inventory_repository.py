"""Database access for inventory-risk analysis. SQL only — no risk logic lives here.

Three questions, deliberately separate:

    stock_by_medicine()          how much stock, worth how much, per medicine
    oldest_receipt_by_medicine() when the stock currently on the shelf arrived
    count_medicines()            how many medicines exist at all

Demand is **not** here. It comes from
:class:`app.services.demand_service.DemandService`, which the expiry and reorder
agents also use. Adding a fourth sales query would recreate exactly the divergence
that service was extracted to end.

CAPITAL vs COVER — WHY STOCK IS COUNTED TWICE
---------------------------------------------
Expired stock is money already spent that cannot be recovered by selling, so it
belongs in the capital figure. But it cannot satisfy a single day of demand, so
including it in days-of-cover would make a shelf of dead product look well supplied.
One number cannot be both, so the query returns both:

    stock_quantity / inventory_value   every positive batch      -> the capital view
    sellable_quantity / sellable_value  non-expired batches only  -> the cover view

The reorder repository already excludes expired batches from cover for the same
reason. This is that rule, kept consistent.

INDEXES
-------
``ix_batches_medicine_expiry`` covers the batch scan and its GROUP BY.
``ix_purchase_items_purchase_id`` and ``ix_purchases_purchase_date`` cover the
receipt query's join to the purchase header.

The receipt query also joins ``purchase_items.batch_id``, which has **no index** —
the model indexes ``purchase_id`` and ``medicine_id`` only. At 500 purchase lines
that is an irrelevant scan, and the brief is not to add an index without evidence.
The evidence to watch for is this query slowing as purchase history grows; the fix
is one index on ``purchase_items(batch_id)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, case, func
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem


@dataclass(frozen=True)
class MedicineStock:
    """One medicine's stock position, straight from the database.

    Every field is a raw fact. Nothing here is a judgement — no thresholds, no risk,
    no velocity. The service turns these into meaning.
    """

    medicine_id: int
    medicine_name: str

    # Capital view: every batch holding stock, expired or not.
    stock_quantity: int
    inventory_value: Decimal

    # Cover view: only batches that can still be dispensed.
    sellable_quantity: int
    sellable_value: Decimal

    # Data-quality signal, surfaced rather than silently dropped.
    negative_batch_count: int


class InventoryRepository:
    """Reads the stock facts the inventory-risk calculation needs. Never writes."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Stock
    # ------------------------------------------------------------------

    def stock_by_medicine(self, *, as_of: date) -> list[MedicineStock]:
        """Stock and value per medicine, for every medicine holding stock.

        Aggregated entirely in SQL: one GROUP BY over ``batches``, not a row per
        batch pulled into Python. On today's data that is 261 batches collapsing to
        96 rows inside the database instead of crossing the wire.

        Ordered by ``medicine_id`` so the result is stable between runs and a ranking
        built on top of it cannot flap.

        **Negative quantities are excluded from both totals and counted separately.**
        The column has no CHECK constraint, so bad data is reachable. Letting a
        negative batch cancel out a real one would understate capital that physically
        exists on the shelf; dropping it silently would hide the defect. It is
        excluded from the arithmetic and reported as a count.

        Medicines with no batches never appear — they are not rows in the join. Use
        :meth:`count_medicines` to find out how many were left out.

        Table       batches
        Join        medicines ON medicines.id = batches.medicine_id
        Filter      HAVING positive stock
        Aggregation SUM with CASE, GROUP BY medicine_id
        Index       ix_batches_medicine_expiry
        """

        positive = Batch.quantity > 0
        sellable = (Batch.quantity > 0) & (Batch.expiry_date > as_of)

        stock_quantity = func.coalesce(
            func.sum(case((positive, Batch.quantity), else_=0)), 0
        )
        inventory_value = func.coalesce(
            func.sum(case((positive, Batch.quantity * Batch.cost_price), else_=0)), 0
        )
        sellable_quantity = func.coalesce(
            func.sum(case((sellable, Batch.quantity), else_=0)), 0
        )
        sellable_value = func.coalesce(
            func.sum(case((sellable, Batch.quantity * Batch.cost_price), else_=0)), 0
        )
        negative_batches = func.coalesce(
            func.sum(case((Batch.quantity < 0, 1), else_=0)), 0
        )

        statement: Select = (
            Select(
                Medicine.id,
                Medicine.name,
                stock_quantity,
                inventory_value,
                sellable_quantity,
                sellable_value,
                negative_batches,
            )
            .join(Batch, Batch.medicine_id == Medicine.id)
            .group_by(Medicine.id, Medicine.name)
            .having(stock_quantity > 0)
            .order_by(Medicine.id)
        )

        return [
            MedicineStock(
                medicine_id=row[0],
                medicine_name=row[1],
                stock_quantity=int(row[2] or 0),
                inventory_value=Decimal(str(row[3] or 0)),
                sellable_quantity=int(row[4] or 0),
                sellable_value=Decimal(str(row[5] or 0)),
                negative_batch_count=int(row[6] or 0),
            )
            for row in self.db.execute(statement)
        ]

    # ------------------------------------------------------------------
    # Stock age
    # ------------------------------------------------------------------

    def oldest_receipt_by_medicine(
        self, *, medicine_ids: list[int] | None = None
    ) -> dict[int, date]:
        """When the stock currently on the shelf was first received.

        Returns ``{medicine_id: earliest purchase_date}``. Absent means **unknown**,
        not new — see below.

        Only batches that still hold stock are considered. The question being answered
        is "how long has the money currently tied up been tied up", and a batch that
        sold out years ago is not tied up in anything.

        ``MIN`` because a batch can appear on more than one purchase line, and the
        earliest receipt is when that capital first went out of the door.

        WHY NOT ``batches.created_at``
        ------------------------------
        Because it lies here. Every in-stock batch in the production database was
        written by the same seeding run, so ``created_at`` puts all 238 of them in one
        30-90 day band that has nothing to do with when stock actually arrived. A
        metric built on it would be confident and wrong. ``purchases.purchase_date``
        is a real business date entered per delivery.

        The cost is honesty about coverage: ``purchase_items.batch_id`` is nullable,
        so a batch received before purchase tracking existed has no receipt line and
        no age. Those medicines are **absent from this mapping** and the service
        reports their age as ``None`` rather than guessing zero.

        Table       purchase_items
        Join        purchases ON purchases.id = purchase_items.purchase_id
                    batches   ON batches.id   = purchase_items.batch_id
        Filter      batches.quantity > 0, medicine_ids when given
        Aggregation MIN(purchases.purchase_date) GROUP BY medicine_id
        Index       ix_purchase_items_purchase_id, ix_purchase_items_medicine_id
                    (batch_id is unindexed — see the module docstring)
        """

        statement: Select = (
            Select(PurchaseItem.medicine_id, func.min(Purchase.purchase_date))
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .join(Batch, Batch.id == PurchaseItem.batch_id)
            .where(Batch.quantity > 0)
            .group_by(PurchaseItem.medicine_id)
        )

        if medicine_ids:
            statement = statement.where(PurchaseItem.medicine_id.in_(medicine_ids))

        return {
            row[0]: row[1] for row in self.db.execute(statement) if row[1] is not None
        }

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def count_medicines(self) -> int:
        """How many medicines exist, stocked or not.

        Exists so the report can say how many medicines it left out instead of
        quietly presenting a filtered list as the whole catalogue.
        """

        return int(self.db.scalar(Select(func.count(Medicine.id))) or 0)
