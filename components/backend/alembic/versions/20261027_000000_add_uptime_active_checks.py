"""Add endpoint_uptime_samples.active_checks.

``active_checks`` counts the monitor cycles in which the endpoint was listed
active, i.e. after the consecutive-failure rule that also drives
``is_active``. The uptime chart now draws this instead of the raw
``healthy_checks``, so a single missed report no longer paints a day red.
Existing rows are backfilled with ``healthy_checks`` so history keeps its
shape; the two series only diverge for samples written after this upgrade.

Revision ID: 027_uptime_active_checks
Revises: 026_endpoint_query_schema
Create Date: 2026-10-27 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "027_uptime_active_checks"
down_revision: str | None = "026_endpoint_query_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "endpoint_uptime_samples",
        sa.Column(
            "active_checks",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute("UPDATE endpoint_uptime_samples SET active_checks = healthy_checks")


def downgrade() -> None:
    op.drop_column("endpoint_uptime_samples", "active_checks")
