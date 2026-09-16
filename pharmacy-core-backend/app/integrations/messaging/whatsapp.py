"""WhatsApp Cloud API provider (M6.3).

This is the ONLY module in the codebase that knows Meta exists. Nothing in the
refill domain, the notification service or the frontend imports it directly —
they go through ``MessagingProvider``.

CONFIGURATION IS READ AT CONSTRUCTION, NOT AT IMPORT
----------------------------------------------------
So that a process without WhatsApp credentials can still import the app, run the
test suite and serve every other endpoint. A missing token is a send-time
failure, not a startup crash.

DISABLED BY DEFAULT
-------------------
``WHATSAPP_ENABLED`` defaults to ``false``. A developer who clones this repo and
runs the sweep does not message real customers by accident. Turning it on is a
deliberate act, and the flag is checked in the FACTORY rather than inside the
send method, so a disabled system builds a fake provider and no HTTP client is
ever constructed.

ERROR SEMANTICS
---------------
Meta's error codes are mapped into the three outcomes the service understands.
The mapping is the whole reason this class exists: retrying a 131026 (the number
is not on WhatsApp) can never succeed, and burning quota on it also damages the
number's quality rating, which throttles messages to everybody else.
"""

from __future__ import annotations

import logging
import os

import httpx

from app.integrations.messaging.base import (
    MessagingProvider,
    SendOutcome,
    SendResult,
    TemplateMessage,
)

logger = logging.getLogger("app.whatsapp")

DEFAULT_API_VERSION = "v21.0"
DEFAULT_BASE_URL = "https://graph.facebook.com"
DEFAULT_TIMEOUT_SECONDS = 15.0

# Errors that will never succeed on a retry. Retrying these wastes quota and
# damages the phone number's quality rating, which throttles delivery to every
# other customer.
PERMANENT_ERROR_CODES = {
    "131026",  # message undeliverable — not on WhatsApp, blocked, restricted
    "131047",  # re-engagement required (outside the window, no valid template)
    "131051",  # unsupported message type
    "132000",  # template param count mismatch — our bug, not a transient one
    "132001",  # template does not exist / not approved in this language
    "132005",  # template hydrated text too long
    "132007",  # template format character policy violated
    "133010",  # phone number not registered
}

# Errors that mean an operator must act NOW: every message to every customer is
# failing, not just this one.
ALERT_ERROR_CODES = {
    "190",    # access token expired / invalid
    "0",      # auth exception
    "10",     # permission denied
    "200",    # permission error
    "133004", # phone number is not verified / business account issue
}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else value


