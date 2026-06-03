"""Pydantic schemas for the Billing domain — the HTTP contract.

Input/output split, same convention as the Medicine domain:
- BillingRequest  — what the CLIENT sends (just the free-text sentence)
- BillingResponse — what the SERVER returns (the receipt: sale id, lines, total, errors)

The graph's internal state (BillingState) is NOT exposed directly — these schemas
are the clean public face. Internal fields (batch_id, medicine_id) are included
because they're useful to the pharmacist UI, but cost_price etc. never appear.
"""
from pydantic import BaseModel, Field


class BillingRequest(BaseModel):
    """Input contract: the pharmacist's free-text order.

    FastAPI validates incoming JSON against this. Empty / oversized input → 422
    automatically, before the graph (and the paid LLM call) ever runs.
    """

    pharmacist_input: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Free-text order, e.g. '2 strips Crocin 500mg for Anurag 9876543210'",
    )


class MatchCandidate(BaseModel):
    """A possible catalog medicine for an uncertain (voice-mis-heard) line."""

    medicine_id: int
    name: str


class BillingLineItem(BaseModel):
    """One line on the returned receipt — mirrors a priced_item from graph state."""

    name: str
    quantity: int
    unit: str
    medicine_id: int
    batch_id: int
    batch_number: str
    expiry_date: str
    unit_price: float
    line_total: float

    # ----- Voice-match metadata (defaults keep older callers working) -----
    # True when the match was uncertain and the owner should confirm before billing.
    needs_confirm: bool = False
    # The raw spoken text we matched FROM (e.g. "mat CB"), for "did you hear this right?".
    matched_from: str | None = None
    # Alternative catalog medicines the owner can switch to (dropdown).
    candidates: list[MatchCandidate] = Field(default_factory=list)


class BillingResponse(BaseModel):
    """Output contract: the receipt the server returns.

    sale_id is None when no sale could be created (e.g. every medicine was
    out of stock or unrecognized). In that case `errors` explains why and the
    router returns HTTP 422.
    """

    sale_id: int | None = Field(
        default=None,
        description="The new invoice id, or null if no sale could be created",
    )
    total_amount: float = Field(default=0.0, description="Grand total of all line items")
    customer_name: str | None = Field(default=None)
    customer_phone: str | None = Field(default=None)
    items: list[BillingLineItem] = Field(
        default_factory=list,
        description="One entry per successfully-billed medicine line",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Soft errors / warnings (e.g. 'Medicine not found', 'Insufficient stock')",
    )


class ConfirmLineItem(BaseModel):
    """One owner-reviewed line sent to POST /confirm to finalize the sale.

    Note there is NO price field here: the server RE-FETCHES the MRP from the DB
    at confirm time and recomputes the price. The client can never dictate the
    price (server-side pricing rule). These fields are exactly the 'batched_item'
    shape the quote step returned, minus the prices.
    """

    name: str
    quantity: int = Field(..., ge=1, le=1000)
    unit: str
    medicine_id: int
    batch_id: int
    batch_number: str
    expiry_date: str


class PriceItemRequest(BaseModel):
    """Price ONE medicine by id (used when the owner picks a different candidate
    from a confirm dropdown). Server fetches the FEFO batch + MRP."""

    medicine_id: int
    quantity: int = Field(..., ge=1, le=1000)
    name: str | None = Field(default=None)
    unit: str | None = Field(default="strip")


class ConfirmSaleRequest(BaseModel):
    """Input contract for POST /confirm — finalize a previously-quoted bill.

    The owner may have edited quantities or removed rows in the preview; we
    persist exactly the items sent here. Customer fields stay optional.
    """

    items: list[ConfirmLineItem] = Field(..., min_length=1)
    customer_name: str | None = Field(default=None)
    customer_phone: str | None = Field(default=None)
