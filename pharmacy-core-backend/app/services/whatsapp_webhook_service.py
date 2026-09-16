"""Processes Meta webhook callbacks (M6.3).

WHAT ARRIVES
------------
Meta POSTs status updates for messages we sent (sent / delivered / read / failed)
and, if a customer replies, inbound messages. M6.3 records both and acts on the
statuses. **It does not interpret replies** — no intent classification, no LLM,
no auto-reply. A reply is stored as an event so M6.4 has the history, and so a
pharmacist knows the customer answered.

THREE THINGS MAKE THIS HARDER THAN IT LOOKS
-------------------------------------------
1. **Meta may deliver the same event more than once.** Documented behaviour, not
   a rare race. Deduplication is on (wamid, status) and is enforced by a UNIQUE
   constraint, not by a "have I seen this" set in memory.

2. **Events arrive out of order.** A late `sent` can land after `read`. Statuses
   are therefore applied only when they RANK HIGHER than what is stored, so a
   message never travels backwards.

3. **One message can emit both `delivered` and `failed`.** This happens in
   multi-device setups where a message reaches one device and fails on another.
   A `failed` that arrives after a successful delivery must NOT overwrite it —
   the message did reach the customer, and marking it failed would make the
   pharmacist chase a reminder that actually arrived.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.notification_repository import NotificationRepository
from app.schemas.notification import STATUS_RANK, NotificationStatus

logger = logging.getLogger("app.whatsapp")

# Meta status -> our status. Identical strings today, but the mapping is explicit
# so an unknown status Meta adds later is ignored rather than written to a column
# nothing understands.
PROVIDER_STATUS_MAP = {
    "sent": NotificationStatus.SENT,
    "delivered": NotificationStatus.DELIVERED,
    "read": NotificationStatus.READ,
    "failed": NotificationStatus.FAILED,
}


def verify_token() -> str | None:
    return os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN")


def app_secret() -> str | None:
    return os.environ.get("WHATSAPP_APP_SECRET")


def verify_subscription(mode: str | None, token: str | None, challenge: str | None) -> str | None:
    """Answer Meta's GET verification handshake.

    Meta sends hub.mode=subscribe with the token configured in the app dashboard
    and expects the challenge echoed back verbatim. Returns the challenge on
    success, or None so the router can answer 403.

    ``compare_digest`` rather than ``==`` because this compares a secret, and a
    short-circuiting comparison leaks its length and prefix through timing.
    """
    expected = verify_token()
    if not expected or mode != "subscribe" or not token or not challenge:
        return None
    if not hmac.compare_digest(token, expected):
        return None
    return challenge


def signature_is_valid(raw_body: bytes, header: str | None) -> bool:
    """Validate Meta's X-Hub-Signature-256 over the RAW request body.

    The raw bytes matter: re-serialising the parsed JSON changes whitespace and
    key order, and the HMAC would never match. The router therefore reads the
    body once, verifies it, and parses afterwards.

    Returns False when no app secret is configured — fail closed. An unsigned
    endpoint accepting status updates would let anyone mark any message read.
    """
    secret = app_secret()
    if not secret or not header:
        return False
    if not header.startswith("sha256="):
        return False

    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header[len("sha256=") :])


class WhatsAppWebhookService:
    """Applies provider callbacks to notification rows, exactly once each."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = NotificationRepository(db)

    def process(self, payload: dict) -> dict[str, int]:
        """Walk a webhook payload and apply every status it carries.

        Returns counts for the log and the tests. Malformed or unknown shapes are
        counted and skipped rather than raising: Meta retries a non-2xx, so a 500
        on one unparseable event would have Meta redeliver the whole batch
        forever, including the events that DID process.
        """
        counts = {"statuses": 0, "applied": 0, "duplicates": 0, "unknown": 0, "replies": 0}

        # Every level is type-checked, not just presence-checked. A payload like
        # {"entry": "oops"} would otherwise iterate the STRING character by
        # character and raise AttributeError on the first one — which becomes a
        # 500, which makes Meta redeliver the entire batch forever, including
        # every event that had already processed correctly.
        for entry in self._as_list(payload.get("entry")):
            for change in self._as_list(entry.get("changes")):
                value = change.get("value")
                if not isinstance(value, dict):
                    continue

                for status in self._as_list(value.get("statuses")):
                    counts["statuses"] += 1
                    outcome = self._apply_status(status)
                    counts[outcome] += 1

                for message in self._as_list(value.get("messages")):
                    # A customer replied. Recorded only — M6.3 builds no reply
                    # agent, and answering automatically without understanding
                    # the message is worse than not answering.
                    counts["replies"] += 1
                    logger.info(
                        "whatsapp_reply_received",
                        extra={
                            "message_type": message.get("type"),
                            # The body is deliberately NOT logged: it is a
                            # customer's own words about their medicine.
                        },
                    )

        self.db.commit()
        logger.info("whatsapp_webhook_processed", extra=counts)
        return counts

    # -----------------------------------------------------------------

    @staticmethod
    def _as_list(value) -> list[dict]:
        """Only the dict entries of something that claims to be a list.

        Anything else -- a string, a number, None, or a list holding those -- is
        dropped rather than raising. Meta's payloads are well formed in practice;
        this is about what a proxy, a truncation or a spoofed-but-correctly-signed
        request could produce.
        """
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _apply_status(self, status: dict) -> str:
        wamid = status.get("id")
        raw_status = status.get("status")

        if not wamid or raw_status not in PROVIDER_STATUS_MAP:
            logger.info("whatsapp_webhook_unknown_status", extra={"status": raw_status})
            return "unknown"

        mapped = PROVIDER_STATUS_MAP[raw_status]

        if self.repository.event_exists(provider_event_id=wamid, status=raw_status):
            # Meta redelivered. Nothing to do, and saying so is not an error.
            logger.debug("whatsapp_webhook_duplicate", extra={"status": raw_status})
            return "duplicates"

        notification = self.repository.find_by_provider_message_id(wamid)
        if notification is None:
            # A status for a message this system did not send — another app on
            # the same WhatsApp number, or a message predating this database.
            logger.info("whatsapp_webhook_unmatched", extra={"status": raw_status})
            return "unknown"

        error_code, error_message = self._first_error(status)

        try:
            self.repository.add_event(
                notification_id=notification.id,
                provider_event_id=wamid,
                status=raw_status,
                event_at=self._timestamp(status.get("timestamp")),
                error_code=error_code,
                error_message=error_message,
            )
        except IntegrityError:
            # Lost a race with a concurrent redelivery. The UNIQUE constraint is
            # the real guarantee; the pre-check above is just the fast path.
            self.db.rollback()
            return "duplicates"

        self._advance(notification, mapped, error_code, error_message)
        return "applied"

    @staticmethod
    def _advance(notification, new_status, error_code, error_message) -> None:
        """Move the notification forward, never backwards."""
        current = notification.status

        if new_status is NotificationStatus.FAILED:
            # A `failed` arriving after the message already reached the handset
            # is the multi-device case: delivered on one device, failed on
            # another. The customer got it, so delivery wins.
            if STATUS_RANK.get(current, 0) >= STATUS_RANK[NotificationStatus.DELIVERED]:
                logger.info(
                    "whatsapp_message_failed_after_delivery",
                    extra={"notification_id": notification.id, "kept": current},
                )
                return
            notification.status = NotificationStatus.FAILED
            notification.failed_at = datetime.now()
            notification.last_error_code = error_code
            notification.last_error_message = error_message
            logger.warning(
                "whatsapp_message_failed",
                extra={"notification_id": notification.id, "error_code": error_code},
            )
            return

        # Out-of-order protection: only ever move up the happy path.
        if STATUS_RANK.get(new_status, 0) <= STATUS_RANK.get(current, 0):
            logger.debug(
                "whatsapp_webhook_out_of_order",
                extra={"notification_id": notification.id, "current": current},
            )
            return

        notification.status = new_status
        now = datetime.now()
        if new_status is NotificationStatus.SENT and notification.sent_at is None:
            notification.sent_at = now
        elif new_status is NotificationStatus.DELIVERED:
            notification.delivered_at = now
            logger.info(
                "whatsapp_message_delivered", extra={"notification_id": notification.id}
            )
        elif new_status is NotificationStatus.READ:
            notification.read_at = now
            logger.info(
                "whatsapp_message_read", extra={"notification_id": notification.id}
            )

    @staticmethod
    def _first_error(status: dict) -> tuple[str | None, str | None]:
        errors = status.get("errors") or []
        if not errors:
            return None, None
        first = errors[0]
        code = first.get("code")
        message = first.get("title") or first.get("message")
        return (str(code) if code is not None else None), (str(message)[:480] if message else None)

    @staticmethod
    def _timestamp(value) -> datetime | None:
        """Meta sends a unix timestamp as a STRING."""
        try:
            return datetime.fromtimestamp(int(value))
        except (TypeError, ValueError):
            return None
