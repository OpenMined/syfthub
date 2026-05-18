"""Remove the Organization entity.

Organizations and organization-owned endpoints are being removed entirely.
Every endpoint is now owned by exactly one user.

This migration:
- Deletes all organization-owned endpoints (``organization_id IS NOT NULL``).
- Drops the ``(user_id XOR organization_id)`` check constraint, the
  ``organization_id`` foreign key, column, and its indexes from ``endpoints``.
- Makes ``endpoints.user_id`` NOT NULL (every endpoint is user-owned).
- Drops the ``organization_members`` and ``organizations`` tables.

WARNING: This migration is destructive. Organization-owned endpoint rows are
deleted permanently and cannot be recovered by ``downgrade()`` — the downgrade
only restores the schema, not the deleted data.

Revision ID: 015_remove_organizations
Revises: 014_drop_uptime_latency
Create Date: 2026-05-18 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_remove_organizations"
down_revision: str | None = "014_drop_uptime_latency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Delete organization-owned endpoints before dropping the column.
    op.execute("DELETE FROM endpoints WHERE organization_id IS NOT NULL")

    # Drop the single-owner check constraint (references organization_id).
    op.drop_constraint("ck_endpoints_single_owner", "endpoints", type_="check")

    # Drop the foreign key and indexes tied to organization_id.
    op.drop_constraint(
        "endpoints_organization_id_fkey", "endpoints", type_="foreignkey"
    )
    op.drop_index("idx_endpoints_org_slug", table_name="endpoints")
    op.drop_index("idx_endpoints_organization_id", table_name="endpoints")

    # Every remaining endpoint is user-owned; enforce it at the schema level.
    op.alter_column("endpoints", "user_id", existing_type=sa.Integer(), nullable=False)

    # Drop the organization_id column.
    op.drop_column("endpoints", "organization_id")

    # Drop organization tables (organization_members first — FK to organizations).
    op.drop_table("organization_members")
    op.drop_table("organizations")


def downgrade() -> None:
    # Recreate the organizations table.
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("domain", sa.String(length=500), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_organizations_slug", "organizations", ["slug"])
    op.create_index("idx_organizations_name", "organizations", ["name"])
    op.create_index("idx_organizations_is_active", "organizations", ["is_active"])
    op.create_index(
        "idx_organizations_heartbeat_expires_at",
        "organizations",
        ["heartbeat_expires_at"],
    )

    # Recreate the organization_members table.
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_org_members_org_id", "organization_members", ["organization_id"]
    )
    op.create_index("idx_org_members_user_id", "organization_members", ["user_id"])
    op.create_index("idx_org_members_role", "organization_members", ["role"])
    op.create_index("idx_org_members_is_active", "organization_members", ["is_active"])
    op.create_index(
        "idx_org_members_unique",
        "organization_members",
        ["organization_id", "user_id"],
        unique=True,
    )

    # Restore the organization_id column on endpoints.
    op.add_column(
        "endpoints",
        sa.Column("organization_id", sa.Integer(), nullable=True),
    )
    op.alter_column("endpoints", "user_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        "endpoints_organization_id_fkey",
        "endpoints",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index("idx_endpoints_organization_id", "endpoints", ["organization_id"])
    op.create_index(
        "idx_endpoints_org_slug",
        "endpoints",
        ["organization_id", "slug"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_endpoints_single_owner",
        "endpoints",
        "(user_id IS NULL) != (organization_id IS NULL)",
    )
