"""Authentication endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    OAuth2PasswordRequestForm,
)

from syfthub.auth.db_dependencies import (
    get_current_active_user,
    security,
)
from syfthub.auth.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
)
from syfthub.core.config import settings
from syfthub.database.dependencies import (
    get_api_token_service,
    get_auth_service,
    get_otp_service,
)
from syfthub.domain.exceptions import (
    AccountingAccountExistsError,
    AccountingServiceUnavailableError,
    EmailNotVerifiedError,
    InvalidAccountingPasswordError,
    InvalidOTPError,
    OTPMaxAttemptsError,
    OTPRateLimitedError,
    UserAlreadyExistsError,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.api_token import (
    APIToken,
    APITokenCreate,
    APITokenCreateResponse,
    APITokenListResponse,
    APITokenUpdate,
)
from syfthub.schemas.auth import (
    AuthConfigResponse,
    AuthResponse,
    GoogleAuthRequest,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    RegistrationResponse,
    ResendOTPRequest,
    Token,
    UserRegister,
    VerifyOTPRequest,
)
from syfthub.schemas.user import User, UserResponse
from syfthub.services.api_token_service import APITokenService
from syfthub.services.auth_service import AuthService
from syfthub.services.email_service import send_otp_email
from syfthub.services.otp_service import OTPService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config() -> AuthConfigResponse:
    """Return public authentication configuration.

    No authentication required. Frontends use this to decide whether to show
    email-verification or password-reset UI.
    """
    return AuthConfigResponse(
        require_email_verification=(
            settings.require_email_verification and settings.smtp_configured
        ),
        smtp_configured=settings.smtp_configured,
        password_reset_enabled=settings.smtp_configured,
    )


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
    background_tasks: BackgroundTasks,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    otp_service: Annotated[OTPService, Depends(get_otp_service)],
) -> RegistrationResponse:
    """Register a new user.

    This endpoint handles user registration with optional accounting service integration
    and optional email OTP verification.

    If username or email already exists in SyftHub, a 409 Conflict is returned.

    If an accounting service URL is configured (via request or default config), the backend
    will automatically create an accounting account for the user. If the email already
    exists in the accounting service, a 424 Failed Dependency response is returned and
    the user must provide their existing accounting password to link accounts.

    When email verification is enabled (REQUIRE_EMAIL_VERIFICATION=true and SMTP configured),
    the response will have null tokens and requires_email_verification=True. The client must
    call /auth/register/verify-otp with the code sent to the user's email.
    """
    try:
        result = auth_service.register(user_data)

        # If email verification is required, generate and send OTP
        if result.requires_email_verification:
            code = otp_service.generate_otp(user_data.email, "registration")
            background_tasks.add_task(
                send_otp_email, user_data.email, code, "registration"
            )

        return result

    except UserAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": e.error_code,
                "message": e.message,
                "field": e.field,
            },
        ) from e

    except AccountingAccountExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={
                "code": e.error_code,
                "message": e.message,
                "requires_accounting_password": e.requires_accounting_password,
            },
        ) from e

    except InvalidAccountingPasswordError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": e.error_code,
                "message": e.message,
            },
        ) from e

    except AccountingServiceUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": e.error_code,
                "message": e.message,
            },
        ) from e


@router.post("/login", response_model=AuthResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    """OAuth2 compatible token login, get an access token for future requests."""
    try:
        return auth_service.login(form_data.username, form_data.password)
    except EmailNotVerifiedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": e.error_code,
                "message": e.message,
            },
        ) from e


@router.post(
    "/google",
    response_model=AuthResponse,
    responses={
        401: {
            "description": "Invalid Google token",
            "content": {
                "application/json": {"example": {"detail": "Invalid Google token"}}
            },
        },
        503: {
            "description": "Google OAuth not configured",
            "content": {
                "application/json": {
                    "example": {"detail": "Google OAuth is not configured"}
                }
            },
        },
    },
)
async def google_login(
    google_data: GoogleAuthRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    """Authenticate or register user via Google OAuth.

    This endpoint handles both login and registration for Google OAuth:
    - If the user exists (by Google ID or email), they are logged in
    - If the user doesn't exist, a new account is created
    - If email matches an existing account, the Google account is linked

    The credential should be the Google ID token (JWT) received from
    Google Sign-In on the frontend.
    """
    return auth_service.google_login(google_data.credential)


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


# =============================================================================
# Email OTP Endpoints
# =============================================================================


@router.post("/register/verify-otp", response_model=AuthResponse)
async def verify_registration_otp(
    body: VerifyOTPRequest,
    otp_service: Annotated[OTPService, Depends(get_otp_service)],
) -> AuthResponse:
    """Verify the registration OTP and return auth tokens.

    After a successful registration that requires email verification,
    the client calls this endpoint with the 6-digit code sent to the
    user's email. On success, tokens are returned.

    Idempotent: if the user is already verified, tokens are issued
    without requiring an OTP.
    """
    user_repo = UserRepository(otp_service.otp_repo.session)
    user = user_repo.get_by_email(body.email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User not found"},
        )

    # Idempotent: already verified → just issue tokens
    if user.is_email_verified:
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "username": user.username}
        )
        return AuthResponse(
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
            },
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    try:
        otp_service.verify_otp(body.email, body.code, "registration")
    except InvalidOTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": e.error_code, "message": e.message},
        ) from e
    except OTPMaxAttemptsError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": e.error_code, "message": e.message},
        ) from e

    # Mark email verified
    user_repo.set_email_verified(user.id)

    # Issue tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "username": user.username}
    )

    return AuthResponse(
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
        },
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post(
    "/register/resend-otp",
    status_code=status.HTTP_200_OK,
)
async def resend_registration_otp(
    body: ResendOTPRequest,
    background_tasks: BackgroundTasks,
    otp_service: Annotated[OTPService, Depends(get_otp_service)],
) -> dict[str, str]:
    """Resend the registration OTP code.

    Rate-limited: max 3 requests per 10-minute window.
    Always returns 200 to prevent email enumeration.
    """
    try:
        user_repo = UserRepository(otp_service.otp_repo.session)
        user = user_repo.get_by_email(body.email)

        if user and not user.is_email_verified:
            code = otp_service.generate_otp(body.email, "registration")
            background_tasks.add_task(send_otp_email, body.email, code, "registration")
    except OTPRateLimitedError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": e.error_code, "message": e.message},
        ) from e
    except Exception:
        # Silently succeed to prevent enumeration
        logger.exception("Error in resend-otp for %s", body.email)

    return {
        "message": "If the email is registered and unverified, a new code was sent."
    }


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_200_OK,
)
async def request_password_reset(
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    otp_service: Annotated[OTPService, Depends(get_otp_service)],
) -> dict[str, str]:
    """Request a password-reset OTP.

    Always returns 200 to prevent email enumeration. If SMTP is not
    configured, silently does nothing.
    """
    if not settings.smtp_configured:
        return {"message": "If the email is registered, a reset code was sent."}

    try:
        user_repo = UserRepository(otp_service.otp_repo.session)
        model = user_repo.get_model_by_email(body.email)

        # Only send if user exists and has a password (not OAuth-only)
        if model and model.password_hash:
            code = otp_service.generate_otp(body.email, "password_reset")
            background_tasks.add_task(
                send_otp_email, body.email, code, "password_reset"
            )
    except OTPRateLimitedError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": e.error_code, "message": e.message},
        ) from e
    except Exception:
        logger.exception("Error in password-reset request for %s", body.email)

    return {"message": "If the email is registered, a reset code was sent."}


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_200_OK,
)
async def confirm_password_reset(
    body: PasswordResetConfirm,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    otp_service: Annotated[OTPService, Depends(get_otp_service)],
) -> dict[str, str]:
    """Verify the password-reset OTP and set a new password."""
    try:
        otp_service.verify_otp(body.email, body.code, "password_reset")
    except InvalidOTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": e.error_code, "message": e.message},
        ) from e
    except OTPMaxAttemptsError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": e.error_code, "message": e.message},
        ) from e

    auth_service.reset_password(body.email, body.new_password)
    return {"message": "Password has been reset successfully."}


# =============================================================================
# API Token Management Endpoints
# =============================================================================


@router.post(
    "/tokens",
    response_model=APITokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API token",
    responses={
        201: {
            "description": "API token created successfully. "
            "IMPORTANT: Save the token immediately - it will not be shown again!",
        },
        400: {"description": "Token limit exceeded"},
    },
)
async def create_api_token(
    token_data: APITokenCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    api_token_service: Annotated[APITokenService, Depends(get_api_token_service)],
) -> APITokenCreateResponse:
    """Create a new API token for authentication.

    API tokens provide an alternative to username/password authentication.
    They are ideal for CI/CD pipelines, scripts, and programmatic access.

    **IMPORTANT**: The full token is only shown ONCE in this response.
    Make sure to save it immediately - it cannot be retrieved later.

    The token can be used in the Authorization header:
    ```
    Authorization: Bearer syft_pat_xxxxx...
    ```
    """
    return api_token_service.create_token(current_user, token_data)


@router.get(
    "/tokens",
    response_model=APITokenListResponse,
    summary="List API tokens",
)
async def list_api_tokens(
    current_user: Annotated[User, Depends(get_current_active_user)],
    api_token_service: Annotated[APITokenService, Depends(get_api_token_service)],
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> APITokenListResponse:
    """List all API tokens for the current user.

    By default, only active tokens are returned. Use `include_inactive=true`
    to also include revoked tokens.

    Note: The full token value is never returned - only the prefix for identification.
    """
    return api_token_service.list_tokens(
        current_user,
        include_inactive=include_inactive,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/tokens/{token_id}",
    response_model=APIToken,
    summary="Get API token",
    responses={
        404: {"description": "Token not found"},
    },
)
async def get_api_token(
    token_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    api_token_service: Annotated[APITokenService, Depends(get_api_token_service)],
) -> APIToken:
    """Get details of a specific API token.

    Note: The full token value is never returned - only the prefix for identification.
    """
    return api_token_service.get_token(current_user, token_id)


@router.patch(
    "/tokens/{token_id}",
    response_model=APIToken,
    summary="Update API token",
    responses={
        404: {"description": "Token not found"},
    },
)
async def update_api_token(
    token_id: int,
    token_data: APITokenUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    api_token_service: Annotated[APITokenService, Depends(get_api_token_service)],
) -> APIToken:
    """Update an API token's name.

    Only the name can be updated. Scopes and expiration cannot be changed
    after creation for security reasons.
    """
    return api_token_service.update_token(current_user, token_id, token_data)


@router.delete(
    "/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke API token",
    responses={
        404: {"description": "Token not found"},
    },
)
async def revoke_api_token(
    token_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    api_token_service: Annotated[APITokenService, Depends(get_api_token_service)],
) -> None:
    """Revoke an API token.

    The token becomes immediately unusable. The record is kept for audit purposes.
    This action cannot be undone.
    """
    api_token_service.revoke_token(current_user, token_id)
