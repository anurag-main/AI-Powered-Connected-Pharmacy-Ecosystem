"""SQLAlchemy ORM model for the medicines table.

DB-shaped twin of app/schemas/medicine.py (the HTTP-shaped Pydantic schemas).
Different responsibilities:
- Schemas validate JSON in/out of the API.
- This ORM model maps Python ↔ MySQL rows.
- The service layer is the only place that converts between them.
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Imported only for type hints — avoids a runtime circular import.
    from app.models.batch import Batch


class Medicine(Base):
    """Catalog entry — one row per unique medicine (e.g. "Crocin 500mg").

    The table-level constraints (UNIQUE on normalized_name, index on it) are
    declared inline on the column. Alembic translates them into the migration
    `CREATE TABLE` statement in step 2.4.
    """

    __tablename__ = "medicines"

    # Primary key. autoincrement=True is the default in MySQL for int PKs,
    # but we set it explicitly so the intent is obvious to readers.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # The brand name as the user typed it ("Crocin 500mg"). Max 200 chars.
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # The canonical form ("crocin 500mg") used for duplicate detection.
    # UNIQUE constraint = DB-level guarantee no two medicines share this value.
    # index=True = fast O(log n) lookup by normalized_name.
    normalized_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
    )

    # Maximum Retail Price. DECIMAL(10, 2) = up to 99,999,999.99 rupees, 2 decimals.
    # NEVER use FLOAT for money — it can't represent 0.1 exactly (binary float trap).
    mrp: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Indian GST HSN code (always exactly 8 chars for pharmaceuticals: "30049099").
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=False)

    # Optional. `Mapped[str | None]` + `nullable=True` is the 2.0 idiom.
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Server-stamped audit timestamps.
    # server_default=func.now() means MySQL fills it in, not Python — survives clock skew.
    # onupdate=func.now() on updated_at means MySQL updates it whenever the row changes.
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

    # 1:N relationship — lets you access medicine.batches as a list of Batch objects.
    # `back_populates` pairs with Batch.medicine to keep both sides in sync.
    # `cascade='all'` means if you delete a Medicine in Python, SQLAlchemy will
    # try to delete its batches first (the DB-level ON DELETE RESTRICT still applies
    # if you skip the ORM cascade — defense in depth).
    batches: Mapped[list["Batch"]] = relationship(
        back_populates="medicine",
        cascade="all",
    )

    def __repr__(self) -> str:
        return f"<Medicine id={self.id} name={self.name!r}>"
