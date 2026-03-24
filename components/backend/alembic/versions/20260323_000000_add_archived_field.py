"""Add archived field to endpoints table.

Adds an `archived` boolean column (default False) so endpoint owners can
archive endpoints to prevent new bundle purchases while allowing existing
users to consume remaining credits.

Revision ID: 008_archived
Revises: 007_endpoint_health
Create Date: 2026-03-23 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic
revision: str = "008_archived"
down_revision: str | None = "007_endpoint_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "endpoints",
        sa.Column(
            "archived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )


def downgrade() -> None:
    op.drop_column("endpoints", "archived")
