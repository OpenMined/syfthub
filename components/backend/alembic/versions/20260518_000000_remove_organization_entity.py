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


# SQLite does not persist foreign-key constraint names, so a batch-mode
# recreate reflects the organization_id FK as anonymous. This naming
# convention re-derives the PostgreSQL-style name Alembic created in
# 001_initial (``endpoints_organization_id_fkey``) so it can be dropped by
# name on SQLite as well.
_FK_NAMING_CONVENTION = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}


def upgrade() -> None:
    # Delete organization-owned endpoints before dropping the column.
    op.execute("DELETE FROM endpoints WHERE organization_id IS NOT NULL")

    # Batch mode so the endpoints changes work on SQLite (used by the test
    # suite) as well as PostgreSQL. SQLite cannot ALTER constraints or columns
    # in place; batch mode recreates the table via copy-and-move, while on
    # PostgreSQL it emits direct ALTER statements.
    with op.batch_alter_table(
        "endpoints", schema=None, naming_convention=_FK_NAMING_CONVENTION
    ) as batch_op:
        # Drop the single-owner check constraint (references organization_id).
        batch_op.drop_constraint("ck_endpoints_single_owner", type_="check")

        # Drop the foreign key and indexes tied to organization_id.
        batch_op.drop_constraint("endpoints_organization_id_fkey", type_="foreignkey")
        batch_op.drop_index("idx_endpoints_org_slug")
        batch_op.drop_index("idx_endpoints_organization_id")

        # Every remaining endpoint is user-owned; enforce it at the schema level.
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)

        # Drop the organization_id column.
        batch_op.drop_column("organization_id")

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

    # Restore the organization_id column on endpoints. Batch mode keeps this
    # SQLite-compatible (see upgrade() for the rationale).
    with op.batch_alter_table("endpoints", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_foreign_key(
            "endpoints_organization_id_fkey",
            "organizations",
            ["organization_id"],
            ["id"],
        )
        batch_op.create_index("idx_endpoints_organization_id", ["organization_id"])
        batch_op.create_index(
            "idx_endpoints_org_slug",
            ["organization_id", "slug"],
            unique=True,
        )
        batch_op.create_check_constraint(
            "ck_endpoints_single_owner",
            "(user_id IS NULL) != (organization_id IS NULL)",
        )
