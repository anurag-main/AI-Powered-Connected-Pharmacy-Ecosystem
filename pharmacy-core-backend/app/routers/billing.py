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

from app.schemas.billing import BillingRequest, BillingResponse
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
