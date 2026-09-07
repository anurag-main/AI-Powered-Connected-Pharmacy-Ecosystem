"""Repository for Business Intelligence queries.

The only layer that touches SQLAlchemy. It receives a validated
:class:`~app.ai.schemas.business_query.BusinessQuery` and turns it into SQL.

TWO SHAPES OF ANSWER
--------------------
``summary``    one row of headline figures for the whole period
``breakdown``  ranked rows grouped by a dimension

FILTERING, GROUPING, RANKING AND LIMITING ALL HAPPEN IN SQL
-----------------------------------------------------------
Never "load the rows and sort in Python". With three months of seed data either
approach looks fine; with three years of real sales the Python version loads every
row into memory to return ten. ``WHERE`` / ``GROUP BY`` / ``ORDER BY`` / ``LIMIT``
push that work to the database, which has the indexes for it.

The relevant indexes already exist — ``ix_sales_sold_at``,
``ix_purchases_purchase_date``, ``ix_returns_returned_at`` for the date filters, and
``ix_sale_items_medicine_id`` / ``ix_purchase_items_medicine_id`` for the grouping
joins — so no new index is added here. (Adding one "for performance" without a slow
query to point at is guesswork.)

DATE COLUMN TYPES DIFFER, DELIBERATELY HANDLED
----------------------------------------------
``sales.sold_at`` and ``returns.returned_at`` are ``DateTime``;
``purchases.purchase_date`` is ``Date``. A single ``<= end`` predicate would be
correct for one and drop the final day of the range for the other, so the two cases
go through :meth:`DateRange.as_datetime_bounds` and
:meth:`DateRange.as_date_bounds` respectively.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Select, func
from sqlalchemy.orm import Session

from app.ai.schemas.business_query import (
    BusinessQuery,
    Dimension,
    Metric,
    SortDirection,
)
from app.core.time_range import DateRange
from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.returns import Return
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.supplier import Supplier


class BusinessRepository:
    """Database access layer for Business Intelligence."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, query: BusinessQuery, *, as_of: date | None = None) -> dict:
        """Execute a validated query and return its result.

        The single door into this repository for the agent. Dispatch is explicit
        rather than reflective (no ``getattr(self, f"get_{metric}")``) so the set of
        reachable methods is visible here and cannot be widened by a crafted value.
        """

        date_range = query.date_range(as_of=as_of)

        if query.dimension is None:
            return self._summary(query.metric, date_range)

        return {
            "dimension": query.dimension.value,
            "period": date_range.describe(),
            "rows": self._breakdown(query, date_range),
        }

    # ------------------------------------------------------------------
    # Date predicates
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_datetime(statement: Select, column, date_range: DateRange) -> Select:
        lower, upper = date_range.as_datetime_bounds()
        if lower is not None:
            statement = statement.where(column >= lower)
        if upper is not None:
            # Exclusive: `upper` is midnight the day AFTER the range ends, so the
            # whole of the final day counts. `<= end` would drop it.
            statement = statement.where(column < upper)
        return statement

    @staticmethod
    def _filter_date(statement: Select, column, date_range: DateRange) -> Select:
        lower, upper = date_range.as_date_bounds()
        if lower is not None:
            statement = statement.where(column >= lower)
        if upper is not None:
            statement = statement.where(column <= upper)
        return statement

    def _scalar(self, statement: Select) -> Any:
        return self.db.execute(statement).scalar()

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def _summary(self, metric: Metric, date_range: DateRange) -> dict:
        if metric is Metric.SALES:
            return self.get_sales_summary(date_range)
        if metric is Metric.PURCHASES:
            return self.get_purchase_summary(date_range)
        if metric is Metric.RETURNS:
            return self.get_return_summary(date_range)
        if metric is Metric.EXPIRY:
            return self.get_expiry_summary()
        if metric is Metric.MARGIN:
            return self.get_margin_summary(date_range)
        raise ValueError(f"No summary implementation for metric {metric!r}")

    def get_sales_summary(self, date_range: DateRange | None = None) -> dict:
        """Headline sales metrics for the period (all time when omitted)."""

        window = date_range or DateRange(None, None)

        totals = self._filter_datetime(
            Select(
                func.coalesce(func.sum(Sale.total_amount), 0),
                func.count(Sale.id),
                func.max(Sale.sold_at),
            ),
            Sale.sold_at,
            window,
        )
        total_sales, total_orders, latest_sale = self.db.execute(totals).one()

        total_sales = float(total_sales)
        average_order_value = total_sales / total_orders if total_orders else 0

        return {
            "total_sales": total_sales,
            "total_orders": total_orders,
            "average_order_value": round(average_order_value, 2),
            "latest_sale": latest_sale,
            "period": window.describe(),
        }

    def get_purchase_summary(self, date_range: DateRange | None = None) -> dict:
        """Headline purchase metrics. ``purchase_date`` is a Date column."""

        window = date_range or DateRange(None, None)

        totals = self._filter_date(
            Select(
                func.coalesce(func.sum(Purchase.total_amount), 0),
                func.count(Purchase.id),
                func.max(Purchase.purchase_date),
            ),
            Purchase.purchase_date,
            window,
        )
        total_purchase, total_orders, latest_purchase = self.db.execute(totals).one()

        total_purchase = float(total_purchase)
        average = total_purchase / total_orders if total_orders else 0

        return {
            "total_purchase": total_purchase,
            "total_purchase_orders": total_orders,
            "average_purchase_value": round(average, 2),
            "latest_purchase": latest_purchase,
            "period": window.describe(),
        }

    def get_return_summary(self, date_range: DateRange | None = None) -> dict:
        """Return metrics, split by direction.

        One grouped query rather than six scalar ones: the previous implementation ran
        six separate aggregates over the same table to build this dict.
        """

        window = date_range or DateRange(None, None)

        grouped = self._filter_datetime(
            Select(
                Return.return_type,
                func.count(Return.id),
                func.coalesce(func.sum(Return.amount), 0),
            ),
            Return.returned_at,
            window,
        ).group_by(Return.return_type)

        counts: dict[str, int] = {}
        amounts: dict[str, float] = {}
        for return_type, count, amount in self.db.execute(grouped):
            counts[return_type] = count
            amounts[return_type] = float(amount)

        return {
            "total_returns": sum(counts.values()),
            "total_return_amount": round(sum(amounts.values()), 2),
            "sales_return_count": counts.get("sales", 0),
            "sales_return_amount": amounts.get("sales", 0.0),
            "purchase_return_count": counts.get("purchase", 0),
            "purchase_return_amount": amounts.get("purchase", 0.0),
            "period": window.describe(),
        }

    def get_expiry_summary(self) -> dict:
        """Stock that has already expired — a snapshot of now, not a period.

        ``func.current_date()`` rather than Python's ``date.today()`` so the
        comparison happens in the database's timezone, matching the convention in
        the batch and reorder repositories.
        """

        expired = Batch.expiry_date < func.current_date()

        expired_batches = self._scalar(Select(func.count(Batch.id)).where(expired))
        expiry_loss = self._scalar(
            Select(
                func.coalesce(func.sum(Batch.quantity * Batch.cost_price), 0)
            ).where(expired)
        )

        return {
            "expired_batches": expired_batches,
            "expiry_loss": float(expiry_loss),
            "period": "stock as at today",
        }

    def get_margin_summary(self, date_range: DateRange | None = None) -> dict:
        """Revenue, COGS and margin over the period.

        COGS comes from the cost price of the batch each line actually sold, which is
        why this joins ``sale_items -> batches`` rather than assuming a flat markup.
        The date filter applies to the parent sale, so it needs the ``sales`` join too.
        """

        window = date_range or DateRange(None, None)

        statement = self._filter_datetime(
            Select(
                func.coalesce(func.sum(SaleItem.line_total), 0),
                func.coalesce(func.sum(SaleItem.quantity * Batch.cost_price), 0),
            )
            .join(Batch, Batch.id == SaleItem.batch_id)
            .join(Sale, Sale.id == SaleItem.sale_id),
            Sale.sold_at,
            window,
        )
        revenue, cogs = self.db.execute(statement).one()

        revenue = float(revenue)
        cogs = float(cogs)
        gross_profit = revenue - cogs
        margin = (gross_profit / revenue * 100) if revenue > 0 else 0

        return {
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": round(gross_profit, 2),
            "profit_margin_percent": round(margin, 2),
            "period": window.describe(),
        }

    # ------------------------------------------------------------------
    # Breakdowns
    # ------------------------------------------------------------------

    def _breakdown(self, query: BusinessQuery, date_range: DateRange) -> list[dict]:
        builders = {
            Metric.SALES: self._sales_breakdown,
            Metric.PURCHASES: self._purchase_breakdown,
            Metric.RETURNS: self._return_breakdown,
            Metric.MARGIN: self._margin_breakdown,
            Metric.EXPIRY: self._expiry_breakdown,
        }

        builder = builders.get(query.metric)
        if builder is None:
            raise ValueError(f"No breakdown implementation for {query.metric!r}")

        statement = builder(query.dimension, date_range)

        # WHAT GETS SORTED depends on the dimension, because "top" means different
        # things. Ranking a product list by value answers "which sold most". Ranking
        # a DAY list by value would answer "which was my best day" while destroying
        # the trend the user asked to see, so time buckets sort chronologically and
        # `sort` chooses the direction of time instead.
        #
        # Columns are addressed by position: label is 0, the metric is 1, in every
        # builder. Ordering and limiting then happen once here rather than in each.
        is_time_dimension = query.dimension in (Dimension.DAY, Dimension.MONTH)
        order_column = statement.selected_columns[0 if is_time_dimension else 1]

        direction = (
            order_column.desc()
            if query.sort is SortDirection.DESC
            else order_column.asc()
        )

        statement = statement.order_by(direction).limit(query.limit)

        return [
            {"label": label, "value": float(value or 0), "quantity": int(quantity or 0)}
            for label, value, quantity in self.db.execute(statement)
        ]

    @staticmethod
    def _time_label(column, dimension: Dimension):
        """A groupable label for a date/datetime column.

        ``strftime`` is SQLite's; MySQL provides ``date_format``. SQLAlchemy's
        ``func`` passes either straight through, so this is the one place in the
        repository that is dialect-aware — flagged as such in the docs.
        """

        pattern = "%Y-%m-%d" if dimension is Dimension.DAY else "%Y-%m"
        return func.strftime(pattern, column)

    def _sales_breakdown(self, dimension: Dimension, date_range: DateRange) -> Select:
        if dimension in (Dimension.DAY, Dimension.MONTH):
            label = self._time_label(Sale.sold_at, dimension)
            statement = Select(
                label.label("label"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("value"),
                func.count(Sale.id).label("quantity"),
            )
            return self._filter_datetime(statement, Sale.sold_at, date_range).group_by(
                label
            )

        label_column = (
            Medicine.name if dimension is Dimension.PRODUCT else Medicine.manufacturer
        )
        statement = (
            Select(
                label_column.label("label"),
                func.coalesce(func.sum(SaleItem.line_total), 0).label("value"),
                func.coalesce(func.sum(SaleItem.quantity), 0).label("quantity"),
            )
            .join(Medicine, Medicine.id == SaleItem.medicine_id)
            .join(Sale, Sale.id == SaleItem.sale_id)
        )
        return self._filter_datetime(statement, Sale.sold_at, date_range).group_by(
            label_column
        )

    def _purchase_breakdown(self, dimension: Dimension, date_range: DateRange) -> Select:
        if dimension in (Dimension.DAY, Dimension.MONTH):
            label = self._time_label(Purchase.purchase_date, dimension)
            statement = Select(
                label.label("label"),
                func.coalesce(func.sum(Purchase.total_amount), 0).label("value"),
                func.count(Purchase.id).label("quantity"),
            )
            return self._filter_date(
                statement, Purchase.purchase_date, date_range
            ).group_by(label)

        # SUPPLIER — the only non-time purchase dimension.
        statement = Select(
            Supplier.name.label("label"),
            func.coalesce(func.sum(Purchase.total_amount), 0).label("value"),
            func.count(Purchase.id).label("quantity"),
        ).join(Supplier, Supplier.id == Purchase.supplier_id)
        return self._filter_date(
            statement, Purchase.purchase_date, date_range
        ).group_by(Supplier.name)

    def _return_breakdown(self, dimension: Dimension, date_range: DateRange) -> Select:
        if dimension in (Dimension.DAY, Dimension.MONTH):
            label = self._time_label(Return.returned_at, dimension)
            statement = Select(
                label.label("label"),
                func.coalesce(func.sum(Return.amount), 0).label("value"),
                func.count(Return.id).label("quantity"),
            )
            return self._filter_datetime(
                statement, Return.returned_at, date_range
            ).group_by(label)

        label_column = (
            Medicine.name if dimension is Dimension.PRODUCT else Medicine.manufacturer
        )
        statement = Select(
            label_column.label("label"),
            func.coalesce(func.sum(Return.amount), 0).label("value"),
            func.coalesce(func.sum(Return.quantity), 0).label("quantity"),
        ).join(Medicine, Medicine.id == Return.medicine_id)
        return self._filter_datetime(
            statement, Return.returned_at, date_range
        ).group_by(label_column)

    def _margin_breakdown(self, dimension: Dimension, date_range: DateRange) -> Select:
        """Gross profit per product or manufacturer: revenue minus batch cost."""

        label_column = (
            Medicine.name if dimension is Dimension.PRODUCT else Medicine.manufacturer
        )
        gross_profit = func.coalesce(
            func.sum(SaleItem.line_total) - func.sum(SaleItem.quantity * Batch.cost_price),
            0,
        )
        statement = (
            Select(
                label_column.label("label"),
                gross_profit.label("value"),
                func.coalesce(func.sum(SaleItem.quantity), 0).label("quantity"),
            )
            .join(Medicine, Medicine.id == SaleItem.medicine_id)
            .join(Batch, Batch.id == SaleItem.batch_id)
            .join(Sale, Sale.id == SaleItem.sale_id)
        )
        return self._filter_datetime(statement, Sale.sold_at, date_range).group_by(
            label_column
        )

    def _expiry_breakdown(self, dimension: Dimension, _date_range: DateRange) -> Select:
        """Value of already-expired stock per product or manufacturer.

        The date range is ignored by design — expiry is a snapshot of stock on hand.
        ``BusinessQuery`` rejects a non-all-time period for this metric, so an ignored
        range here can only ever be the unbounded one.
        """

        label_column = (
            Medicine.name if dimension is Dimension.PRODUCT else Medicine.manufacturer
        )
        return (
            Select(
                label_column.label("label"),
                func.coalesce(
                    func.sum(Batch.quantity * Batch.cost_price), 0
                ).label("value"),
                func.coalesce(func.sum(Batch.quantity), 0).label("quantity"),
            )
            .join(Medicine, Medicine.id == Batch.medicine_id)
            .where(Batch.expiry_date < func.current_date())
            .group_by(label_column)
        )
