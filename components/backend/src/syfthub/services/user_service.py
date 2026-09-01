"""User management business logic service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from syfthub.domain.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import (
    PublicUserProfile,
    User,
    UserResponse,
    UserUpdate,
)
from syfthub.services.base import BaseService
from syfthub.services.satellite_service import SatelliteService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class UserService(BaseService):
    """User service for handling user management operations."""

    def __init__(self, session: Session):
        """Initialize user service."""
        super().__init__(session)
        self.user_repository = UserRepository(session)
        self.satellite_service = SatelliteService(session)

    def _with_domain(self, user: Any) -> UserResponse:
        """Build a profile response with ``domain`` derived from the account's space.

        ``users.domain`` is no longer written — it described one host per account
        and could not survive a second space. The field stays on the response for
        compatibility and now reports the account's **oldest space**, never a
        station, whose origin serves nothing. ``None`` for an account with no
        space, which is what the column already held for those.
        """
        response = UserResponse.model_validate(user)
        response.domain = self.satellite_service.primary_space_url(user.id)
        return response

    def get_user_profile(self, user_id: int) -> Optional[UserResponse]:
        """Get user profile by ID."""
        user = self.user_repository.get_by_id(user_id)
        if user:
            return self._with_domain(user)
        return None

    def get_user_by_username(self, username: str) -> Optional[UserResponse]:
        """Get user profile by username."""
        user = self.user_repository.get_by_username(username)
        if user:
            return self._with_domain(user)
        return None

    def get_public_user_profile(self, username: str) -> Optional[PublicUserProfile]:
        """Get a sanitized public profile by username.

        Returns ``None`` if the user does not exist or is inactive. The email
        field is populated only when the user has opted in via
        ``is_email_public``.
        """
        user = self.user_repository.get_by_username(username)
        if user is None or not user.is_active:
            return None

        return PublicUserProfile(
            username=user.username,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            role=user.role,
            bio=user.bio,
            domain=self.satellite_service.primary_space_url(user.id),
            email=user.email if user.is_email_public else None,
            is_email_public=user.is_email_public,
            created_at=user.created_at,
        )

    def get_users_list(
        self, skip: int = 0, limit: int = 10, active_only: bool = True
    ) -> List[UserResponse]:
        """Get paginated list of users."""
        filters = {"is_active": True} if active_only else None
        user_models = self.user_repository.get_all(
            skip=skip, limit=limit, filters=filters
        )

        users = []
        for user_model in user_models:
            user = User.model_validate(user_model)
            users.append(UserResponse.model_validate(user))

        return users

    def update_user_profile(
        self, user_id: int, user_data: UserUpdate, current_user: User
    ) -> tuple[UserResponse, Optional[str]]:
        """Update user profile.

        Returns ``(user, previous_email)``, where ``previous_email`` is set only
        when the address actually moved. The caller uses it to send a
        verification code to the new address and to tell the old address it was
        replaced — neither of which this service does itself, since it has no
        business knowing about mail transport.

        Changing an address clears its verified state (see
        ``UserRepository.update_user``). That is safe here because nothing gates
        on it: an unverified address costs the user a tick in the UI, not access
        to their account.
        """
        # Check permissions - users can only update their own profile, admins can update any
        if current_user.id != user_id and current_user.role != "admin":
            raise PermissionDeniedError("Can only update your own profile")

        # Validate username uniqueness if being updated
        if user_data.username and self.user_repository.username_exists(
            user_data.username
        ):
            existing_user = self.user_repository.get_by_username(user_data.username)
            if existing_user and existing_user.id != user_id:
                raise ConflictError("user", "username")

        # Validate email uniqueness if being updated
        if user_data.email and self.user_repository.email_exists(user_data.email):
            existing_user = self.user_repository.get_by_email(user_data.email)
            if existing_user and existing_user.id != user_id:
                raise ConflictError("user", "email")

        # Read the address before the write so the caller can tell whether it
        # moved, and what it moved from.
        before = self.user_repository.get_by_id(user_id)
        if before is None:
            raise NotFoundError("User")
        previous_email = before.email

        # Legacy path: a submitted ``domain`` registers or moves the account's
        # space instead of writing the old account-wide field. Idempotent, so a
        # space re-running setup lands on the satellite it already has.
        #
        # Clearing it (``domain: null``) is accepted and deliberately ignored.
        # It used to mean "this space shut down" and deactivated the whole
        # account; liveness is per-endpoint now, so TTL expiry already covers it.
        # Not rejected either — older spaces are not ours to upgrade. The field
        # goes once they move to POST /satellites.
        if user_data.domain:
            self.satellite_service.register_or_move_space(user_id, user_data.domain)

        updated_user = self.user_repository.update_user(user_id, user_data)
        if not updated_user:
            raise NotFoundError("User")

        changed = updated_user.email.lower() != previous_email.lower()
        return self._with_domain(updated_user), (previous_email if changed else None)

    def deactivate_user(self, user_id: int, current_user: User) -> bool:
        """Deactivate a user account."""
        # Check permissions - only admins can deactivate users
        if current_user.role != "admin":
            raise PermissionDeniedError("Admin role required")

        # Prevent self-deactivation
        if current_user.id == user_id:
            raise ValidationError("Cannot deactivate your own account")

        success = self.user_repository.deactivate_user(user_id)
        if not success:
            raise NotFoundError("User")

        return success

    def search_users(self, query: str, limit: int = 10) -> List[UserResponse]:
        """Search users by username or full name."""
        # For now, get all users and filter manually
        # In a real implementation, you'd want to add proper search to the repository
        all_users = self.user_repository.get_all(limit=100, filters={"is_active": True})

        query_lower = query.lower()
        matching_users = []

        for user_model in all_users:
            user = User.model_validate(user_model)
            if (
                query_lower in user.username.lower()
                or query_lower in user.full_name.lower()
            ):
                matching_users.append(UserResponse.model_validate(user))
                if len(matching_users) >= limit:
                    break

        return matching_users

    def get_user_stats(self, user_id: int) -> dict[str, Any]:
        """Get user statistics (endpoints count, etc.)."""
        # This would typically involve calling other services/repositories
        # For now, return basic stats
        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise NotFoundError("User")

        return {
            "user_id": user.id,
            "username": user.username,
            "member_since": user.created_at,
            "last_updated": user.updated_at,
            "is_active": user.is_active,
            # These would be calculated by querying related tables
            "endpoints_count": 0,
            "stars_given": 0,
        }

    def username_available(self, username: str) -> bool:
        """Check if username is available."""
        return not self.user_repository.username_exists(username)

    def email_available(self, email: str) -> bool:
        """Check if email is available."""
        return not self.user_repository.email_exists(email)
