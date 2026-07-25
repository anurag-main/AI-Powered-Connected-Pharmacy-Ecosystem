"""SQLAlchemy ORM model for the suppliers table.

A Supplier is a vendor the pharmacy buys stock from. Needed by the Business
Intelligence Agent to answer "which suppliers are most frequently used" and to
attribute purchase cost + purchase-returns to a real, de-duplicated entity
(instead of a free-text name that would split "Sun Pharma" from "sun pharma").

One Supplier has many Purchases (1:N). Both sides are NEW models, so this
relationship is bidirectional (back_populates) — unlike links into existing
tables, which stay one-directional so no existing file has to change.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Imported only for type hints — avoids a runtime circular import.
    from app.models.purchase import Purchase


class Supplier(Base):
    """One row per vendor the pharmacy purchases stock from."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Supplier name. UNIQUE + indexed so "group purchases by supplier" (the
    # "most frequently used" query) counts one canonical row per vendor and the
    # service layer can safely find-or-create without duplicates.
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
    )

    # Optional — the pharmacy may not record a contact number.
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

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

    # 1:N — one supplier has many purchases over time.
    purchases: Mapped[list["Purchase"]] = relationship(back_populates="supplier")

    def __repr__(self) -> str:
        return f"<Supplier id={self.id} name={self.name!r}>"
