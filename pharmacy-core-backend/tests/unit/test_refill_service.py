"""Unit tests for the refill engine (M6.2).

The coverage maths and the decision rules are pure functions over plain
dataclasses, so almost every test here runs without a database. That is the
payoff of keeping ``RefillRepository`` free of refill logic: the business rules
can be checked exhaustively and instantly.

Dates are explicit literals rather than offsets from the real today. A test that
computes its own expectation cannot catch a bug in the code that computes it, and
a test anchored to the day it runs is a time bomb.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.repositories.refill_repository import PurchaseRecord
from app.schemas.refill import Contactability, RefillStatus
from app.services.refill_service import (
    MAX_DAYS_OVERDUE,
    RefillService,
    assess_contactability,
    compute_coverage,
)

SEPT_1 = date(2026, 9, 1)


def purchase(day: date, days_supply: int | None, *, sale_id: int = 1, item_id: int = 1):
    return PurchaseRecord(
        customer_id=1,
        customer_name="Anurag",
        customer_phone="9876543210",
        medicine_id=17,
        medicine_name="Crocin 500",
        sale_id=sale_id,
        sale_item_id=item_id,
        purchased_on=day,
        days_supply=days_supply,
    )


# ---------------------------------------------------------------------------
# The basic calculation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "days_supply,expected",
    [
        (1, date(2026, 9, 2)),
        (5, date(2026, 9, 6)),
        (30, date(2026, 10, 1)),
        (365, date(2027, 9, 1)),
    ],
)
def test_expected_refill_date_is_purchase_plus_days_supply(days_supply, expected):
    assert compute_coverage([purchase(SEPT_1, days_supply)]).covered_until == expected


def test_month_boundary():
    """30 days from Sept 1 is Oct 1, not Sept 31."""
    assert compute_coverage([purchase(SEPT_1, 30)]).covered_until == date(2026, 10, 1)


def test_year_boundary():
    assert compute_coverage([purchase(date(2026, 12, 20), 20)]).covered_until == date(
        2027, 1, 9
    )


def test_leap_year_february():
    """2028 is a leap year: 5 days from Feb 26 lands on Mar 2, not Mar 1."""
    assert compute_coverage([purchase(date(2028, 2, 26), 5)]).covered_until == date(
        2028, 3, 2
    )


def test_non_leap_year_february():
    assert compute_coverage([purchase(date(2027, 2, 26), 5)]).covered_until == date(
        2027, 3, 3
    )


# ---------------------------------------------------------------------------
# Unknown duration -- never guess
# ---------------------------------------------------------------------------


def test_unknown_days_supply_produces_no_date():
    assert compute_coverage([purchase(SEPT_1, None)]).covered_until is None


def test_unknown_on_the_LATEST_purchase_wins_even_if_an_older_one_was_known():
    """They walked out with medicine of unknown duration. We cannot know.

    Falling back to the older known purchase would produce a refill date that
    ignores what the customer most recently took home.
    """
    coverage = compute_coverage([purchase(SEPT_1, 5), purchase(date(2026, 9, 3), None)])
    assert coverage.covered_until is None
    assert coverage.days_supply is None


def test_an_older_unknown_line_does_not_shorten_coverage():
    """A NULL contributes nothing -- it must not extend OR truncate cover."""
    coverage = compute_coverage(
        [purchase(SEPT_1, None), purchase(date(2026, 9, 2), 10)]
    )
    assert coverage.covered_until == date(2026, 9, 12)


# ---------------------------------------------------------------------------
# Multiple purchases -- the shift-forward rule
# ---------------------------------------------------------------------------


def test_second_purchase_shifts_forward_rather_than_restarting():
    """Sept 1 +5 covers to Sept 6. Sept 3 +5 starts at Sept 6, not Sept 3.

    Restarting from the latest purchase would say Sept 8 and remind a customer
    who still has three days of medicine in the drawer.
    """
    coverage = compute_coverage([purchase(SEPT_1, 5), purchase(date(2026, 9, 3), 5)])
    assert coverage.covered_until == date(2026, 9, 11)


def test_a_gap_between_purchases_does_not_carry_stale_coverage():
    """Bought Sept 1 (+5, ran out Sept 6), bought again Sept 20.

    Coverage restarts from Sept 20 -- summing both supplies from the first
    purchase would wrongly claim cover to Sept 11 plus 5.
    """
    coverage = compute_coverage([purchase(SEPT_1, 5), purchase(date(2026, 9, 20), 5)])
    assert coverage.covered_until == date(2026, 9, 25)


def test_back_to_back_purchases_of_equal_length():
    """Sept 1 and Sept 5, each 5 days: covered to Sept 11."""
    coverage = compute_coverage([purchase(SEPT_1, 5), purchase(date(2026, 9, 5), 5)])
    assert coverage.covered_until == date(2026, 9, 11)


def test_source_is_always_the_latest_purchase():
    """Provenance points at the sale the customer most recently made."""
    coverage = compute_coverage(
        [
            purchase(SEPT_1, 5, sale_id=10, item_id=100),
            purchase(date(2026, 9, 3), 5, sale_id=11, item_id=101),
        ]
    )
    assert coverage.source_sale_id == 11
    assert coverage.source_sale_item_id == 101
    assert coverage.last_purchase_on == date(2026, 9, 3)


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


def decide(records, reference):
    return RefillService._decide(compute_coverage(records), records, reference)


def test_not_due_before_the_supply_runs_out():
    status, overdue, reason = decide([purchase(SEPT_1, 5)], date(2026, 9, 4))
    assert status is RefillStatus.NOT_DUE
    assert overdue == 0
    assert "Still covered until 2026-09-06" in reason


def test_due_on_the_day_the_supply_runs_out():
    status, overdue, reason = decide([purchase(SEPT_1, 5)], date(2026, 9, 6))
    assert status is RefillStatus.DUE
    assert overdue == 0
    assert "runs out today" in reason


def test_overdue_counts_days_since_the_supply_ran_out():
    """Expected Oct 1, today Oct 5, nothing bought -> 4 days overdue."""
    status, overdue, _ = decide([purchase(SEPT_1, 30)], date(2026, 10, 5))
    assert status is RefillStatus.DUE
    assert overdue == 4


def test_an_early_refill_removes_the_candidate():
    """The brief's scenario: 30 days from Sept 1, bought again Sept 25.

    On Oct 1 there must be no candidate -- shift-forward carries cover to Oct 31.
    """
    records = [purchase(SEPT_1, 30), purchase(date(2026, 9, 25), 30)]
    status, _, reason = decide(records, date(2026, 10, 1))

    assert status is RefillStatus.NOT_DUE
    assert "Already refilled" in reason


def test_already_refilled_is_a_reason_not_a_status():
    """One fewer state to keep in sync everywhere downstream."""
    records = [purchase(SEPT_1, 5), purchase(date(2026, 9, 4), 5)]
    status, _, reason = decide(records, date(2026, 9, 5))

    assert status is RefillStatus.NOT_DUE
    assert "Already refilled on 2026-09-04" in reason


def test_unknown_duration_is_its_own_status():
    status, overdue, reason = decide([purchase(SEPT_1, None)], date(2026, 9, 30))

    assert status is RefillStatus.UNKNOWN_DURATION
    assert overdue is None
    assert "No days supply was recorded" in reason


def test_very_old_candidates_stop_being_due():
    """Someone 200 days past a 5-day course did not forget -- they stopped.

    A reminder then reads as a shop trawling old records rather than helping.
    """
    reference = date(2026, 9, 6) + __import__("datetime").timedelta(
        days=MAX_DAYS_OVERDUE + 1
    )
    status, overdue, reason = decide([purchase(SEPT_1, 5)], reference)

    assert status is RefillStatus.NOT_DUE
    assert overdue == MAX_DAYS_OVERDUE + 1
    assert "too long past" in reason


def test_the_boundary_day_is_still_due():
    reference = date(2026, 9, 6) + __import__("datetime").timedelta(
        days=MAX_DAYS_OVERDUE
    )
    status, _, _ = decide([purchase(SEPT_1, 5)], reference)
    assert status is RefillStatus.DUE


# ---------------------------------------------------------------------------
# Contactability -- reusing the consent domain, never re-implementing it
# ---------------------------------------------------------------------------


class _FakeCustomer:
    def __init__(self, opt_in=None, opt_out=None, phone="9876543210"):
        self.id = 1
        self.name = "Anurag"
        self.phone = phone
        self.whatsapp_opt_in_at = opt_in
        self.whatsapp_opt_out_at = opt_out


NOW = date(2026, 9, 15)
import datetime as _dt  # noqa: E402

STAMP = _dt.datetime(2026, 9, 15, 10, 0)
EARLIER = _dt.datetime(2026, 8, 1, 10, 0)


def test_opted_in_with_a_good_number_is_contactable():
    assert assess_contactability(_FakeCustomer(opt_in=STAMP)) is Contactability.CONTACTABLE


def test_never_asked_is_not_opted_in():
    assert assess_contactability(_FakeCustomer()) is Contactability.NOT_OPTED_IN


def test_opted_out_is_reported_as_opted_out():
    assert assess_contactability(_FakeCustomer(opt_out=STAMP)) is Contactability.OPTED_OUT


def test_opt_out_beats_an_older_opt_in():
    customer = _FakeCustomer(opt_in=EARLIER, opt_out=STAMP)
    assert assess_contactability(customer) is Contactability.OPTED_OUT


def test_re_opt_in_beats_an_older_opt_out():
    customer = _FakeCustomer(opt_in=STAMP, opt_out=EARLIER)
    assert assess_contactability(customer) is Contactability.CONTACTABLE


def test_an_unusable_number_is_not_contactable_even_when_opted_in():
    """Rows predating M6.1 were never validated. Consent is not reachability."""
    customer = _FakeCustomer(opt_in=STAMP, phone="12345")
    assert assess_contactability(customer) is Contactability.NO_PHONE


def test_opted_out_is_reported_even_with_a_bad_number():
    """Opt-out is checked FIRST -- the strongest signal wins.

    Reporting NO_PHONE for someone who explicitly refused would hide the refusal
    behind a data-quality problem, and a future "fix the number" job would then
    quietly make them contactable again.
    """
    customer = _FakeCustomer(opt_out=STAMP, phone="12345")
    assert assess_contactability(customer) is Contactability.OPTED_OUT


# ---------------------------------------------------------------------------
# The idempotency key
# ---------------------------------------------------------------------------


def test_the_idempotency_key_is_stable_for_the_same_opportunity():
    """Two scans of unchanged data must produce the same key.

    M6.2 persists nothing, so nothing depends on this yet. It is asserted now so
    that M6.3 can put a UNIQUE constraint on it and get duplicate-send protection
    from the database rather than from careful scheduler code.
    """
    from app.schemas.refill import RefillCandidate

    def build():
        return RefillCandidate(
            customer_id=1,
            customer_name="Anurag",
            customer_phone="9876543210",
            medicine_id=17,
            medicine_name="Crocin 500",
            source_sale_id=10,
            source_sale_item_id=100,
            last_purchase_date=SEPT_1,
            days_supply=5,
            expected_refill_date=date(2026, 9, 6),
            days_overdue=0,
            status=RefillStatus.DUE,
            contactability=Contactability.CONTACTABLE,
            reason="Supply runs out today.",
        )

    assert build().idempotency_key == build().idempotency_key
    assert build().idempotency_key == "refill:100:2026-09-06"


def test_the_key_changes_when_the_corrected_days_supply_moves_the_date():
    """A corrected sale line is a DIFFERENT opportunity, not the old one again."""
    from app.schemas.refill import RefillCandidate

    def build(refill_date, overdue):
        return RefillCandidate(
            customer_id=1,
            customer_name="A",
            customer_phone="9876543210",
            medicine_id=17,
            medicine_name="M",
            source_sale_id=10,
            source_sale_item_id=100,
            last_purchase_date=SEPT_1,
            days_supply=5,
            expected_refill_date=refill_date,
            days_overdue=overdue,
            status=RefillStatus.DUE,
            contactability=Contactability.CONTACTABLE,
            reason="r",
        )

    assert build(date(2026, 9, 6), 0).idempotency_key != build(
        date(2026, 9, 11), 0
    ).idempotency_key
