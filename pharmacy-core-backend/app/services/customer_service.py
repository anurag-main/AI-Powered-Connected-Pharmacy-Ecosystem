"""Customer domain — identity and WhatsApp consent (M6.1).

WHY CONSENT IS ITS OWN SERVICE AND NOT PART OF BILLING
-------------------------------------------------------
Billing captures consent as a side effect of a sale, because that is the one
moment the customer is standing at the counter. But consent has a life of its
own afterwards: it is withdrawn by phone, re-given weeks later, and audited long
after the sale it came from is forgotten. Modelling it inside billing would tie
the right to be left alone to the existence of an invoice.

THE ARCHITECTURAL BOUNDARY THIS PROTECTS
----------------------------------------
Nothing in this module knows what WhatsApp is. It records whether a customer
agreed to be messaged; it does not message anyone, hold an API key, or import a
client. The future communication layer will ASK this service a question and get
a yes or a no.

That separation is what lets the Marathi voice agent arrive later without
touching consent: the question "may we contact this person" is the same question
whatever wire carries the answer. If a channel ever needs its own consent, it
gets its own columns -- it does not get to redefine these.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy.orm import Session

from app.core.phone import is_valid_indian_mobile
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerOut

# Where a consent record came from. Free-form in the column, constrained here to
# the sources that actually exist, so a typo does not become a new category.
CONSENT_SOURCE_BILLING = "billing_counter"
CONSENT_SOURCE_STAFF = "staff"


class ConsentState(StrEnum):
    """The three states the research report required us to distinguish.

    Deliberately three, not two. "Never asked" and "asked and refused" look the
    same to a boolean and must not: the first is a customer the pharmacy may
    still approach at the counter, the second is one it may not.
    """

    NOT_SET = "not_set"
    OPTED_IN = "opted_in"
    OPTED_OUT = "opted_out"


def consent_state(customer) -> ConsentState:
    """Derive consent from the two timestamps. The only place this is decided.

    Rules, in order:

        both NULL                  -> NOT_SET
        only opt_in                -> OPTED_IN
        only opt_out               -> OPTED_OUT
        both, opt_in strictly newer-> OPTED_IN   (a genuine re-opt-in)
        both, otherwise            -> OPTED_OUT

    The tie deliberately favours OPTED_OUT. Two identical timestamps mean the
    ordering is unknowable, and the safe reading of an unknowable consent state
    is that we do not have consent.
    """
    opt_in = customer.whatsapp_opt_in_at
    opt_out = customer.whatsapp_opt_out_at

    if opt_in is None and opt_out is None:
        return ConsentState.NOT_SET
    if opt_out is None:
        return ConsentState.OPTED_IN
    if opt_in is None:
        return ConsentState.OPTED_OUT
    return ConsentState.OPTED_IN if opt_in > opt_out else ConsentState.OPTED_OUT


def is_contactable(customer) -> bool:
    """May the future refill engine send this customer a WhatsApp message?

    Two independent conditions, and both are required:

      1. consent is OPTED_IN
      2. the stored phone is a plausible Indian mobile

    The second is not redundant. Rows predating M6.1 were written when the API
    validated nothing, so the table can hold numbers that no message could ever
    reach. Consent to be messaged is not the same as being reachable.

    M6.1 exposes this; nothing calls it to send anything yet. It exists so the
    eligibility engine in M6.2 inherits one definition instead of writing a
    second one.
    """
    return (
        consent_state(customer) is ConsentState.OPTED_IN
        and is_valid_indian_mobile(customer.phone)
    )


class CustomerService:
    """Reads customers and records consent decisions."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CustomerRepository(db)

    # -----------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------

    def list_customers(self, *, limit: int = 100) -> list[CustomerOut]:
        """Customers, newest first. Bounded -- this feeds a screen, not a report."""
        return [self._to_out(c) for c in self.repository.list_recent(limit=limit)]

    def get_customer(self, customer_id: int) -> CustomerOut | None:
        customer = self.repository.get(customer_id)
        return self._to_out(customer) if customer is not None else None

    # -----------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------

    def opt_in(
        self, customer_id: int, *, source: str = CONSENT_SOURCE_STAFF
    ) -> CustomerOut | None:
        """Record affirmative consent. Idempotent in effect, not in timestamp.

        Opting in an already-opted-in customer refreshes the timestamp rather
        than erroring. That is the honest record: they were asked again and
        agreed again.

        The earlier opt-out timestamp is NOT cleared. Consent history is
        append-only in spirit -- erasing the withdrawal would destroy exactly the
        evidence an audit would ask for.
        """
        customer = self.repository.get(customer_id)
        if customer is None:
            return None

        customer.whatsapp_opt_in_at = datetime.now()
        customer.whatsapp_consent_source = source
        self.db.commit()
        self.db.refresh(customer)
        return self._to_out(customer)

    def opt_out(self, customer_id: int, *, reason: str | None = None) -> CustomerOut | None:
        """Record withdrawal of consent.

        Works from ANY prior state, including NOT_SET. A customer who says "never
        message me" before ever opting in has made a decision, and recording it
        as an explicit opt-out is what stops staff asking them again at the next
        visit. Treating it as a no-op would lose that.
        """
        customer = self.repository.get(customer_id)
        if customer is None:
            return None

        customer.whatsapp_opt_out_at = datetime.now()
        customer.whatsapp_opt_out_reason = reason
        self.db.commit()
        self.db.refresh(customer)
        return self._to_out(customer)

    # -----------------------------------------------------------------
    # Mapping
    # -----------------------------------------------------------------

    @staticmethod
    def _to_out(customer) -> CustomerOut:
        return CustomerOut(
            id=customer.id,
            name=customer.name,
            phone=customer.phone,
            consent_state=consent_state(customer),
            whatsapp_opt_in_at=customer.whatsapp_opt_in_at,
            whatsapp_opt_out_at=customer.whatsapp_opt_out_at,
            whatsapp_opt_out_reason=customer.whatsapp_opt_out_reason,
            whatsapp_consent_source=customer.whatsapp_consent_source,
            phone_is_reachable=is_valid_indian_mobile(customer.phone),
            created_at=customer.created_at,
        )
