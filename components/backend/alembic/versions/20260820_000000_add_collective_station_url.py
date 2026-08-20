"""Add optional station URL to collectives.

Adds a nullable ``station_url`` column to the ``collectives`` table — the base
URL of the station hosting the collective, editable by the owner from the
collective settings page. Visible only to the owner, admins, and the owners of
approved member endpoints; the service redacts it for everyone else.

Revision ID: 024_collective_station_url
Revises: 023_user_email_verified_at
Create Date: 2026-08-20 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "024_collective_station_url"
down_revision: str | None = "023_user_email_verified_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collectives",
        sa.Column("station_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collectives", "station_url")
