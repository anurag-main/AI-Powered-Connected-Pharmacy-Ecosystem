"""SQL-backed repository for reorder_requests (the approve write-path).

Two methods: find an existing pending request (for idempotency) and create a new
one. Separate from SQLAlchemyReorderRepository, which is read-only analytics —
this one WRITES.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reorder_request import ReorderRequest


class SQLAlchemyReorderRequestRepository:
    """Create + look up approved reorder requests."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def find_pending(self, medicine_id: int) -> ReorderRequest | None:
        """The open ('pending') request for this medicine, if one already exists.

        Powers idempotency: approving the same medicine twice must not create two
        rows. Uses the (medicine_id, status) index → a single seek.
        """
        stmt = (
            select(ReorderRequest)
            .where(ReorderRequest.medicine_id == medicine_id)
            .where(ReorderRequest.status == "pending")
            .limit(1)
        )
        return self._db.scalars(stmt).first()

    def create(
        self, *, medicine_id: int, quantity: int, source: str, reason: str | None
    ) -> ReorderRequest:
        """Insert a new pending reorder request and return it."""
        row = ReorderRequest(
            medicine_id=medicine_id,
            quantity=quantity,
            source=source,
            reason=reason,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row
    
    def pending_medicine_ids(self) -> set[int]:
        """Return medicine_ids that already have a 'pending' reorder request.

        Used by fetch_candidates to skip medicines the pharmacist already approved.
        """
        stmt = select(ReorderRequest.medicine_id).where(
            ReorderRequest.status == "pending"
        )
        return set(self._db.scalars(stmt).all())
