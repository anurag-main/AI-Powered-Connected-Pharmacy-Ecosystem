"""HTTP layer for Refill Intelligence (M6.2).

One read-only endpoint. There is no POST, because M6.2 creates nothing: it
derives candidates from purchase history every time it is asked.

The future scheduler will call ``RefillService`` directly rather than making an
HTTP request to its own process. This endpoint exists for the pharmacist's screen
and for inspecting the engine's reasoning, which is also why every candidate
carries a plain-language ``reason``.

NOT HERE, deliberately: any notion of sending. No WhatsApp, no templates, no
webhooks, no message state. M6.2's job is to prove the system can work out WHO
should be contacted, before anything is wired up to contact them.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.refill import RefillCandidatesResponse
from app.services.refill_service import DEFAULT_LOOKBACK_DAYS, RefillService

router = APIRouter(prefix="/api/v1/refill", tags=["refill"])


def get_service(db: Session = Depends(get_db)) -> RefillService:
    return RefillService(db)


@router.get(
    "/candidates",
    response_model=RefillCandidatesResponse,
    summary="Customers who look due for a refill, with the reason for each",
)
def list_candidates(
    as_of: date | None = Query(
        default=None,
        description="Reference date. Defaults to today in the pharmacy timezone. "
        "Mainly for answering 'who was due last Monday'.",
    ),
    lookback_days: int = Query(default=DEFAULT_LOOKBACK_DAYS, ge=1, le=1000),
    due_only: bool = Query(
        default=True,
        description="False also returns not-due and unknown-duration rows, which "
        "is how the screen shows why someone is absent from the list.",
    ),
    contactable_only: bool = Query(
        default=False,
        description="Only customers who could actually be messaged. Off by "
        "default: a due customer with no consent is still a customer to phone.",
    ),
    customer_id: int | None = Query(default=None, ge=1),
    medicine_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    service: RefillService = Depends(get_service),
) -> RefillCandidatesResponse:
    """Run the deterministic scan and return the candidates.

    The summary counts cover the WHOLE scan, before the filters and the limit, so
    the screen can honestly say "20 of 143 due" rather than counting its own rows.
    """
    return service.find_candidates(
        as_of=as_of,
        lookback_days=lookback_days,
        due_only=due_only,
        contactable_only=contactable_only,
        customer_id=customer_id,
        medicine_id=medicine_id,
        limit=limit,
    )
