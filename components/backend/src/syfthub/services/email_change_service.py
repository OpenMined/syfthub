"""Verified email-change business logic.

An email address is an identity claim, not a profile field. Once SyftHub asserts
it to a third party — as the OIDC ``email`` claim alongside ``email_verified`` —
a relying party may link accounts by it, so SyftHub must only ever present an
address whose owner has actually proven control of it.

That rules out writing ``users.email`` on request. Instead the requested address
is parked in ``users.pending_email`` and an OTP is sent to it; ``email`` moves
only when that code is verified. Until then the user keeps their current,
genuinely verified address, which means:

- ``is_email_verified`` never describes an unproven address, and
- a typo'd address cannot lock anyone out, because their working address and
  login are untouched while the change is pending.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from syfthub.domain.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import User, UserResponse
from syfthub.services.base import BaseService
from syfthub.services.otp_service import OTPService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# OTP purpose discriminator. `otp_codes.purpose` is a free String(20), so this
# needs no migration; `send_otp_email` resolves subjects via SUBJECTS.get() with
# a fallback, so an unknown purpose degrades to a generic subject line rather
# than raising.
EMAIL_CHANGE_PURPOSE = "email_change"

# The purpose used for a code minted by an administrator's change.
#
# Deliberately "registration", not EMAIL_CHANGE_PURPOSE. A user whose address an
# admin just changed may have no session at all — a never-verified signup never
# receives tokens — so they must be able to finish without one. The only
# session-less completion endpoints are POST /auth/register/{resend-otp,verify-otp},
# and those accept the "registration" purpose exclusively. Using it means the
# user completes with the machinery that already exists, and verify-otp hands
# back tokens, so confirming the code *is* their login.
ADMIN_SET_PURPOSE = "registration"

# Copy variant for the email that carries an admin-set code.
#
# Separate from ADMIN_SET_PURPOSE because the stored OTP purpose and the wording
# of the message are independent: `send_otp_email` only renders, it never reads
# the OTP store. Reusing "registration" for the copy would tell a long-standing
# user to "complete your SyftHub registration", which is both confusing and
# fails to explain that their address was changed by an administrator.
ADMIN_SET_EMAIL_TEMPLATE = "admin_email_change"


class EmailChangeService(BaseService):
    """Drives the request → verify → swap lifecycle of an email change."""

    def __init__(self, session: Session):
        """Initialize the email-change service."""
        super().__init__(session)
        self.user_repository = UserRepository(session)
        self.otp_service = OTPService(session)

    def request_change(
        self,
        current_user: User,
        new_email: str,
        *,
        requester_ip: Optional[str] = None,
    ) -> str:
        """Park a requested address and mint the OTP proving it.

        Returns the plain OTP code so the caller can hand delivery to a
        background task — this service does not send mail itself, keeping it
        free of any transport dependency.

        Raises:
            ValidationError: If the address matches the user's current one.
            ConflictError: If another account already holds the address.
            OTPRateLimitedError: If too many codes were requested recently.
            NotFoundError: If the user no longer exists.
        """
        normalized = new_email.strip().lower()

        if normalized == current_user.email.lower():
            raise ValidationError("That is already your email address")

        # Fail early on a taken address rather than letting the user complete an
        # OTP round-trip that can only fail at the unique constraint. This is a
        # courtesy check, not the guarantee — confirm_pending_email re-checks
        # under the constraint, which is what actually settles a race.
        existing = self.user_repository.get_by_email(normalized)
        if existing and existing.id != current_user.id:
            raise ConflictError("user", "email")

        if not self.user_repository.set_pending_email(current_user.id, normalized):
            raise NotFoundError("User")

        code = self.otp_service.generate_otp(
            normalized, EMAIL_CHANGE_PURPOSE, requester_ip=requester_ip
        )
        logger.info(
            "Email change requested for user %s → %s (pending verification)",
            current_user.id,
            normalized,
        )
        return code

    def resend_code(
        self, current_user: User, *, requester_ip: Optional[str] = None
    ) -> tuple[str, str]:
        """Mint a fresh OTP for the address already pending.

        Returns ``(pending_email, code)``.

        Raises:
            ValidationError: If no change is pending.
            OTPRateLimitedError: If too many codes were requested recently.
        """
        pending = self._require_pending(current_user)
        code = self.otp_service.generate_otp(
            pending, EMAIL_CHANGE_PURPOSE, requester_ip=requester_ip
        )
        return pending, code

    def confirm_change(self, current_user: User, code: str) -> UserResponse:
        """Verify the OTP and promote the pending address.

        Raises:
            ValidationError: If no change is pending.
            InvalidOTPError: If the code is wrong or expired.
            OTPMaxAttemptsError: If too many attempts were made.
            ConflictError: If another account claimed the address meanwhile.
        """
        pending = self._require_pending(current_user)

        # Verify before mutating anything: a failed code must leave the pending
        # change intact so the user can retry.
        self.otp_service.verify_otp(pending, code, EMAIL_CHANGE_PURPOSE)

        updated = self.user_repository.confirm_pending_email(current_user.id)
        if updated is None:
            raise ConflictError("user", "email")

        logger.info("Email change confirmed for user %s → %s", current_user.id, pending)
        return UserResponse.model_validate(updated)

    def cancel_change(self, current_user: User) -> None:
        """Discard an in-flight change. Idempotent."""
        self.user_repository.clear_pending_email(current_user.id)

    def _require_pending(self, current_user: User) -> str:
        """Return the user's pending address, re-read from the database.

        ``current_user`` comes from an auth dependency and may predate a change
        made in this request, so the pending address is re-read rather than
        trusted from the passed-in snapshot.
        """
        user = self.user_repository.get_by_id(current_user.id)
        if user is None:
            raise NotFoundError("User")
        if not user.pending_email:
            raise ValidationError("No email change is pending")
        return user.pending_email

    def admin_set_email(
        self,
        target_user_id: int,
        new_email: str,
        actor: User,
        *,
        requester_ip: Optional[str] = None,
    ) -> tuple[UserResponse, str, str]:
        """Set another user's address outright, and mint the code to prove it.

        Admin-only, and deliberately different from ``request_change``: it
        applies at once rather than parking the address. An administrator cannot
        prove the new address belongs to its owner, so ``is_email_verified`` is
        cleared rather than carried over from the old address.

        The code is minted here rather than left to the user to request, because
        otherwise the change is silent: the previous address stops resolving, and
        the user is given no signal at all. The email carrying this code is what
        tells them their address moved and what it moved to.

        Returns ``(user, pending_verification_address, code)`` so the caller can
        hand delivery to a background task; this service sends no mail itself.

        Raises:
            PermissionDeniedError: If the actor is not an admin.
            ValidationError: If the actor is targeting their own account.
            NotFoundError: If the target user does not exist.
            ConflictError: If another account already holds the address.
        """
        if actor.role != "admin":
            raise PermissionDeniedError(
                "Admin role required to change another user's email"
            )

        # Prevent self-lockout, mirroring the self-deactivation guard in
        # UserService. This path clears `is_email_verified`, and login is refused
        # while that is false, so an admin aiming it at their own account would
        # lock themselves out. PUT /auth/me/email keeps the current address
        # working throughout, so route them there instead.
        if actor.id == target_user_id:
            raise ValidationError(
                "Use PUT /api/v1/auth/me/email to change your own address — it "
                "keeps your current address working until the new one is verified"
            )

        target = self.user_repository.get_by_id(target_user_id)
        if target is None:
            raise NotFoundError("User")

        normalized = new_email.strip().lower()
        if normalized == target.email.lower():
            # Not a change. Returning the existing state keeps the endpoint
            # idempotent, and mints no code for an address already verified.
            return UserResponse.model_validate(target), normalized, ""

        existing = self.user_repository.get_by_email(normalized)
        if existing and existing.id != target_user_id:
            raise ConflictError("user", "email")

        updated = self.user_repository.set_email(
            target_user_id, normalized, verified=False
        )
        if updated is None:
            raise ConflictError("user", "email")

        code = self.otp_service.generate_otp(
            normalized, ADMIN_SET_PURPOSE, requester_ip=requester_ip
        )
        logger.info(
            "Admin %s set the email of user %s to %s (verification pending)",
            actor.id,
            target_user_id,
            normalized,
        )
        return UserResponse.model_validate(updated), normalized, code
