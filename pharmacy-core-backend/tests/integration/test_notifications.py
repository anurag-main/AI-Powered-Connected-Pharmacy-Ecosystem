"""Integration tests for the notification pipeline and webhooks (M6.3).

Real database, real services, real state machine — with the fake messaging
provider standing in for Meta. That is the point of the provider boundary: every
line of the pipeline runs exactly as it does in production, right up to the wire.

The tests that matter most:

  * consent FAILS CLOSED — not contactable means no send attempt is even made
  * the same opportunity produces ONE message however many times it is processed
  * a `failed` webhook arriving after `delivered` does NOT overwrite delivery
  * a redelivered webhook is applied once
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.integrations.messaging.base import SendOutcome, SendResult
from app.integrations.messaging.fake import FakeMessagingProvider
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.notification import Notification, NotificationEvent
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.schemas.notification import NotificationStatus
from app.services.notification_service import NotificationService

AS_OF = date(2026, 9, 15)
WEBHOOK = "/api/v1/webhooks/whatsapp"
APP_SECRET = "test-app-secret"


@pytest.fixture(autouse=True)
def webhook_secrets(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verify-me")
    # Never let a test reach the real provider even if the factory is hit.
    monkeypatch.setenv("WHATSAPP_ENABLED", "false")


@pytest.fixture
def world(db_session):
    """One opted-in customer who ran out of medicine 4 days ago."""
    medicine = Medicine(
        name="Crocin 500",
        normalized_name="crocin 500",
        mrp=Decimal("20.00"),
        hsn_code="30049099",
    )
    customer = Customer(
        name="Anurag",
        phone="9876543210",
        whatsapp_opt_in_at=datetime(2026, 1, 1, 10, 0),
        whatsapp_consent_source="billing_counter",
    )
    db_session.add_all([medicine, customer])
    db_session.flush()

    batch = Batch(
        medicine_id=medicine.id,
        batch_number="B1",
        expiry_date=date(2028, 1, 1),
        quantity=100,
        cost_price=Decimal("10.00"),
    )
    db_session.add(batch)
    db_session.flush()

    sale = Sale(
        customer_id=customer.id,
        total_amount=Decimal("100.00"),
        sold_at=datetime(2026, 9, 1, 11, 0),
    )
    db_session.add(sale)
    db_session.flush()

    item = SaleItem(
        sale_id=sale.id,
        medicine_id=medicine.id,
        batch_id=batch.id,
        quantity=10,
        unit_price=Decimal("10.00"),
        line_total=Decimal("100.00"),
        days_supply=10,  # ran out 2026-09-11, so 4 days overdue at AS_OF
    )
    db_session.add(item)
    db_session.commit()

    return {
        "db": db_session,
        "customer": customer,
        "medicine_id": medicine.id,
        "sale_item_id": item.id,
        "expected_refill_date": date(2026, 9, 11),
    }


def service(world, provider=None) -> tuple[NotificationService, FakeMessagingProvider]:
    fake = provider or FakeMessagingProvider()
    return NotificationService(world["db"], provider=fake), fake


def send(world, provider=None, as_of=AS_OF):
    svc, fake = service(world, provider)
    result = svc.send_reminder_for(
        source_sale_item_id=world["sale_item_id"],
        expected_refill_date=world["expected_refill_date"],
        as_of=as_of,
    )
    return result, fake


def signed(client, body: dict):
    raw = json.dumps(body).encode()
    digest = hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        WEBHOOK, content=raw, headers={"X-Hub-Signature-256": f"sha256={digest}"}
    )


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_due_opted_in_customer_gets_one_message(world):
    (notification, sent, reason), fake = send(world)

    assert sent is True
    assert notification.status == NotificationStatus.SENT
    assert notification.provider_message_id.startswith("wamid.")
    assert fake.call_count == 1


def test_the_message_carries_the_template_and_parameters(world):
    _, fake = send(world)

    assert fake.last.template_name == "refill_reminder"
    assert fake.last.language == "en"
    # Customer name and pharmacy name only.
    assert fake.last.body_params[0] == "Anurag"
    assert len(fake.last.body_params) == 2


def test_the_message_never_names_the_medicine(world):
    """A WhatsApp message shows on a lock screen.

    "Your Metformin is due" tells anyone holding the phone that its owner is
    diabetic. The medicine is discussed in the shop, not in the notification.
    """
    _, fake = send(world)

    for param in fake.last.body_params:
        assert "crocin" not in param.lower()


def test_the_notification_records_which_template_was_used(world):
    """Templates get re-approved and reworded; last month's message must stay
    explainable by what was actually sent."""
    (notification, _, _), _ = send(world)

    assert notification.template_name == "refill_reminder"
    assert notification.template_language == "en"
    assert json.loads(notification.template_params) == ["Anurag", "Apna Medical"] or len(
        json.loads(notification.template_params)
    ) == 2


# ---------------------------------------------------------------------------
# Consent — fail closed
# ---------------------------------------------------------------------------


def test_a_customer_who_never_opted_in_is_never_contacted(world):
    world["customer"].whatsapp_opt_in_at = None
    world["db"].commit()

    (notification, sent, reason), fake = send(world)

    assert sent is False
    assert notification is None
    # The important assertion: no request was even constructed.
    assert fake.call_count == 0
    assert "not opted in" in reason.lower()


def test_an_opted_out_customer_is_never_contacted(world):
    world["customer"].whatsapp_opt_out_at = datetime(2026, 6, 1, 10, 0)
    world["db"].commit()

    (_, sent, reason), fake = send(world)

    assert sent is False
    assert fake.call_count == 0
    assert "opted out" in reason.lower()


def test_an_unusable_phone_number_blocks_the_send(world):
    """Consent is not the same as reachability. Rows predate phone validation."""
    world["customer"].phone = "12345"
    world["db"].commit()

    (_, sent, reason), fake = send(world)

    assert sent is False
    assert fake.call_count == 0
    assert "number" in reason.lower()


def test_no_notification_row_is_created_for_a_blocked_customer(world):
    world["customer"].whatsapp_opt_out_at = datetime(2026, 6, 1, 10, 0)
    world["db"].commit()
    send(world)

    assert world["db"].scalar(select(func.count()).select_from(Notification)) == 0


# ---------------------------------------------------------------------------
# Eligibility recheck — protects against stale jobs
# ---------------------------------------------------------------------------


def test_a_customer_who_already_refilled_is_not_messaged(world):
    """The scheduler's job may be hours stale; they may have walked in since."""
    db = world["db"]
    sale = Sale(
        customer_id=world["customer"].id,
        total_amount=Decimal("100.00"),
        sold_at=datetime(2026, 9, 14, 11, 0),
    )
    db.add(sale)
    db.flush()
    db.add(
        SaleItem(
            sale_id=sale.id,
            medicine_id=world["medicine_id"],
            batch_id=db.scalars(select(Batch)).first().id,
            quantity=10,
            unit_price=Decimal("10.00"),
            line_total=Decimal("100.00"),
            days_supply=10,
        )
    )
    db.commit()

    (notification, sent, reason), fake = send(world)

    assert sent is False
    assert fake.call_count == 0
    assert "already refilled" in reason.lower()


