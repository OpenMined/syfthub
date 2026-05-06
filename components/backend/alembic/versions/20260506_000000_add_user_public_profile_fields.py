"""Add bio and is_email_public to users.

Backs the public ``/:username`` profile page by giving users an editable bio
(Markdown) and an opt-in toggle that controls whether their email is shown
to anonymous viewers.

Revision ID: 012_user_public_profile
Revises: 011_xendit_subs
Create Date: 2026-05-06 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012_user_public_profile"
down_revision: str | None = "011_xendit_subs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "is_email_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_email_public")
    op.drop_column("users", "bio")
