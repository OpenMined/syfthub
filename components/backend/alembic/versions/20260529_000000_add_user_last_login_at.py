"""Add users.last_login_at column.

Adds a nullable, timezone-aware ``last_login_at`` timestamp to the ``users``
table. Stamped on a successful password login or Google sign-in (not on token
refresh or registration). Backs the last-login recency buckets of the admin
user-overview dashboard.

Revision ID: 019_add_user_last_login_at
Revises: 018_collective_shared_endpoints
Create Date: 2026-05-29 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019_add_user_last_login_at"
down_revision: str | None = "018_collective_shared_endpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_last_login_at", "users", ["last_login_at"])


def downgrade() -> None:
    op.drop_index("idx_users_last_login_at", table_name="users")
    op.drop_column("users", "last_login_at")
