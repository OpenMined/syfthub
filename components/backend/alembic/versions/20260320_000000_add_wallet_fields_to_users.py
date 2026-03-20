"""Replace accounting fields with wallet fields on users table.

Adds wallet_address and wallet_private_key columns for MPP / Tempo blockchain
payments. Drops old accounting_service_url and accounting_password columns.

Revision ID: 008_wallet_fields
Revises: 007_endpoint_health
Create Date: 2026-03-20 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic
revision: str = "008_wallet_fields"
down_revision: str | None = "007_endpoint_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add wallet fields, drop accounting fields."""
    # Add new wallet fields
    op.add_column(
        "users",
        sa.Column("wallet_address", sa.String(42), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("wallet_private_key", sa.String(66), nullable=True),
    )

    # Drop old accounting fields
    op.drop_column("users", "accounting_service_url")
    op.drop_column("users", "accounting_password")


def downgrade() -> None:
    """Remove wallet fields, restore accounting fields."""
    # Restore accounting fields
    op.add_column(
        "users",
        sa.Column(
            "accounting_service_url", sa.String(), nullable=True, server_default=""
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "accounting_password", sa.String(), nullable=True, server_default=""
        ),
    )

    # Drop wallet fields
    op.drop_column("users", "wallet_private_key")
    op.drop_column("users", "wallet_address")
