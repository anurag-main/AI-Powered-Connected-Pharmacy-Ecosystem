"""Manual reminder sending and notification history (M6.3).

These endpoints exist for the pharmacist's dashboard and for operators. The
scheduler does NOT use them: it calls ``NotificationService`` in-process, because
an application making HTTP requests to itself adds a network hop, a second set of
failure modes and an authentication problem to reach code it can already import.

The frontend can trigger a send but can never bypass a rule: this router takes
the refill opportunity's identity, and the service re-derives the candidate and
re-checks consent and due-ness server-side. A client cannot assert that someone
is due, or that they consented.
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.notification import (
    NotificationOut,
    SendReminderRequest,
    SendReminderResponse,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def get_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db)


@router.post(
    "/refill-reminder",
    response_model=SendReminderResponse,
    summary="Send (or reuse) the refill reminder for one opportunity",
)
def send_refill_reminder(
    payload: SendReminderRequest,
    service: NotificationService = Depends(get_service),
) -> SendReminderResponse:
    """Idempotent. Calling this twice for the same opportunity sends once.

    Always 200, including when nothing was sent: "the customer opted out" and
    "they already refilled" are ordinary business answers the screen needs to
    display, not HTTP errors.
    """
    notification, sent, reason = service.send_reminder_for(
        source_sale_item_id=payload.source_sale_item_id,
        expected_refill_date=payload.expected_refill_date,
    )

    return SendReminderResponse(
        notification=(
            NotificationOut.model_validate(notification) if notification else None
        ),
        created=bool(notification and notification.attempts <= 1 and sent),
        sent=sent,
        reason=reason,
    )


@router.get(
    "",
    response_model=list[NotificationOut],
    summary="Recent reminders, newest first",
)
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    service: NotificationService = Depends(get_service),
) -> list[NotificationOut]:
    return [
        NotificationOut.model_validate(n)
        for n in service.repository.list_recent(limit=limit)
    ]
