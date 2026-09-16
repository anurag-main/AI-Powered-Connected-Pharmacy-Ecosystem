"""Unit tests for the WhatsApp provider and webhook security (M6.3).

No network. The provider is driven with stubbed ``httpx.Response`` objects, so
Meta's documented response shapes are exercised without a token, a phone number
or an internet connection.

What matters here is the ERROR MAPPING. Retrying a 131026 (the recipient is not
on WhatsApp) can never succeed, and burning quota on it damages the phone
number's quality rating — which throttles delivery to every other customer. So
the classification of each error is asserted individually.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx
import pytest

from app.integrations.messaging.base import SendOutcome, TemplateMessage
from app.integrations.messaging.fake import FakeMessagingProvider
from app.integrations.messaging.whatsapp import (
    WhatsAppConfigError,
    WhatsAppProvider,
    whatsapp_is_enabled,
)
from app.services.whatsapp_webhook_service import (
    signature_is_valid,
    verify_subscription,
)


@pytest.fixture
def provider() -> WhatsAppProvider:
    return WhatsAppProvider(
        access_token="test-token",
        phone_number_id="123456",
        api_version="v21.0",
        base_url="https://graph.example.test",
    )


def response(status_code: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code, json=body, request=httpx.Request("POST", "https://x")
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_sending_is_disabled_by_default(monkeypatch):
    """A fresh clone must not be able to message real customers."""
    monkeypatch.delenv("WHATSAPP_ENABLED", raising=False)
    assert whatsapp_is_enabled() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_enabling_is_explicit(monkeypatch, value):
    monkeypatch.setenv("WHATSAPP_ENABLED", value)
    assert whatsapp_is_enabled() is True


def test_missing_credentials_fail_loudly_at_construction(monkeypatch):
    """Better than a confusing 401 on the first real send."""
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    with pytest.raises(WhatsAppConfigError):
        WhatsAppProvider()


def test_the_factory_returns_the_fake_when_disabled(monkeypatch):
    from app.integrations.messaging.factory import get_messaging_provider

    monkeypatch.setenv("WHATSAPP_ENABLED", "false")
    assert get_messaging_provider().name == "fake"


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


def test_the_indian_country_code_is_added(provider):
    """Customers are stored as canonical 10-digit mobiles; Meta wants 91xxxxxxxxxx."""
    assert provider._to_e164_digits("9876543210") == "919876543210"


def test_an_already_prefixed_number_is_not_double_prefixed(provider):
    assert provider._to_e164_digits("919876543210") == "919876543210"


def test_the_send_url_is_built_from_configuration(provider):
    assert provider._endpoint == "https://graph.example.test/v21.0/123456/messages"


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


def test_a_successful_send_returns_the_wamid(provider):
    result = provider._interpret(
        response(200, {"messages": [{"id": "wamid.ABC123"}]})
    )
    assert result.outcome is SendOutcome.ACCEPTED
    assert result.provider_message_id == "wamid.ABC123"


def test_a_200_without_a_message_id_is_permanent(provider):
    """Should never happen — and retrying risks a duplicate we cannot detect.

    Without a wamid no webhook can ever be matched to the notification, so a
    retry could deliver a second message with no way to notice.
    """
    result = provider._interpret(response(200, {"messages": []}))
    assert result.outcome is SendOutcome.PERMANENT


# ---------------------------------------------------------------------------
# Error classification — the reason this provider exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,label",
    [
        ("131026", "recipient not on WhatsApp"),
        ("131047", "re-engagement required"),
        ("132000", "template parameter count mismatch"),
        ("132001", "template does not exist"),
        ("133010", "number not registered"),
    ],
)
def test_permanent_errors_are_never_retried(provider, code, label):
    result = provider._interpret(
        response(400, {"error": {"code": int(code), "message": label}})
    )
    assert result.outcome is SendOutcome.PERMANENT, label


@pytest.mark.parametrize("code", ["190", "10", "200"])
def test_auth_failures_are_permanent_and_alert(provider, code):
    """These stop EVERY message for EVERY customer, not just this one."""
    result = provider._interpret(
        response(401, {"error": {"code": int(code), "message": "token expired"}})
    )
    assert result.outcome is SendOutcome.PERMANENT
    assert result.alert is True


def test_rate_limiting_is_retryable(provider):
    result = provider._interpret(response(429, {"error": {"code": 80007}}))
    assert result.outcome is SendOutcome.RETRYABLE


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_server_errors_are_retryable(provider, status_code):
    result = provider._interpret(response(status_code, {"error": {"code": 1}}))
    assert result.outcome is SendOutcome.RETRYABLE


def test_an_unrecognised_4xx_is_permanent_not_retryable(provider):
    """Retrying an error we do not understand is how a bug becomes thousands of
    failed sends and a throttled phone number."""
    result = provider._interpret(response(418, {"error": {"code": 99999}}))
    assert result.outcome is SendOutcome.PERMANENT


def test_an_html_error_body_does_not_crash(provider):
    """A gateway can answer with HTML; a parse failure must not be an exception."""
    raw = httpx.Response(
        status_code=502, text="<html>bad gateway</html>", request=httpx.Request("POST", "https://x")
    )
    assert provider._interpret(raw).outcome is SendOutcome.RETRYABLE


def test_provider_error_text_is_bounded(provider):
    """It lands in a VARCHAR(500) and on a pharmacist's screen."""
    result = provider._interpret(
        response(400, {"error": {"code": 131026, "message": "x" * 5000}})
    )
    assert len(result.error_message) <= 480


