"""Add the endpoint_benchmark_cards table.

A table of its own, not more columns on ``endpoints``: most endpoints are
never benchmarked, so columns on the parent table would be NULL for most rows
and every one of them would have to be nullable. Here the row is the card, so
absence of a measurement is absence of a row, and the fields that make a card
a card can be NOT NULL.

The card is stored in two shapes at once: scalar columns for a listing to
paint a badge and sort by, and ``report`` (the whole card) for the detail
page. See ``EndpointBenchmarkCardModel`` for the column-by-column rationale.

Revision ID: 026_benchmark_cards
Revises: 025_satellites
Create Date: 2026-09-16 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# Revision identifiers, used by Alembic
revision: str = "026_benchmark_cards"
down_revision: str | None = "025_satellites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors EndpointBenchmarkCardModel.report: JSONB on PostgreSQL so the
# document can be queried later, plain JSON on SQLite for the test database.
_REPORT_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")  # type: ignore[no-untyped-call]


def upgrade() -> None:
    """Create the benchmark card table."""
    op.create_table(
        "endpoint_benchmark_cards",
        # The endpoint is the key. One card per endpoint, uniqueness for free,
        # and no surrogate id to let a second card in through the side door.
        sa.Column("endpoint_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("fabrication_rate", sa.Float(), nullable=True),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("reliable", sa.Boolean(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report", _REPORT_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # CASCADE: a deleted endpoint has no quality to report. A card outliving
        # its endpoint could only ever be shown against the wrong one.
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("endpoint_id"),
    )
    # Browsing sorts and filters by the headline share; the detail document is
    # never a search key, which is the whole reason it can stay a document.
    op.create_index(
        "idx_endpoint_benchmark_cards_score",
        "endpoint_benchmark_cards",
        ["score"],
    )


def downgrade() -> None:
    """Drop the benchmark card table."""
    op.drop_index(
        "idx_endpoint_benchmark_cards_score",
        table_name="endpoint_benchmark_cards",
    )
    op.drop_table("endpoint_benchmark_cards")
