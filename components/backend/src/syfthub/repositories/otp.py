"""OTP code repository for database operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import delete, func, select, update

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
        requester_ip: Optional[str] = None,
    ) -> Optional[OTPCodeModel]:
        """Create a new OTP code record."""
        try:
            otp = OTPCodeModel(
                email=email.lower(),
                code_hash=code_hash,
                purpose=purpose,
                expires_at=expires_at,
                attempts=0,
                requester_ip=requester_ip,
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
        """Atomically increment the attempt count for an OTP and return the new count."""
        try:
            stmt = (
                update(OTPCodeModel)
                .where(OTPCodeModel.id == otp_id)
                .values(attempts=OTPCodeModel.attempts + 1)
                .returning(OTPCodeModel.attempts)
            )
            result = self.session.execute(stmt)
            self.session.commit()
            new_count = result.scalar()
            return new_count if new_count is not None else 0
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

    def count_recent_by_ip(self, requester_ip: str, window_minutes: int) -> int:
        """Count OTP codes created from a specific IP within the rate limit window."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        stmt = (
            select(func.count())
            .select_from(OTPCodeModel)
            .where(
                OTPCodeModel.requester_ip == requester_ip,
                OTPCodeModel.created_at > cutoff,
            )
        )
        result = self.session.execute(stmt)
        return result.scalar() or 0

    def delete_expired_used(self, retention_hours: int) -> int:
        """Delete OTP records that are expired or used and older than the retention period."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
            stmt = delete(OTPCodeModel).where(
                OTPCodeModel.created_at < cutoff,
                (
                    OTPCodeModel.used_at.is_not(None)
                    | (OTPCodeModel.expires_at < datetime.now(timezone.utc))
                ),
            )
            result = self.session.execute(stmt)
            self.session.commit()
            return result.rowcount  # type: ignore[union-attr]
        except Exception:
            self.session.rollback()
            return 0
