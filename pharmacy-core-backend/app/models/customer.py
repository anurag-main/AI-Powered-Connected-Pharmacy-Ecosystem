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

    # ---------------- WhatsApp consent (M6.1) ----------------
    #
    # Consent is stored as two TIMESTAMPS rather than one boolean, and the state
    # is derived by comparing them. A boolean cannot answer "when did they agree"
    # or "did they opt back in after opting out", and under India's DPDP Act the
    # pharmacy has to be able to show WHEN consent was given for WHAT.
    #
    # Derived state (see CustomerService.consent_state):
    #   both NULL                         -> not_set     (never asked)
    #   opt_in newer than opt_out         -> opted_in
    #   opt_out newer than or equal opt_in-> opted_out
    #
    # Re-opt-in therefore needs no extra column and no row deletion: a newer
    # opt_in timestamp simply wins. Nothing is ever erased, so the history of
    # who agreed and who withdrew stays auditable.
    whatsapp_opt_in_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    whatsapp_opt_out_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Free text, optional -- "asked to stop", "wrong number", or whatever the
    # customer actually said. Not an enum: the point of this column is to record
    # a human reason we did not anticipate, and an enum would force the pharmacy
    # to file every complaint under "other".
    whatsapp_opt_out_reason: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    # WHERE the consent was captured -- "billing_counter", "staff", "import".
    # Kept because DPDP consent must be demonstrably informed, and "we have a
    # timestamp" is a weaker answer than "it was taken at the counter".
    #
    # There is deliberately NO consent_version column yet. Versioning records
    # WHICH wording someone agreed to, and in M6.1 no wording exists: nothing is
    # sent, and no message template has been written or approved. A version
    # column now would store a fiction. It lands in M6.3 with the real template.
    whatsapp_consent_source: Mapped[str | None] = mapped_column(
        String(30), nullable=True
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