def test_a_not_yet_due_opportunity_is_not_messaged(world):
    (_, sent, _), fake = send(world, as_of=date(2026, 9, 5))

    assert sent is False
    assert fake.call_count == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_processing_the_same_opportunity_twice_sends_once(world):
    fake = FakeMessagingProvider()
    send(world, fake)
    (notification, sent_again, reason), _ = send(world, fake)

    assert sent_again is False
    assert "already sent" in reason.lower()
    assert fake.call_count == 1
    assert world["db"].scalar(select(func.count()).select_from(Notification)) == 1


def test_the_sweep_is_safe_to_run_repeatedly(world):
    fake = FakeMessagingProvider()
    svc = NotificationService(world["db"], provider=fake)

    first = svc.run_sweep(as_of=AS_OF)
    second = svc.run_sweep(as_of=AS_OF)
    third = svc.run_sweep(as_of=AS_OF)

    assert first["sent"] == 1
    assert second["sent"] == 0 and third["sent"] == 0
    assert fake.call_count == 1
    assert world["db"].scalar(select(func.count()).select_from(Notification)) == 1


def test_the_idempotency_key_includes_the_channel(world):
    """So a future voice reminder for the same opportunity is a separate row."""
    (notification, _, _), _ = send(world)
    assert notification.idempotency_key.endswith(":whatsapp")


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


