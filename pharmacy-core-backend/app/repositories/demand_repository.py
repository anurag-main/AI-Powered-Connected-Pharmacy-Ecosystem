"""SQL for sales demand. One place, so every agent counts the same units.

Nothing here interprets a number. It sums, it groups, it returns. The window
boundaries arrive as concrete datetimes because deciding what "the last 90 days"
means is a business rule, and business rules do not belong in a repository —
:class:`app.services.demand_service.DemandWindow` owns that.

Every query aggregates in SQL. The alternative — pulling sale lines into Python and
summing them there — moves 1,818 rows over the wire on today's data and grows with
the shop. The existing indexes carry all three queries:

    ix_sale_items_medicine_id   the medicine filter and the GROUP BY
    ix_sales_sold_at            the date range on the join's other side
    ix_sale_items_sale_id       the join itself

No index is added. None is needed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func
from sqlalchemy.orm import Session

from app.models.sale import Sale
from app.models.sale_item import SaleItem


class DemandRepository:
    """Read-only aggregates over ``sales`` and ``sale_items``. Never writes."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def units_sold_by_medicine(
        self,
        *,
        start: datetime,
        end: datetime,
        medicine_ids: list[int] | None = None,
    ) -> dict[int, int]:
        """Units sold per medicine in ``[start, end)``.

        Returns ``{medicine_id: units}``. A medicine that sold nothing is **absent**
        rather than present with a zero, because the two mean different things to a
        caller: "sold nothing in this window" is a fact about the window, and the
        caller may want to ask separately whether the medicine has ever sold at all.

        ``medicine_ids=None`` or an empty list means every medicine. That is the
        behaviour ``ExpiryRepository.recent_demand`` has always had, and changing it
        here would silently change the expiry report.

        Table       sale_items
        Join        sales ON sales.id = sale_items.sale_id   (ix_sale_items_sale_id)
        Filter      sales.sold_at >= start AND < end         (ix_sales_sold_at)
        Aggregation SUM(sale_items.quantity) GROUP BY medicine_id
        Index       ix_sale_items_medicine_id when the id filter is supplied
        """

        statement: Select = (
            Select(
                SaleItem.medicine_id,
                func.coalesce(func.sum(SaleItem.quantity), 0),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(Sale.sold_at >= start)
            .where(Sale.sold_at < end)
            .group_by(SaleItem.medicine_id)
        )

        if medicine_ids:
            statement = statement.where(SaleItem.medicine_id.in_(medicine_ids))

        return {row[0]: int(row[1] or 0) for row in self.db.execute(statement)}

    def last_sale_at_by_medicine(
        self, *, medicine_ids: list[int] | None = None
    ) -> dict[int, datetime]:
        """The most recent ``sold_at`` per medicine, over all time.

        Deliberately unbounded: the question "when did this last move?" is only
        interesting when the answer is allowed to be two years ago. Bounding it to a
        window would make a dead medicine indistinguishable from a brisk one.

        Table       sale_items
        Join        sales ON sales.id = sale_items.sale_id
        Filter      medicine_ids, when given
        Aggregation MAX(sales.sold_at) GROUP BY medicine_id
        Index       ix_sale_items_medicine_id
        """

        statement: Select = (
            Select(SaleItem.medicine_id, func.max(Sale.sold_at))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .group_by(SaleItem.medicine_id)
        )

        if medicine_ids:
            statement = statement.where(SaleItem.medicine_id.in_(medicine_ids))

        return {row[0]: row[1] for row in self.db.execute(statement) if row[1] is not None}

    def medicines_with_any_sales(self, medicine_ids: list[int]) -> set[int]:
        """Which of these medicines have EVER been sold.

        Separates "sold nothing lately" from "never sold at all". The first is a slow
        mover; the second is a product with no history to estimate from, and a report
        must say so rather than quietly treating zero demand as a measurement.

        An empty input returns an empty set without touching the database — an
        unfiltered ``IN ()`` would otherwise scan every sale line to answer a question
        about nothing.
        """

        if not medicine_ids:
            return set()

        statement = (
            Select(SaleItem.medicine_id)
            .where(SaleItem.medicine_id.in_(medicine_ids))
            .group_by(SaleItem.medicine_id)
        )

        return {row[0] for row in self.db.execute(statement)}
