"""Database-based authentication dependencies for FastAPI.

This module supports two authentication methods:
1. JWT tokens (default): Standard Bearer token authentication
2. API tokens: Long-lived tokens starting with "syft_" prefix

Both methods are transparent to endpoints - they receive the same User object.
"""

from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from syfthub.auth.api_tokens import hash_api_token, is_api_token
from syfthub.auth.security import verify_token
from syfthub.database.dependencies import get_api_token_repository, get_user_repository
from syfthub.repositories.api_token import APITokenRepository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import UserRole
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


async def _authenticate_with_api_token(
    token: str,
    api_token_repo: APITokenRepository,
    request: Optional[Request] = None,
) -> User:
    """Authenticate using an API token.

    Args:
        token: The API token string (starting with "syft_").
        api_token_repo: Repository for API token operations.
        request: Optional request object for IP tracking.

    Returns:
        User object if authentication succeeds.

    Raises:
        HTTPException: If authentication fails.
    """
    # Hash the token for lookup
    token_hash = hash_api_token(token)

    # Look up the token
    api_token = api_token_repo.get_by_hash(token_hash)

    if api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token is revoked
    if not api_token.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token is expired
    if api_token.expires_at is not None:
        now = datetime.now(timezone.utc)
        expires_at = api_token.expires_at
        # Ensure timezone-aware comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Get the user from the relationship (eager loaded)
    user_model = api_token.user
    if user_model is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user_model.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last used timestamp (fire-and-forget, don't fail auth on error)
    try:
        client_ip = None
        if request and request.client:
            client_ip = request.client.host
        api_token_repo.update_last_used(api_token.id, client_ip)
    except Exception:
        # Don't fail authentication if tracking fails
        pass

    # Convert to User schema
    return User.model_validate(user_model)


async def _authenticate_with_jwt(
    token: str,
    user_repo: UserRepository,
) -> User:
    """Authenticate using a JWT token.

    Args:
        token: The JWT token string.
        user_repo: Repository for user operations.

    Returns:
        User object if authentication succeeds.

    Raises:
        HTTPException: If authentication fails.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Verify the token
    payload = verify_token(token, token_type="access")
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


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    api_token_repo: Annotated[APITokenRepository, Depends(get_api_token_repository)],
    request: Request,
) -> User:
    """Get the current authenticated user.

    Supports two authentication methods:
    1. API tokens: Long-lived tokens starting with "syft_" prefix
    2. JWT tokens: Standard Bearer token authentication

    The authentication method is determined by the token prefix.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Check if credentials were provided
        if credentials is None:
            raise credentials_exception

        token = credentials.credentials

        # Check if this is an API token (starts with "syft_")
        if is_api_token(token):
            return await _authenticate_with_api_token(token, api_token_repo, request)

        # Otherwise, use JWT authentication
        return await _authenticate_with_jwt(token, user_repo)

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
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    api_token_repo: Annotated[APITokenRepository, Depends(get_api_token_repository)],
    request: Request,
) -> Optional[User]:
    """Get the current user if authenticated, otherwise return None.

    Supports both JWT and API token authentication.
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials

        # Check if this is an API token
        if is_api_token(token):
            return await _authenticate_with_api_token(token, api_token_repo, request)

        # Otherwise, use JWT authentication
        payload = verify_token(token, token_type="access")
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

    except HTTPException:
        # For optional auth, convert auth errors to None
        return None
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
