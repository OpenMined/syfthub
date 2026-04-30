"""Add user_xendit_subscriptions table.

Stores the publisher-side wallets (identified by credits_url) that a SyftHub
user has funded via the Xendit policy flow. Lets the credits panel list every
wallet a user holds across publishers without scanning endpoint policies.

Revision ID: 011_xendit_subs
Revises: 010_merge_heads
Create Date: 2026-04-29 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011_xendit_subs"
down_revision: str | None = "010_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_xendit_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credits_url", sa.Text(), nullable=False),
        sa.Column("payment_url", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="IDR"),
        sa.Column("endpoint_owner", sa.String(50), nullable=False),
        sa.Column("endpoint_slug", sa.String(255), nullable=True),
        sa.Column("last_known_balance", sa.Numeric(18, 4), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_funded_at", sa.DateTime(timezone=True), nullable=True),
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
            "user_id", "credits_url", name="uq_user_xendit_subs_user_credits"
        ),
    )
    op.create_index(
        "idx_user_xendit_subs_user",
        "user_xendit_subscriptions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_xendit_subs_user", table_name="user_xendit_subscriptions")
    op.drop_table("user_xendit_subscriptions")
