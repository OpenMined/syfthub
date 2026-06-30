"""Drop deprecated user domain-heartbeat fields.

Removes the per-owner domain heartbeat tracking columns from ``users``:
``last_heartbeat_at`` and ``heartbeat_expires_at`` (and the
``idx_users_heartbeat_expires_at`` index). These backed the deprecated
``POST /users/me/heartbeat`` endpoint and the health monitor's domain-level
heartbeat fallback, both of which have been removed. Endpoint liveness is now
driven solely by per-endpoint health reports (``POST /endpoints/health``).

Revision ID: 021_drop_user_heartbeat_fields
Revises: 020_unify_mpp_policy_type
Create Date: 2026-06-30 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021_drop_user_heartbeat_fields"
down_revision: str | None = "020_unify_mpp_policy_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_users_heartbeat_expires_at", table_name="users")
    op.drop_column("users", "heartbeat_expires_at")
    op.drop_column("users", "last_heartbeat_at")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("heartbeat_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_heartbeat_expires_at", "users", ["heartbeat_expires_at"])
