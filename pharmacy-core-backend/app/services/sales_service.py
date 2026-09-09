"""Business layer for sales history.

Thin by design: history is a read, and there are no rules to apply to a past
invoice beyond presenting it. The one job here is turning repository dataclasses
into the HTTP contract, so the router never touches a Decimal.
"""

from app.repositories.sales_repository import SaleDetail, SalesRepository, SaleSummary
from app.schemas.sales import (
    SaleDetailOut,
    SaleLineOut,
    SalesPageOut,
    SaleSummaryOut,
)


def _to_summary(summary: SaleSummary) -> SaleSummaryOut:
    return SaleSummaryOut(
        sale_id=summary.sale_id,
        sold_at=summary.sold_at,
        total_amount=float(summary.total_amount),
        item_count=summary.item_count,
        customer_name=summary.customer_name,
        customer_phone=summary.customer_phone,
    )


class SalesService:
    """Reads saved invoices for the history screen."""

    def __init__(self, repository: SalesRepository) -> None:
        self._repo = repository

    def list_sales(self, *, limit: int, offset: int) -> SalesPageOut:
        """One page of history, newest first."""

        return SalesPageOut(
            total=self._repo.count(),
            limit=limit,
            offset=offset,
            sales=[_to_summary(s) for s in self._repo.list_recent(limit=limit, offset=offset)],
        )

    def get_sale(self, sale_id: int) -> SaleDetailOut | None:
        """One invoice with its lines, or None if it does not exist."""

        detail: SaleDetail | None = self._repo.get_detail(sale_id)
        if detail is None:
            return None

        return SaleDetailOut(
            **_to_summary(detail.summary).model_dump(),
            lines=[
                SaleLineOut(
                    medicine_id=line.medicine_id,
                    medicine_name=line.medicine_name,
                    batch_number=line.batch_number,
                    expiry_date=line.expiry_date,
                    quantity=line.quantity,
                    unit_price=float(line.unit_price),
                    line_total=float(line.line_total),
                )
                for line in detail.lines
            ],
        )
