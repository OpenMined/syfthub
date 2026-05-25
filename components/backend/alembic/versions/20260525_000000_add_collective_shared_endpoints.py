"""Add collective_shared_endpoints and collective_shared_endpoint_members tables.

Adds "shared endpoints" to a collective: named, curated subsets of approved
member endpoints. The implicit ``all`` subset is hardcoded as an alias and is
NOT stored. Existing ``collective/<slug>`` paths continue to fan out to every
approved member.

Revision ID: 018_collective_shared_endpoints
Revises: 017_collective_about
Create Date: 2026-05-25 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_collective_shared_endpoints"
down_revision: str | None = "017_collective_about"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collective_shared_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "collective_id",
            sa.Integer(),
            sa.ForeignKey("collectives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
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
        sa.UniqueConstraint(
            "collective_id", "slug", name="uq_shared_endpoint_collective_slug"
        ),
    )
    op.create_index(
        "idx_shared_endpoint_collective_id",
        "collective_shared_endpoints",
        ["collective_id"],
    )

    op.create_table(
        "collective_shared_endpoint_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "shared_endpoint_id",
            sa.Integer(),
            sa.ForeignKey("collective_shared_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "endpoint_id",
            sa.Integer(),
            sa.ForeignKey("endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "shared_endpoint_id",
            "endpoint_id",
            name="uq_shared_endpoint_member_pair",
        ),
    )
    op.create_index(
        "idx_shared_endpoint_member_shared_id",
        "collective_shared_endpoint_members",
        ["shared_endpoint_id"],
    )
    op.create_index(
        "idx_shared_endpoint_member_endpoint_id",
        "collective_shared_endpoint_members",
        ["endpoint_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_shared_endpoint_member_endpoint_id",
        table_name="collective_shared_endpoint_members",
    )
    op.drop_index(
        "idx_shared_endpoint_member_shared_id",
        table_name="collective_shared_endpoint_members",
    )
    op.drop_table("collective_shared_endpoint_members")

    op.drop_index(
        "idx_shared_endpoint_collective_id",
        table_name="collective_shared_endpoints",
    )
    op.drop_table("collective_shared_endpoints")