def test_a_timeout_is_retryable(provider, monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("app.integrations.messaging.whatsapp.httpx.post", boom)
    result = provider.send_template(
        TemplateMessage(to="9876543210", template_name="t", language="en")
    )
    assert result.outcome is SendOutcome.RETRYABLE
    assert result.error_code == "timeout"


def test_a_transport_error_is_retryable(provider, monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("app.integrations.messaging.whatsapp.httpx.post", boom)
    assert (
        provider.send_template(
            TemplateMessage(to="9876543210", template_name="t", language="en")
        ).outcome
        is SendOutcome.RETRYABLE
    )


# ---------------------------------------------------------------------------
# The fake
# ---------------------------------------------------------------------------


def test_the_fake_captures_what_it_was_asked_to_send():
    """It is a real implementation, not a mock of our own code."""
    fake = FakeMessagingProvider()
    fake.send_template(
        TemplateMessage(
            to="9876543210",
            template_name="refill_reminder",
            language="en",
            body_params=["Anurag", "Apna Medical"],
        )
    )

    assert fake.call_count == 1
    assert fake.last.to == "9876543210"
    assert fake.last.template_name == "refill_reminder"
    assert fake.last.body_params == ["Anurag", "Apna Medical"]


def test_the_fake_can_be_scripted_to_fail():
    from app.integrations.messaging.base import SendResult

    fake = FakeMessagingProvider(
        results=[SendResult(outcome=SendOutcome.RETRYABLE, error_code="timeout")]
    )
    assert fake.send_template(
        TemplateMessage(to="9", template_name="t", language="en")
    ).outcome is SendOutcome.RETRYABLE
    # Exhausted scripts fall back to accepting.
    assert fake.send_template(
        TemplateMessage(to="9", template_name="t", language="en")
    ).outcome is SendOutcome.ACCEPTED


# ---------------------------------------------------------------------------
# Webhook security
# ---------------------------------------------------------------------------


def test_subscription_verification_echoes_the_challenge(monkeypatch):
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "s3cret")
    assert verify_subscription("subscribe", "s3cret", "12345") == "12345"


@pytest.mark.parametrize(
    "mode,token",
    [("subscribe", "wrong"), ("unsubscribe", "s3cret"), (None, "s3cret"), ("subscribe", None)],
)
def test_subscription_verification_rejects_anything_else(monkeypatch, mode, token):
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "s3cret")
    assert verify_subscription(mode, token, "12345") is None


def test_verification_fails_closed_when_no_token_is_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", raising=False)
    assert verify_subscription("subscribe", "anything", "12345") is None


def test_a_valid_signature_passes(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    body = b'{"entry":[]}'
    digest = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()

    assert signature_is_valid(body, f"sha256={digest}") is True


def test_a_tampered_body_fails(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    digest = hmac.new(b"app-secret", b'{"entry":[]}', hashlib.sha256).hexdigest()

    assert signature_is_valid(b'{"entry":[{"evil":1}]}', f"sha256={digest}") is False


@pytest.mark.parametrize("header", [None, "", "abc", "sha1=deadbeef", "sha256=deadbeef"])
def test_bad_signature_headers_fail(monkeypatch, header):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    assert signature_is_valid(b"{}", header) is False


def test_signature_check_fails_closed_without_an_app_secret(monkeypatch):
    """An unsigned endpoint would let anyone mark any message as read."""
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    body = b"{}"
    digest = hmac.new(b"whatever", body, hashlib.sha256).hexdigest()

    assert signature_is_valid(body, f"sha256={digest}") is False
