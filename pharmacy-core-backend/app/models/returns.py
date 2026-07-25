"""SQLAlchemy ORM model for the returns table — BOTH return kinds in one table.

The Business Intelligence Agent needs return trends. In a pharmacy there are two
distinct kinds of return, and you chose to model BOTH:
  - "sales"    : customer -> pharmacy (a refund; reduces net revenue)
  - "purchase" : pharmacy -> supplier (expired/damaged stock sent back)

They share most columns (what medicine, how many, how much, when), so they live
in ONE table with a `return_type` discriminator plus a type-specific FK:
  - sales-return    sets sale_id      (which sale it came from)
  - purchase-return sets supplier_id  (which vendor it went back to)

A CHECK constraint enforces that exactly the RIGHT FK is populated for each type,
so the table can never hold a nonsensical half-populated row.

FILE NAME: this module is `returns.py`, not `return.py`, because `return` is a
Python keyword — `from app.models.return import Return` would be a syntax error.

All FKs point at existing tables (medicines, batches, sales) or the new suppliers
table via ONE-DIRECTIONAL relationships, so no existing model file changes.

Computed, NOT stored: return rate (returns / sales), expiry-driven return loss,
and period trends are all SQL aggregates over these rows.
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
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.medicine import Medicine
    from app.models.sale import Sale
    from app.models.supplier import Supplier


class Return(Base):
    """One returned-goods event — either a sales-return or a purchase-return."""

    __tablename__ = "returns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Discriminator: 'sales' or 'purchase'. Indexed because trend queries almost
    # always filter/group by the kind of return. A CHECK below restricts values.
    return_type: Mapped[str] = mapped_column(String(10), nullable=False)

    # What was returned. RESTRICT preserves history (can't delete a medicine that
    # has return records). Required for every return.
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # OPTIONAL: which specific batch, when known (drives expiry-loss attribution).
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Type-specific link — SALES return: the originating sale.
    # RESTRICT (not SET NULL): MySQL forbids a column that has a SET NULL/CASCADE
    # referential action from ALSO appearing in a CHECK constraint (error 3823),
    # and sale_id is referenced by ck_returns_type_fk_consistency below. RESTRICT
    # is allowed in a CHECK and matches the audit-preserving policy used on the
    # other historical FKs (you don't delete sales in a pharmacy anyway).
    # Nullable because purchase-returns leave this empty.
    sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Type-specific link — PURCHASE return: the vendor it went back to.
    # RESTRICT preserves supplier history. Nullable because sales-returns leave
    # this empty.
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(nullable=False)

    # Money value of the return: refund amount (sales) or cost recovered
    # (purchase). Numeric(10,2), never FLOAT.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Optional free-text reason ("expired", "wrong medicine", "damaged").
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # When the return happened. Indexed for time-range trend queries; defaults to
    # NOW() but can be back-dated.
    returned_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_returns_return_type", "return_type"),
        Index("ix_returns_medicine_id", "medicine_id"),
        Index("ix_returns_returned_at", "returned_at"),
        # Only the two valid discriminator values are allowed.
        CheckConstraint(
            "return_type IN ('sales', 'purchase')",
            name="ck_returns_type_valid",
        ),
        # Positive quantity.
        CheckConstraint("quantity > 0", name="ck_returns_qty_positive"),
        # Integrity of the "both kinds in one table" design: a sales-return MUST
        # carry sale_id and NOT supplier_id; a purchase-return the reverse. This
        # makes a malformed row impossible at the DB level.
        CheckConstraint(
            "(return_type = 'sales' AND sale_id IS NOT NULL AND supplier_id IS NULL) "
            "OR (return_type = 'purchase' AND supplier_id IS NOT NULL AND sale_id IS NULL)",
            name="ck_returns_type_fk_consistency",
        ),
    )

    # All one-directional (no back_populates) so no existing file — and not even
    # the new Supplier/Sale — needs a reverse `returns` collection.
    medicine: Mapped["Medicine"] = relationship("Medicine")
    batch: Mapped["Batch | None"] = relationship("Batch")
    sale: Mapped["Sale | None"] = relationship("Sale")
    supplier: Mapped["Supplier | None"] = relationship("Supplier")

    def __repr__(self) -> str:
        return (
            f"<Return id={self.id} type={self.return_type!r} "
            f"medicine_id={self.medicine_id} qty={self.quantity} "
            f"amount={self.amount}>"
        )
