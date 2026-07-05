"""Create persistent deals and append-only ledger.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deals",
        sa.Column("deal_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.String(length=100), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("deal_id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_deals_customer_id", "deals", ["customer_id"])
    op.create_index("ix_deals_sku", "deals", ["sku"])
    op.create_index("ix_deals_status", "deals", ["status"])
    op.create_index("ix_deals_updated_at", "deals", ["updated_at"])
    op.create_table(
        "deal_events",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("deal_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["deal_id"],
            ["deals.deal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "deal_id",
            "sequence_number",
            name="uq_deal_event_sequence",
        ),
    )
    op.create_index("ix_deal_events_deal_id", "deal_events", ["deal_id"])
    op.create_index(
        "ix_deal_events_event_type",
        "deal_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_deal_events_event_type", table_name="deal_events")
    op.drop_index("ix_deal_events_deal_id", table_name="deal_events")
    op.drop_table("deal_events")
    op.drop_index("ix_deals_updated_at", table_name="deals")
    op.drop_index("ix_deals_status", table_name="deals")
    op.drop_index("ix_deals_sku", table_name="deals")
    op.drop_index("ix_deals_customer_id", table_name="deals")
    op.drop_table("deals")
