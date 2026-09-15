"""Integration tests for Refill Intelligence (M6.2).

The core test does a REAL round trip with no mocked repository:

    Sale + SaleItem.days_supply -> RefillService -> RefillRepository
        -> SQLAlchemy -> database -> RefillCandidate -> JSON

Sales are written through the ORM rather than the billing endpoint so the tests
can control ``sold_at`` precisely. The billing path's own persistence of
``days_supply`` is already covered by the M6.1 integration suite; what is under
test here is the engine that reads it back.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.batch import Batch
from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.schemas.refill import Contactability, RefillStatus
from app.services.refill_service import RefillService

ENDPOINT = "/api/v1/refill/candidates"

AS_OF = date(2026, 9, 15)


@pytest.fixture
def world(db_session):
    """Two medicines, one batch each, and one opted-in customer."""
    crocin = Medicine(
        name="Crocin 500",
        normalized_name="crocin 500",
        mrp=Decimal("20.00"),
        hsn_code="30049099",
    )
    dolo = Medicine(
        name="Dolo 650",
        normalized_name="dolo 650",
        mrp=Decimal("30.00"),
        hsn_code="30049099",
    )
    customer = Customer(
        name="Anurag",
        phone="9876543210",
        whatsapp_opt_in_at=datetime(2026, 1, 1, 10, 0),
        whatsapp_consent_source="billing_counter",
    )
    db_session.add_all([crocin, dolo, customer])
    db_session.flush()

    batches = {}
    for medicine in (crocin, dolo):
        batch = Batch(
            medicine_id=medicine.id,
            batch_number=f"B{medicine.id}",
            expiry_date=date(2028, 1, 1),
            quantity=1000,
            cost_price=Decimal("10.00"),
        )
        db_session.add(batch)
        db_session.flush()
        batches[medicine.id] = batch.id

    db_session.commit()
    return {
        "crocin": crocin.id,
        "dolo": dolo.id,
        "customer": customer.id,
        "batches": batches,
        "db": db_session,
    }


def sell(world, *, medicine_id, sold_at: datetime, days_supply, customer_id=...):
    """Write one real sale with one line, at a controlled timestamp."""
    db = world["db"]
    cid = world["customer"] if customer_id is ... else customer_id

    sale = Sale(customer_id=cid, total_amount=Decimal("100.00"), sold_at=sold_at)
    db.add(sale)
    db.flush()

    item = SaleItem(
        sale_id=sale.id,
        medicine_id=medicine_id,
        batch_id=world["batches"][medicine_id],
        quantity=10,
        unit_price=Decimal("10.00"),
        line_total=Decimal("100.00"),
        days_supply=days_supply,
    )
    db.add(item)
    db.commit()
    return sale.id, item.id


def scan(world, **kwargs):
    kwargs.setdefault("as_of", AS_OF)
    kwargs.setdefault("due_only", False)
    return RefillService(world["db"]).find_candidates(**kwargs)


# ---------------------------------------------------------------------------
# The real round trip
# ---------------------------------------------------------------------------


def test_a_five_day_supply_becomes_due_on_the_sixth_day(world):
    sale_id, item_id = sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 10, 11, 0),
        days_supply=5,
    )

    result = scan(world)
    candidate = result.candidates[0]

    assert candidate.status is RefillStatus.DUE
    assert candidate.expected_refill_date == date(2026, 9, 15)
    assert candidate.days_overdue == 0
    assert candidate.days_supply == 5
    # Provenance survives the whole trip -- a pharmacist can open the invoice.
    assert candidate.source_sale_id == sale_id
    assert candidate.source_sale_item_id == item_id


def test_a_thirty_day_supply_is_not_due_yet(world):
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 10, 11, 0),
        days_supply=30,
    )

    assert scan(world).candidates[0].status is RefillStatus.NOT_DUE


def test_null_days_supply_never_produces_a_due_candidate(world):
    """The M6.1 contract, enforced end to end through the database."""
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 1, 1, 11, 0),
        days_supply=None,
    )

    result = scan(world)
    assert result.candidates[0].status is RefillStatus.UNKNOWN_DURATION
    assert result.candidates[0].expected_refill_date is None
    assert result.summary.due == 0


def test_the_medicine_default_is_never_used_retroactively(world):
    """A catalogue default must not resurrect a sale recorded as unknown."""
    db = world["db"]
    medicine = db.get(Medicine, world["crocin"])
    medicine.default_days_supply = 5
    db.commit()

    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=None,
    )

    assert scan(world).candidates[0].status is RefillStatus.UNKNOWN_DURATION


def test_an_early_refill_suppresses_the_candidate(world):
    """Sept 1 +30 would be due Oct 1, but they came back on Sept 12."""
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 8, 11, 0),
        days_supply=10,
    )

    candidate = scan(world).candidates[0]
    assert candidate.status is RefillStatus.NOT_DUE
    # Shift-forward: Sept 1 covers to Sept 11, the second supply starts there.
    assert candidate.expected_refill_date == date(2026, 9, 21)
    assert "Already refilled" in candidate.reason


def test_a_late_customer_is_reported_as_overdue(world):
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )

    candidate = scan(world).candidates[0]
    assert candidate.status is RefillStatus.DUE
    assert candidate.days_overdue == 4  # ran out Sept 11, as_of Sept 15


# ---------------------------------------------------------------------------
# Timezone / boundary
# ---------------------------------------------------------------------------


def test_a_late_night_sale_belongs_to_that_calendar_day(world):
    """23:30 on Sept 10 plus 5 days is Sept 15, not Sept 16.

    The database stores naive local datetimes, so taking .date() gives the day
    the pharmacist would recognise. Resolving in UTC would file this sale under
    the previous day and shift every derived date by one.
    """
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 10, 23, 30),
        days_supply=5,
    )

    assert scan(world).candidates[0].expected_refill_date == date(2026, 9, 15)


def test_a_sale_made_today_is_included_in_the_window(world):
    """Half-open upper bound: a sale at 14:00 today must not fall outside it."""
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 15, 14, 0),
        days_supply=5,
    )

    assert scan(world).summary.purchases_reviewed == 1


# ---------------------------------------------------------------------------
# Multiple medicines
# ---------------------------------------------------------------------------


def test_each_medicine_gets_its_own_independent_schedule(world):
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )
    sell(
        world,
        medicine_id=world["dolo"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=30,
    )

    result = scan(world)
    by_medicine = {c.medicine_id: c for c in result.candidates}

    assert by_medicine[world["crocin"]].status is RefillStatus.DUE
    assert by_medicine[world["dolo"]].status is RefillStatus.NOT_DUE


def test_candidates_are_flat_so_the_caller_can_group_by_customer(world):
    """One row per (customer, medicine), each carrying customer_id.

    M6.3 will group these to send ONE combined message rather than three, and
    the screen groups them to avoid three rows for one person. Returning a flat
    list lets both decide for themselves.
    """
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=5,
    )
    sell(
        world,
        medicine_id=world["dolo"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=5,
    )

    result = scan(world, due_only=True)
    assert len(result.candidates) == 2
    assert {c.customer_id for c in result.candidates} == {world["customer"]}


# ---------------------------------------------------------------------------
# Consent -- due and contactable are separate facts
# ---------------------------------------------------------------------------


def test_a_due_customer_who_never_opted_in_is_still_a_candidate(world):
    """The critical distinction. A consent gap must not delete the opportunity.

    The pharmacist can still phone them; only the WhatsApp channel is closed.
    """
    db = world["db"]
    customer = db.get(Customer, world["customer"])
    customer.whatsapp_opt_in_at = None
    db.commit()

    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )

    candidate = scan(world).candidates[0]
    assert candidate.status is RefillStatus.DUE
    assert candidate.contactability is Contactability.NOT_OPTED_IN


def test_an_opted_out_customer_is_due_but_not_contactable(world):
    db = world["db"]
    customer = db.get(Customer, world["customer"])
    customer.whatsapp_opt_out_at = datetime(2026, 6, 1, 10, 0)
    db.commit()

    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )

    candidate = scan(world).candidates[0]
    assert candidate.status is RefillStatus.DUE
    assert candidate.contactability is Contactability.OPTED_OUT


def test_contactable_due_is_counted_separately_in_the_summary(world):
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )

    result = scan(world)
    assert result.summary.due == 1
    assert result.summary.contactable_due == 1


def test_walk_in_sales_produce_no_candidates(world):
    """38% of this shop's real sales are anonymous. Nobody to remind."""
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=5,
        customer_id=None,
    )

    result = scan(world)
    assert result.candidates == []
    assert result.summary.purchases_reviewed == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_running_the_scan_twice_writes_nothing_and_changes_nothing(world):
    """M6.2 derives rather than persists, so repetition is free and safe.

    This is the whole idempotency argument: there is no insert to duplicate. The
    counts are asserted to prove the second run did not double anything, and the
    row counts to prove the engine is genuinely read-only.
    """
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )
    db = world["db"]
    sales_before = db.scalar(select(SaleItem.id).order_by(SaleItem.id.desc()))

    first = scan(world)
    second = scan(world)

    assert first.summary.due == second.summary.due == 1
    assert len(first.candidates) == len(second.candidates) == 1
    assert first.candidates[0].idempotency_key == second.candidates[0].idempotency_key
    assert db.scalar(select(SaleItem.id).order_by(SaleItem.id.desc())) == sales_before


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def test_the_endpoint_returns_candidates_and_a_summary(client, world):
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )

    response = client.get(ENDPOINT, params={"as_of": "2026-09-15"})

    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == "2026-09-15"
    assert body["summary"]["due"] == 1
    assert body["candidates"][0]["status"] == "due"
    assert body["candidates"][0]["reason"]


