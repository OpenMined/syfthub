"""Add users.pending_email for verified email changes.

``PUT /api/v1/users/me`` previously wrote ``users.email`` directly and left
``is_email_verified`` untouched, so a user could move to an address they had
never proven control of while the row still claimed the address was verified.
That is harmless while the flag is only read internally to gate login, but it
becomes an account-takeover vector the moment it is exported as an OIDC
``email_verified`` claim: a relying party that links accounts by verified email
would accept the new address as proven.

``pending_email`` holds the requested address until an OTP sent to it verifies.
Only then does ``email`` move and ``is_email_verified`` become true, so the flag
never describes an unproven address. See ``EmailChangeService``.

Revision ID: 023_user_pending_email
Revises: 022_user_public_id
Create Date: 2026-08-18 01:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "023_user_pending_email"
down_revision: str | None = "022_user_public_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable pending_email column."""
    op.add_column("users", sa.Column("pending_email", sa.String(255), nullable=True))


def downgrade() -> None:
    """Drop pending_email, discarding any in-flight email changes."""
    op.drop_column("users", "pending_email")
