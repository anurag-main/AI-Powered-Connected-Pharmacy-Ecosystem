"""Pydantic schemas for the Customer domain (M6.1).

`CustomerOut` carries a DERIVED `consent_state` alongside the raw timestamps.
Both on purpose: the state is what every caller actually branches on, and
recomputing it in the frontend would be a second implementation of a rule with
legal weight. The timestamps travel too because an audit asks "when", and a
state alone cannot answer that.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CustomerOut(BaseModel):
    """A customer and their WhatsApp consent position."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    phone: str

    # "not_set" | "opted_in" | "opted_out" -- derived, never stored.
    consent_state: str

    whatsapp_opt_in_at: datetime | None
    whatsapp_opt_out_at: datetime | None
    whatsapp_opt_out_reason: str | None
    whatsapp_consent_source: str | None

    # Whether the stored number could actually receive a message. Separate from
    # consent: rows written before M6.1 were never validated, so a customer can
    # be opted in AND unreachable.
    phone_is_reachable: bool

    created_at: datetime


class OptOutRequest(BaseModel):
    """Optional free-text reason for withdrawing consent.

    Not an enum. The value of this field is recording the reason nobody
    anticipated; a fixed list would file every one of those under "other".
    """

    reason: str | None = Field(default=None, max_length=200)
