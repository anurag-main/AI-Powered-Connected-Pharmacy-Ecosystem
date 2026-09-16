"""Outbound notifications for refill reminders (M6.3).

WHERE THIS SITS
---------------
    RefillService  ->  RefillCandidate  ->  NotificationService  ->  MessagingProvider

The refill domain decides *who is due*. This service decides *whether to send and
records what happened*. The provider decides *how a message reaches a phone*.
Nothing here builds a Meta URL, reads a token or names a Graph API version.

FAIL CLOSED, ALWAYS
-------------------
Consent is checked here, in our code, before a request is ever constructed.
WhatsApp has its own opt-in rules, but relying on them would mean the pharmacy's
legal obligation under the DPDP Act is enforced by a third party's API — and a
missing check would only surface as a complaint. Not contactable means no HTTP
request is made at all, not a request that gets rejected.

TEMPLATE CONTENT AND HEALTH DATA
--------------------------------
The reminder deliberately does NOT name the medicine. A WhatsApp message is
visible on a lock screen, and "your Metformin is due" tells anyone holding the
phone that its owner is diabetic. The template says a refill may be due and asks
them to get in touch; the medicine is discussed in the shop.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time_range import today
from app.integrations.messaging.base import (
    MessagingProvider,
    SendOutcome,
    TemplateMessage,
)
from app.integrations.messaging.factory import get_messaging_provider
from app.models.notification import Notification
from app.repositories.notification_repository import NotificationRepository
from app.schemas.notification import (
    TERMINAL_STATUSES,
    NotificationStatus,
)
from app.schemas.refill import Contactability, RefillCandidate, RefillStatus
from app.services.refill_service import RefillService

logger = logging.getLogger(__name__)

CHANNEL_WHATSAPP = "whatsapp"

# The approved template. Name and language must match what Meta approved; they
# are read from the environment so a different WhatsApp Business Account can use
# its own approved template without a code change.
DEFAULT_TEMPLATE_NAME = "refill_reminder"
DEFAULT_TEMPLATE_LANGUAGE = "en"

# Give up after this many attempts on retryable errors. Small on purpose: a
# reminder that has failed three times is not a transient blip, and continuing to
# hammer Meta damages the number's quality rating for every other customer.
MAX_SEND_ATTEMPTS = 3


def template_name() -> str:
    return os.environ.get("WHATSAPP_TEMPLATE_NAME", DEFAULT_TEMPLATE_NAME).strip()


def template_language() -> str:
    return os.environ.get(
        "WHATSAPP_TEMPLATE_LANGUAGE", DEFAULT_TEMPLATE_LANGUAGE
    ).strip()


def pharmacy_name() -> str:
    """Appears in the message body, so it must be configurable per shop."""
    return os.environ.get("PHARMACY_NAME", "your pharmacy").strip()


class NotificationService:
    """Creates, sends and records refill reminders."""

    def __init__(
        self,
        db: Session,
        *,
        provider: MessagingProvider | None = None,
        refill_service: RefillService | None = None,
    ) -> None:
        self.db = db
        self.repository = NotificationRepository(db)
        # Injected in tests with the fake; resolved from configuration otherwise.
        # The factory returns the fake unless WHATSAPP_ENABLED is true, so a
        # default construction cannot message anyone.
        self.provider = provider or get_messaging_provider()
        self.refill_service = refill_service or RefillService(db)

    # -----------------------------------------------------------------
    # The one entry point worth calling
    # -----------------------------------------------------------------

    def send_reminder_for(
        self,
        *,
        source_sale_item_id: int,
        expected_refill_date: date,
        as_of: date | None = None,
    ) -> tuple[Notification | None, bool, str]:
        """Re-derive the opportunity, re-check it, then send at most once.

        Returns ``(notification, sent, reason)``.

        The caller passes the OPPORTUNITY's identity, not a pre-built candidate.
        That is deliberate: a scheduler's queued job and a pharmacist's click can
        both be minutes or hours stale, and the customer may have walked into the
        shop in between. Everything is re-derived from the database here so a
        stale trigger cannot produce a wrong message.
        """
        reference = as_of or today()

        candidate = self._find_candidate(
            source_sale_item_id=source_sale_item_id,
            expected_refill_date=expected_refill_date,
            as_of=reference,
        )

        if candidate is None:
            # Not an error: the customer almost certainly bought the medicine
            # again, which is the outcome the whole feature exists to produce.
            logger.info(
                "notification_eligibility_checked",
                extra={
                    "source_sale_item_id": source_sale_item_id,
                    "eligible": False,
                    "why": "no_longer_due",
                },
            )
            return None, False, "No longer due — the customer has already refilled."

        return self.send_for_candidate(candidate)

    def send_for_candidate(
        self, candidate: RefillCandidate
    ) -> tuple[Notification | None, bool, str]:
        """Create (or reuse) the notification for this candidate and try to send."""
        key = f"{candidate.idempotency_key}:{CHANNEL_WHATSAPP}"

        # ---- consent, checked in OUR code, before anything is built ----
        if candidate.contactability is not Contactability.CONTACTABLE:
            logger.info(
                "notification_eligibility_checked",
                extra={
                    "customer_id": candidate.customer_id,
                    "eligible": False,
                    "why": candidate.contactability.value,
                },
            )
            return None, False, self._contactability_reason(candidate.contactability)

        notification = self.repository.find_by_key(key)

        if notification is None:
            notification = self._create(key, candidate)
        else:
            decided = self._already_handled(notification)
            if decided is not None:
                return notification, False, decided

        return self._attempt_send(notification, candidate)

    # -----------------------------------------------------------------
    # Creation
    # -----------------------------------------------------------------

    def _create(self, key: str, candidate: RefillCandidate) -> Notification:
        """Insert the notification, tolerating a concurrent creator.

        The pre-check in ``send_for_candidate`` handles the ordinary case. This
        handles the race: two sweeps, or a sweep and a pharmacist's click, can
        both pass that check and reach here together. The UNIQUE index rejects
        the loser, and the loser reads the winner's row rather than failing —
        which is the difference between a duplicate message and no message.
        """
        params = [candidate.customer_name or "there", pharmacy_name()]

        try:
            notification = self.repository.create(
                idempotency_key=key,
                customer_id=candidate.customer_id,
                medicine_id=candidate.medicine_id,
                source_sale_item_id=candidate.source_sale_item_id,
                expected_refill_date=datetime.combine(
                    candidate.expected_refill_date, datetime.min.time()
                ),
                channel=CHANNEL_WHATSAPP,
                template_name=template_name(),
                template_language=template_language(),
                template_params=json.dumps(params),
                status=NotificationStatus.PENDING,
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.repository.find_by_key(key)
            if existing is None:
                raise
            logger.info("notification_create_raced", extra={"idempotency_key": key})
            return existing

        logger.info(
            "notification_created",
            extra={
                "notification_id": notification.id,
                "customer_id": candidate.customer_id,
                "medicine_id": candidate.medicine_id,
                "idempotency_key": key,
            },
        )
        return notification

    @staticmethod
    def _already_handled(notification: Notification) -> str | None:
        """Reason to stop, or None to go ahead with a send attempt."""
        status = notification.status

        if status in TERMINAL_STATUSES:
            return f"Already {status}."
        if status in {
            NotificationStatus.SENT,
            NotificationStatus.DELIVERED,
            NotificationStatus.READ,
        }:
            # THE duplicate guard in practice: a second sweep finds this row and
            # stops here rather than sending again.
            return f"Reminder already sent ({status})."
        if notification.attempts >= MAX_SEND_ATTEMPTS:
            return f"Gave up after {notification.attempts} attempts."
        return None

    # -----------------------------------------------------------------
    # Sending
    # -----------------------------------------------------------------

    def _attempt_send(
        self, notification: Notification, candidate: RefillCandidate
    ) -> tuple[Notification, bool, str]:
        notification.status = NotificationStatus.SENDING
        notification.attempts += 1
        self.db.commit()

        logger.info(
            "notification_send_started",
            extra={
                "notification_id": notification.id,
                "attempt": notification.attempts,
                "provider": self.provider.name,
                "template": notification.template_name,
            },
        )

        params = json.loads(notification.template_params or "[]")
        result = self.provider.send_template(
            TemplateMessage(
                to=candidate.customer_phone,
                template_name=notification.template_name,
                language=notification.template_language,
                body_params=params,
            )
        )

        now = datetime.now()

        if result.outcome is SendOutcome.ACCEPTED:
            notification.status = NotificationStatus.SENT
            notification.provider_message_id = result.provider_message_id
            notification.sent_at = now
            notification.last_error_code = None
            notification.last_error_message = None
            self.db.commit()

            logger.info(
                "notification_send_accepted",
                extra={
                    "notification_id": notification.id,
                    "attempt": notification.attempts,
                },
            )
            return notification, True, "Sent."

        notification.last_error_code = result.error_code
        notification.last_error_message = result.error_message

        if (
            result.outcome is SendOutcome.RETRYABLE
            and notification.attempts < MAX_SEND_ATTEMPTS
        ):
            # Back to PENDING so the next sweep picks it up. No sleep-and-retry
            # inside the request: holding a web worker open for a backoff is how
            # one slow provider takes down the whole API.
            notification.status = NotificationStatus.PENDING
            self.db.commit()

            logger.warning(
                "notification_send_failed",
                extra={
                    "notification_id": notification.id,
                    "attempt": notification.attempts,
                    "error_code": result.error_code,
                    "will_retry": True,
                },
            )
            return notification, False, f"Temporary failure — will retry ({result.error_code})."

        notification.status = NotificationStatus.FAILED
        notification.failed_at = now
        self.db.commit()

        logger.warning(
            "notification_send_failed",
            extra={
                "notification_id": notification.id,
                "attempt": notification.attempts,
                "error_code": result.error_code,
                "will_retry": False,
                "alert": result.alert,
            },
        )
        if result.alert:
            # Distinct event, because this class of failure stops EVERY message
            # for EVERY customer and needs a human now, not in the morning report.
            logger.error(
                "notification_provider_alert",
                extra={
                    "notification_id": notification.id,
                    "error_code": result.error_code,
                },
            )
        return notification, False, f"Failed ({result.error_code})."

    # -----------------------------------------------------------------
    # The sweep — called directly by the scheduler, never over HTTP
    # -----------------------------------------------------------------

    def run_sweep(
        self, *, as_of: date | None = None, limit: int = 50
    ) -> dict[str, int]:
        """Send reminders for every currently due, contactable candidate.

        Called directly by ``scripts/refill_sweep.py``. It does NOT make an HTTP
        request to this application's own API: that would add a network hop, a
        second set of failure modes and an authentication problem, to reach code
        already importable in-process.
        """
        reference = as_of or today()
        report = self.refill_service.find_candidates(
            as_of=reference, due_only=True, contactable_only=True, limit=limit
        )

        counts = {"considered": len(report.candidates), "sent": 0, "skipped": 0, "failed": 0}

        for candidate in report.candidates:
            _, sent, reason = self.send_for_candidate(candidate)
            if sent:
                counts["sent"] += 1
            elif reason.startswith("Failed"):
                counts["failed"] += 1
            else:
                counts["skipped"] += 1

        logger.info("notification_sweep_completed", extra={**counts, "as_of": str(reference)})
        return counts

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _find_candidate(
        self, *, source_sale_item_id: int, expected_refill_date: date, as_of: date
    ) -> RefillCandidate | None:
        """Re-derive the exact opportunity, or None if it no longer exists."""
        report = self.refill_service.find_candidates(
            as_of=as_of, due_only=False, limit=500
        )
        for candidate in report.candidates:
            if (
                candidate.source_sale_item_id == source_sale_item_id
                and candidate.expected_refill_date == expected_refill_date
                and candidate.status is RefillStatus.DUE
            ):
                return candidate
        return None

    @staticmethod
    def _contactability_reason(contactability: Contactability) -> str:
        return {
            Contactability.NOT_OPTED_IN: "Customer has not opted in to WhatsApp reminders.",
            Contactability.OPTED_OUT: "Customer has opted out of WhatsApp reminders.",
            Contactability.NO_PHONE: "No usable WhatsApp number on file.",
        }.get(contactability, "Customer cannot be contacted.")
