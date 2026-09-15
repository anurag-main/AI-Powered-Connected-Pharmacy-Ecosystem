"""HTTP layer for the Customer domain — identity and WhatsApp consent (M6.1).

Consent lives on its own endpoints rather than on a generic customer PATCH.
A PATCH that can set `whatsapp_opt_in_at` to an arbitrary timestamp is a
back-dating tool, and back-dated consent is the exact thing an audit exists to
catch. `POST .../opt-in` can only mean "they agreed, now".

NOT IMPLEMENTED HERE, deliberately: sending anything. These endpoints record a
decision. No WhatsApp client, no credentials, no template.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.customer import CustomerOut, OptOutRequest
from app.services.customer_service import (
    CONSENT_SOURCE_STAFF,
    CustomerService,
)

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


def get_service(db: Session = Depends(get_db)) -> CustomerService:
    return CustomerService(db)


@router.get(
    "",
    response_model=list[CustomerOut],
    summary="Customers with their WhatsApp consent state",
)
def list_customers(
    limit: int = Query(default=100, ge=1, le=200),
    service: CustomerService = Depends(get_service),
) -> list[CustomerOut]:
    """Newest first. Bounded — this feeds a screen, not an export."""
    return service.list_customers(limit=limit)


@router.get(
    "/{customer_id}",
    response_model=CustomerOut,
    summary="One customer",
)
def get_customer(
    customer_id: int,
    service: CustomerService = Depends(get_service),
) -> CustomerOut:
    result = service.get_customer(customer_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )
    return result


@router.post(
    "/{customer_id}/whatsapp/opt-in",
    response_model=CustomerOut,
    summary="Record that the customer agreed to WhatsApp reminders",
)
def opt_in(
    customer_id: int,
    service: CustomerService = Depends(get_service),
) -> CustomerOut:
    """Stamps consent at NOW. Takes no timestamp from the client, by design.

    Works from any prior state, including a previous opt-out — that is the
    re-opt-in path, and it needs no special endpoint because the newer timestamp
    simply wins.
    """
    result = service.opt_in(customer_id, source=CONSENT_SOURCE_STAFF)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )
    return result


@router.post(
    "/{customer_id}/whatsapp/opt-out",
    response_model=CustomerOut,
    summary="Record that the customer withdrew consent",
)
def opt_out(
    customer_id: int,
    payload: OptOutRequest | None = None,
    service: CustomerService = Depends(get_service),
) -> CustomerOut:
    """Always succeeds for an existing customer, whatever the prior state.

    Opting out someone who was never opted in is not an error. They have made a
    decision, and recording it is what stops staff asking again next visit.
    """
    result = service.opt_out(
        customer_id, reason=payload.reason if payload is not None else None
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )
    return result
