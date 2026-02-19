"""Initial schema migration capturing the existing SyftHub database structure.

This migration represents the baseline schema as of the Alembic migration system
introduction. For existing databases that were created using Base.metadata.create_all(),
run `alembic stamp head` to mark this migration as applied without executing it.

For new databases, this migration will create all tables from scratch.

Revision ID: 001_initial
Revises:
Create Date: 2025-02-18 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all initial tables for SyftHub.

    Tables created:
    - users: User accounts (local and OAuth)
    - organizations: Organization accounts
    - organization_members: User-organization membership
    - endpoints: AI/ML endpoints (owned by users or organizations)
    - endpoint_stars: User stars on endpoints
    - user_aggregators: User RAG aggregator configurations
    - error_logs: Error logging for observability
    """
    # Determine if we're on PostgreSQL for JSONB support
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    # JSON type selection: JSONB for PostgreSQL, JSON for SQLite
    json_type = postgresql.JSONB() if is_postgresql else sa.JSON()

    # =========================================================================
    # users table
    # =========================================================================
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False, default="user"),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "auth_provider", sa.String(length=20), nullable=False, default="local"
        ),
        sa.Column("google_id", sa.String(length=255), nullable=True),
        sa.Column("accounting_service_url", sa.String(length=500), nullable=True),
        sa.Column("accounting_password", sa.String(length=255), nullable=True),
        sa.Column("domain", sa.String(length=500), nullable=True),
        sa.Column("aggregator_url", sa.String(length=500), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("google_id"),
    )
    op.create_index("idx_users_username", "users", ["username"])
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_role", "users", ["role"])
    op.create_index("idx_users_is_active", "users", ["is_active"])
    op.create_index("idx_users_heartbeat_expires_at", "users", ["heartbeat_expires_at"])
    op.create_index("idx_users_google_id", "users", ["google_id"])

    # =========================================================================
    # organizations table
    # =========================================================================
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

    # =========================================================================
    # organization_members table
    # =========================================================================
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
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

    # =========================================================================
    # endpoints table
    # =========================================================================
    op.create_table(
        "endpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False, default="public"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("consecutive_failure_count", sa.Integer(), nullable=False, default=0),
        sa.Column("version", sa.String(length=20), nullable=False, default="0.1.0"),
        sa.Column("readme", sa.Text(), nullable=False, server_default=""),
        sa.Column("stars_count", sa.Integer(), nullable=False, default=0),
        sa.Column("tags", json_type, nullable=False),
        sa.Column("contributors", json_type, nullable=False),
        sa.Column("policies", json_type, nullable=False),
        sa.Column("connect", json_type, nullable=False),
        sa.Column("rag_file_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(user_id IS NULL) != (organization_id IS NULL)",
            name="ck_endpoints_single_owner",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_endpoints_user_id", "endpoints", ["user_id"])
    op.create_index("idx_endpoints_organization_id", "endpoints", ["organization_id"])
    op.create_index("idx_endpoints_slug", "endpoints", ["slug"])
    op.create_index(
        "idx_endpoints_user_slug", "endpoints", ["user_id", "slug"], unique=True
    )
    op.create_index(
        "idx_endpoints_org_slug", "endpoints", ["organization_id", "slug"], unique=True
    )
    op.create_index("idx_endpoints_type", "endpoints", ["type"])
    op.create_index("idx_endpoints_visibility", "endpoints", ["visibility"])
    op.create_index("idx_endpoints_is_active", "endpoints", ["is_active"])
    op.create_index("idx_endpoints_version", "endpoints", ["version"])
    op.create_index("idx_endpoints_stars_count", "endpoints", ["stars_count"])
    op.create_index("idx_endpoints_rag_file_id", "endpoints", ["rag_file_id"])

    # =========================================================================
    # endpoint_stars table
    # =========================================================================
    op.create_table(
        "endpoint_stars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint_id", sa.Integer(), nullable=False),
        sa.Column("starred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["endpoints.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_endpoint_stars_user_id", "endpoint_stars", ["user_id"])
    op.create_index("idx_endpoint_stars_endpoint_id", "endpoint_stars", ["endpoint_id"])
    op.create_index(
        "idx_endpoint_stars_unique",
        "endpoint_stars",
        ["user_id", "endpoint_id"],
        unique=True,
    )
    op.create_index("idx_endpoint_stars_starred_at", "endpoint_stars", ["starred_at"])

    # =========================================================================
    # user_aggregators table
    # =========================================================================
    op.create_table(
        "user_aggregators",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user_aggregators_user_id", "user_aggregators", ["user_id"])
    op.create_index(
        "idx_user_aggregators_is_default", "user_aggregators", ["is_default"]
    )

    # =========================================================================
    # error_logs table
    # =========================================================================
    op.create_table(
        "error_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service", sa.String(length=50), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("event", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("context", json_type, nullable=True),
        sa.Column("request_data", json_type, nullable=True),
        sa.Column("response_data", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_error_logs_correlation_id", "error_logs", ["correlation_id"])
    op.create_index("idx_error_logs_service", "error_logs", ["service"])
    op.create_index("idx_error_logs_event", "error_logs", ["event"])
    op.create_index("idx_error_logs_user_id", "error_logs", ["user_id"])
    op.create_index(
        "idx_error_logs_timestamp",
        "error_logs",
        [sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_error_logs_correlation_event",
        "error_logs",
        ["correlation_id", "event"],
    )


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("error_logs")
    op.drop_table("user_aggregators")
    op.drop_table("endpoint_stars")
    op.drop_table("endpoints")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_table("users")
