"""Add encryption_public_key column to users table for NATS tunnel E2E encryption.

Spaces register their X25519 public key on startup so the aggregator can encrypt
tunnel request payloads destined for that space.

Revision ID: 003_encryption_key
Revises: 002_api_tokens
Create Date: 2026-02-26 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic
revision: str = "003_encryption_key"
down_revision: str | None = "002_api_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add encryption_public_key column to users table.

    Column: encryption_public_key
    - Stores the base64url-encoded X25519 public key for the space
    - Nullable: spaces that have not registered a key have NULL
    - VARCHAR(500): sufficient for a 32-byte key in base64url (44 chars) plus headroom
    - No index needed: lookups are by username (already indexed), not by key value
    """
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.add_column(
        "users",
        sa.Column("encryption_public_key", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """Drop encryption_public_key column from users table."""
    op.drop_column("users", "encryption_public_key")
