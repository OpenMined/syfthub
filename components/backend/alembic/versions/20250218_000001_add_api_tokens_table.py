"""Add api_tokens table for personal access token authentication.

This migration adds the api_tokens table which enables API token-based
authentication as an alternative to username/password. Tokens are stored
as SHA-256 hashes for security.

Revision ID: 002_api_tokens
Revises: 001_initial
Create Date: 2025-02-18 00:00:01.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic
revision: str = "002_api_tokens"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create api_tokens table for personal access token authentication.

    Table: api_tokens
    - Stores hashed API tokens for programmatic access
    - Supports scoped permissions (read, write, full)
    - Tracks usage (last_used_at, last_used_ip)
    - Supports optional expiration dates
    - Soft delete via is_active flag for audit trail
    """
    # Determine if we're on PostgreSQL for JSONB support
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    # JSON type selection: JSONB for PostgreSQL, JSON for SQLite
    json_type = postgresql.JSONB() if is_postgresql else sa.JSON()

    # =========================================================================
    # api_tokens table
    # =========================================================================
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Owner relationship
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Token identification
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        # Permissions - scopes as JSON array
        sa.Column("scopes", json_type, nullable=False),
        # Expiration - null means never expires
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        # Usage tracking
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", sa.String(length=45), nullable=True),
        # Soft delete for revocation
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        # Timestamps from TimestampMixin
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Constraints
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    # Indexes for performance
    # Primary lookup index - must be unique for auth
    op.create_index(
        "idx_api_tokens_token_hash",
        "api_tokens",
        ["token_hash"],
        unique=True,
    )
    # For listing user's tokens
    op.create_index("idx_api_tokens_user_id", "api_tokens", ["user_id"])
    # For listing active tokens for a user
    op.create_index(
        "idx_api_tokens_user_active",
        "api_tokens",
        ["user_id", "is_active"],
    )
    # For cleanup of expired tokens
    op.create_index("idx_api_tokens_expires_at", "api_tokens", ["expires_at"])


def downgrade() -> None:
    """Drop api_tokens table and all its indexes."""
    op.drop_index("idx_api_tokens_expires_at", table_name="api_tokens")
    op.drop_index("idx_api_tokens_user_active", table_name="api_tokens")
    op.drop_index("idx_api_tokens_user_id", table_name="api_tokens")
    op.drop_index("idx_api_tokens_token_hash", table_name="api_tokens")
    op.drop_table("api_tokens")
