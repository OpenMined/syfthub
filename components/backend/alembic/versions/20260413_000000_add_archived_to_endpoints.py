"""Add archived column to endpoints table.

Marks endpoints as archived when the operator wants to stop new purchases/
subscriptions while keeping the endpoint accessible to existing users.
Archived endpoints are forced to private visibility so they no longer appear
in public marketplace listings.

Revision ID: 009_add_archived
Revises: 008_encrypt_accounting_pw
Create Date: 2026-04-13 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic
revision: str = "009_add_archived"
down_revision: str | None = "008_encrypt_accounting_pw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add archived boolean column (default False) and a covering index."""
    op.add_column(
        "endpoints",
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_index("idx_endpoints_archived", "endpoints", ["archived"])


def downgrade() -> None:
    """Remove archived column and its index."""
    op.drop_index("idx_endpoints_archived", table_name="endpoints")
    op.drop_column("endpoints", "archived")
