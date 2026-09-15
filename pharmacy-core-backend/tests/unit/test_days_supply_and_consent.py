"""Unit tests for M6.1 — days supply, phone normalisation and WhatsApp consent.

WHAT MATTERS HERE
-----------------
None of this code sends anything. It records facts a later milestone will act
on, which makes the tests about one question: is the fact recorded EXACTLY as
given, including the absence of one?

The load-bearing case is ``days_supply IS NULL``. A NULL means the pharmacist
did not know how long a medicine would last, and the refill engine must skip
that line. Any code path that quietly turns NULL into a number would produce a
confidently-timed health-adjacent message built on a value nobody supplied, so
several tests exist purely to prove that never happens.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.phone import (
    InvalidPhoneNumberError,
    is_valid_indian_mobile,
    normalize_indian_mobile,
)
from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.schemas.billing import ConfirmLineItem, ConfirmSaleRequest
from app.services.customer_service import (
    ConsentState,
    CustomerService,
    consent_state,
    is_contactable,
)


# ---------------------------------------------------------------------------
# Phone normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9876543210", "9876543210"),
        ("+91 9876543210", "9876543210"),
        ("+91 98765-43210", "9876543210"),
        ("919876543210", "9876543210"),
        ("09876543210", "9876543210"),
        ("  9876543210  ", "9876543210"),
        ("(98765) 43210", "9876543210"),
    ],
)
def test_every_spelling_of_one_number_normalises_to_one_string(raw, expected):
    """The reason this exists: customers.phone is UNIQUE.

    Before M6.1 each of these created a separate customer row for one person,
    and the future refill engine would have messaged them four times.
    """
    assert normalize_indian_mobile(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_blank_is_not_an_error(raw):
    """No phone is an ordinary walk-in sale, not a validation failure."""
    assert normalize_indian_mobile(raw) is None


@pytest.mark.parametrize("raw", ["-", "()", "abcdefghij", "n/a"])
def test_typed_characters_with_no_digits_are_an_error_not_a_blank(raw):
    """Something was typed, so it was an attempt at a phone number.

    Treating it as "not given" would record the sale as a walk-in and the
    pharmacist would never learn the number did not save.
    """
    with pytest.raises(InvalidPhoneNumberError):
        normalize_indian_mobile(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "12345",              # too short
        "98765432101",        # 11 digits, no leading 0
        "5876543210",         # Indian mobiles never start below 6
        "1234567890",
        "+1 415 555 0123",    # not an Indian number
    ],
)
def test_implausible_numbers_are_rejected_not_stored(raw):
    """A wrong number does not bounce -- it reaches a stranger.

    Rejecting at the boundary is cheap while the pharmacist is still standing
    there. Storing it is expensive later, when it addresses a real message.
    """
    with pytest.raises(InvalidPhoneNumberError):
        normalize_indian_mobile(raw)


def test_is_valid_helper_does_not_raise():
    """Read paths need a yes/no, not an exception."""
    assert is_valid_indian_mobile("9876543210") is True
    assert is_valid_indian_mobile("123") is False
    assert is_valid_indian_mobile(None) is False


# ---------------------------------------------------------------------------
# days_supply validation at the API contract
# ---------------------------------------------------------------------------


def _line(**overrides) -> dict:
    base = {
        "name": "Crocin 500",
        "quantity": 10,
        "unit": "strip",
        "medicine_id": 1,
        "batch_id": 1,
        "batch_number": "B1",
        "expiry_date": "2027-01-01",
    }
    base.update(overrides)
    return base


def test_days_supply_may_be_omitted_entirely():
    """Omission is a real answer: "unknown"."""
    item = ConfirmLineItem(**_line())
    assert item.days_supply is None


def test_days_supply_may_be_explicitly_null():
    item = ConfirmLineItem(**_line(days_supply=None))
    assert item.days_supply is None


@pytest.mark.parametrize("value", [1, 5, 30, 365])
def test_valid_days_supply_accepted(value):
    assert ConfirmLineItem(**_line(days_supply=value)).days_supply == value


def test_zero_is_rejected_so_unknown_has_exactly_one_spelling():
    """0 must NOT become a second way of saying "unknown".

    Zero days of supply is not a thing. Allowing it would give the refill engine
    two values meaning the same thing that would behave differently in a date
    comparison.
    """
    with pytest.raises(ValueError):
        ConfirmLineItem(**_line(days_supply=0))


@pytest.mark.parametrize("value", [-1, -30, 366, 3650, 100_000])
def test_out_of_range_rejected(value):
    """366 upward is refused: it parks a reminder implausibly far out."""
    with pytest.raises(ValueError):
        ConfirmLineItem(**_line(days_supply=value))


@pytest.mark.parametrize("value", ["abc", "", [], {}, 5.5])
def test_non_integer_rejected(value):
    with pytest.raises(ValueError):
        ConfirmLineItem(**_line(days_supply=value))


def test_numeric_string_is_coerced():
    """An <input type="number"> yields a string; Pydantic coerces "5" to 5."""
    assert ConfirmLineItem(**_line(days_supply="5")).days_supply == 5


# ---------------------------------------------------------------------------
# The confirm request as a whole
# ---------------------------------------------------------------------------


def test_phone_is_normalised_by_the_request_schema():
    request = ConfirmSaleRequest(items=[_line()], customer_phone="+91 98765-43210")
    assert request.customer_phone == "9876543210"


def test_bad_phone_fails_the_whole_request():
    with pytest.raises(ValueError):
        ConfirmSaleRequest(items=[_line()], customer_phone="12345")


def test_consent_defaults_to_false():
    """Consent is never implied by handing over a phone number.

    Under the DPDP Act the number is given for the sale; messaging is a separate
    purpose needing its own affirmative act. The default encodes that.
    """
    request = ConfirmSaleRequest(items=[_line()], customer_phone="9876543210")
    assert request.whatsapp_opt_in is False


# ---------------------------------------------------------------------------
# Consent state derivation -- pure, no database
# ---------------------------------------------------------------------------


class _FakeCustomer:
    def __init__(self, opt_in=None, opt_out=None, phone="9876543210"):
        self.whatsapp_opt_in_at = opt_in
        self.whatsapp_opt_out_at = opt_out
        self.phone = phone


NOW = datetime(2026, 9, 15, 10, 0, 0)
EARLIER = NOW - timedelta(days=30)


def test_never_asked_is_not_set():
    """Distinct from opted_out: this customer may still be asked at the counter."""
    assert consent_state(_FakeCustomer()) is ConsentState.NOT_SET


def test_opt_in_only():
    assert consent_state(_FakeCustomer(opt_in=NOW)) is ConsentState.OPTED_IN


def test_opt_out_only():
    """Opting out without ever opting in is legal and must be recorded."""
    assert consent_state(_FakeCustomer(opt_out=NOW)) is ConsentState.OPTED_OUT


def test_opt_out_after_opt_in_wins():
    assert consent_state(_FakeCustomer(opt_in=EARLIER, opt_out=NOW)) is ConsentState.OPTED_OUT


def test_re_opt_in_after_opt_out_wins():
    """The whole reason consent is two timestamps rather than a boolean."""
    assert consent_state(_FakeCustomer(opt_in=NOW, opt_out=EARLIER)) is ConsentState.OPTED_IN


def test_identical_timestamps_resolve_to_opted_out():
    """The ordering is unknowable, so the safe reading is "no consent"."""
    assert consent_state(_FakeCustomer(opt_in=NOW, opt_out=NOW)) is ConsentState.OPTED_OUT


def test_contactable_requires_consent_AND_a_reachable_number():
    """Consent to be messaged is not the same as being reachable.

    Rows written before M6.1 were never phone-validated, so an opted-in customer
    can still hold a number no message could reach.
    """
    assert is_contactable(_FakeCustomer(opt_in=NOW)) is True
    assert is_contactable(_FakeCustomer(opt_in=NOW, phone="12345")) is False
    assert is_contactable(_FakeCustomer(opt_out=NOW)) is False
    assert is_contactable(_FakeCustomer()) is False


# ---------------------------------------------------------------------------
# Consent service against a database
# ---------------------------------------------------------------------------


@pytest.fixture
def customer(db_session):
    row = Customer(name="Anurag", phone="9876543210")
    db_session.add(row)
    db_session.commit()
    return row


def test_opt_in_then_opt_out_then_opt_in_again(db_session, customer):
    """The full lifecycle the brief asked for, through the real service."""
    service = CustomerService(db_session)

    assert service.get_customer(customer.id).consent_state == ConsentState.NOT_SET

    assert service.opt_in(customer.id).consent_state == ConsentState.OPTED_IN
    assert service.opt_out(customer.id, reason="asked to stop").consent_state == (
        ConsentState.OPTED_OUT
    )
    assert service.opt_in(customer.id).consent_state == ConsentState.OPTED_IN


def test_opt_out_preserves_the_earlier_opt_in_timestamp(db_session, customer):
    """History is never erased -- it is exactly what an audit asks for."""
    service = CustomerService(db_session)
    service.opt_in(customer.id)
    result = service.opt_out(customer.id, reason="wrong number")

    assert result.whatsapp_opt_in_at is not None
    assert result.whatsapp_opt_out_at is not None
    assert result.whatsapp_opt_out_reason == "wrong number"


def test_opt_in_records_its_source(db_session, customer):
    """DPDP consent must be demonstrably informed; "where" is part of that."""
    assert CustomerService(db_session).opt_in(customer.id).whatsapp_consent_source == "staff"


def test_opt_out_reason_is_optional(db_session, customer):
    assert CustomerService(db_session).opt_out(customer.id).whatsapp_opt_out_reason is None


def test_missing_customer_returns_none_not_an_exception(db_session):
    """The router turns None into a 404; the service does not raise for it."""
    service = CustomerService(db_session)
    assert service.opt_in(999_999) is None
    assert service.opt_out(999_999) is None
    assert service.get_customer(999_999) is None


# ---------------------------------------------------------------------------
# Historical correctness -- the point of freezing days_supply on the line
# ---------------------------------------------------------------------------


def test_sale_item_days_supply_is_immune_to_a_later_catalogue_change(db_session):
    """The scenario the brief spelled out.

    Medicine.default_days_supply is a form hint. SaleItem.days_supply is what was
    dispensed. Changing the hint must not rewrite history -- same rule that keeps
    unit_price frozen against a later MRP change.
    """
    medicine = Medicine(
        name="Crocin 500",
        normalized_name="crocin 500",
        mrp=Decimal("20.00"),
        hsn_code="30049099",
        default_days_supply=5,
    )
    db_session.add(medicine)
    db_session.flush()

    sale = Sale(customer_id=None, total_amount=Decimal("200.00"))
    db_session.add(sale)
    db_session.flush()

    from app.models.batch import Batch

    batch = Batch(
        medicine_id=medicine.id,
        batch_number="B1",
        expiry_date=datetime(2027, 1, 1).date(),
        quantity=100,
        cost_price=Decimal("10.00"),
    )
    db_session.add(batch)
    db_session.flush()

    line = SaleItem(
        sale_id=sale.id,
        medicine_id=medicine.id,
        batch_id=batch.id,
        quantity=10,
        unit_price=Decimal("20.00"),
        line_total=Decimal("200.00"),
        days_supply=5,
    )
    db_session.add(line)
    db_session.commit()

    # The catalogue default changes a year later.
    medicine.default_days_supply = 10
    db_session.commit()

    stored = db_session.scalars(select(SaleItem)).one()
    assert stored.days_supply == 5, "history followed the catalogue -- it must not"


def test_days_supply_defaults_to_null_on_an_unspecified_line(db_session):
    """A line written without a duration stays unknown forever.

    This is what every one of the 537 pre-M6.1 sale rows looks like, and why the
    migration backfills nothing.
    """
    medicine = Medicine(
        name="Dolo 650",
        normalized_name="dolo 650",
        mrp=Decimal("30.00"),
        hsn_code="30049099",
    )
    db_session.add(medicine)
    db_session.flush()
    assert medicine.default_days_supply is None

    sale = Sale(customer_id=None, total_amount=Decimal("30.00"))
    db_session.add(sale)
    db_session.flush()

    from app.models.batch import Batch

    batch = Batch(
        medicine_id=medicine.id,
        batch_number="B2",
        expiry_date=datetime(2027, 1, 1).date(),
        quantity=10,
        cost_price=Decimal("12.00"),
    )
    db_session.add(batch)
    db_session.flush()

    db_session.add(
        SaleItem(
            sale_id=sale.id,
            medicine_id=medicine.id,
            batch_id=batch.id,
            quantity=1,
            unit_price=Decimal("30.00"),
            line_total=Decimal("30.00"),
        )
    )
    db_session.commit()

    assert db_session.scalars(select(SaleItem)).one().days_supply is None
