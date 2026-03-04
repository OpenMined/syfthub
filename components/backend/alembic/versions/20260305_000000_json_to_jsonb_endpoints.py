"""Alter endpoints JSON columns to JSONB.

The initial Alembic migration (000) created these columns as JSONB on
PostgreSQL, but databases that existed before Alembic (i.e., prod) were
created via SQLAlchemy create_all() which used plain JSON.  The ORM model
now declares JSONB (via JSON().with_variant(JSONB(), "postgresql")), so
this migration brings older databases in line.

Revision ID: 006_json_to_jsonb
Revises: 003_encryption_key
Create Date: 2026-03-05 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_json_to_jsonb"
down_revision: str | None = "003_encryption_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Columns on the endpoints table that need to be converted.
_COLUMNS = ("tags", "contributors", "policies", "connect")


def upgrade() -> None:
    """Convert endpoints JSON columns from json to jsonb."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # Only relevant for PostgreSQL

    for col in _COLUMNS:
        op.execute(
            sa.text(
                f'ALTER TABLE endpoints ALTER COLUMN "{col}" '
                f'TYPE jsonb USING "{col}"::jsonb'
            )
        )


def downgrade() -> None:
    """Revert endpoints jsonb columns back to json."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for col in _COLUMNS:
        op.execute(
            sa.text(
                f'ALTER TABLE endpoints ALTER COLUMN "{col}" '
                f'TYPE json USING "{col}"::json'
            )
        )
