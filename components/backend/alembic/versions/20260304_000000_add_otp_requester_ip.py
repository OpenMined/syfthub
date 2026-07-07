"""Add requester_ip column to otp_codes table.

Stores the IP address of the client that requested OTP generation,
enabling per-IP rate limiting to prevent SMTP abuse.

Revision ID: 005_otp_requester_ip
Revises: 004_email_otp
Create Date: 2026-03-04 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_otp_requester_ip"
down_revision: str | None = "004_email_otp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add requester_ip column and index to otp_codes."""
    op.add_column(
        "otp_codes",
        sa.Column("requester_ip", sa.String(length=45), nullable=True),
    )
    op.create_index("idx_otp_codes_requester_ip", "otp_codes", ["requester_ip"])


def downgrade() -> None:
    """Remove requester_ip column and index from otp_codes."""
    op.drop_index("idx_otp_codes_requester_ip", table_name="otp_codes")
    op.drop_column("otp_codes", "requester_ip")
