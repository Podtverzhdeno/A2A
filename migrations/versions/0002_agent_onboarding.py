"""Add organization and external agent onboarding.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("tax_id", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("organization_id"),
        sa.UniqueConstraint("tax_id"),
    )
    op.create_index(
        "ix_organizations_tax_id",
        "organizations",
        ["tax_id"],
    )
    op.create_table(
        "agent_registrations",
        sa.Column("registration_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("endpoint_url", sa.String(length=500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("registration_id"),
        sa.UniqueConstraint("agent_id"),
    )
    op.create_index(
        "ix_agent_registrations_agent_id",
        "agent_registrations",
        ["agent_id"],
    )
    op.create_index(
        "ix_agent_registrations_organization_id",
        "agent_registrations",
        ["organization_id"],
    )
    op.create_index(
        "ix_agent_registrations_status",
        "agent_registrations",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_registrations_status",
        table_name="agent_registrations",
    )
    op.drop_index(
        "ix_agent_registrations_organization_id",
        table_name="agent_registrations",
    )
    op.drop_index(
        "ix_agent_registrations_agent_id",
        table_name="agent_registrations",
    )
    op.drop_table("agent_registrations")
    op.drop_index("ix_organizations_tax_id", table_name="organizations")
    op.drop_table("organizations")
