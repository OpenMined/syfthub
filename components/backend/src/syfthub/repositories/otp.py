"""OTP code repository for database operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, select, update

from syfthub.models.otp import OTPCodeModel
from syfthub.repositories.base import BaseRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class OTPRepository(BaseRepository[OTPCodeModel]):
    """Repository for OTP code database operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, OTPCodeModel)

    def create_otp(
        self,
        email: str,
        code_hash: str,
        purpose: str,
        expires_at: datetime,
    ) -> Optional[OTPCodeModel]:
        """Create a new OTP code record."""
        try:
            otp = OTPCodeModel(
                email=email.lower(),
                code_hash=code_hash,
                purpose=purpose,
                expires_at=expires_at,
                attempts=0,
            )
            self.session.add(otp)
            self.session.commit()
            self.session.refresh(otp)
            return otp
        except Exception:
            self.session.rollback()
            return None

    def invalidate_existing(self, email: str, purpose: str) -> None:
        """Invalidate all existing active OTP codes for an email+purpose."""
        try:
            now = datetime.now(timezone.utc)
            stmt = (
                update(OTPCodeModel)
                .where(
                    OTPCodeModel.email == email.lower(),
                    OTPCodeModel.purpose == purpose,
                    OTPCodeModel.used_at.is_(None),
                )
                .values(used_at=now)
            )
            self.session.execute(stmt)
            self.session.commit()
        except Exception:
            self.session.rollback()

    def get_active_otp(self, email: str, purpose: str) -> Optional[OTPCodeModel]:
        """Get the most recent active (unused, not expired) OTP for an email+purpose."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(OTPCodeModel)
            .where(
                OTPCodeModel.email == email.lower(),
                OTPCodeModel.purpose == purpose,
                OTPCodeModel.used_at.is_(None),
                OTPCodeModel.expires_at > now,
            )
            .order_by(OTPCodeModel.created_at.desc())
            .limit(1)
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def increment_attempts(self, otp_id: int) -> int:
        """Increment the attempt count for an OTP and return the new count."""
        try:
            otp = self.session.get(OTPCodeModel, otp_id)
            if not otp:
                return 0
            otp.attempts += 1
            self.session.commit()
            return otp.attempts
        except Exception:
            self.session.rollback()
            return 0

    def mark_used(self, otp_id: int) -> bool:
        """Atomically mark an OTP as used (WHERE used_at IS NULL for safety)."""
        try:
            now = datetime.now(timezone.utc)
            stmt = (
                update(OTPCodeModel)
                .where(
                    OTPCodeModel.id == otp_id,
                    OTPCodeModel.used_at.is_(None),
                )
                .values(used_at=now)
            )
            result = self.session.execute(stmt)
            self.session.commit()
            return result.rowcount > 0  # type: ignore[union-attr]
        except Exception:
            self.session.rollback()
            return False

    def count_recent(self, email: str, purpose: str, window_minutes: int) -> int:
        """Count OTP codes created within the rate limit window."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        stmt = (
            select(func.count())
            .select_from(OTPCodeModel)
            .where(
                OTPCodeModel.email == email.lower(),
                OTPCodeModel.purpose == purpose,
                OTPCodeModel.created_at > cutoff,
            )
        )
        result = self.session.execute(stmt)
        return result.scalar() or 0
