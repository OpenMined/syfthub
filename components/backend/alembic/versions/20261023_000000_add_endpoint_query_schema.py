"""Add query_schema to endpoints.

Adds a nullable ``query_schema`` JSON column to ``endpoints``: what a query
against the endpoint may carry, as declared by the publishing space
(``schemas.endpoint.QuerySchema``). NULL means the publisher declared nothing,
which is every row written before this column existed.

Revision ID: 026_endpoint_query_schema
Revises: 025_satellites
Create Date: 2026-10-23 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "026_endpoint_query_schema"
down_revision: str | None = "025_satellites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "endpoints",
        sa.Column(
            "query_schema",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("endpoints", "query_schema")
