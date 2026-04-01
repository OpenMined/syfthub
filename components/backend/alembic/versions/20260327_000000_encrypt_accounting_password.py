"""Encrypt accounting_password column in users table.

Security fix: the accounting_password column previously stored plaintext
credentials for the external accounting service.  This migration:

1. Adds a new ``accounting_password_encrypted`` column (String 500 to fit
   Fernet tokens which are longer than the original plaintext).
2. Copies and encrypts existing plaintext values into the new column.
3. Drops the old ``accounting_password`` column.

Downgrade re-creates the old column but **cannot recover plaintext** for
rows that were encrypted after the original column was dropped, so it
sets those values to NULL.

Revision ID: 008_encrypt_accounting_pw
Revises: 007_endpoint_health
Create Date: 2026-03-27 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic
revision: str = "008_encrypt_accounting_pw"
down_revision: str | None = "007_endpoint_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _encrypt_existing_passwords() -> None:
    """Read all rows with a plaintext accounting_password and encrypt them
    into the new accounting_password_encrypted column.

    This runs inside the migration transaction so it's atomic.
    """
    # Import here to avoid top-level dependency on app code in migrations
    from syfthub.auth.security import encrypt_field

    connection = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("accounting_password", sa.String),
        sa.column("accounting_password_encrypted", sa.String),
    )

    results = connection.execute(
        sa.select(users.c.id, users.c.accounting_password).where(
            users.c.accounting_password.isnot(None),
            users.c.accounting_password != "",
        )
    )

    for row in results:
        encrypted = encrypt_field(row.accounting_password)
        connection.execute(
            users.update()
            .where(users.c.id == row.id)
            .values(accounting_password_encrypted=encrypted)
        )


def upgrade() -> None:
    """Encrypt accounting passwords at rest.

    Steps:
    1. Add accounting_password_encrypted column (wider to fit Fernet tokens).
    2. Encrypt existing plaintext values into the new column.
    3. Drop the old plaintext accounting_password column.
    """
    # Step 1: add the new encrypted column
    op.add_column(
        "users",
        sa.Column("accounting_password_encrypted", sa.String(500), nullable=True),
    )

    # Step 2: encrypt existing plaintext passwords
    _encrypt_existing_passwords()

    # Step 3: drop the old plaintext column
    op.drop_column("users", "accounting_password")


def downgrade() -> None:
    """Re-create the plaintext column (values will be NULL for previously encrypted rows)."""
    op.add_column(
        "users",
        sa.Column("accounting_password", sa.String(255), nullable=True),
    )
    op.drop_column("users", "accounting_password_encrypted")
