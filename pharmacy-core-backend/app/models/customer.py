"""SQLAlchemy ORM model for the customers table.

A Customer is a known walk-in or repeat patient at the pharmacy. Phone is
the natural identifier — one phone number = one customer row. We put a
UNIQUE index on phone so the service layer can safely "find or create"
without worrying about duplicates.

Walk-in customers whose details weren't captured are NOT a row here —
those sales have sales.customer_id = NULL.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Imported only for type hints — prevents a runtime circular import.
    from app.models.sale import Sale


class Customer(Base):
    """One row per known pharmacy customer (identified by phone)."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Optional — pharmacist may know only the phone number.
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # 10-digit phone (digits only; the extract_intent prompt strips +91/spaces/dashes).
    # UNIQUE + indexed: phone is the natural key — find-or-create relies on this.
    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
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

    # 1:N — one customer has many sales over time.
    sales: Mapped[list["Sale"]] = relationship(back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer id={self.id} phone={self.phone!r}>"
