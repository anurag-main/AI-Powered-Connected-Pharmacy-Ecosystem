"""SQL-backed repository for the Smart Reorder Agent's raw numbers.

The reorder agent needs two facts per medicine:
  1. how much sellable stock is on hand  (current_stock)
  2. how fast it has been selling lately   (for daily_velocity)

Both are computed here as SINGLE aggregate queries (GROUP BY), NOT one query
per medicine. This is the difference between a toy and production:

    ❌ N+1:  for each of 10,000 medicines -> run a SUM query  = 10,000 queries
    ✅ this: ONE GROUP BY over the whole table               = 1 query

Like select_fefo(), the expiry filter uses func.current_date() (MySQL-side)
instead of Python's date.today(), so the comparison runs in the DB's timezone
and can't skew if the app server and DB live in different zones.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.sale import Sale
from app.models.sale_item import SaleItem

# Rolling sales window that defines "how fast it leaves right now".
# NOT all-time — a medicine hot last year must not look urgent today.
VELOCITY_WINDOW_DAYS = 30


class SQLAlchemyReorderRepository:
    """Read-only analytics queries that feed the reorder agent.

    Session is injected the same way as the other repositories. This repo only
    READS (aggregates) — it never writes, so no commit() anywhere.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def stock_on_hand_by_medicine(self) -> dict[int, int]:
        """Sellable stock per medicine: SUM(quantity) of NON-EXPIRED batches.

        Returns {medicine_id: total_qty}. A medicine with no usable batches
        simply won't be a key in the dict (caller treats missing as 0).

        Expired batches are excluded — you can't sell them, so they don't count
        as cover.
        """
        stmt = (
            select(Batch.medicine_id, func.sum(Batch.quantity))
            .where(Batch.expiry_date > func.current_date())
            .group_by(Batch.medicine_id)
        )
        return {med_id: int(total or 0) for med_id, total in self._db.execute(stmt).all()}

    def units_sold_since(self, cutoff: datetime) -> dict[int, int]:
        """Units sold per medicine since `cutoff`: SUM(SaleItem.quantity).

        Joins sale_items -> sales to filter by when the sale happened
        (Sale.sold_at >= cutoff). Returns {medicine_id: units_sold}.
        A medicine with no sales in the window won't be a key (caller -> 0).

        Pass a rolling cutoff (e.g. now - 30 days) so demand is RECENT, not
        all-time — a medicine that was hot last year shouldn't look urgent now.
        """
        stmt = (
            select(SaleItem.medicine_id, func.sum(SaleItem.quantity))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(Sale.sold_at >= cutoff)
            .group_by(SaleItem.medicine_id)
        )
        return {med_id: int(total or 0) for med_id, total in self._db.execute(stmt).all()}

    def get_reorder_candidates(self, window_days: int = VELOCITY_WINDOW_DAYS) -> list[dict]:
        """Raw numbers per medicine for the reorder agent to reason over.

        Stitches the two aggregate queries above together with the full medicine
        list. Every medicine appears exactly once; the .get(..., 0) defaults turn
        "no batches" into stock 0 and "no recent sales" into velocity 0.0.

        Returns one dict per medicine:
            {"medicine_id": int, "name": str,
             "current_stock": int, "daily_velocity": float}

        Total DB cost = 3 queries (stock + sold + medicine list), regardless of
        how many medicines exist — NOT one query per medicine.
        """
        cutoff = datetime.now() - timedelta(days=window_days)
        stock = self.stock_on_hand_by_medicine()
        sold = self.units_sold_since(cutoff)

        candidates: list[dict] = []
        for medicine in self._db.scalars(select(Medicine)).all():
            units_sold = sold.get(medicine.id, 0)
            candidates.append({
                "medicine_id": medicine.id,
                "name": medicine.name,
                "current_stock": stock.get(medicine.id, 0),
                "daily_velocity": units_sold / window_days,
            })
        return candidates
