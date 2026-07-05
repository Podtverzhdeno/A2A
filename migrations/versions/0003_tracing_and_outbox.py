"""Add ledger tracing fields and transactional outbox.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deal_events",
        sa.Column("event_uuid", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "deal_events",
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "deal_events",
        sa.Column("causation_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "deal_events",
        sa.Column("message_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "deal_events",
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE deal_events SET correlation_id = "
        "'00000000-0000-4000-8000-000000000001'"
    )
    op.execute(
        "UPDATE deal_events SET message_id = "
        "'00000000-0000-4000-8000-000000000002'"
    )
    op.execute(
        "UPDATE deal_events SET event_uuid = "
        "'00000000-0000-4000-8000-000000000003'"
    )
    op.alter_column("deal_events", "event_uuid", nullable=False)
    op.alter_column("deal_events", "correlation_id", nullable=False)
    op.alter_column("deal_events", "message_id", nullable=False)

    op.create_table(
        "outbox_messages",
        sa.Column("outbox_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_agent_id", sa.String(length=100), nullable=False),
        sa.Column("message_type", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("causation_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("outbox_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
    )
    op.create_index("ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"])
    op.create_index(
        "ix_outbox_messages_message_type",
        "outbox_messages",
        ["message_type"],
    )
    op.create_index(
        "ix_outbox_messages_recipient_agent_id",
        "outbox_messages",
        ["recipient_agent_id"],
    )
    op.create_index("ix_outbox_messages_status", "outbox_messages", ["status"])


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_status", table_name="outbox_messages")
    op.drop_index(
        "ix_outbox_messages_recipient_agent_id",
        table_name="outbox_messages",
    )
    op.drop_index("ix_outbox_messages_message_type", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_aggregate_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_column("deal_events", "event_uuid")
    op.drop_column("deal_events", "payload_hash")
    op.drop_column("deal_events", "message_id")
    op.drop_column("deal_events", "causation_id")
    op.drop_column("deal_events", "correlation_id")
