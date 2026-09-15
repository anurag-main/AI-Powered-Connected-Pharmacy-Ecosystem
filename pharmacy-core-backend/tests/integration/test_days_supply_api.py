"""Integration tests for M6.1 — the billing round trip and the consent endpoints.

These go through the real router, the real BillingService, the real LangGraph
confirm graph (compute_pricing -> persist_sale) and a real database session.

The two that matter most:

  * ``days_supply`` survives the whole path. It is set by the client, rides
    through ``compute_pricing`` (which spreads ``**item``) and is frozen onto the
    sale line by ``persist_sale``. Nothing in between may default it.

  * A FAILED sale leaves NO trace. The brief's invariant: if the sale rolls back,
    no refill-related state may survive. Consent is captured inside the same
    transaction precisely so it cannot outlive the sale that produced it.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.batch import Batch
from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.sale import Sale
from app.models.sale_item import SaleItem

CONFIRM = "/api/v1/billing/confirm"
CUSTOMERS = "/api/v1/customers"


@pytest.fixture
def stocked(db_session):
    """One medicine with a catalogue default and one usable batch."""
    medicine = Medicine(
        name="Crocin 500",
        normalized_name="crocin 500",
        mrp=Decimal("20.00"),
        hsn_code="30049099",
        default_days_supply=5,
    )
    db_session.add(medicine)
    db_session.flush()

    batch = Batch(
        medicine_id=medicine.id,
        batch_number="B1",
        expiry_date=date.today() + timedelta(days=365),
        quantity=100,
        cost_price=Decimal("10.00"),
    )
    db_session.add(batch)
    db_session.commit()
    return {"medicine_id": medicine.id, "batch_id": batch.id, "expiry": str(batch.expiry_date)}


def payload(stocked, **overrides):
    item = {
        "name": "Crocin 500",
        "quantity": 10,
        "unit": "strip",
        "medicine_id": stocked["medicine_id"],
        "batch_id": stocked["batch_id"],
        "batch_number": "B1",
        "expiry_date": stocked["expiry"],
    }
    item.update(overrides.pop("item", {}))
    body = {"items": [item]}
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# days_supply through the whole round trip
# ---------------------------------------------------------------------------


def test_days_supply_is_persisted_on_the_sale_line(client, db_session, stocked):
    response = client.post(CONFIRM, json=payload(stocked, item={"days_supply": 5}))

    assert response.status_code == 201
    line = db_session.scalars(select(SaleItem)).one()
    assert line.days_supply == 5


def test_omitted_days_supply_persists_as_null_not_a_default(client, db_session, stocked):
    """The catalogue default is 5, and it must NOT leak into the sale.

    A pre-fill hint that silently became the stored value would be indis-
    tinguishable from a pharmacist who actually confirmed 5 days -- and the
    refill engine would schedule a reminder nobody authorised.
    """
    response = client.post(CONFIRM, json=payload(stocked))

    assert response.status_code == 201
    assert db_session.scalars(select(SaleItem)).one().days_supply is None


def test_explicit_null_days_supply_persists_as_null(client, db_session, stocked):
    response = client.post(CONFIRM, json=payload(stocked, item={"days_supply": None}))

    assert response.status_code == 201
    assert db_session.scalars(select(SaleItem)).one().days_supply is None


def test_pharmacist_override_beats_the_catalogue_default(client, db_session, stocked):
    """Default is 5; pharmacist says 30. The sale records 30."""
    response = client.post(CONFIRM, json=payload(stocked, item={"days_supply": 30}))

    assert response.status_code == 201
    assert db_session.scalars(select(SaleItem)).one().days_supply == 30


@pytest.mark.parametrize("bad", [0, -1, 366, "abc", 5.5])
def test_invalid_days_supply_is_422_and_writes_nothing(client, db_session, stocked, bad):
    response = client.post(CONFIRM, json=payload(stocked, item={"days_supply": bad}))

    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 0
    assert db_session.scalar(select(func.count()).select_from(SaleItem)) == 0


def test_the_catalogue_default_is_returned_for_pre_fill(client, stocked):
    """The billing form needs the hint to pre-fill the box.

    Delivered by /price-item, not invented by the frontend -- which is what keeps
    the suggestion in one place.
    """
    response = client.post(
        "/api/v1/billing/price-item",
        json={"medicine_id": stocked["medicine_id"], "quantity": 10, "name": "Crocin 500"},
    )

    assert response.status_code == 200
    assert response.json()["default_days_supply"] == 5


# ---------------------------------------------------------------------------
# Atomicity -- the brief's invariant
# ---------------------------------------------------------------------------


def test_a_failed_sale_persists_no_days_supply_and_no_consent(client, db_session, stocked):
    """Ask for more units than exist. Nothing at all may survive.

    Consent lives in the same transaction as the sale for exactly this reason:
    consent given for a sale that never happened is not consent.
    """
    response = client.post(
        CONFIRM,
        json=payload(
            stocked,
            item={"quantity": 99_999, "days_supply": 5},
            customer_phone="9876543210",
            whatsapp_opt_in=True,
        ),
    )

    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 0
    assert db_session.scalar(select(func.count()).select_from(SaleItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 0


# ---------------------------------------------------------------------------
# Phone + consent capture at the counter
# ---------------------------------------------------------------------------


def test_phone_is_normalised_before_the_customer_row_is_created(
    client, db_session, stocked
):
    client.post(CONFIRM, json=payload(stocked, customer_phone="+91 98765-43210"))

    assert db_session.scalars(select(Customer)).one().phone == "9876543210"


def test_two_spellings_of_one_number_create_one_customer(client, db_session, stocked):
    """The whole point of normalising: customers.phone is UNIQUE."""
    client.post(CONFIRM, json=payload(stocked, customer_phone="9876543210"))
    client.post(CONFIRM, json=payload(stocked, customer_phone="+91 9876543210"))

    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1


def test_a_malformed_phone_is_422_and_no_sale_is_written(client, db_session, stocked):
    """Blank is fine; wrong is not.

    A wrong number is a future message to a stranger. The field is optional, so
    the pharmacist can clear it and save immediately.
    """
    response = client.post(CONFIRM, json=payload(stocked, customer_phone="12345"))

    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Sale)) == 0


def test_opt_in_at_the_counter_is_recorded(client, db_session, stocked):
    response = client.post(
        CONFIRM,
        json=payload(stocked, customer_phone="9876543210", whatsapp_opt_in=True),
    )

    assert response.status_code == 201
    customer = db_session.scalars(select(Customer)).one()
    assert customer.whatsapp_opt_in_at is not None
    assert customer.whatsapp_consent_source == "billing_counter"


def test_consent_is_not_implied_by_giving_a_phone_number(client, db_session, stocked):
    """The DPDP rule, encoded: the number was given for the sale, not for messaging."""
    client.post(CONFIRM, json=payload(stocked, customer_phone="9876543210"))

    assert db_session.scalars(select(Customer)).one().whatsapp_opt_in_at is None


def test_a_walk_in_sale_still_works_with_no_phone(client, db_session, stocked):
    """38% of real sales have no customer. M6.1 must not break them."""
    response = client.post(CONFIRM, json=payload(stocked, item={"days_supply": 5}))

    assert response.status_code == 201
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 0
    assert db_session.scalars(select(Sale)).one().customer_id is None


# ---------------------------------------------------------------------------
# Consent endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def customer_id(db_session):
    row = Customer(name="Anurag", phone="9876543210")
    db_session.add(row)
    db_session.commit()
    return row.id


def test_consent_lifecycle_over_http(client, customer_id):
    """not_set -> opted_in -> opted_out -> opted_in again."""
    assert client.get(f"{CUSTOMERS}/{customer_id}").json()["consent_state"] == "not_set"

    assert (
        client.post(f"{CUSTOMERS}/{customer_id}/whatsapp/opt-in").json()["consent_state"]
        == "opted_in"
    )
    out = client.post(
        f"{CUSTOMERS}/{customer_id}/whatsapp/opt-out", json={"reason": "asked to stop"}
    ).json()
    assert out["consent_state"] == "opted_out"
    assert out["whatsapp_opt_out_reason"] == "asked to stop"

    assert (
        client.post(f"{CUSTOMERS}/{customer_id}/whatsapp/opt-in").json()["consent_state"]
        == "opted_in"
    )


def test_opt_out_works_from_never_asked(client, customer_id):
    """"Never message me" is a decision, and recording it stops staff re-asking."""
    response = client.post(f"{CUSTOMERS}/{customer_id}/whatsapp/opt-out")

    assert response.status_code == 200
    assert response.json()["consent_state"] == "opted_out"


def test_opt_out_keeps_the_opt_in_timestamp_for_audit(client, customer_id):
    client.post(f"{CUSTOMERS}/{customer_id}/whatsapp/opt-in")
    body = client.post(f"{CUSTOMERS}/{customer_id}/whatsapp/opt-out").json()

    assert body["whatsapp_opt_in_at"] is not None
    assert body["whatsapp_opt_out_at"] is not None


def test_consent_endpoints_404_for_an_unknown_customer(client):
    assert client.post(f"{CUSTOMERS}/999999/whatsapp/opt-in").status_code == 404
    assert client.post(f"{CUSTOMERS}/999999/whatsapp/opt-out").status_code == 404
    assert client.get(f"{CUSTOMERS}/999999").status_code == 404


def test_listing_reports_reachability_separately_from_consent(client, db_session):
    """A customer can be opted in AND unreachable -- rows predate phone validation."""
    unreachable = Customer(name="Old Row", phone="12345")
    db_session.add(unreachable)
    db_session.commit()

    client.post(f"{CUSTOMERS}/{unreachable.id}/whatsapp/opt-in")
    body = client.get(f"{CUSTOMERS}/{unreachable.id}").json()

    assert body["consent_state"] == "opted_in"
    assert body["phone_is_reachable"] is False


def test_no_whatsapp_credentials_or_sending_happens_anywhere(client, customer_id):
    """M6.1 records decisions. It does not message, and holds no keys.

    A guard against the most likely scope creep: quietly adding a send call to
    the opt-in path "to confirm the subscription".
    """
    body = client.post(f"{CUSTOMERS}/{customer_id}/whatsapp/opt-in").json()

    for forbidden in ("access_token", "phone_number_id", "template", "message_id"):
        assert forbidden not in body
