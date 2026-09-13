"""Stock-on-hand for the Smart Reorder Agent, stitched to shared demand.

The reorder agent needs two facts per medicine:
  1. how much sellable stock is on hand  (this repository)
  2. how fast it has been selling lately (DemandService — shared with expiry)

Both are computed as SINGLE aggregate queries (GROUP BY), NOT one query per
medicine. This is the difference between a toy and production:

    N+1:  for each of 10,000 medicines -> run a SUM query  = 10,000 queries
    this: ONE GROUP BY over the whole table               = 1 query

Total DB cost stays 3 queries — stock, demand, medicine list — regardless of how
many medicines exist.

WHAT CHANGED, AND WHY IT MATTERS
--------------------------------
``units_sold_since(cutoff)`` used to live here and computed its own window::

    cutoff = datetime.now() - timedelta(days=30)
    WHERE sales.sold_at >= cutoff          # no upper bound at all

Three problems, all real:

* ``datetime.now()`` read the **system** clock, while the expiry agent read
  ``APP_TIMEZONE``. Two agents, two definitions of "now".
* The cutoff was a mid-afternoon timestamp, so running the report twice in one day
  measured two different windows.
* No upper bound meant a back-dated correction or a future-dated sale counted
  toward "the last 30 days".

It now calls :class:`app.services.demand_service.DemandService`, which uses
``[midnight(today - 30), midnight(today))`` in the pharmacy's timezone. Velocity may
therefore move slightly against the old numbers — that is the bug being fixed, not a
regression.

Like select_fefo(), the expiry filter below uses ``func.current_date()`` (evaluated
MySQL-side) rather than Python's ``date.today()``, so the comparison runs in the
database's own timezone.

KNOWN DEBT
----------
``get_reorder_candidates`` is not really repository work — it loops, defaults and
stitches, which is service logic that has always lived here. Left in place because
moving it would change the reorder node's contract for no gain in this step.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.services.demand_service import DemandService, DemandWindow

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

    def get_reorder_candidates(
        self,
        window_days: int = VELOCITY_WINDOW_DAYS,
        exclude_ids: set[int] | None = None,
    ) -> list[dict]:
        """Raw numbers per medicine for the reorder agent to reason over.

        Stitches stock with shared demand across the full medicine list. Every
        medicine appears exactly once; the ``.get(..., 0)`` defaults turn "no
        batches" into stock 0 and "no recent sales" into velocity 0.0 — which is
        what sends a never-sold medicine to the LLM judgment node rather than into
        a divide-by-zero.

        Returns one dict per medicine:
            {"medicine_id": int, "name": str,
             "current_stock": int, "daily_velocity": float,
             "days_since_added": int}
        """
        window = DemandWindow.trailing(lookback_days=window_days)
        stock = self.stock_on_hand_by_medicine()
        velocity = DemandService(self._db).daily_velocity(window)

        # Age of the product record, NOT a demand figure — it keeps its own
        # wall-clock reading. Measuring it from the window's midnight boundary
        # would make a medicine added this morning come out at -1 days old.
        now = datetime.now()

        candidates: list[dict] = []
        for medicine in self._db.scalars(select(Medicine)).all():
            candidates.append({
                "medicine_id": medicine.id,
                "name": medicine.name,
                "current_stock": stock.get(medicine.id, 0),
                "daily_velocity": velocity.get(medicine.id, 0.0),
                "days_since_added": (now - medicine.created_at).days,
            })
        if exclude_ids:
            candidates = [c for c in candidates if c["medicine_id"] not in exclude_ids]
        return candidates
