"""SQLAlchemy ORM model for the sales table — the INVOICE HEADER.

One row per checkout. Holds totals and the link to the customer (optional).
Line items live in sale_items via a 1:N relationship.

This is the "header" half of the classic header + lines pattern used in
orders, invoices, receipts, journal entries — anywhere a single transaction
has multiple line items.
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.sale_item import SaleItem


class Sale(Base):
    """Invoice header — one row per checkout."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # FK → customers.id. NULLable for walk-in sales without captured customer info.
    # ON DELETE SET NULL — if a customer is ever deleted, the sale row remains
    # but loses its customer link (audit trail preserved).
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Pre-computed total = sum(sale_items.line_total).
    # Stored (denormalized) on the header so report queries don't re-aggregate
    # millions of line rows every time.
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # When the sale physically happened. Defaults to NOW(); can be back-dated.
    sold_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Indexes for the two most common report queries:
    #   - "all sales for customer X"      → ix_sales_customer_id
    #   - "all sales between dates Y..Z"  → ix_sales_sold_at
    __table_args__ = (
        Index("ix_sales_customer_id", "customer_id"),
        Index("ix_sales_sold_at", "sold_at"),
    )

    customer: Mapped["Customer | None"] = relationship(back_populates="sales")

    # cascade="all, delete-orphan" — deleting a Sale via ORM auto-deletes its
    # SaleItems. Combined with ON DELETE CASCADE on the FK below = defense in depth.
    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Sale id={self.id} customer_id={self.customer_id} "
            f"total={self.total_amount}>"
        )
