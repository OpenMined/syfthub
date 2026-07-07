"""Merge the 009_wallet_fields and 009_add_archived branch heads.

Both migrations descended from 008_encrypt_accounting_pw independently,
creating two alembic heads. This merge migration unifies the graph so that
'alembic upgrade head' resolves to a single target.

Revision ID: 010_merge_heads
Revises: 009_wallet_fields, 009_add_archived
Create Date: 2026-04-28 00:00:00.000000+00:00
"""

from collections.abc import Sequence

revision: str = "010_merge_heads"
down_revision: tuple[str, str] = ("009_wallet_fields", "009_add_archived")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
