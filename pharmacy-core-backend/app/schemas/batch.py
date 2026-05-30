"""Pydantic schemas for the Batch domain.

Same input/output contract split as Medicine (Phase 1.4):
- BatchCreate  — what a client sends (admin / supplier import)
- BatchOut     — what the server returns

CRITICAL: BatchOut does NOT include cost_price. That field exists only in the
DB row and is used for internal profit / write-off calculations — never exposed
to API consumers.
"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BatchCreate(BaseModel):
    """Input contract for adding a new batch."""

    medicine_id: int = Field(..., gt=0)
    batch_number: str = Field(..., min_length=1, max_length=50)
    expiry_date: date  # service-layer rule will reject past dates
    quantity: int = Field(..., ge=0)  # initial stock for this batch
    cost_price: Decimal = Field(..., gt=0)


class BatchOut(BaseModel):
    """Output contract — cost_price intentionally NOT included."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    medicine_id: int
    batch_number: str
    expiry_date: date
    quantity: int
    created_at: datetime
    # cost_price intentionally omitted (INTERNAL field).