def whatsapp_is_enabled() -> bool:
    """Whether real sending is switched on. Defaults to FALSE."""
    return (_env("WHATSAPP_ENABLED", "false") or "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class WhatsAppConfigError(RuntimeError):
    """Raised when sending is enabled but the configuration is incomplete."""


class WhatsAppProvider(MessagingProvider):
    """Sends template messages through the Meta Cloud API."""

    name = "whatsapp"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        api_version: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.access_token = access_token or _env("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = phone_number_id or _env("WHATSAPP_PHONE_NUMBER_ID")
        self.api_version = api_version or _env("WHATSAPP_API_VERSION", DEFAULT_API_VERSION)
        self.base_url = (base_url or _env("WHATSAPP_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout

        if not self.access_token or not self.phone_number_id:
            raise WhatsAppConfigError(
                "WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID must be set "
                "when WHATSAPP_ENABLED is true."
            )

    @property
    def _endpoint(self) -> str:
        return f"{self.base_url}/{self.api_version}/{self.phone_number_id}/messages"

    def send_template(self, message: TemplateMessage) -> SendResult:
        """POST one template message. Never raises for a provider-side failure."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            # Meta expects the full international number without a "+".
            "to": self._to_e164_digits(message.to),
            "type": "template",
            "template": {
                "name": message.template_name,
                "language": {"code": message.language},
                "components": (
                    [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": p} for p in message.body_params
                            ],
                        }
                    ]
                    if message.body_params
                    else []
                ),
            },
        }

        try:
            response = httpx.post(
                self._endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=self.timeout,
            )
        except httpx.TimeoutException:
            # The request may or may not have reached Meta. Retryable, and the
            # idempotency key is what stops a retry becoming a second message.
            logger.warning("whatsapp_send_timeout", extra={"template": message.template_name})
            return SendResult(
                outcome=SendOutcome.RETRYABLE,
                error_code="timeout",
                error_message="Request to WhatsApp timed out.",
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "whatsapp_send_transport_error",
                extra={"error_type": type(exc).__name__},
            )
            return SendResult(
                outcome=SendOutcome.RETRYABLE,
                error_code="transport",
                error_message=f"{type(exc).__name__} contacting WhatsApp.",
            )

        return self._interpret(response)

    # -----------------------------------------------------------------
    # Response interpretation
    # -----------------------------------------------------------------

    def _interpret(self, response: httpx.Response) -> SendResult:
        body = self._safe_json(response)

        if response.is_success:
            messages = body.get("messages") or []
            wamid = messages[0].get("id") if messages else None
            if not wamid:
                # 200 with no message id should not happen. Treating it as
                # retryable would risk a duplicate we cannot detect, because
                # without a wamid no webhook can ever be matched to this row.
                return SendResult(
                    outcome=SendOutcome.PERMANENT,
                    error_code="no_message_id",
                    error_message="WhatsApp accepted the request but returned no message id.",
                )
            return SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id=wamid)

        error = body.get("error") or {}
        # Meta nests the useful code one level down; the top-level `code` is
        # coarser. Prefer the specific one when present.
        details = error.get("error_data") or {}
        code = str(error.get("code", response.status_code))
        subcode = str(error.get("error_subcode") or "") or None
        message = (
            details.get("details")
            or error.get("message")
            or f"WhatsApp returned HTTP {response.status_code}"
        )

        specific = subcode if subcode in PERMANENT_ERROR_CODES else code

        if specific in ALERT_ERROR_CODES or code in ALERT_ERROR_CODES:
            # Authentication and permission failures stop EVERY message, so they
            # are permanent for this notification and an operator alert.
            return SendResult(
                outcome=SendOutcome.PERMANENT,
                error_code=specific,
                error_message=self._redact(message),
                alert=True,
            )

        if specific in PERMANENT_ERROR_CODES or code in PERMANENT_ERROR_CODES:
            return SendResult(
                outcome=SendOutcome.PERMANENT,
                error_code=specific,
                error_message=self._redact(message),
            )

        if response.status_code == 429 or code == "80007":
            # Rate limited. Retry with backoff — the service decides when.
            return SendResult(
                outcome=SendOutcome.RETRYABLE,
                error_code=code,
                error_message="Rate limited by WhatsApp.",
            )

        if response.status_code >= 500:
            return SendResult(
                outcome=SendOutcome.RETRYABLE,
                error_code=code,
                error_message=self._redact(message),
            )

        # An unrecognised 4xx. Treated as PERMANENT on purpose: retrying an error
        # we do not understand is how a bug turns into thousands of failed sends
        # and a throttled phone number.
        return SendResult(
            outcome=SendOutcome.PERMANENT,
            error_code=code,
            error_message=self._redact(message),
        )

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict:
        """A gateway can answer with HTML; a parse failure must not be a crash."""
        try:
            data = response.json()
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    @staticmethod
    def _redact(message: str) -> str:
        """Trim provider text before it is stored or logged.

        Bounded because it lands in a VARCHAR(500), and never trusted to be free
        of anything sensitive — it is provider-authored text that ends up on a
        pharmacist's screen.
        """
        return (message or "")[:480]

    @staticmethod
    def _to_e164_digits(phone: str) -> str:
        """Meta wants digits including the country code, with no "+".

        Customer phones are stored as canonical 10-digit Indian mobiles by
        ``app/core/phone.py``, so the country code is prepended here. This is the
        one place that knows the pharmacy is in India; if the product ever sells
        elsewhere, the country code belongs on the customer row and this reads it
        from there instead.
        """
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) == 10:
            return f"91{digits}"
        return digits
