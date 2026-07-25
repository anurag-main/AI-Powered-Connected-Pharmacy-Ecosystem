"""SQLAlchemy ORM model for the purchase_items table — the PURCHASE INVOICE LINES.

One row per medicine on a purchase invoice. This is where the pharmacy's COST
BASIS is recorded per stock-in: `unit_cost` is FROZEN at purchase time so that,
even if a later purchase of the same medicine comes in cheaper/dearer, this row
still reflects what was actually paid. That frozen cost is what gross-profit and
margin reports subtract from sale revenue.

Links into EXISTING tables (medicines, batches) use ONE-DIRECTIONAL relationships
(same technique as ReorderRequest.medicine) so no existing model file changes.
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.medicine import Medicine
    from app.models.purchase import Purchase


class PurchaseItem(Base):
    """One line on a purchase invoice — one medicine bought in one batch."""

    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # FK -> purchases.id. CASCADE — deleting the invoice deletes its lines
    # (a line is meaningless without its header). Mirrors sale_items.sale_id.
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id", ondelete="CASCADE"),
        nullable=False,
    )

    # FK -> medicines.id. RESTRICT — can't delete a medicine that has purchase
    # history (audit trail).
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # FK -> batches.id. OPTIONAL: links this line to the batch it created, when
    # known. Nullable because a purchase may be recorded before its batch row is
    # created (or for legacy imports). RESTRICT preserves the link's integrity.
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(nullable=False)

    # FROZEN cost per unit at purchase time. STORED, not derived — this is the
    # authoritative cost basis for profit math. Numeric(10,2), never FLOAT.
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # FROZEN line total = unit_cost * quantity at purchase time. Stored (slight
    # denormalization) so purchase valuation never recomputes it. Same rationale
    # as sale_items.line_total.
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # "all lines of purchase X"        -> ix_purchase_items_purchase_id
        Index("ix_purchase_items_purchase_id", "purchase_id"),
        # "all purchases of medicine Y"    -> ix_purchase_items_medicine_id
        Index("ix_purchase_items_medicine_id", "medicine_id"),
        # DB-level guard: a purchased quantity must be positive. MySQL 8 enforces
        # CHECK constraints. Defense-in-depth beyond app validation.
        CheckConstraint("quantity > 0", name="ck_purchase_items_qty_positive"),
    )

    # NEW <-> NEW: bidirectional back to the header.
    purchase: Mapped["Purchase"] = relationship(back_populates="items")

    # Links into EXISTING tables: one-directional (no back_populates) so
    # medicines.py and batch.py stay untouched.
    medicine: Mapped["Medicine"] = relationship("Medicine")
    batch: Mapped["Batch | None"] = relationship("Batch")

    def __repr__(self) -> str:
        return (
            f"<PurchaseItem id={self.id} purchase_id={self.purchase_id} "
            f"medicine_id={self.medicine_id} qty={self.quantity} "
            f"line_total={self.line_total}>"
        )
