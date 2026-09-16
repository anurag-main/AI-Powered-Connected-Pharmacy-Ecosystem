"""Notification contract and lifecycle (M6.3)."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class NotificationStatus(StrEnum):
    """The lifecycle of one reminder.

    Every value except PENDING/SENDING/CANCELLED maps to something Meta actually
    reports, which was the constraint: a status the provider can never produce is
    a status that will be wrong forever once set.

        PENDING    created, not yet attempted
        SENDING    an attempt is in flight
        SENT       Meta accepted it and returned a wamid
        DELIVERED  reached the handset          (webhook)
        READ       the customer opened it       (webhook)
        FAILED     permanently failed           (send or webhook)
        CANCELLED  no longer wanted (no longer eligible, or cancelled by staff)
    """

    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    CANCELLED = "cancelled"


# How far along the happy path each status is. Webhooks arrive out of order and
# Meta can send `delivered` after `read`, so a status is only applied when it
# RANKS HIGHER than what is already stored. Without this, a late `sent` callback
# would drag a message that was already read back to "sent".
STATUS_RANK: dict[str, int] = {
    NotificationStatus.PENDING: 0,
    NotificationStatus.SENDING: 1,
    NotificationStatus.SENT: 2,
    NotificationStatus.DELIVERED: 3,
    NotificationStatus.READ: 4,
}

# Terminal states. Nothing moves out of these.
TERMINAL_STATUSES = {NotificationStatus.FAILED, NotificationStatus.CANCELLED}


class NotificationOut(BaseModel):
    """One reminder, as the dashboard sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    idempotency_key: str
    customer_id: int
    medicine_id: int
    source_sale_item_id: int
    expected_refill_date: date
    channel: str
    template_name: str
    template_language: str
    status: str
    attempts: int
    last_error_code: str | None = None
    # Deliberately NOT the provider's raw error text. See NotificationService.
    last_error_message: str | None = None
    created_at: datetime
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None

    # `provider_message_id` is intentionally absent. The dashboard never needs a
    # wamid, and it is an identifier for a customer's message that has no reason
    # to travel to a browser.


class SendReminderRequest(BaseModel):
    """Manual send, triggered by a pharmacist from /refills.

    Takes the refill opportunity's identity rather than a notification id,
    because before the first send there is no notification to reference. The
    server re-derives the candidate and re-checks eligibility; the client cannot
    assert that someone is due.
    """

    source_sale_item_id: int = Field(..., ge=1)
    expected_refill_date: date


class SendReminderResponse(BaseModel):
    """What happened. `created` is False when an existing reminder was reused."""

    notification: NotificationOut | None = None
    created: bool
    sent: bool
    reason: str
