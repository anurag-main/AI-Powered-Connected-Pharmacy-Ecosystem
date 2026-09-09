"""Read-only database access for sales history. SQL only, no business rules.

Sales are written by the billing confirm step; nothing here writes. This exists so
the invoices that step creates can be looked at again.

The list query deliberately does NOT load line items. A history page shows one row
per invoice, and eager-loading every line for every sale would fetch thousands of
rows to render a hundred. Lines arrive only when one sale is opened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.sale import Sale
from app.models.sale_item import SaleItem


@dataclass(frozen=True)
class SaleSummary:
    """One row of the history list."""

    sale_id: int
    sold_at: datetime
    total_amount: Decimal
    item_count: int
    customer_name: str | None
    customer_phone: str | None


@dataclass(frozen=True)
class SaleLine:
    """One line of an opened invoice."""

    medicine_id: int
    medicine_name: str
    batch_number: str | None
    expiry_date: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class SaleDetail:
    """One invoice, with its lines."""

    summary: SaleSummary
    lines: list[SaleLine]


class SalesRepository:
    """Reads saved invoices."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Total invoices, so the UI can page without guessing."""

        return self.db.execute(select(func.count(Sale.id))).scalar_one()

    def list_recent(self, *, limit: int, offset: int) -> list[SaleSummary]:
        """Invoices newest first.

        Ordered by ``(sold_at DESC, id DESC)``. The id tiebreak matters more than it
        looks: several sales in the same second are ordinary at a busy counter, and
        without it two pages could repeat an invoice or skip one.

        ``item_count`` comes from a grouped subquery rather than ``len(sale.items)``,
        which would be one extra query per row.
        """

        line_counts = (
            select(SaleItem.sale_id, func.count(SaleItem.id).label("item_count"))
            .group_by(SaleItem.sale_id)
            .subquery()
        )

        statement: Select = (
            select(
                Sale.id,
                Sale.sold_at,
                Sale.total_amount,
                func.coalesce(line_counts.c.item_count, 0),
                Customer.name,
                Customer.phone,
            )
            # Outer joins: a walk-in sale has no customer, and a sale whose lines were
            # somehow lost should still appear rather than vanish from history.
            .outerjoin(line_counts, line_counts.c.sale_id == Sale.id)
            .outerjoin(Customer, Customer.id == Sale.customer_id)
            .order_by(Sale.sold_at.desc(), Sale.id.desc())
            .limit(limit)
            .offset(offset)
        )

        return [
            SaleSummary(
                sale_id=row[0],
                sold_at=row[1],
                total_amount=row[2],
                item_count=row[3],
                customer_name=row[4],
                customer_phone=row[5],
            )
            for row in self.db.execute(statement)
        ]

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    def get_detail(self, sale_id: int) -> SaleDetail | None:
        """One invoice and its lines, or None if there is no such invoice.

        Two queries, fixed — the header, then all its lines. ``sale_items`` stores
        ``medicine_id`` rather than a name, so the line query joins Medicine for the
        label and Batch for the batch number.

        Prices come from ``sale_items``, never from ``medicines.mrp``: the line price
        was frozen at sale time, and re-reading today's MRP would silently rewrite the
        history of what a customer actually paid.
        """

        header = (
            select(
                Sale.id,
                Sale.sold_at,
                Sale.total_amount,
                Customer.name,
                Customer.phone,
            )
            .outerjoin(Customer, Customer.id == Sale.customer_id)
            .where(Sale.id == sale_id)
        )

        row = self.db.execute(header).first()
        if row is None:
            return None

        line_statement: Select = (
            select(
                SaleItem.medicine_id,
                Medicine.name,
                Batch.batch_number,
                Batch.expiry_date,
                SaleItem.quantity,
                SaleItem.unit_price,
                SaleItem.line_total,
            )
            .join(Medicine, Medicine.id == SaleItem.medicine_id)
            # Outer: a batch could have been purged; the line still happened.
            .outerjoin(Batch, Batch.id == SaleItem.batch_id)
            .where(SaleItem.sale_id == sale_id)
            .order_by(SaleItem.id)
        )

        lines = [
            SaleLine(
                medicine_id=line[0],
                medicine_name=line[1],
                batch_number=line[2],
                expiry_date=line[3].isoformat() if line[3] else None,
                quantity=line[4],
                unit_price=line[5],
                line_total=line[6],
            )
            for line in self.db.execute(line_statement)
        ]

        return SaleDetail(
            summary=SaleSummary(
                sale_id=row[0],
                sold_at=row[1],
                total_amount=row[2],
                item_count=len(lines),
                customer_name=row[3],
                customer_phone=row[4],
            ),
            lines=lines,
        )
