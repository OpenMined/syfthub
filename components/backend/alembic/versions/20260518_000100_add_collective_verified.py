"""Add verified flag to collectives.

Adds a platform-granted trust signal to the ``collectives`` table. The column
defaults to False; verification is toggled out-of-band (admin/ops) rather than
through the public collective API.

Revision ID: 016_collective_verified
Revises: 015_collectives
Create Date: 2026-05-18 01:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_collective_verified"
down_revision: str | None = "015_collectives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collectives",
        sa.Column(
            "verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("collectives", "verified")
