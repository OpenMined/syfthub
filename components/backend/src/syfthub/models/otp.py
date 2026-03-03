"""OTP code database model for email verification and password reset."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from syfthub.models.base import BaseModel, TimestampMixin


class OTPCodeModel(BaseModel, TimestampMixin):
    """OTP code database model.

    Stores hashed OTP codes for email verification (registration)
    and password reset flows. Codes are SHA-256 hashed at rest.
    """

    __tablename__ = "otp_codes"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    __table_args__ = (
        Index("idx_otp_codes_email_purpose", "email", "purpose"),
        Index("idx_otp_codes_email_purpose_active", "email", "purpose", "used_at"),
    )

    def __repr__(self) -> str:
        """String representation of OTPCode."""
        return (
            f"<OTPCode(id={self.id}, email='{self.email}', "
            f"purpose='{self.purpose}', attempts={self.attempts})>"
        )
