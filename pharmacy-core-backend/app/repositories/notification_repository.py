"""Storage for outbound notifications (M6.3).

Never commits. The notification service owns the transaction boundary, for the
same reason the goods receipt service does: a send flow touches the notification
row and its event rows together, and a commit in the middle would leave a
notification marked sent with no record of why.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationEvent


class NotificationRepository:
    """SQL access for notifications and their provider events."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -----------------------------------------------------------------
    # Notifications
    # -----------------------------------------------------------------

    def find_by_key(self, idempotency_key: str) -> Notification | None:
        """The duplicate check, backed by a UNIQUE index.

        Checked before inserting so the ordinary path does not rely on catching
        an IntegrityError — but the constraint is still the real guarantee, and
        the service handles the race where two workers pass this check together.
        """
        stmt = select(Notification).where(
            Notification.idempotency_key == idempotency_key
        )
        return self.db.scalars(stmt).first()

    def find_by_provider_message_id(self, provider_message_id: str) -> Notification | None:
        """Look a notification up from a webhook's wamid."""
        stmt = select(Notification).where(
            Notification.provider_message_id == provider_message_id
        )
        return self.db.scalars(stmt).first()

    def get(self, notification_id: int) -> Notification | None:
        return self.db.get(Notification, notification_id)

    def create(self, **fields) -> Notification:
        """Insert and flush for the id. No commit."""
        notification = Notification(**fields)
        self.db.add(notification)
        self.db.flush()
        return notification

    def list_recent(self, *, limit: int) -> list[Notification]:
        stmt = select(Notification).order_by(Notification.id.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())

    def by_source_sale_items(self, sale_item_ids: set[int]) -> dict[int, Notification]:
        """Latest notification per source sale line, for the dashboard.

        One query keyed by sale item, so the refill screen can show notification
        status beside each candidate without a lookup per row.
        """
        if not sale_item_ids:
            return {}
        stmt = (
            select(Notification)
            .where(Notification.source_sale_item_id.in_(sale_item_ids))
            .order_by(Notification.id)
        )
        # Later rows win, so the newest notification per sale line is kept.
        return {n.source_sale_item_id: n for n in self.db.scalars(stmt).all()}

    # -----------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------

    def event_exists(self, *, provider_event_id: str, status: str) -> bool:
        """Has this exact provider event already been processed?

        Keyed on the PAIR because one message emits several events that all carry
        the same wamid. Deduplicating on the wamid alone would discard the
        delivered and read callbacks and freeze every message at "sent".
        """
        stmt = select(NotificationEvent.id).where(
            NotificationEvent.provider_event_id == provider_event_id,
            NotificationEvent.status == status,
        )
        return self.db.scalars(stmt).first() is not None

    def add_event(
        self,
        *,
        notification_id: int,
        provider_event_id: str,
        status: str,
        event_at: datetime | None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> NotificationEvent:
        """Record a provider callback. No commit."""
        event = NotificationEvent(
            notification_id=notification_id,
            provider_event_id=provider_event_id,
            status=status,
            event_at=event_at,
            error_code=error_code,
            error_message=error_message,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def events_for(self, notification_id: int) -> list[NotificationEvent]:
        stmt = (
            select(NotificationEvent)
            .where(NotificationEvent.notification_id == notification_id)
            .order_by(NotificationEvent.id)
        )
        return list(self.db.scalars(stmt).all())
