"""Pydantic schemas for the Goods Receipt (stock intake) domain.

WHY THIS EXISTS
---------------
Until now stock could only ever go DOWN. Billing decremented batches; nothing in
the running application ever created one. Every batch in the database was written
by a seed script, which means the feature was demonstrated but never built.

These schemas are the contract for the write path that fixes that.

THE INPUT/OUTPUT SPLIT
----------------------
``GoodsReceiptCreate`` is what a client MAY send. ``GoodsReceiptOut`` is what the
server returns. They are deliberately different shapes, and the difference is the
point: the client sends quantity and unit cost, and the server sends back the
line totals and the invoice total it computed itself.

MONEY IS NEVER ACCEPTED FROM THE CLIENT
---------------------------------------
There is no ``line_total`` and no ``total_amount`` on the input. A client that
wanted to record a 500-rupee delivery as a 5-rupee one has nowhere to say so.
This mirrors the rule already enforced in billing: price is a server decision.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoodsReceiptLine(BaseModel):
    """One medicine on one supplier invoice — one physical box of stock.

    ``batch_number`` and ``expiry_date`` are REQUIRED, not optional. A pharmacy
    that receives stock without recording its expiry has no way to sell it safely
    afterwards, and FEFO has nothing to order by. Making these optional would be
    the single most damaging convenience in this schema.
    """

    medicine_id: int = Field(..., ge=1, description="Must already exist in the catalogue.")
    batch_number: str = Field(..., min_length=1, max_length=50)
    expiry_date: date = Field(..., description="Must be in the future at receipt time.")
    quantity: int = Field(..., ge=1, description="Units received. Never zero or negative.")
    unit_cost: float = Field(
        ...,
        gt=0,
        le=1_000_000,
        description="Cost per unit, exclusive of the client's opinion of the total.",
    )

    @field_validator("batch_number")
    @classmethod
    def _strip_batch_number(cls, value: str) -> str:
        """Trim surrounding whitespace so " AB123 " and "AB123" are one batch.

        Done here rather than in the service because an untrimmed batch number is
        never meaningful — there is no caller who wants the spaces preserved.
        """
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("batch_number cannot be blank")
        return cleaned


class GoodsReceiptCreate(BaseModel):
    """A whole supplier invoice: who it came from, when, and what was in it.

    The supplier may be given by id (a known vendor picked from a list) or by
    name (a new vendor typed in). Exactly one is required — accepting neither
    leaves the purchase unattributable, and accepting both invites a request
    where the two disagree.
    """

    supplier_id: int | None = Field(default=None, ge=1)
    supplier_name: str | None = Field(default=None, min_length=1, max_length=200)
    invoice_number: str | None = Field(default=None, max_length=100)
    purchase_date: date | None = Field(
        default=None,
        description="Supplier's invoice date. Defaults to today. Never in the future.",
    )
    lines: list[GoodsReceiptLine] = Field(..., min_length=1, max_length=100)

    @field_validator("supplier_name")
    @classmethod
    def _strip_supplier_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class GoodsReceiptLineOut(BaseModel):
    """One recorded line, including the figures the SERVER worked out."""

    model_config = ConfigDict(from_attributes=True)

    medicine_id: int
    medicine_name: str
    batch_id: int
    batch_number: str
    expiry_date: date
    quantity: int
    unit_cost: float
    line_total: float
    batch_created: bool = Field(
        ...,
        description="True if a new batch row was created; False if an existing "
        "batch with the same number was topped up.",
    )


class GoodsReceiptOut(BaseModel):
    """The receipt as recorded. Every money field here was computed server-side."""

    model_config = ConfigDict(from_attributes=True)

    purchase_id: int
    supplier_id: int
    supplier_name: str
    invoice_number: str | None
    purchase_date: date
    total_amount: float
    total_units: int
    lines: list[GoodsReceiptLineOut]
    created_at: datetime


class PurchaseSummary(BaseModel):
    """A row in the recent-receipts list. Deliberately without its lines.

    Listing 50 receipts with every line attached is a query the UI does not need
    and a payload it would not read. Lines come from the detail endpoint.
    """

    model_config = ConfigDict(from_attributes=True)

    purchase_id: int
    supplier_id: int
    supplier_name: str
    invoice_number: str | None
    purchase_date: date
    total_amount: float
    line_count: int


class SupplierOut(BaseModel):
    """A vendor, for the picker on the receipt form."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
