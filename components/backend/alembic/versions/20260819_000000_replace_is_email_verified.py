"""Replace users.is_email_verified with users.email_verified_at.

``is_email_verified`` answered two unrelated questions with one boolean:

1. "has this account ever proven an address?" — which gated login, and
2. "is the address currently on file proven?" — which is what an OIDC
   ``email_verified`` claim needs.

Because a change to the address had to clear the flag, changing an email yanked
the login gate as a side effect: users were locked out, admins could lock
themselves out, and recovery needed a session the locked-out user did not have.
Worse, registration set the flag ``True`` **without any proof** whenever email
delivery was unconfigured, so ``True`` never actually meant "proven".

``email_verified_at`` answers only the second question. It gates nothing; login
no longer consults it. It is cleared whenever the address changes and set when a
code sent to that address is confirmed, so it describes the address on file and
nothing else — which makes it safe to export as a claim.

**Backfill:** rows with ``is_email_verified`` true get ``email_verified_at =
created_at``, preserving today's behaviour so nothing regresses for existing
users and the admin dashboard's Verified/Unverified badges are unchanged. Those
rows therefore inherit the old ambiguity: in a deployment that never had email
configured, they claim a verified address that was never proven. Only the
*forward* semantics are fixed here — new accounts and new changes record
``email_verified_at`` solely on real proof. If strictness matters before this is
exported anywhere, null the column in a one-off pass; that is a policy decision,
not a migration one.

Revision ID: 023_user_email_verified_at
Revises: 022_user_public_id
Create Date: 2026-08-19 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "023_user_email_verified_at"
down_revision: str | None = "022_user_public_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add email_verified_at, backfill it, and drop is_email_verified."""
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE users SET email_verified_at = created_at WHERE is_email_verified"
        )
    )
    op.drop_column("users", "is_email_verified")


def downgrade() -> None:
    """Restore the boolean, losing when verification happened."""
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE users SET is_email_verified = true "
            "WHERE email_verified_at IS NOT NULL"
        )
    )
    op.drop_column("users", "email_verified_at")
