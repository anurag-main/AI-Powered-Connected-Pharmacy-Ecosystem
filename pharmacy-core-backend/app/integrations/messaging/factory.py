"""Chooses which messaging provider the application uses (M6.3).

The switch lives here rather than inside the provider so that a disabled system
never constructs an HTTP client, never reads a token, and cannot make a network
call even if a bug reached the send path.

    WHATSAPP_ENABLED=false  (the default)  -> FakeMessagingProvider
    WHATSAPP_ENABLED=true                  -> WhatsAppProvider

Not ``lru_cache``d: the fake accumulates sent messages, and a cached instance
would leak one test's sends into the next.
"""

from __future__ import annotations

import logging

from app.integrations.messaging.base import MessagingProvider
from app.integrations.messaging.fake import FakeMessagingProvider
from app.integrations.messaging.whatsapp import WhatsAppProvider, whatsapp_is_enabled

logger = logging.getLogger("app.whatsapp")


def get_messaging_provider() -> MessagingProvider:
    """The provider for this process, decided by configuration."""
    if not whatsapp_is_enabled():
        logger.debug("messaging_provider_selected", extra={"provider": "fake"})
        return FakeMessagingProvider()

    logger.info("messaging_provider_selected", extra={"provider": "whatsapp"})
    return WhatsAppProvider()
