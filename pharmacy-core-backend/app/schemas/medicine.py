"""Pydantic schemas for the Medicine domain.

Convention (input/output contract split):
- MedicineCreate — what a CLIENT sends when adding a new medicine
- MedicineOut    — what the SERVER returns to a client

Never use one schema for both. Even when fields overlap 90%, keep them separate.
Internal-only fields (cost_price, supplier_notes) live in the repository layer
and never appear in any schema sent to a client.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MedicineCreate(BaseModel):
    """Input contract: fields a client must provide to create a new medicine.

    FastAPI auto-validates incoming JSON against this class.
    Invalid input -> automatic 422 Unprocessable Entity (you don't write the handler).
    """

    name: str = Field(..., min_length=1, max_length=200)
    mrp: float = Field(..., gt=0)
    hsn_code: str = Field(..., min_length=8, max_length=8)
    manufacturer: str | None = Field(default=None, max_length=200)

    # M6.1 -- a typical course length in days, used ONLY to pre-fill the billing
    # form. Optional, and None is the honest answer for most of the catalogue:
    # a painkiller bought as needed has no natural course length.
    #
    # Range matches the CHECK constraint on the column and the bounds on
    # SaleItem.days_supply, so the hint can never suggest a value the sale line
    # would refuse.
    default_days_supply: int | None = Field(default=None, ge=1, le=365)


class MedicineOut(BaseModel):
    """Output contract: fields the server returns to the client.

    Includes server-generated fields (id, created_at).
    Never includes internal-only fields like cost_price or supplier_notes —
    those live in the repository layer only.
    """

    # from_attributes=True lets MedicineOut.model_validate(orm_obj) read the
    # values directly from a SQLAlchemy ORM row's attributes.
    # Without this, model_validate would only accept dicts.
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    mrp: float
    hsn_code: str
    manufacturer: str | None

    # M6.1. Read by compute_pricing so the billing form can pre-fill the
    # days-supply box, and by the catalogue screen so the hint is visible.
    default_days_supply: int | None = None

    created_at: datetime
