"""Add collectives and collective_members tables.

Introduces the Collectives feature: a user-owned grouping of endpoints. The
``collectives`` table holds the group itself; ``collective_members`` is the
associative table linking endpoints to collectives, carrying the join/invite
workflow status (pending / invited / approved / rejected).

Revision ID: 015_collectives
Revises: 014_drop_uptime_latency
Create Date: 2026-05-18 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "015_collectives"
down_revision: str | None = "014_drop_uptime_latency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSONB on PostgreSQL, JSON elsewhere (SQLite in tests) — matches the model's JSONType.
_json_type = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "collectives",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "auto_approve",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("icon_url", sa.String(500), nullable=True),
        sa.Column("tags", _json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("slug", name="uq_collectives_slug"),
    )
    op.create_index("idx_collectives_owner_id", "collectives", ["owner_id"])
    op.create_index("idx_collectives_slug", "collectives", ["slug"])

    op.create_table(
        "collective_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "collective_id",
            sa.Integer(),
            sa.ForeignKey("collectives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "endpoint_id",
            sa.Integer(),
            sa.ForeignKey("endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "collective_id", "endpoint_id", name="uq_collective_members_pair"
        ),
    )
    op.create_index(
        "idx_collective_members_collective_id",
        "collective_members",
        ["collective_id"],
    )
    op.create_index(
        "idx_collective_members_endpoint_id",
        "collective_members",
        ["endpoint_id"],
    )
    op.create_index(
        "idx_collective_members_collective_status",
        "collective_members",
        ["collective_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_collective_members_collective_status",
        table_name="collective_members",
    )
    op.drop_index("idx_collective_members_endpoint_id", table_name="collective_members")
    op.drop_index(
        "idx_collective_members_collective_id", table_name="collective_members"
    )
    op.drop_table("collective_members")

    op.drop_index("idx_collectives_slug", table_name="collectives")
    op.drop_index("idx_collectives_owner_id", table_name="collectives")
    op.drop_table("collectives")
