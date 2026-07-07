"""Add per-endpoint health fields for client-reported health status.

This migration adds three nullable columns to the endpoints table to support
client-reported per-endpoint health status via POST /endpoints/health.

Fields:
- health_status: "healthy" or "unhealthy" (reported by client)
- health_checked_at: When the client last checked the endpoint
- health_ttl_seconds: How long the health status is valid

All columns are nullable with no defaults, so existing endpoints are unaffected.
NULL values mean no client-reported status (fallback to heartbeat-based health).

Revision ID: 007_endpoint_health
Revises: 006_json_to_jsonb
Create Date: 2026-03-02 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic
revision: str = "007_endpoint_health"
down_revision: str | None = "006_json_to_jsonb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add per-endpoint health fields to endpoints table."""
    op.add_column(
        "endpoints",
        sa.Column("health_status", sa.String(20), nullable=True),
    )
    op.add_column(
        "endpoints",
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "endpoints",
        sa.Column("health_ttl_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Remove per-endpoint health fields from endpoints table."""
    op.drop_column("endpoints", "health_ttl_seconds")
    op.drop_column("endpoints", "health_checked_at")
    op.drop_column("endpoints", "health_status")
