"""Database access for expiry-risk analysis. SQL only — no risk logic lives here.

Two questions, deliberately separate:

    batches_in_window()   which batches exist, with how much stock, expiring when
    recent_demand()       how many units of each medicine sold recently

They are separate because they aggregate at different grains. Stock is **per batch**;
demand is **per medicine** — a customer asks for "Crocin", and FEFO decides which
batch it comes out of. Joining them in one query would force a choice between
duplicating demand across a medicine's batches or dividing it arbitrarily, and both
are wrong. The service allocates demand across batches in FEFO order instead, which
is what actually happens at the counter.

The `ix_batches_medicine_expiry` index already covers the batch scan, and
`ix_sale_items_medicine_id` plus `ix_sales_sold_at` cover the demand aggregate, so no
new index is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import Select, func
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.sale import Sale
from app.models.sale_item import SaleItem


@dataclass(frozen=True)
class BatchStock:
    """One batch's raw facts, straight from the database."""

    batch_id: int
    batch_number: str
    medicine_id: int
    medicine_name: str
    expiry_date: date
    quantity: int
    cost_price: Decimal


class ExpiryRepository:
    """Reads the stock and sales facts the expiry-risk calculation needs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Stock
    # ------------------------------------------------------------------

    def batches_in_window(
        self,
        *,
        as_of: date,
        window_days: int,
        include_expired: bool = True,
        medicine_id: int | None = None,
    ) -> list[BatchStock]:
        """Batches expiring on or before ``as_of + window_days``.

        Ordered by ``(medicine_id, expiry_date, batch_id)`` — FEFO order within each
        medicine, which is the order the service must walk to allocate demand. The
        ``batch_id`` tiebreak makes the ordering total, so two batches sharing an
        expiry date always come back the same way and a ranking cannot flap between
        runs.

        Zero-quantity batches are excluded: nothing is at risk if there is nothing on
        the shelf. Batches with *negative* quantity are kept — the column has no CHECK
        constraint, so bad data is reachable, and hiding it would hide the bug.
        """

        cutoff = as_of + timedelta(days=window_days)

        statement: Select = (
            Select(
                Batch.id,
                Batch.batch_number,
                Batch.medicine_id,
                Medicine.name,
                Batch.expiry_date,
                Batch.quantity,
                Batch.cost_price,
            )
            .join(Medicine, Medicine.id == Batch.medicine_id)
            .where(Batch.expiry_date <= cutoff)
            .where(Batch.quantity != 0)
            .order_by(Batch.medicine_id, Batch.expiry_date, Batch.id)
        )

        if not include_expired:
            statement = statement.where(Batch.expiry_date >= as_of)

        if medicine_id is not None:
            statement = statement.where(Batch.medicine_id == medicine_id)

        return [
            BatchStock(
                batch_id=row[0],
                batch_number=row[1],
                medicine_id=row[2],
                medicine_name=row[3],
                expiry_date=row[4],
                quantity=row[5],
                cost_price=row[6],
            )
            for row in self.db.execute(statement)
        ]

    # ------------------------------------------------------------------
    # Demand
    # ------------------------------------------------------------------

    def recent_demand(
        self,
        *,
        as_of: date,
        lookback_days: int,
        medicine_ids: list[int] | None = None,
    ) -> dict[int, int]:
        """Units sold per medicine over the lookback window.

        Returns ``{medicine_id: units}``. A medicine absent from the result sold
        nothing — the service distinguishes that from "no sales history at all", since
        the two mean different things to a pharmacist.

        The window is ``[as_of - lookback_days, as_of)``: it ends at midnight today so
        a partial day cannot drag the daily average down.
        """

        start = datetime.combine(as_of - timedelta(days=lookback_days), time.min)
        end = datetime.combine(as_of, time.min)

        statement: Select = (
            Select(
                SaleItem.medicine_id,
                func.coalesce(func.sum(SaleItem.quantity), 0),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(Sale.sold_at >= start)
            .where(Sale.sold_at < end)
            .group_by(SaleItem.medicine_id)
        )

        if medicine_ids:
            statement = statement.where(SaleItem.medicine_id.in_(medicine_ids))

        return {row[0]: int(row[1] or 0) for row in self.db.execute(statement)}

    def medicines_with_any_sales(self, medicine_ids: list[int]) -> set[int]:
        """Which of these medicines have EVER been sold.

        Distinguishes "sold nothing lately" from "never sold at all". The first is a
        slow mover; the second is a new product with no history to estimate from, and
        the report must say so rather than quietly treating zero demand as a fact.
        """

        if not medicine_ids:
            return set()

        statement = (
            Select(SaleItem.medicine_id)
            .where(SaleItem.medicine_id.in_(medicine_ids))
            .group_by(SaleItem.medicine_id)
        )

        return {row[0] for row in self.db.execute(statement)}
