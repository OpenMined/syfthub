"""Proving that the address on a user's account is real.

An email address is a claim SyftHub makes about a user, and one that relying
parties act on — an OIDC ``email_verified`` claim is what lets an app link an
account by email. So the claim must only ever be true of an address whose owner
actually proved control of it.

That is the *only* job here. Verification gates nothing: an unverified address
does not block sign-in or anything else, because whether an address is proven
says nothing about whether the account holder may use their own account. Tying
the two together is what previously locked users out whenever their address
changed.

Changing an address is therefore an ordinary profile write (see
``UserService.update_user_profile``), which clears ``email_verified_at``. This
service exists to set it again.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from syfthub.core.config import settings
from syfthub.domain.exceptions import NotFoundError, ValidationError
from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import User, UserResponse
from syfthub.services.base import BaseService
from syfthub.services.otp_service import OTPService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Purpose the verification codes are stored under.
#
# Shared with registration on purpose: both prove "the address on this account is
# real", and sharing it means the existing unauthenticated
# POST /auth/register/{resend-otp,verify-otp} pair keeps working for a user who
# has no session yet. One concept, one purpose, no third code path.
EMAIL_VERIFY_PURPOSE = "registration"


class EmailVerificationService(BaseService):
    """Sends and confirms proof of the address currently on an account."""

    def __init__(self, session: Session):
        """Initialize the email-verification service."""
        super().__init__(session)
        self.user_repository = UserRepository(session)
        self.otp_service = OTPService(session)

    def send_code(
        self, current_user: User, *, requester_ip: Optional[str] = None
    ) -> tuple[str, str]:
        """Mint a code for the address currently on the account.

        Returns ``(address, code)`` so the caller can hand delivery to a
        background task; this service sends no mail itself.

        Raises:
            ValidationError: If the address is already verified, or email
                delivery is not configured so no code could ever arrive.
            NotFoundError: If the user no longer exists.
            OTPRateLimitedError: If too many codes were requested recently.
        """
        user = self._reread(current_user)

        if not settings.smtp_configured:
            raise ValidationError(
                "Email delivery is not configured, so addresses cannot be verified"
            )
        if user.is_email_verified:
            raise ValidationError("Your email address is already verified")

        code = self.otp_service.generate_otp(
            user.email, EMAIL_VERIFY_PURPOSE, requester_ip=requester_ip
        )
        return user.email, code

    def confirm(self, current_user: User, code: str) -> UserResponse:
        """Verify a code against the address on the account and record the proof.

        Raises:
            ValidationError: If the address is already verified.
            InvalidOTPError: If the code is wrong or expired.
            OTPMaxAttemptsError: If too many attempts were made.
            NotFoundError: If the user no longer exists.
        """
        user = self._reread(current_user)
        if user.is_email_verified:
            raise ValidationError("Your email address is already verified")

        # Verify before recording anything: a bad code must leave the account
        # untouched so the user can retry.
        self.otp_service.verify_otp(user.email, code, EMAIL_VERIFY_PURPOSE)

        if not self.user_repository.set_email_verified(user.id):
            raise NotFoundError("User")

        updated = self.user_repository.get_by_id(user.id)
        if updated is None:
            raise NotFoundError("User")

        logger.info("Email verified for user %s (%s)", user.id, user.email)
        return UserResponse.model_validate(updated)

    def _reread(self, current_user: User) -> User:
        """Return the user as stored, not as the auth dependency snapshotted them.

        ``current_user`` may predate a change made earlier in this same request —
        an address updated by ``PUT /users/me``, for instance — so the address and
        its verified state are always read back from the database.
        """
        user = self.user_repository.get_by_id(current_user.id)
        if user is None:
            raise NotFoundError("User")
        return user
