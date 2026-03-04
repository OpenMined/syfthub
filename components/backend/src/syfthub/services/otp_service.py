"""OTP generation, validation, and rate-limiting business logic."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from syfthub.core.config import settings
from syfthub.domain.exceptions import (
    InvalidOTPError,
    OTPMaxAttemptsError,
    OTPRateLimitedError,
)
from syfthub.repositories.otp import OTPRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _hash_code(code: str) -> str:
    """SHA-256 hash of a plain-text OTP code."""
    return hashlib.sha256(code.encode()).hexdigest()


class OTPService:
    """Central business logic for OTP lifecycle."""

    def __init__(self, session: Session):
        """Initialize with a database session."""
        self.otp_repo = OTPRepository(session)

    def generate_otp(
        self, email: str, purpose: str, requester_ip: Optional[str] = None
    ) -> str:
        """Generate a new 6-digit OTP, store it hashed, and return the plain code.

        Raises:
            OTPRateLimitedError: If too many codes were requested recently.
        """
        # Per-IP rate limit check (runs first to catch broad abuse)
        if requester_ip is not None:
            ip_count = self.otp_repo.count_recent_by_ip(
                requester_ip,
                settings.otp_ip_rate_limit_window_minutes,
            )
            if ip_count >= settings.otp_ip_rate_limit_max_requests:
                logger.warning(
                    "OTP IP rate limit hit for %s (%s)", requester_ip, purpose
                )
                raise OTPRateLimitedError()

        # Per-email rate limit check
        recent_count = self.otp_repo.count_recent(
            email,
            purpose,
            settings.otp_rate_limit_window_minutes,
        )
        if recent_count >= settings.otp_rate_limit_max_requests:
            logger.warning("OTP rate limit hit for %s (%s)", email, purpose)
            raise OTPRateLimitedError()

        # Invalidate any existing active codes
        self.otp_repo.invalidate_existing(email, purpose)

        # Generate 6-digit numeric code (100000-999999)
        code = str(secrets.randbelow(900000) + 100000)
        code_hash = _hash_code(code)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.otp_expiry_minutes
        )

        otp = self.otp_repo.create_otp(
            email=email,
            code_hash=code_hash,
            purpose=purpose,
            expires_at=expires_at,
            requester_ip=requester_ip,
        )

        if not otp:
            raise InvalidOTPError("Failed to create verification code")

        logger.info("OTP generated for %s (%s)", email, purpose)
        return code

    def verify_otp(self, email: str, code: str, purpose: str) -> bool:
        """Verify an OTP code.

        Returns True on success.

        Raises:
            InvalidOTPError: If no active code found or code doesn't match.
            OTPMaxAttemptsError: If max verification attempts exceeded.
        """
        otp = self.otp_repo.get_active_otp(email, purpose)

        if not otp:
            raise InvalidOTPError("No active verification code found")

        # Narrow optional fields that are always set for DB-retrieved records
        otp_id = otp.id or 0
        otp_attempts = otp.attempts or 0
        otp_code_hash = otp.code_hash or ""

        # Check attempts
        if otp_attempts >= settings.otp_max_attempts:
            raise OTPMaxAttemptsError()

        # Increment attempts before comparing (prevents timing-based bypass)
        self.otp_repo.increment_attempts(otp_id)

        # Constant-time comparison
        submitted_hash = _hash_code(code)
        if not hmac.compare_digest(submitted_hash, otp_code_hash):
            remaining = settings.otp_max_attempts - (otp_attempts + 1)
            if remaining <= 0:
                raise OTPMaxAttemptsError()
            raise InvalidOTPError("Invalid verification code")

        # Mark as used (atomic WHERE used_at IS NULL)
        self.otp_repo.mark_used(otp_id)

        logger.info("OTP verified for %s (%s)", email, purpose)
        return True
