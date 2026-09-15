"""Storage layer for Refill Intelligence (M6.2).

WHY THIS IS ITS OWN REPOSITORY
------------------------------
The query it runs joins sales, sale_items, medicines and customers, so it could
plausibly have been bolted onto any of three existing repositories. It is not,
because it belongs to none of them: "the purchase history relevant to refills" is
a refill concept, and putting it in ``sales_repository`` would mean the sales
domain grows a method only the refill domain understands.

WHAT IT DOES NOT DO
-------------------
No refill logic lives here. It fetches rows; ``RefillService`` decides what they
mean. That split is what lets every rule in the engine be unit-tested against
plain objects with no database at all.

WHY THERE IS NO refill_schedules TABLE
--------------------------------------
M6.2 derives candidates from sales instead of persisting them. The reasoning is
in ``docs/features/refill_intelligence.md`` §M6.2, but the short version is that
a stored schedule goes stale the moment the customer buys again, so it would need
invalidating on every sale -- a second write path, and a source of drift from the
sales data that is already the truth. Deriving keeps one source of truth, and a
pure query is idempotent by definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.sale import Sale
from app.models.sale_item import SaleItem


@dataclass(frozen=True)
class PurchaseRecord:
    """One dispensed line, flattened to exactly what the engine needs.

    A frozen dataclass rather than ORM rows so the service can be unit-tested by
    constructing these directly -- no session, no fixtures, no database.
    """

    customer_id: int
    customer_name: str | None
    customer_phone: str
    medicine_id: int
    medicine_name: str
    sale_id: int
    sale_item_id: int
    purchased_on: date
    days_supply: int | None


class RefillRepository:
    """Read-only access to the purchase history refills are computed from."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def purchases_for_refill(
        self, *, as_of: date, lookback_days: int
    ) -> list[PurchaseRecord]:
        """Every identified purchase in the window, oldest first.

        ``customer_id IS NOT NULL`` is the first filter and it is doing real
        work: roughly 38% of this shop's sales are anonymous walk-ins, and a
        refill reminder needs somebody to remind.

        The window is bounded because an unbounded scan gets slower every day the
        shop stays open. ``lookback_days`` must comfortably exceed the longest
        plausible ``days_supply`` (365) or a long course would fall out of the
        window mid-treatment and silently stop producing candidates.

        Ordered oldest-first because the engine walks purchases chronologically
        to build coverage, and doing the sort in SQL keeps the index doing the
        work instead of Python.
        """
        window_start = datetime.combine(as_of - timedelta(days=lookback_days), time.min)
        # Half-open upper bound: everything up to the END of `as_of`. Using
        # `<= as_of 00:00` would drop every sale made today, which is the classic
        # off-by-one-day reporting bug this codebase already avoids elsewhere.
        window_end = datetime.combine(as_of + timedelta(days=1), time.min)

        stmt = (
            select(
                Customer.id,
                Customer.name,
                Customer.phone,
                Medicine.id,
                Medicine.name,
                Sale.id,
                SaleItem.id,
                Sale.sold_at,
                SaleItem.days_supply,
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Customer, Customer.id == Sale.customer_id)
            .join(Medicine, Medicine.id == SaleItem.medicine_id)
            .where(
                Sale.customer_id.is_not(None),
                Sale.sold_at >= window_start,
                Sale.sold_at < window_end,
            )
            .order_by(Sale.sold_at, SaleItem.id)
        )

        return [
            PurchaseRecord(
                customer_id=row[0],
                customer_name=row[1],
                customer_phone=row[2],
                medicine_id=row[3],
                medicine_name=row[4],
                sale_id=row[5],
                sale_item_id=row[6],
                # sold_at is a naive local datetime (the app and the database
                # share a timezone). Taking .date() therefore gives the calendar
                # day the pharmacist would recognise -- an 11:30 PM sale belongs
                # to that day, not to the next one in UTC.
                purchased_on=row[7].date(),
                days_supply=row[8],
            )
            for row in self.db.execute(stmt).all()
        ]

    def customers_by_id(self, customer_ids: set[int]) -> dict[int, Customer]:
        """Load the customer rows whose consent state the engine needs.

        One query, keyed by id. Deliberately not a lookup per candidate: a shop
        with 200 due customers would otherwise issue 200 round trips, which is
        the easiest performance bug in this codebase to introduce by accident.

        Returns ORM rows rather than a projection because ``is_contactable()``
        in the customer domain takes a customer, and re-implementing its rules
        against a tuple here would be exactly the duplication M6.2 was told to
        avoid.
        """
        if not customer_ids:
            return {}
        stmt = select(Customer).where(Customer.id.in_(customer_ids))
        return {row.id: row for row in self.db.scalars(stmt).all()}
