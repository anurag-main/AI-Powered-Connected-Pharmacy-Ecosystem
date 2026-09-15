"""Refill Intelligence — the deterministic engine (M6.2).

WHAT THIS DECIDES
-----------------
For each (customer, medicine) pair: when their supply runs out, whether that has
happened, and whether the pharmacy is allowed to contact them about it.

NO AI, AND THAT IS THE DESIGN
-----------------------------
Every rule here is arithmetic on dates a pharmacist recorded. An LLM would make
it slower, more expensive and non-deterministic, and a non-deterministic answer
about somebody's medicine is a defect rather than a feature. There is no
LangGraph graph in M6.2 because there is nothing to plan, no tool to choose and
no ambiguity to resolve.

THE COVERAGE MODEL
------------------
Refill dates are computed with the pharmacy-standard **shift-forward** rule used
by Proportion of Days Covered, not by naively adding days_supply to the last
purchase:

    coverage_end = max(purchase_date, previous_coverage_end) + days_supply

Worked through two purchases of a 5-day supply:

    Sept 1 bought 5 days  -> covered to Sept 6
    Sept 3 bought 5 days  -> does NOT start on Sept 3 (they still have 3 days
                             left). Starts Sept 6, covered to Sept 11.

Naively using the latest purchase would say Sept 8 and remind someone who still
has medicine in the drawer. Summing both supplies from the first purchase would
say Sept 11 by luck, but breaks the moment there is a gap between purchases.
Shift-forward is correct in both shapes and is what the industry measure does.

It also answers "already refilled" without a special case: a customer who bought
again simply has coverage running into the future, so they are NOT_DUE.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.time_range import today
from app.repositories.refill_repository import PurchaseRecord, RefillRepository
from app.schemas.refill import (
    Contactability,
    RefillCandidate,
    RefillCandidatesResponse,
    RefillStatus,
    RefillSummary,
)
from app.services.customer_service import ConsentState, consent_state
from app.core.phone import is_valid_indian_mobile

logger = logging.getLogger(__name__)

# How far back to look for purchases. Must comfortably exceed the largest legal
# days_supply (365) so a long course cannot fall out of the window while the
# customer is still on it.
DEFAULT_LOOKBACK_DAYS = 400

# A candidate stops being actionable eventually. Someone 200 days past a 5-day
# course did not forget -- they stopped, or they went elsewhere, and a reminder
# then reads as a shop trawling old records rather than helping. Reported in the
# summary as unknown-free NOT_DUE rather than silently dropped.
MAX_DAYS_OVERDUE = 120


@dataclass(frozen=True)
class _Coverage:
    """The computed supply position for one (customer, medicine) pair."""

    covered_until: date | None       # None when the duration is unknown
    last_purchase_on: date
    source_sale_id: int
    source_sale_item_id: int
    days_supply: int | None


def compute_coverage(purchases: list[PurchaseRecord]) -> _Coverage:
    """Walk one medicine's purchases chronologically and return where cover ends.

    ``purchases`` must be for ONE (customer, medicine) pair, oldest first.

    The unknown rule, which is the important one: if the customer's MOST RECENT
    purchase has no recorded ``days_supply``, the answer is unknown -- full stop.
    We cannot know what they currently hold, and falling back to an older known
    purchase would produce a refill date that ignores the medicine they most
    recently walked out with.

    ``Medicine.default_days_supply`` is deliberately never consulted. It is a
    form pre-fill hint; using it retroactively would invent a duration for a sale
    where the pharmacist declined to give one, which is precisely what the NULL
    was recorded to prevent.
    """
    latest = purchases[-1]

    if latest.days_supply is None:
        return _Coverage(
            covered_until=None,
            last_purchase_on=latest.purchased_on,
            source_sale_id=latest.sale_id,
            source_sale_item_id=latest.sale_item_id,
            days_supply=None,
        )

    covered_until: date | None = None
    for purchase in purchases:
        if purchase.days_supply is None:
            # An older line with no duration contributes nothing. It cannot
            # extend coverage, and it must not shorten it either.
            continue
        start = purchase.purchased_on
        if covered_until is not None and covered_until > start:
            # Bought early -- the new supply begins when the old one runs out.
            start = covered_until
        covered_until = start + timedelta(days=purchase.days_supply)

    return _Coverage(
        covered_until=covered_until,
        last_purchase_on=latest.purchased_on,
        source_sale_id=latest.sale_id,
        source_sale_item_id=latest.sale_item_id,
        days_supply=latest.days_supply,
    )


def assess_contactability(customer) -> Contactability:
    """Translate the customer's consent and phone into one verdict.

    Reuses ``consent_state()`` from the customer domain rather than re-reading
    the timestamps. The rule for what counts as consent must have exactly one
    implementation, or the day it changes only one of the copies will be updated.

    Phone validity is checked as well as consent because they are independent:
    rows written before M6.1 were never validated, so a customer can be opted in
    and still hold a number no message could reach.
    """
    state = consent_state(customer)
    if state is ConsentState.OPTED_OUT:
        return Contactability.OPTED_OUT
    if not is_valid_indian_mobile(customer.phone):
        return Contactability.NO_PHONE
    if state is ConsentState.NOT_SET:
        return Contactability.NOT_OPTED_IN
    return Contactability.CONTACTABLE


class RefillService:
    """Finds customers who look due for a refill. Contacts nobody."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = RefillRepository(db)

    def find_candidates(
        self,
        *,
        as_of: date | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        due_only: bool = True,
        customer_id: int | None = None,
        medicine_id: int | None = None,
        contactable_only: bool = False,
        limit: int = 100,
    ) -> RefillCandidatesResponse:
        """Scan purchase history and return refill candidates.

        ``as_of`` exists for tests and for answering "who was due last Monday".
        It defaults to today in the pharmacy's timezone via the app's single
        ``today()`` helper -- M6.2 introduces no second timezone implementation.
        """
        reference = as_of or today()

        logger.info(
            "refill_scan_started",
            extra={"as_of": str(reference), "lookback_days": lookback_days},
        )

        purchases = self.repository.purchases_for_refill(
            as_of=reference, lookback_days=lookback_days
        )

        # Group by (customer, medicine). "Same medicine" is medicine_id and
        # nothing else: it is the existing stable database identity, it is what
        # the sale line already points at, and fuzzy matching on names or salts
        # would make the engine non-deterministic for no MVP gain. Two brands of
        # paracetamol are two medicines here, which is also how the shelf works.
        grouped: dict[tuple[int, int], list[PurchaseRecord]] = defaultdict(list)
        for purchase in purchases:
            grouped[(purchase.customer_id, purchase.medicine_id)].append(purchase)

        customers = self.repository.customers_by_id({c for c, _ in grouped})

        candidates: list[RefillCandidate] = []
        counts = {status: 0 for status in RefillStatus}
        contactable_due = 0

        for (cust_id, _med_id), records in grouped.items():
            customer = customers.get(cust_id)
            if customer is None:
                # The customer row vanished between the two queries. Skipping is
                # correct: there is nobody left to remind.
                continue

            candidate = self._build_candidate(records, customer, reference)
            counts[candidate.status] += 1
            if (
                candidate.status is RefillStatus.DUE
                and candidate.contactability is Contactability.CONTACTABLE
            ):
                contactable_due += 1

            candidates.append(candidate)

        summary = RefillSummary(
            customers_reviewed=len(customers),
            purchases_reviewed=len(purchases),
            due=counts[RefillStatus.DUE],
            not_due=counts[RefillStatus.NOT_DUE],
            unknown_duration=counts[RefillStatus.UNKNOWN_DURATION],
            contactable_due=contactable_due,
        )

        visible = self._apply_filters(
            candidates,
            due_only=due_only,
            customer_id=customer_id,
            medicine_id=medicine_id,
            contactable_only=contactable_only,
        )

        # Most overdue first: the person who ran out a week ago needs the call
        # before the one who ran out this morning. Unknown dates sort last.
        visible.sort(key=lambda c: (-(c.days_overdue or 0), c.customer_id))

        logger.info(
            "refill_scan_completed",
            extra={
                "as_of": str(reference),
                "purchases_reviewed": summary.purchases_reviewed,
                "customers_reviewed": summary.customers_reviewed,
                "due": summary.due,
                "unknown_duration": summary.unknown_duration,
                "contactable_due": summary.contactable_due,
                "returned": min(len(visible), limit),
            },
        )

        return RefillCandidatesResponse(
            as_of=reference,
            lookback_days=lookback_days,
            summary=summary,
            candidates=visible[:limit],
            notes=self._build_notes(summary),
        )

    # -----------------------------------------------------------------
    # Per-candidate decision
    # -----------------------------------------------------------------

    def _build_candidate(
        self, records: list[PurchaseRecord], customer, reference: date
    ) -> RefillCandidate:
        coverage = compute_coverage(records)
        latest = records[-1]
        contactability = assess_contactability(customer)

        status, days_overdue, reason = self._decide(coverage, records, reference)

        if status is RefillStatus.DUE:
            # Only logged for candidates that would actually be acted on, and
            # deliberately WITHOUT the medicine name or the phone number: an
            # application log is not the place to accumulate a list of who takes
            # what. Ids are enough to investigate, and they are not readable at a
            # glance by anyone who happens to see the log.
            logger.info(
                "refill_candidate_found",
                extra={
                    "customer_id": customer.id,
                    "medicine_id": latest.medicine_id,
                    "source_sale_item_id": coverage.source_sale_item_id,
                    "days_overdue": days_overdue,
                    "contactability": contactability.value,
                },
            )
        elif status is RefillStatus.UNKNOWN_DURATION:
            logger.debug(
                "refill_candidate_suppressed",
                extra={
                    "customer_id": customer.id,
                    "medicine_id": latest.medicine_id,
                    "why": "unknown_duration",
                },
            )

        return RefillCandidate(
            customer_id=customer.id,
            customer_name=customer.name,
            customer_phone=customer.phone,
            medicine_id=latest.medicine_id,
            medicine_name=latest.medicine_name,
            source_sale_id=coverage.source_sale_id,
            source_sale_item_id=coverage.source_sale_item_id,
            last_purchase_date=coverage.last_purchase_on,
            days_supply=coverage.days_supply,
            expected_refill_date=coverage.covered_until,
            days_overdue=days_overdue,
            status=status,
            contactability=contactability,
            reason=reason,
        )

    @staticmethod
    def _decide(
        coverage: _Coverage, records: list[PurchaseRecord], reference: date
    ) -> tuple[RefillStatus, int | None, str]:
        """The whole decision, in one readable place."""
        if coverage.covered_until is None:
            return (
                RefillStatus.UNKNOWN_DURATION,
                None,
                "No days supply was recorded on the last purchase, so no refill "
                "date can be worked out.",
            )

        if coverage.covered_until > reference:
            # Covered into the future. If they bought more than once, the reason
            # a pharmacist cares about is that they already came back.
            if len(records) > 1:
                return (
                    RefillStatus.NOT_DUE,
                    0,
                    f"Already refilled on {coverage.last_purchase_on}; covered "
                    f"until {coverage.covered_until}.",
                )
            return (
                RefillStatus.NOT_DUE,
                0,
                f"Still covered until {coverage.covered_until}.",
            )

        days_overdue = (reference - coverage.covered_until).days

        if days_overdue > MAX_DAYS_OVERDUE:
            return (
                RefillStatus.NOT_DUE,
                days_overdue,
                f"Ran out {days_overdue} days ago — too long past to treat as a "
                f"refill reminder.",
            )

        if days_overdue == 0:
            return (RefillStatus.DUE, 0, "Supply runs out today.")

        return (
            RefillStatus.DUE,
            days_overdue,
            f"Ran out {days_overdue} day(s) ago, on {coverage.covered_until}.",
        )

    # -----------------------------------------------------------------
    # Filtering and notes
    # -----------------------------------------------------------------

    @staticmethod
    def _apply_filters(
        candidates: list[RefillCandidate],
        *,
        due_only: bool,
        customer_id: int | None,
        medicine_id: int | None,
        contactable_only: bool,
    ) -> list[RefillCandidate]:
        result = candidates
        if due_only:
            result = [c for c in result if c.status is RefillStatus.DUE]
        if customer_id is not None:
            result = [c for c in result if c.customer_id == customer_id]
        if medicine_id is not None:
            result = [c for c in result if c.medicine_id == medicine_id]
        if contactable_only:
            result = [
                c for c in result if c.contactability is Contactability.CONTACTABLE
            ]
        return list(result)

    @staticmethod
    def _build_notes(summary: RefillSummary) -> list[str]:
        """Plain-language caveats about what the scan could NOT see.

        Written for the pharmacist, not for a developer. The unknown-duration
        count is the one that matters commercially: every one of those is a
        customer who will never be reminded, and the fix is at the billing
        counter rather than in this engine.
        """
        notes = [
            "Anonymous walk-in sales are not included — a reminder needs someone "
            "to remind.",
        ]
        if summary.unknown_duration:
            notes.append(
                f"{summary.unknown_duration} medicine(s) have no recorded days "
                f"supply and can never produce a reminder. Enter the duration at "
                f"billing to include them."
            )
        if summary.due and summary.contactable_due < summary.due:
            notes.append(
                f"{summary.due - summary.contactable_due} of {summary.due} due "
                f"customer(s) cannot be messaged — no consent or no usable "
                f"number. They can still be phoned."
            )
        return notes
