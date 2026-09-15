"""Storage layer for the Customer domain (M6.1).

Thin by design. Consent is two timestamp columns on an existing table, so there
is no aggregate to assemble and no join to get right -- the interesting logic is
the state derivation in CustomerService, which is pure and therefore testable
without a database at all.

Writes are committed by the SERVICE, not here, matching the boundary the goods
receipt repository established. Consent changes are single-row updates today,
but the eligibility work in M6.2 will want to record a consent change alongside
other rows in one transaction, and a repository that commits for itself makes
that impossible.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer


class CustomerRepository:
    """SQL access for customers. Never commits."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, customer_id: int) -> Customer | None:
        """Primary-key lookup. Returns the ORM row so the service can mutate it."""
        return self.db.get(Customer, customer_id)

    def find_by_phone(self, phone: str) -> Customer | None:
        """Exact match on the canonical phone.

        Deliberately NOT normalising here: the caller must hand over an already
        canonical number. One normalisation point (app/core/phone.py, applied at
        the API boundary) is what keeps the UNIQUE index meaningful; a second one
        buried in a repository would be a place for the two to drift apart.
        """
        return self.db.scalars(select(Customer).where(Customer.phone == phone)).first()

    def list_recent(self, *, limit: int) -> list[Customer]:
        """Newest customers first, bounded."""
        stmt = select(Customer).order_by(Customer.id.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())
