"""Add long-form 'about' field to collectives.

Adds a markdown ``about`` / README column to the ``collectives`` table,
separate from the short ``description``. Shown as the "About" card on the
collective detail page. Defaults to an empty string.

Revision ID: 017_collective_about
Revises: 016_collective_verified
Create Date: 2026-05-18 02:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017_collective_about"
down_revision: str | None = "016_collective_verified"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collectives",
        sa.Column(
            "about",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("collectives", "about")
