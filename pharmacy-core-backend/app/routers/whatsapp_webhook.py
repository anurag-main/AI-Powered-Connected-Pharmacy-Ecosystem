"""Meta webhook endpoints (M6.3).

Two endpoints, both required by Meta:

    GET  /api/v1/webhooks/whatsapp   one-time subscription handshake
    POST /api/v1/webhooks/whatsapp   status callbacks and inbound messages

WHY THIS ALWAYS RETURNS 200 FOR A SIGNED REQUEST
------------------------------------------------
Meta retries any non-2xx response, redelivering the ENTIRE batch. A 500 caused by
one unparseable event would therefore have Meta replay every event in that batch
forever, including the ones that processed correctly. So a signed request is
acknowledged and the problems are counted and logged instead.

An UNSIGNED request is a different matter and gets 403 — that is not Meta.
"""

import logging

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.whatsapp_webhook_service import (
    WhatsAppWebhookService,
    signature_is_valid,
    verify_subscription,
)

logger = logging.getLogger("app.whatsapp")

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.get("/whatsapp", summary="Meta webhook subscription handshake")
def verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    """Echo Meta's challenge when the verify token matches.

    Meta requires the challenge back as PLAIN TEXT. Returning it as JSON (with
    quotes) fails verification with a message that does not say why.
    """
    challenge = verify_subscription(hub_mode, hub_verify_token, hub_challenge)
    if challenge is None:
        logger.warning("whatsapp_webhook_verification_rejected")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    logger.info("whatsapp_webhook_verified")
    return Response(content=challenge, media_type="text/plain")


@router.post("/whatsapp", summary="Meta message status and inbound message callbacks")
async def receive(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    """Verify the signature over the RAW body, then apply the events."""
    raw = await request.body()

    # Read the raw bytes BEFORE parsing: re-serialising the parsed JSON changes
    # whitespace and key order, and the HMAC would never match.
    if not signature_is_valid(raw, x_hub_signature_256):
        logger.warning("whatsapp_webhook_bad_signature")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — any malformed body, not just JSONDecodeError
        logger.warning("whatsapp_webhook_malformed_body")
        # Signed but unparseable. Acknowledged so Meta stops retrying something
        # that will never parse.
        return Response(status_code=status.HTTP_200_OK)

    logger.info("whatsapp_webhook_received")
    WhatsAppWebhookService(db).process(payload if isinstance(payload, dict) else {})
    return Response(status_code=status.HTTP_200_OK)