def test_a_retryable_failure_goes_back_to_pending(world):
    fake = FakeMessagingProvider(
        results=[SendResult(outcome=SendOutcome.RETRYABLE, error_code="timeout")]
    )
    (notification, sent, reason), _ = send(world, fake)

    assert sent is False
    assert notification.status == NotificationStatus.PENDING
    assert notification.attempts == 1
    assert notification.last_error_code == "timeout"
    assert "will retry" in reason.lower()


def test_a_retry_succeeds_without_creating_a_second_notification(world):
    fake = FakeMessagingProvider(
        results=[SendResult(outcome=SendOutcome.RETRYABLE, error_code="timeout")]
    )
    send(world, fake)
    (notification, sent, _), _ = send(world, fake)

    assert sent is True
    assert notification.attempts == 2
    assert world["db"].scalar(select(func.count()).select_from(Notification)) == 1


def test_a_permanent_failure_is_not_retried(world):
    fake = FakeMessagingProvider(
        results=[SendResult(outcome=SendOutcome.PERMANENT, error_code="131026")]
    )
    (notification, sent, _), _ = send(world, fake)

    assert sent is False
    assert notification.status == NotificationStatus.FAILED
    assert notification.failed_at is not None

    # A later attempt must not resurrect it.
    (again, sent_again, reason), _ = send(world, FakeMessagingProvider())
    assert sent_again is False
    assert "already failed" in reason.lower()


def test_retries_give_up_after_the_limit(world):
    from app.services.notification_service import MAX_SEND_ATTEMPTS

    fake = FakeMessagingProvider(
        results=[
            SendResult(outcome=SendOutcome.RETRYABLE, error_code="timeout")
            for _ in range(MAX_SEND_ATTEMPTS)
        ]
    )
    for _ in range(MAX_SEND_ATTEMPTS):
        (notification, _, _), _ = send(world, fake)

    assert notification.attempts == MAX_SEND_ATTEMPTS
    assert notification.status == NotificationStatus.FAILED


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def status_payload(wamid: str, status: str, *, errors=None, timestamp="1757923200"):
    entry = {"id": wamid, "status": status, "timestamp": timestamp, "recipient_id": "919876543210"}
    if errors:
        entry["errors"] = errors
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {"field": "messages", "value": {"messaging_product": "whatsapp", "statuses": [entry]}}
                ],
            }
        ],
    }


@pytest.fixture
def sent_notification(world):
    (notification, _, _), _ = send(world)
    return notification


def test_webhook_verification_echoes_the_challenge(client):
    response = client.get(
        WEBHOOK,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "1158201444",
        },
    )
    assert response.status_code == 200
    # Plain text, not JSON — quotes would fail Meta's verification.
    assert response.text == "1158201444"


def test_webhook_verification_rejects_a_wrong_token(client):
    response = client.get(
        WEBHOOK,
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
    )
    assert response.status_code == 403


def test_an_unsigned_webhook_is_rejected(client):
    """Without this anyone could mark any message as read."""
    assert client.post(WEBHOOK, json=status_payload("wamid.X", "delivered")).status_code == 403


def test_a_tampered_webhook_is_rejected(client):
    raw = json.dumps(status_payload("wamid.X", "delivered")).encode()
    digest = hmac.new(APP_SECRET.encode(), b"different", hashlib.sha256).hexdigest()

    response = client.post(
        WEBHOOK, content=raw, headers={"X-Hub-Signature-256": f"sha256={digest}"}
    )
    assert response.status_code == 403


def test_delivered_then_read_advances_the_notification(client, world, sent_notification):
    wamid = sent_notification.provider_message_id

    assert signed(client, status_payload(wamid, "delivered")).status_code == 200
    world["db"].refresh(sent_notification)
    assert sent_notification.status == NotificationStatus.DELIVERED
    assert sent_notification.delivered_at is not None

    assert signed(client, status_payload(wamid, "read")).status_code == 200
    world["db"].refresh(sent_notification)
    assert sent_notification.status == NotificationStatus.READ
    assert sent_notification.read_at is not None


