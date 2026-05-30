"""SQL-backed repository for the Batch domain.

Key method: select_fefo() — picks the next batch to dispense from for a given
medicine, applying FEFO + stock + expiry filters in one indexed SQL query.

We use func.current_date() (MySQL-side) instead of date.today() (Python-side)
for the expiry filter — that way the comparison happens in MySQL's timezone,
avoiding timezone-skew bugs if the app server and DB are in different zones.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.schemas.batch import BatchOut


class SQLAlchemyBatchRepository:
    """MySQL-backed Batch repository.

    Session is injected per request via Depends(get_db), same lifecycle as
    SQLAlchemyMedicineRepository.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def add(
        self,
        *,
        medicine_id: int,
        batch_number: str,
        expiry_date: date,
        quantity: int,
        cost_price: Decimal,
    ) -> BatchOut:
        """Insert a new batch row."""
        batch = Batch(
            medicine_id=medicine_id,
            batch_number=batch_number,
            expiry_date=expiry_date,
            quantity=quantity,
            cost_price=cost_price,
        )
        self._db.add(batch)
        self._db.commit()
        self._db.refresh(batch)
        return BatchOut.model_validate(batch)

    def get_by_id(self, batch_id: int) -> BatchOut | None:
        """O(1) lookup by primary key. None if no batch with that id."""
        orm = self._db.get(Batch, batch_id)
        return BatchOut.model_validate(orm) if orm is not None else None

    def list_for_medicine(self, medicine_id: int) -> list[BatchOut]:
        """Every batch of this medicine, ordered by expiry (FEFO-ish view)."""
        stmt = (
            select(Batch)
            .where(Batch.medicine_id == medicine_id)
            .order_by(Batch.expiry_date.asc())
        )
        rows = self._db.scalars(stmt).all()
        return [BatchOut.model_validate(row) for row in rows]

    def select_fefo(self, medicine_id: int) -> BatchOut | None:
        """First-Expiry-First-Out: next batch to dispense from.

        Returns the soonest-expiring batch of the given medicine that satisfies:
          - quantity > 0   (has stock to sell)
          - expiry_date > current DB date  (not yet expired)

        None if every batch is empty or expired.

        Uses the composite (medicine_id, expiry_date) index → single index seek
        even at millions of rows.
        """
        stmt = (
            select(Batch)
            .where(Batch.medicine_id == medicine_id)
            .where(Batch.quantity > 0)
            .where(Batch.expiry_date > func.current_date())
            .order_by(Batch.expiry_date.asc())
            .limit(1)
        )
        orm = self._db.scalars(stmt).first()
        return BatchOut.model_validate(orm) if orm is not None else None
