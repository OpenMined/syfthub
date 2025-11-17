"""Database-based authentication dependencies for FastAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from syfthub.auth.security import verify_token
from syfthub.database.dependencies import get_user_repository
from syfthub.schemas.auth import UserRole

if TYPE_CHECKING:
    from syfthub.database.repositories import UserRepository
    from syfthub.schemas.user import User

# OAuth2 bearer token scheme
security = HTTPBearer(auto_error=False)


def get_user_by_id(
    user_id: int,
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> Optional[User]:
    """Get user by ID from database."""
    return user_repo.get_by_id(user_id)


def get_user_by_username(
    username: str,
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> Optional[User]:
    """Get user by username from database."""
    return user_repo.get_by_username(username)


def get_user_by_email(
    email: str,
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> Optional[User]:
    """Get user by email from database."""
    return user_repo.get_by_email(email)


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Check if credentials were provided
        if credentials is None:
            raise credentials_exception

        # Verify the token
        payload = verify_token(credentials.credentials, token_type="access")
        if payload is None:
            raise credentials_exception

        # Get user info from token payload
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            raise credentials_exception from None

        # Get user from database
        user = user_repo.get_by_id(user_id)
        if user is None:
            raise credentials_exception

        return user

    except HTTPException:
        raise
    except Exception:
        raise credentials_exception from None


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get the current authenticated and active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )
    return current_user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    user_repo: UserRepository = Depends(get_user_repository),
) -> Optional[User]:
    """Get the current user if authenticated, otherwise return None."""
    if credentials is None:
        return None

    try:
        # Verify the token
        payload = verify_token(credentials.credentials, token_type="access")
        if payload is None:
            return None

        # Get user info from token payload
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            return None

        # Get user from database
        return user_repo.get_by_id(user_id)

    except Exception:
        return None


class RoleChecker:
    """Dependency class for role-based access control."""

    def __init__(self, allowed_roles: List[UserRole]):
        """Initialize with allowed roles."""
        self.allowed_roles = allowed_roles

    def __call__(
        self, current_user: Annotated[User, Depends(get_current_active_user)]
    ) -> bool:
        """Check if user has required role."""
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Operation not permitted"
            )
        return True


class OwnershipChecker:
    """Dependency class for resource ownership validation."""

    def __init__(self, resource_user_id_field: str = "user_id"):
        """Initialize with the field name that contains user ID."""
        self.resource_user_id_field = resource_user_id_field

    def __call__(
        self,
        current_user: Annotated[User, Depends(get_current_active_user)],
        resource_user_id: int,
    ) -> bool:
        """Check if user owns the resource or is admin."""
        if current_user.role == UserRole.ADMIN or current_user.id == resource_user_id:
            return True

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient permissions",
        )


# Pre-configured dependency instances
require_admin = RoleChecker([UserRole.ADMIN])
require_user_or_admin = RoleChecker([UserRole.USER, UserRole.ADMIN])
require_any_role = RoleChecker([UserRole.GUEST, UserRole.USER, UserRole.ADMIN])
