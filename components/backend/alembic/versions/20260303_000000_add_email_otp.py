"""Add email OTP verification support.

Adds is_email_verified column to users table and creates otp_codes table
for storing hashed OTP codes used in email verification and password reset.

Existing users get is_email_verified=true via server_default so they are
unaffected by the migration.

Revision ID: 004_email_otp
Revises: 003_encryption_key
Create Date: 2026-03-03 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_email_otp"
down_revision: str | None = "003_encryption_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add email verification column and OTP codes table."""
    # Detect dialect for boolean server_default
    dialect = op.get_bind().dialect.name

    bool_true = sa.text("true") if dialect == "postgresql" else sa.text("1")

    # Add is_email_verified to users table
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=bool_true,
        ),
    )

    # Create otp_codes table
    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for otp_codes
    op.create_index("idx_otp_codes_email_purpose", "otp_codes", ["email", "purpose"])
    op.create_index(
        "idx_otp_codes_email_purpose_active",
        "otp_codes",
        ["email", "purpose", "used_at"],
    )


def downgrade() -> None:
    """Remove email verification column and OTP codes table."""
    op.drop_index("idx_otp_codes_email_purpose_active", table_name="otp_codes")
    op.drop_index("idx_otp_codes_email_purpose", table_name="otp_codes")
    op.drop_table("otp_codes")
    op.drop_column("users", "is_email_verified")
