"""SQLAlchemy ORM model for the purchases table — the PURCHASE INVOICE HEADER.

One row per stock-in event (a supplier invoice). This is the record the project
was missing: nothing previously captured WHEN stock arrived, from WHOM, or at
what invoice total. The Business Intelligence Agent needs it for:
  - purchase trends over time      (group by purchase_date)
  - most-frequently-used suppliers (group by supplier_id)
  - purchase valuation             (sum of total_amount over a period)

Header + lines pattern, mirroring Sale / SaleItem: the header holds supplier +
date + total; each medicine on the invoice is a PurchaseItem line.

NOTE (computed, NOT stored): purchase trend percentages, period-over-period
deltas, and average order value are SQL aggregates over these rows — never
persisted columns.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.purchase_item import PurchaseItem
    from app.models.supplier import Supplier


class Purchase(Base):
    """Purchase invoice header — one row per stock-in from a supplier."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # FK -> suppliers.id. RESTRICT: can't delete a supplier that has purchase
    # history (preserves the audit trail, same policy as sale_items.medicine_id).
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # The invoice date. A DATE (not datetime) — supplier invoices are dated by
    # day. Defaults to the DB's current date so a quick entry still gets stamped.
    # Indexed because every purchase-trend query filters/groups by this.
    # MySQL 8 requires an expression default to be parenthesized:
    # DEFAULT (CURRENT_DATE). func.current_date() renders the bare keyword
    # CURRENT_DATE (a syntax error as a column default), so use text() to emit
    # the parenthesized form explicitly.
    purchase_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        server_default=text("(CURRENT_DATE)"),
    )

    # Optional — the supplier's own invoice reference number, for reconciliation.
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Pre-computed invoice total = sum(purchase_items.line_total). Denormalized on
    # the header (like sales.total_amount) so valuation reports don't re-aggregate
    # every line. Numeric(10,2) — never FLOAT for money.
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Indexes for the two most common report filters:
    #   - "purchases from supplier X"       -> ix_purchases_supplier_id
    #   - "purchases between dates Y..Z"     -> ix_purchases_purchase_date
    __table_args__ = (
        Index("ix_purchases_supplier_id", "supplier_id"),
        Index("ix_purchases_purchase_date", "purchase_date"),
    )

    # NEW <-> NEW: bidirectional is safe (neither existing file changes).
    supplier: Mapped["Supplier"] = relationship(back_populates="purchases")

    # cascade="all, delete-orphan" — deleting a Purchase via ORM removes its
    # lines (they have no meaning without the header). Mirrors Sale.items.
    items: Mapped[list["PurchaseItem"]] = relationship(
        back_populates="purchase",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Purchase id={self.id} supplier_id={self.supplier_id} "
            f"total={self.total_amount} date={self.purchase_date}>"
        )
