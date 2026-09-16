"""The messaging provider boundary (M6.3).

WHY AN ABSTRACTION AT ALL
-------------------------
Not to build a messaging framework. It exists for exactly two reasons:

1. **Tests must never call Meta.** ``FakeMessagingProvider`` satisfies this
   interface, so the whole notification pipeline is testable end to end without
   a token, a network or a real phone.
2. **Voice is coming.** M7 adds a provider that dials a number instead of
   sending a template. The notification service should not change when it does.

WHAT IT DELIBERATELY IS NOT
---------------------------
There is no queue, no broker, no plugin registry and no retry loop in here. A
provider does one thing: attempt one send, and report what happened in terms the
domain understands. Deciding whether to retry is a policy question and lives in
the service, because the policy depends on the notification, not on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class SendOutcome(StrEnum):
    """What happened, in terms the notification service can act on.

    Deliberately three, not a passthrough of the provider's error codes. The
    service needs to answer one question — *should we try again?* — and mapping
    provider-specific codes into this vocabulary is the provider's job, because
    the provider is the only layer that should know what 131026 means.
    """

    ACCEPTED = "accepted"
    # Worth another go later: timeout, 5xx, rate limit.
    RETRYABLE = "retryable"
    # Never worth retrying: the number is not on WhatsApp, the template is wrong,
    # the token is invalid. Retrying burns quota and hurts the number's quality
    # rating without any chance of success.
    PERMANENT = "permanent"


@dataclass(frozen=True)
class SendResult:
    """The result of one send attempt."""

    outcome: SendOutcome
    # Meta's wamid when accepted. This is what every later webhook is keyed on.
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    # Whether an operator needs to know NOW rather than at the next report — an
    # expired token stops every message for every customer, which is a different
    # class of problem from one unreachable number.
    alert: bool = False


@dataclass(frozen=True)
class TemplateMessage:
    """One template send request, in provider-neutral terms.

    Body parameters are a positional list because that is what WhatsApp's
    approved templates take: {{1}}, {{2}}. Named parameters would be a nicer API
    and a lie about what the platform accepts.
    """

    to: str
    template_name: str
    language: str
    body_params: list[str] = field(default_factory=list)


class MessagingProvider(Protocol):
    """Anything that can attempt to deliver a template message.

    A Protocol rather than a base class, matching ``repositories/protocols.py``:
    implementations are checked structurally, so the fake does not have to
    inherit from anything to be substitutable.
    """

    name: str

    def send_template(self, message: TemplateMessage) -> SendResult:
        """Attempt ONE send. Must not raise for provider-side failures.

        A network error, a 4xx and a 5xx all come back as a ``SendResult``,
        because "the provider said no" is an ordinary outcome that the service
        records against the notification. Only genuine programmer errors should
        escape as exceptions.
        """
        ...
