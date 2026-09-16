"""Domain contract for Refill Intelligence (M6.2).

WHAT THIS LAYER IS
------------------
It answers one question deterministically: **who looks due for a refill, and
why?** It produces a domain result. It does not message anyone.

Nothing in this module, or in the service and repository behind it, imports a
WhatsApp client, a voice provider, an LLM or LangGraph. That is the architectural
boundary M6 depends on: the refill decision belongs to the refill domain, and the
communication layer sits underneath it. If this file ever learns that WhatsApp
exists, a future Marathi voice agent can no longer reuse any of it.

TWO ORTHOGONAL AXES, DELIBERATELY NOT MERGED
--------------------------------------------
"This medicine is due" and "we are allowed to contact this person" are different
facts and are modelled separately:

    status         NOT_DUE | DUE | UNKNOWN_DURATION
    contactability CONTACTABLE | NO_PHONE | NOT_OPTED_IN | OPTED_OUT

Merging them into one enum would produce a state explosion (DUE_BUT_OPTED_OUT,
DUE_BUT_NO_PHONE, ...) and, worse, would let a consent problem delete a real
business opportunity. A customer who is due but has not opted in is still a
customer the pharmacist may want to phone. The engine reports both facts and lets
the caller decide.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RefillStatus(StrEnum):
    """Where a (customer, medicine) pair stands against its expected supply.

    Only three, on purpose. ``ALREADY_REFILLED`` is NOT a status: a customer who
    bought again simply has coverage running into the future, which is
    ``NOT_DUE``. Keeping it as a separate status would mean two states that must
    behave identically everywhere downstream, and one day they would not.
    It survives as a *reason string* instead, because the distinction is useful
    to a human reading the screen.
    """

    NOT_DUE = "not_due"
    DUE = "due"
    # The pharmacist never recorded how long the medicine lasts, so no refill
    # date can be computed. Distinct from NOT_DUE: not-due is an answer, this is
    # the absence of one.
    UNKNOWN_DURATION = "unknown_duration"


class Contactability(StrEnum):
    """Whether the future communication layer would be allowed to reach them.

    Computed here but ACTED ON nowhere in M6.2. It exists so the screen can show
    a pharmacist which due customers are reachable, and so M6.3 inherits one
    definition rather than writing a second.
    """

    CONTACTABLE = "contactable"
    NO_PHONE = "no_phone"          # phone missing or not a usable Indian mobile
    NOT_OPTED_IN = "not_opted_in"  # never asked
    OPTED_OUT = "opted_out"        # asked and refused, or withdrew


class RefillCandidate(BaseModel):
    """One (customer, medicine) pair with a decision and the reason for it.

    Every field is either copied from the database or derived by arithmetic that
    a pharmacist could repeat on paper. There is no score, no model and no
    ranking heuristic -- if the screen says someone is 4 days overdue, the
    supporting dates are right there to check it against.
    """

    model_config = ConfigDict(from_attributes=True)

    # ---- identity ----
    customer_id: int
    customer_name: str | None
    customer_phone: str
    medicine_id: int
    medicine_name: str

    # The sale line whose days_supply set the CURRENT coverage window. This is
    # the candidate's provenance: it lets a pharmacist open the exact invoice
    # that produced the date, and it is the natural idempotency key for M6.3.
    source_sale_id: int
    source_sale_item_id: int

    # ---- the arithmetic ----
    last_purchase_date: date
    days_supply: int | None = Field(
        default=None,
        description="From the sale line, never from the medicine default. "
        "None means the pharmacist did not record it.",
    )
    expected_refill_date: date | None = Field(
        default=None,
        description="When the supply is expected to run out. None when unknown.",
    )
    days_overdue: int | None = Field(
        default=None,
        description="as_of - expected_refill_date, floored at 0. None when unknown.",
    )

    # ---- the decision ----
    status: RefillStatus
    contactability: Contactability
    reason: str = Field(
        description="One plain sentence a pharmacist can act on. Never a score."
    )

    @property
    def idempotency_key(self) -> str:
        """Stable identity for this refill opportunity.

        M6.2 persists nothing, so nothing uses this yet. It is defined here, next
        to the fields it is built from, so that M6.3's notifications table can put
        a UNIQUE constraint on exactly this string and get duplicate-send
        protection from the database rather than from careful scheduler code.

        Keyed on the SOURCE SALE ITEM plus the computed date, not on
        (customer, medicine, date) alone: if a pharmacist corrects a sale line's
        days_supply, the coverage window moves and this correctly becomes a
        different opportunity rather than silently reusing the old one's
        "already sent" record.
        """
        return f"refill:{self.source_sale_item_id}:{self.expected_refill_date}"


class RefillSummary(BaseModel):
    """Counts over the WHOLE scan, before any filter or limit was applied.

    Separate from the returned rows for the same reason the inventory report
    keeps its totals separate: a screen showing 20 rows must be able to say
    "20 of 143" truthfully, and summing the visible rows cannot do that.
    """

    customers_reviewed: int
    purchases_reviewed: int
    due: int
    not_due: int
    unknown_duration: int
    contactable_due: int = Field(
        description="Due AND reachable — the subset M6.3 would actually message."
    )


class NotificationSummary(BaseModel):
    """The reminder status for one refill opportunity, for the dashboard.

    A PROJECTION of a notification, defined here with primitive fields rather
    than importing the notification schema. That is the point: the refill domain
    still has no dependency on the notification domain, and this model would be
    identical if the reminder had gone out by voice.

    It is populated by the ROUTER, never by ``RefillService`` -- composing two
    domains is what an API layer is for, and letting the engine do it would be
    exactly the coupling M6.2 was built to avoid.
    """

    status: str
    attempts: int
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None
    last_error_code: str | None = None


class RefillCandidatesResponse(BaseModel):
    """What ``GET /api/v1/refill/candidates`` returns.

    Candidates are a FLAT list, one per (customer, medicine), rather than
    pre-grouped by customer. Grouping is a presentation decision and the two
    consumers want different ones: the screen groups by customer to avoid three
    rows for one person, and M6.3 will group by customer to send ONE combined
    message rather than three. Returning the flat list with ``customer_id`` on
    every row lets both do their own grouping without the engine guessing.
    """

    as_of: date
    lookback_days: int
    summary: RefillSummary
    candidates: list[RefillCandidate]

    # Keyed by source_sale_item_id as a STRING, because JSON object keys are
    # always strings and a dict[int, ...] would silently become one anyway.
    # Empty unless the caller asked for it.
    notifications: dict[str, NotificationSummary] = Field(default_factory=dict)

    notes: list[str] = Field(
        default_factory=list,
        description="Plain-language caveats about what this scan could not see.",
    )