def test_a_redelivered_event_is_applied_once(client, world, sent_notification):
    """Meta documents that it may deliver the same event more than once."""
    wamid = sent_notification.provider_message_id

    signed(client, status_payload(wamid, "delivered"))
    signed(client, status_payload(wamid, "delivered"))
    signed(client, status_payload(wamid, "delivered"))

    events = world["db"].scalars(
        select(NotificationEvent).where(NotificationEvent.status == "delivered")
    ).all()
    assert len(events) == 1


def test_an_out_of_order_event_does_not_move_the_status_backwards(
    client, world, sent_notification
):
    """A late `sent` must not drag a read message back to sent."""
    wamid = sent_notification.provider_message_id

    signed(client, status_payload(wamid, "read"))
    signed(client, status_payload(wamid, "sent"))

    world["db"].refresh(sent_notification)
    assert sent_notification.status == NotificationStatus.READ


def test_failed_after_delivered_does_not_overwrite_delivery(
    client, world, sent_notification
):
    """The multi-device case: delivered on one device, failed on another.

    The customer did receive it. Marking it failed would send a pharmacist
    chasing a reminder that actually arrived.
    """
    wamid = sent_notification.provider_message_id

    signed(client, status_payload(wamid, "delivered"))
    signed(
        client,
        status_payload(wamid, "failed", errors=[{"code": 131026, "title": "undeliverable"}]),
    )

    world["db"].refresh(sent_notification)
    assert sent_notification.status == NotificationStatus.DELIVERED


def test_a_failure_before_delivery_does_mark_it_failed(client, world, sent_notification):
    wamid = sent_notification.provider_message_id

    signed(
        client,
        status_payload(wamid, "failed", errors=[{"code": 131026, "title": "undeliverable"}]),
    )

    world["db"].refresh(sent_notification)
    assert sent_notification.status == NotificationStatus.FAILED
    assert sent_notification.last_error_code == "131026"


def test_a_status_for_an_unknown_message_is_acknowledged_not_an_error(client):
    """Another app on the same number, or a message predating this database.

    Must still be 200: a non-2xx makes Meta redeliver the whole batch forever.
    """
    assert signed(client, status_payload("wamid.NEVER_SEEN", "delivered")).status_code == 200


def test_a_malformed_payload_is_acknowledged(client):
    assert signed(client, {"entry": "not-a-list"}).status_code == 200
    assert signed(client, {}).status_code == 200


def test_an_unknown_status_value_is_ignored(client, sent_notification):
    assert signed(client, status_payload(sent_notification.provider_message_id, "warp")).status_code == 200


def test_an_inbound_reply_is_acknowledged_but_not_interpreted(client, world):
    """M6.3 builds no reply agent. The event is recorded; nothing answers."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.REPLY",
                                    "timestamp": "1757923200",
                                    "type": "text",
                                    "text": {"body": "Yes, I need it"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    assert signed(client, payload).status_code == 200


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


def test_manual_send_endpoint_is_idempotent(client, world):
    body = {
        "source_sale_item_id": world["sale_item_id"],
        "expected_refill_date": "2026-09-11",
    }

    # as_of defaults to the real today, and the opportunity is from 2026-09-01
    # with a 10-day supply, so it is due on any real date after 2026-09-11.
    first = client.post("/api/v1/notifications/refill-reminder", json=body)
    second = client.post("/api/v1/notifications/refill-reminder", json=body)

    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["sent"] is False
    assert world["db"].scalar(select(func.count()).select_from(Notification)) <= 1


def test_the_api_never_exposes_the_provider_message_id(client, world):
    """A wamid is an identifier for a customer's message. The browser has no use
    for it, so it does not travel there."""
    client.post(
        "/api/v1/notifications/refill-reminder",
        json={
            "source_sale_item_id": world["sale_item_id"],
            "expected_refill_date": "2026-09-11",
        },
    )
    body = client.get("/api/v1/notifications").text

    assert "provider_message_id" not in body
    assert "wamid" not in body


def test_no_response_ever_contains_a_token(client, world):
    client.post(
        "/api/v1/notifications/refill-reminder",
        json={
            "source_sale_item_id": world["sale_item_id"],
            "expected_refill_date": "2026-09-11",
        },
    )
    body = client.get("/api/v1/notifications").text.lower()

    for secret in ("access_token", "app_secret", "bearer", "eaag"):
        assert secret not in body
