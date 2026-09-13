"""Database access for expiry-risk analysis. SQL only — no risk logic lives here.

This repository answers exactly one question: **which batches exist, with how much
stock, expiring when.**

The other half of the calculation — how fast each medicine sells — used to live here
too, in ``recent_demand()``. It moved to
:class:`app.services.demand_service.DemandService`, because the reorder agent was
asking the same question through a different query with a different window, and the
two could disagree about one medicine on one day. There is now one definition.

Stock and demand were always separate queries, and that stays true for a reason worth
restating: they aggregate at different grains. Stock is **per batch**; demand is **per
medicine** — a customer asks for "Crocin", and FEFO decides which batch it comes out
of. Joining them would force a choice between duplicating demand across a medicine's
batches or dividing it arbitrarily, and both are wrong. The service allocates demand
across batches in FEFO order instead, which is what actually happens at the counter.

The ``ix_batches_medicine_expiry`` index already covers the batch scan, so no new
index is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.medicine import Medicine


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
    """Reads the batch-level stock facts the expiry-risk calculation needs."""

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
