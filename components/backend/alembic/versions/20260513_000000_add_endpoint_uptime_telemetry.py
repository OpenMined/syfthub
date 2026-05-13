"""Add endpoint uptime telemetry table and last_latency_ms column.

Adds a new ``endpoint_uptime_samples`` table that stores bucketed uptime
+ latency aggregates emitted by the health monitor once per cycle, and a
``endpoints.last_latency_ms`` column populated by clients reporting through
``POST /endpoints/health``.

Bucket key is ``(endpoint_id, bucket_start)`` where ``bucket_start`` is
``floor(epoch / uptime_bucket_seconds) * uptime_bucket_seconds`` (default
1800s = 30 minutes, mirroring ``heartbeat_max_ttl_seconds``).

Revision ID: 013_endpoint_uptime
Revises: 012_user_public_profile
Create Date: 2026-05-13 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013_endpoint_uptime"
down_revision: str | None = "012_user_public_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "endpoints",
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
    )

    op.create_table(
        "endpoint_uptime_samples",
        sa.Column("endpoint_id", sa.Integer(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "total_checks",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "healthy_checks",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "latency_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "latency_sum_ms",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("latency_min_ms", sa.Integer(), nullable=True),
        sa.Column("latency_max_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("endpoint_id", "bucket_start"),
    )
    op.create_index(
        "idx_endpoint_uptime_endpoint_bucket",
        "endpoint_uptime_samples",
        ["endpoint_id", sa.text("bucket_start DESC")],
    )
    op.create_index(
        "idx_endpoint_uptime_bucket_start",
        "endpoint_uptime_samples",
        ["bucket_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_endpoint_uptime_bucket_start", table_name="endpoint_uptime_samples"
    )
    op.drop_index(
        "idx_endpoint_uptime_endpoint_bucket", table_name="endpoint_uptime_samples"
    )
    op.drop_table("endpoint_uptime_samples")
    op.drop_column("endpoints", "last_latency_ms")
