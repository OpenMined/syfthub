"""User management business logic service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, List, Optional
from urllib.parse import urlparse

from fastapi import HTTPException, status

from syfthub.core.config import settings
from syfthub.domain.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import (
    TUNNELING_PREFIX,
    HeartbeatResponse,
    User,
    UserResponse,
    UserUpdate,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class UserService(BaseService):
    """User service for handling user management operations."""

    def __init__(self, session: Session):
        """Initialize user service."""
        super().__init__(session)
        self.user_repository = UserRepository(session)

    def get_user_profile(self, user_id: int) -> Optional[UserResponse]:
        """Get user profile by ID."""
        user = self.user_repository.get_by_id(user_id)
        if user:
            return UserResponse.model_validate(user)
        return None

    def get_user_by_username(self, username: str) -> Optional[UserResponse]:
        """Get user profile by username."""
        user = self.user_repository.get_by_username(username)
        if user:
            return UserResponse.model_validate(user)
        return None

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
    ) -> UserResponse:
        """Update user profile."""
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

        # Update user
        updated_user = self.user_repository.update_user(user_id, user_data)
        if not updated_user:
            raise NotFoundError("User")

        return UserResponse.model_validate(updated_user)

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
            "organizations_count": 0,
            "stars_given": 0,
        }

    def username_available(self, username: str) -> bool:
        """Check if username is available."""
        return not self.user_repository.username_exists(username)

    def email_available(self, email: str) -> bool:
        """Check if email is available."""
        return not self.user_repository.email_exists(email)

    def send_heartbeat(
        self, user_id: int, url: str, ttl_seconds: Optional[int] = None
    ) -> HeartbeatResponse:
        """Send heartbeat to indicate user's domain is online.

        This method:
        - Extracts domain from the provided URL (or uses full tunneling URL as domain)
        - Calculates effective TTL (capped at server max, defaults if not specified)
        - Updates user's heartbeat information in the database

        Args:
            user_id: ID of the user sending the heartbeat
            url: Full URL of the domain (e.g., 'https://api.example.com' or
                 'tunneling:username' for spaces behind firewalls)
            ttl_seconds: Requested TTL in seconds (optional, will use default if not provided)

        Returns:
            HeartbeatResponse with status, timestamps, domain, and effective TTL

        Raises:
            HTTPException: If URL is invalid or heartbeat update fails
        """
        now = datetime.now(timezone.utc)

        # Calculate effective TTL (cap at max, use default if not specified)
        requested_ttl = ttl_seconds or settings.heartbeat_default_ttl_seconds
        effective_ttl = min(requested_ttl, settings.heartbeat_max_ttl_seconds)

        # Extract domain from URL
        # For tunneling URLs (tunneling:<username>), use the full URL as domain
        # For HTTP URLs, extract scheme + host + port
        if url.startswith(TUNNELING_PREFIX):
            # For tunneling, the domain is the full URL (e.g., "tunneling:username")
            domain = url
        else:
            # Extract domain with protocol (scheme + host + port) from URL
            parsed = urlparse(url)
            if not parsed.netloc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid URL: could not extract domain",
                )
            domain = f"{parsed.scheme}://{parsed.netloc}"

        expires_at = now + timedelta(seconds=effective_ttl)

        # Update user record
        success = self.user_repository.update_heartbeat(
            user_id=user_id,
            domain=domain,
            last_heartbeat_at=now,
            heartbeat_expires_at=expires_at,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update heartbeat",
            )

        return HeartbeatResponse(
            status="ok",
            received_at=now,
            expires_at=expires_at,
            domain=domain,
            ttl_seconds=effective_ttl,
        )