def test_due_only_is_the_default(client, world):
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=300,
    )

    body = client.get(ENDPOINT, params={"as_of": "2026-09-15"}).json()
    assert body["candidates"] == []
    assert body["summary"]["not_due"] == 1


def test_contactable_only_filter(client, world, db_session):
    customer = db_session.get(Customer, world["customer"])
    customer.whatsapp_opt_in_at = None
    db_session.commit()

    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )

    body = client.get(
        ENDPOINT, params={"as_of": "2026-09-15", "contactable_only": "true"}
    ).json()

    assert body["candidates"] == []
    assert body["summary"]["due"] == 1  # the summary still counts the whole scan


def test_summary_counts_the_whole_scan_not_the_returned_rows(client, world):
    """A screen showing 1 row must be able to say "1 of 2" truthfully."""
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )
    sell(
        world,
        medicine_id=world["dolo"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )

    body = client.get(
        ENDPOINT, params={"as_of": "2026-09-15", "limit": 1}
    ).json()

    assert len(body["candidates"]) == 1
    assert body["summary"]["due"] == 2


def test_the_response_never_mentions_a_channel(client, world):
    """M6.2 decides WHO, never HOW. A guard against scope creep.

    If a future edit adds a message body or a template name to this payload, the
    refill domain has started knowing about WhatsApp and the voice agent can no
    longer reuse it.
    """
    sell(
        world,
        medicine_id=world["crocin"],
        sold_at=datetime(2026, 9, 1, 11, 0),
        days_supply=10,
    )

    raw = client.get(ENDPOINT, params={"as_of": "2026-09-15"}).text.lower()
    for forbidden in ("whatsapp_message", "template", "message_body", "access_token"):
        assert forbidden not in raw
