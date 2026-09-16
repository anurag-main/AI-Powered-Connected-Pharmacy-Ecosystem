"""M6.3 add notifications and notification_events

Revision ID: e2d5b7c41a80
Revises: c7a1e4b90f21
Create Date: 2026-09-16

Two tables. The constraints are the interesting part:

* ``uq_notifications_idempotency_key`` is what actually prevents duplicate
  reminders. Not the scheduler, not a lock, not an "already sent" flag checked in
  Python — a UNIQUE index, which is still correct when two workers race, when a
  request is retried, and when the process dies mid-send.

* ``uq_notification_events_id_status`` deduplicates webhook redeliveries. It is
  on the PAIR because one message legitimately emits several events (sent, then
  delivered, then read) that all carry the same wamid. A unique index on the
  wamid alone would discard the delivery and read callbacks and freeze every
  message at "sent".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2d5b7c41a80'
down_revision: Union[str, Sequence[str], None] = 'c7a1e4b90f21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the notification tables."""
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("medicine_id", sa.Integer(), nullable=False),
        sa.Column("source_sale_item_id", sa.Integer(), nullable=False),
        sa.Column("expected_refill_date", sa.DateTime(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("template_name", sa.String(length=100), nullable=False),
        sa.Column("template_language", sa.String(length=10), nullable=False),
        sa.Column("template_params", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=40), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["medicine_id"], ["medicines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_sale_item_id"], ["sale_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_notifications_idempotency_key"),
    )
    op.create_index(
        "ix_notifications_provider_message_id", "notifications", ["provider_message_id"]
    )
    op.create_index("ix_notifications_customer_id", "notifications", ["customer_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])

    op.create_table(
        "notification_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("event_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_event_id", "status", name="uq_notification_events_id_status"
        ),
    )
    op.create_index(
        "ix_notification_events_notification_id",
        "notification_events",
        ["notification_id"],
    )


def downgrade() -> None:
    """Drop both tables. Reversible with no loss to anything pre-existing."""
    op.drop_index(
        "ix_notification_events_notification_id", table_name="notification_events"
    )
    op.drop_table("notification_events")

    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_customer_id", table_name="notifications")
    op.drop_index(
        "ix_notifications_provider_message_id", table_name="notifications"
    )
    op.drop_table("notifications")
