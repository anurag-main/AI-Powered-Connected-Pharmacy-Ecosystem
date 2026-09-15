"""M6.1 add days_supply and WhatsApp consent

Revision ID: c7a1e4b90f21
Revises: a4750b4a1a2a
Create Date: 2026-09-15

Adds the facts the future refill engine will need, and nothing that interprets
them. No schedules, no notifications, no WhatsApp state beyond consent.

Every column added here is NULLABLE, which is what makes this migration safe to
run against the live table with 537 sales already in it. There is no backfill
and deliberately so:

  * sale_items.days_supply stays NULL on every historic row because nobody
    recorded a duration for those sales. NULL means "unknown", and the refill
    engine must skip those lines. Backfilling a guess would manufacture refill
    reminders for medicine bought months ago.

  * customers.whatsapp_opt_in_at stays NULL on all 41 existing customers,
    meaning "never asked". Under the DPDP Act consent cannot be inferred from a
    past transaction, so the only lawful backfill is none.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a1e4b90f21'
down_revision: Union[str, Sequence[str], None] = 'a4750b4a1a2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add days supply columns and WhatsApp consent columns."""
    # ---- The dispensed duration, frozen per line (the M6.1 core) ----
    op.add_column("sale_items", sa.Column("days_supply", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_sale_items_days_supply_range",
        "sale_items",
        "days_supply IS NULL OR (days_supply >= 1 AND days_supply <= 365)",
    )

    # ---- The catalogue hint that pre-fills the billing form ----
    op.add_column(
        "medicines", sa.Column("default_days_supply", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_medicines_default_days_supply_range",
        "medicines",
        "default_days_supply IS NULL "
        "OR (default_days_supply >= 1 AND default_days_supply <= 365)",
    )

    # ---- WhatsApp consent, as timestamps rather than a boolean ----
    op.add_column(
        "customers", sa.Column("whatsapp_opt_in_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "customers", sa.Column("whatsapp_opt_out_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "customers",
        sa.Column("whatsapp_opt_out_reason", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("whatsapp_consent_source", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    """Drop everything this revision added.

    Reversible without data loss for anything that existed before it, because
    every column here is new. The days_supply and consent values recorded while
    it was applied ARE lost on downgrade -- there is nowhere else to put them.
    """
    op.drop_column("customers", "whatsapp_consent_source")
    op.drop_column("customers", "whatsapp_opt_out_reason")
    op.drop_column("customers", "whatsapp_opt_out_at")
    op.drop_column("customers", "whatsapp_opt_in_at")

    op.drop_constraint(
        "ck_medicines_default_days_supply_range", "medicines", type_="check"
    )
    op.drop_column("medicines", "default_days_supply")

    op.drop_constraint(
        "ck_sale_items_days_supply_range", "sale_items", type_="check"
    )
    op.drop_column("sale_items", "days_supply")
