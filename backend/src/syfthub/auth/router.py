"""Authentication endpoints."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    OAuth2PasswordRequestForm,
)

from syfthub.auth.db_dependencies import (
    get_current_active_user,
    security,
)
from syfthub.auth.security import blacklist_token
from syfthub.database.dependencies import get_auth_service
from syfthub.schemas.auth import (
    KeyRegenerationRequest,
    KeyRegenerationResponse,
    PasswordChange,
    RefreshTokenRequest,
    RegistrationResponse,
    Token,
    UserRegister,
)
from syfthub.schemas.user import User, UserResponse
from syfthub.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    user_data: UserRegister,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RegistrationResponse:
    """Register a new user."""
    return auth_service.register(user_data)


@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> Token:
    """OAuth2 compatible token login, get an access token for future requests."""
    return auth_service.login(form_data.username, form_data.password)


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_request: RefreshTokenRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> Token:
    """Refresh access token using refresh token."""
    return auth_service.refresh_token(refresh_request.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: Annotated[User, Depends(get_current_active_user)],  # noqa: ARG001
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> None:
    """Logout user by blacklisting their tokens."""
    # Blacklist the current access token
    blacklist_token(credentials.credentials)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Get current user profile information."""
    return UserResponse.model_validate(current_user)


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    password_data: PasswordChange,
    current_user: Annotated[User, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Change current user's password."""
    auth_service.change_password(
        current_user, password_data.current_password, password_data.new_password
    )


@router.post("/regenerate-keys", response_model=KeyRegenerationResponse)
async def regenerate_user_keys(
    current_user: Annotated[User, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    request: Optional[KeyRegenerationRequest] = None,
) -> KeyRegenerationResponse:
    """Regenerate or update Ed25519 key for the current user.

    If public_key is provided in the request, it will be used.
    Otherwise, a new key pair will be generated.
    """
    return auth_service.regenerate_keys(current_user, request)
