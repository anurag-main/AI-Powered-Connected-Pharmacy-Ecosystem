"""SQLAlchemy ORM model for the sale_items table — the INVOICE LINES.

One row per medicine sold within a Sale. The "lines" half of the
header + lines pattern.

Critically, this is where we FREEZE the price at sale time: `unit_price`
and `line_total` are STORED, not recomputed on read. If Medicine.mrp
changes tomorrow, this row still reflects what the customer actually paid.
That's the audit-trail property tax law requires.
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.sale import Sale


class SaleItem(Base):
    """One line on an invoice — one medicine sold from one batch."""

    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # FK → sales.id. ON DELETE CASCADE — killing the sale auto-deletes its lines
    # (the lines have no meaning without their header).
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
    )

    # FK → medicines.id. ON DELETE RESTRICT — can't delete a medicine that has
    # sale history (preserves audit trail).
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # FK → batches.id. ON DELETE RESTRICT — same audit reason for batches.
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(nullable=False)

    # FROZEN PRICE — what was actually charged per unit at the moment of sale.
    # STORED, not computed on read. If Medicine.mrp changes tomorrow this row
    # still reads the historic price. Tax audit requires this.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # FROZEN line total = unit_price * quantity at sale time. Also stored
    # (not computed) for the same audit-trail reason. Slight denormalization;
    # huge stability win.
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    # Indexes for the two most common joins:
    #   - "all items for sale X"        → ix_sale_items_sale_id
    #   - "all sales of medicine Y"     → ix_sale_items_medicine_id
    __table_args__ = (
        Index("ix_sale_items_sale_id", "sale_id"),
        Index("ix_sale_items_medicine_id", "medicine_id"),
    )

    sale: Mapped["Sale"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return (
            f"<SaleItem id={self.id} sale_id={self.sale_id} "
            f"medicine_id={self.medicine_id} qty={self.quantity} "
            f"line_total={self.line_total}>"
        )
