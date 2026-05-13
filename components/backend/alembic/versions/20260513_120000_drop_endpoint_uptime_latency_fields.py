"""Drop latency fields from the endpoint uptime telemetry.

The 30s health-monitor cycle records uptime via the existing 2-tier health
check. Latency, in contrast, can only be supplied by SDK clients via the
new ``POST /endpoints/health`` route, and the in-the-wild SDKs all still
report through the deprecated owner-level heartbeat endpoints.

In practice this means every uptime sample on prod was being recorded from
the Tier 2 (heartbeat) path with no latency signal, leaving the
``latency_*`` columns NULL/zero forever. Drop them rather than carry dead
schema and dead code paths around indefinitely.

Removes:
- ``endpoints.last_latency_ms``
- ``endpoint_uptime_samples.latency_count``
- ``endpoint_uptime_samples.latency_sum_ms``
- ``endpoint_uptime_samples.latency_min_ms``
- ``endpoint_uptime_samples.latency_max_ms``

Revision ID: 014_drop_uptime_latency
Revises: 013_endpoint_uptime
Create Date: 2026-05-13 12:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014_drop_uptime_latency"
down_revision: str | None = "013_endpoint_uptime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("endpoint_uptime_samples", "latency_max_ms")
    op.drop_column("endpoint_uptime_samples", "latency_min_ms")
    op.drop_column("endpoint_uptime_samples", "latency_sum_ms")
    op.drop_column("endpoint_uptime_samples", "latency_count")
    op.drop_column("endpoints", "last_latency_ms")


def downgrade() -> None:
    op.add_column(
        "endpoints",
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "endpoint_uptime_samples",
        sa.Column(
            "latency_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "endpoint_uptime_samples",
        sa.Column(
            "latency_sum_ms",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "endpoint_uptime_samples",
        sa.Column("latency_min_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "endpoint_uptime_samples",
        sa.Column("latency_max_ms", sa.Integer(), nullable=True),
    )
