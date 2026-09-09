"""HTTP contract for sales history — read-only."""

from datetime import datetime

from pydantic import BaseModel, Field

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


class SaleLineOut(BaseModel):
    """One line of an invoice, exactly as it was charged."""

    medicine_id: int
    medicine_name: str
    batch_number: str | None
    expiry_date: str | None
    quantity: int
    unit_price: float
    line_total: float


class SaleSummaryOut(BaseModel):
    """One row of the history list."""

    sale_id: int
    sold_at: datetime
    total_amount: float
    item_count: int
    customer_name: str | None
    customer_phone: str | None


class SaleDetailOut(SaleSummaryOut):
    """One invoice with its lines."""

    lines: list[SaleLineOut]


class SalesPageOut(BaseModel):
    """A page of history.

    `total` is the count of ALL invoices, not of this page, so the UI can show
    "25 of 549" and decide whether a Load more button belongs on screen.
    """

    total: int = Field(description="Total invoices in the system, ignoring paging.")
    limit: int
    offset: int
    sales: list[SaleSummaryOut]
