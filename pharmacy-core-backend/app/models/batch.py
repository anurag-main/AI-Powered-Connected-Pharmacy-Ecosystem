"""SQLAlchemy ORM model for the batches table.

A Batch is a physical box of a medicine with a unique batch number,
expiry date, remaining quantity, and an INTERNAL cost_price (never exposed in API).

One Medicine has many Batches — modeled as a 1:N relationship.
FEFO (First-Expiry-First-Out) selection is implemented in
SQLAlchemyBatchRepository.select_fefo() using a composite index for speed.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Imported only for type hints — avoids circular import at runtime.
    from app.models.medicine import Medicine


class Batch(Base):
    """One supplier-delivery batch of a medicine (one row per box-with-batch-number)."""

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # FK to medicines.id. ON DELETE RESTRICT = can't delete a medicine that has batches
    # (you must clear batches first; pharma practice rarely deletes medicines anyway).
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="RESTRICT"),
        nullable=False,
    )

    batch_number: Mapped[str] = mapped_column(String(50), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)

    # INTERNAL — never appears in any Pydantic schema sent to a client.
    # Used for profit reporting and expiry write-off calculations.
    cost_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    # Composite index on (medicine_id, expiry_date) makes FEFO a single index seek:
    # WHERE medicine_id=? AND quantity>0 AND expiry_date>NOW() ORDER BY expiry_date ASC
    # uses this index efficiently because medicine_id is leftmost (the equality filter)
    # and expiry_date is next (range + sort).
    __table_args__ = (
        Index("ix_batches_medicine_expiry", "medicine_id", "expiry_date"),
    )

    # Back-reference so you can do `batch.medicine` after loading a batch.
    medicine: Mapped["Medicine"] = relationship(back_populates="batches")

    def __repr__(self) -> str:
        return (
            f"<Batch id={self.id} medicine_id={self.medicine_id} "
            f"batch_number={self.batch_number!r} qty={self.quantity} "
            f"exp={self.expiry_date}>"
        )
