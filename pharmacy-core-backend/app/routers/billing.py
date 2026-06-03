"""HTTP layer for the Billing domain.

POST /api/v1/billing/sale — turn one free-text pharmacist order into a sale.

The router is thin: validate input (FastAPI does it via BillingRequest),
call the service, translate the result into an HTTP status code.

Status decisions:
- sale_id present     → 201 Created (a real invoice was written; `errors` may
                        still list warnings about individual skipped lines)
- sale_id None        → 422 Unprocessable Entity (nothing could be billed —
                        unknown medicines, out of stock, or empty extraction);
                        the body carries the errors so the client can show them
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.billing import (
    BillingRequest,
    BillingResponse,
    ConfirmSaleRequest,
)
from app.services.billing_service import BillingService


def get_billing_service() -> BillingService:
    """Dependency provider. No DB session needed here — the graph owns its sessions."""
    return BillingService()


router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.post(
    "/sale",
    response_model=BillingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sale from a free-text pharmacist order",
)
def create_sale(
    payload: BillingRequest,
    service: BillingService = Depends(get_billing_service),
) -> BillingResponse:
    """Run the AI billing pipeline on one free-text order.

    Example body:
        {"pharmacist_input": "2 strips Crocin 500mg for Anurag 9876543210"}

    Returns 201 with the receipt on success, or 422 with errors if no sale
    could be created.
    """
    result = service.create_sale(payload.pharmacist_input)

    if result.sale_id is None:
        # Nothing billable. 422 = "we understood the request but couldn't act on it."
        # The detail carries the structured errors so the UI can render them.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "No sale could be created",
                "errors": result.errors,
            },
        )

    return result


@router.post(
    "/quote",
    response_model=BillingResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview prices for a free-text order WITHOUT saving",
)
def quote_sale(
    payload: BillingRequest,
    service: BillingService = Depends(get_billing_service),
) -> BillingResponse:
    """Price an order for preview — does NOT write a sale or touch stock.

    Always returns 200 (it's a preview, not a creation). `sale_id` is null,
    `items` holds the priced rows the owner can review/edit, and `errors` lists
    any names the catalog didn't match so the UI can prompt a fix + re-quote.
    """
    return service.quote_sale(payload.pharmacist_input)


@router.post(
    "/confirm",
    response_model=BillingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Finalize a reviewed bill — persists the sale (the Print action)",
)
def confirm_sale(
    payload: ConfirmSaleRequest,
    service: BillingService = Depends(get_billing_service),
) -> BillingResponse:
    """Persist the owner-reviewed line items as a real sale.

    Re-fetches each MRP from the DB and recomputes prices server-side (a tampered
    client price is ignored), then writes the atomic 4-table transaction.

    Returns 201 with the receipt (incl. sale_id) on success, or 422 if nothing
    could be persisted (e.g. stock ran out since the quote).
    """
    result = service.confirm_sale(
        items=payload.items,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
    )

    if result.sale_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Sale could not be finalized",
                "errors": result.errors,
            },
        )

    return result
