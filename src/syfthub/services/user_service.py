"""User management business logic service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from fastapi import HTTPException, status

from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import User, UserResponse, UserUpdate
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
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: can only update your own profile",
            )

        # Validate email uniqueness if being updated
        if user_data.email and self.user_repository.email_exists(user_data.email):
            existing_user = self.user_repository.get_by_email(user_data.email)
            if existing_user and existing_user.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists",
                )

        # Update user
        updated_user = self.user_repository.update_user(user_id, user_data)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UserResponse.model_validate(updated_user)

    def deactivate_user(self, user_id: int, current_user: User) -> bool:
        """Deactivate a user account."""
        # Check permissions - only admins can deactivate users
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: admin role required",
            )

        # Prevent self-deactivation
        if current_user.id == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account",
            )

        success = self.user_repository.deactivate_user(user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return success

    def change_password(
        self, user_id: int, old_password: str, new_password: str, current_user: User
    ) -> bool:
        """Change user password."""
        from syfthub.auth.security import hash_password, verify_password

        # Check permissions - users can only change their own password, admins can change any
        if current_user.id != user_id and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: can only change your own password",
            )

        # Get current user data
        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Verify old password (except for admins changing other users' passwords)
        if current_user.id == user_id and not verify_password(
            old_password, user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        # Validate new password
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters long",
            )

        # Update password
        new_password_hash = hash_password(new_password)
        success = self.user_repository.update_password(user_id, new_password_hash)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password",
            )

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
        """Get user statistics (datasites count, etc.)."""
        # This would typically involve calling other services/repositories
        # For now, return basic stats
        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return {
            "user_id": user.id,
            "username": user.username,
            "member_since": user.created_at,
            "last_updated": user.updated_at,
            "is_active": user.is_active,
            # These would be calculated by querying related tables
            "datasites_count": 0,
            "organizations_count": 0,
            "stars_given": 0,
        }

    def username_available(self, username: str) -> bool:
        """Check if username is available."""
        return not self.user_repository.username_exists(username)

    def email_available(self, email: str) -> bool:
        """Check if email is available."""
        return not self.user_repository.email_exists(email)
