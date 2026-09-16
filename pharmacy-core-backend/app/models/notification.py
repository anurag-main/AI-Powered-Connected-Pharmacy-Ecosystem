"""SQLAlchemy models for outbound notifications (M6.3).

TWO TABLES, AND WHY NOT THREE
-----------------------------
``notifications``       one logical reminder. The thing that must never duplicate.
``notification_events`` one row per provider callback. The audit trail.

A separate ``notification_attempts`` table was considered and rejected. Attempts
are only interesting as "how many times did we try and what went wrong last
time", which is two columns, and a third table would need joining on every
dashboard query to answer a question the parent row can answer itself. The
webhook events DO need their own table, because they arrive out of order, they
arrive more than once, and they must be deduplicated against a provider id we do
not control.

THE INVARIANT
-------------
    ONE refill opportunity + ONE channel = ONE logical notification

That is enforced by a UNIQUE index on ``idempotency_key``, not by careful
scheduler code. A scheduler that runs twice, a retried HTTP request, a server
restart mid-send and an ambiguous provider response all collide on the same key
and lose. Application logic can be wrong at 3am; a UNIQUE constraint cannot.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer


class Notification(Base):
    """One logical reminder to one customer on one channel."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # THE duplicate guard. Built by the refill domain
    # (`RefillCandidate.idempotency_key`) plus the channel, e.g.
    #   refill:1042:2026-09-20:whatsapp
    # Keyed on the SALE ITEM rather than (customer, medicine, date): correcting a
    # sale line's days_supply moves the refill date, which correctly becomes a
    # different opportunity instead of silently reusing this row's "already sent"
    # record.
    idempotency_key: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True
    )

    # ---- who and why (the refill opportunity this came from) ----
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="RESTRICT"), nullable=False
    )
    # The sale line whose days_supply produced the date. Provenance: a pharmacist
    # can open the exact invoice behind any reminder that went out.
    source_sale_item_id: Mapped[int] = mapped_column(
        ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False
    )
    expected_refill_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # ---- channel ----
    # "whatsapp" today. A column rather than an assumption, because the whole
    # point of the M6 layering is that voice arrives later without a new table.
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="whatsapp")

    # ---- which template, frozen ----
    # Stored per notification, not read from config at display time. Templates get
    # edited and re-approved; without this, a message sent last month would be
    # explained by this month's wording. Same freezing rule as unit_price.
    #
    # There is deliberately no invented `template_version` integer: Meta does not
    # expose a version on an approved template, so any number here would be ours
    # and would mean nothing to anyone reading the logs. The NAME and LANGUAGE are
    # what Meta actually keys on, and the parameters we sent are recorded so the
    # rendered text can always be reconstructed.
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    template_language: Mapped[str] = mapped_column(String(10), nullable=False)
    template_params: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- lifecycle ----
    # pending | sending | sent | delivered | read | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # Meta's wamid. NULL until the API accepts the message. Indexed because every
    # inbound webhook looks a notification up by it.
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Separate timestamps rather than one "status_changed_at", because the
    # question a pharmacy asks is "when was it delivered", and a single column
    # loses that the moment the next status arrives.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_notifications_provider_message_id", "provider_message_id"),
        Index("ix_notifications_customer_id", "customer_id"),
        Index("ix_notifications_status", "status"),
    )

    customer: Mapped["Customer"] = relationship("Customer")
    events: Mapped[list["NotificationEvent"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} key={self.idempotency_key!r} "
            f"status={self.status}>"
        )


class NotificationEvent(Base):
    """One provider callback about one notification.

    WHY THIS TABLE EXISTS
    ---------------------
    Meta explicitly may deliver the same webhook more than once, and status
    events arrive out of order. Both problems are solved by recording every event
    with a UNIQUE constraint on (provider_event_id, status) and letting the
    database reject the second copy.

    Why the constraint is on the PAIR and not on the message id alone: one
    message legitimately produces several events (sent, then delivered, then
    read) and they all carry the SAME wamid. Deduplicating on wamid alone would
    throw away the delivery and read notifications and freeze every message at
    "sent".
    """

    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )

    # Meta's wamid for the message this event is about.
    provider_event_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # sent | delivered | read | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # Provider's own timestamp, not ours. Used to reason about ordering when
    # events arrive late.
    event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_event_id", "status", name="uq_notification_events_id_status"
        ),
        Index("ix_notification_events_notification_id", "notification_id"),
    )

    notification: Mapped["Notification"] = relationship(back_populates="events")

    def __repr__(self) -> str:
        return (
            f"<NotificationEvent id={self.id} wamid={self.provider_event_id!r} "
            f"status={self.status}>"
        )
