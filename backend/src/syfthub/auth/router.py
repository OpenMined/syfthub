"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
from syfthub.domain.exceptions import (
    AccountingAccountExistsError,
    AccountingServiceUnavailableError,
    InvalidAccountingPasswordError,
    UserAlreadyExistsError,
)
from syfthub.schemas.auth import (
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
    responses={
        409: {
            "description": "Username or email already exists in SyftHub",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "USER_ALREADY_EXISTS",
                            "message": "Username already exists",
                            "field": "username",
                        }
                    }
                }
            },
        },
        424: {
            "description": "Email already exists in accounting service (requires password)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "ACCOUNTING_ACCOUNT_EXISTS",
                            "message": "This email already has an account...",
                            "requires_accounting_password": True,
                        }
                    }
                }
            },
        },
        401: {
            "description": "Invalid accounting password",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "INVALID_ACCOUNTING_PASSWORD",
                            "message": "The provided accounting password is invalid.",
                        }
                    }
                }
            },
        },
        503: {
            "description": "Accounting service unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "ACCOUNTING_SERVICE_UNAVAILABLE",
                            "message": "Accounting service error: ...",
                        }
                    }
                }
            },
        },
    },
)
async def register_user(
    user_data: UserRegister,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> RegistrationResponse:
    """Register a new user.

    This endpoint handles user registration with optional accounting service integration.

    If username or email already exists in SyftHub, a 409 Conflict is returned.

    If an accounting service URL is configured (via request or default config), the backend
    will automatically create an accounting account for the user. If the email already
    exists in the accounting service, a 424 Failed Dependency response is returned and
    the user must provide their existing accounting password to link accounts.

    Flow:
    1. User submits registration without accounting_password
    2. If accounting URL is configured, backend tries to create accounting account
    3. If 424 (email exists in accounting), return error with requires_accounting_password=True
    4. User re-submits with their existing accounting_password
    5. Backend validates credentials and completes registration
    """
    try:
        return auth_service.register(user_data)

    except UserAlreadyExistsError as e:
        # Username or email already exists in SyftHub
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": e.error_code,
                "message": e.message,
                "field": e.field,
            },
        ) from e

    except AccountingAccountExistsError as e:
        # Email already exists in accounting service - user needs to provide password
        # Using 424 Failed Dependency to distinguish from SyftHub user duplication (409)
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={
                "code": e.error_code,
                "message": e.message,
                "requires_accounting_password": e.requires_accounting_password,
            },
        ) from e

    except InvalidAccountingPasswordError as e:
        # User provided wrong accounting password
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": e.error_code,
                "message": e.message,
            },
        ) from e

    except AccountingServiceUnavailableError as e:
        # Accounting service is down or returned unexpected error
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": e.error_code,
                "message": e.message,
            },
        ) from e


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
