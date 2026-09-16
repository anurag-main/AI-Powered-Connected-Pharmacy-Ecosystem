"""In-memory messaging provider for tests and for a disabled system (M6.3).

This is NOT a mock of our own code. It is a real implementation of the
``MessagingProvider`` interface that records what it was asked to send instead of
sending it, which means the whole pipeline — eligibility, persistence, the state
machine, idempotency — runs exactly as it does in production, right up to the
wire.

It is also what a developer gets when ``WHATSAPP_ENABLED`` is false, so cloning
this repo and running the sweep cannot message a real customer.
"""

from __future__ import annotations

from app.integrations.messaging.base import (
    MessagingProvider,
    SendOutcome,
    SendResult,
    TemplateMessage,
)


class FakeMessagingProvider(MessagingProvider):
    """Captures sends. Optionally scripted to fail."""

    name = "fake"

    def __init__(self, *, results: list[SendResult] | None = None) -> None:
        # Every message it was asked to send, in order. Tests assert on
        # recipient, template and parameters.
        self.sent: list[TemplateMessage] = []
        # Scripted outcomes, consumed one per call. When exhausted (or never
        # supplied) every send is accepted.
        self._results = list(results or [])
        self._counter = 0

    def send_template(self, message: TemplateMessage) -> SendResult:
        self.sent.append(message)
        self._counter += 1

        if self._results:
            return self._results.pop(0)

        # A unique fake wamid per call, shaped like Meta's so anything that
        # parses or stores it behaves the same as in production.
        return SendResult(
            outcome=SendOutcome.ACCEPTED,
            provider_message_id=f"wamid.FAKE{self._counter:06d}",
        )

    # -- helpers for tests -------------------------------------------------

    @property
    def last(self) -> TemplateMessage | None:
        return self.sent[-1] if self.sent else None

    @property
    def call_count(self) -> int:
        return len(self.sent)
