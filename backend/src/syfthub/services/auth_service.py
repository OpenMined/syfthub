"""Authentication business logic service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from fastapi import HTTPException, status

from syfthub.auth.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from syfthub.core.config import settings
from syfthub.domain.exceptions import (
    AccountingAccountExistsError,
    AccountingServiceUnavailableError,
    InvalidAccountingPasswordError,
    UserAlreadyExistsError,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import (
    AuthResponse,
    RefreshTokenRequest,
    RegistrationResponse,
    Token,
    UserLogin,
    UserRegister,
)
from syfthub.schemas.user import User, UserCreate
from syfthub.services.accounting_client import (
    AccountingClient,
    generate_accounting_password,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AuthService(BaseService):
    """Authentication service for handling user authentication operations."""

    def __init__(self, session: Session):
        """Initialize auth service."""
        super().__init__(session)
        self.user_repository = UserRepository(session)

    def _handle_accounting_registration(
        self,
        email: str,
        accounting_url: Optional[str],
        accounting_password: Optional[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Handle accounting service registration during user signup.

        This method uses a "try-create-first" approach that intelligently handles
        both new and existing accounting users:

        1. If accounting_password is provided:
           - First TRY to create a new account with this password
           - If account exists (conflict), VALIDATE the password instead
           This supports both:
           - New users who want to set their own accounting password
           - Existing users linking their accounts

        2. If accounting_password is NOT provided:
           - Auto-generate a secure password
           - Create a new accounting account
           - If account exists, raise error asking for password

        Args:
            email: User's email address
            accounting_url: Accounting service URL (from request or config)
            accounting_password: Password for accounting service. Can be:
                - A new password to create an account with (for new users)
                - An existing password to validate (for existing users)
                - None to auto-generate a password (for new users)

        Returns:
            Tuple of (accounting_url, accounting_password) to store

        Raises:
            AccountingAccountExistsError: If email exists and no password provided
            InvalidAccountingPasswordError: If provided password is invalid
            AccountingServiceUnavailableError: If accounting service is unreachable
        """
        # Determine the accounting URL to use
        effective_url = accounting_url or settings.default_accounting_url

        # If no accounting URL configured, skip accounting integration
        if not effective_url:
            logger.debug(
                "No accounting URL configured, skipping accounting integration"
            )
            return (None, None)

        logger.info(
            f"Processing accounting registration for {email} at {effective_url}"
        )

        # Create accounting client
        client = AccountingClient(
            base_url=effective_url,
            timeout=settings.accounting_timeout,
        )

        try:
            if accounting_password:
                # User provided a password - could be for new OR existing account
                # Try to create first (handles new user with custom password)
                logger.debug(
                    f"Attempting to create accounting account for {email} "
                    "with user-provided password"
                )

                result = client.create_user(
                    email=email,
                    password=accounting_password,
                    organization=None,
                )

                if result.success:
                    # New account created with user's chosen password
                    logger.info(
                        f"Created accounting account for {email} "
                        "with user-provided password"
                    )
                    return (effective_url, accounting_password)

                if result.conflict:
                    # Account already exists - validate the provided password
                    logger.debug(
                        f"Accounting account exists for {email}, validating credentials"
                    )
                    is_valid = client.validate_credentials(email, accounting_password)

                    if not is_valid:
                        logger.warning(f"Invalid accounting credentials for {email}")
                        raise InvalidAccountingPasswordError()

                    logger.info(
                        f"Validated and linked existing accounting account for {email}"
                    )
                    return (effective_url, accounting_password)

                # Other error from accounting service
                logger.error(f"Accounting service error: {result.error}")
                raise AccountingServiceUnavailableError(result.error or "Unknown error")

            else:
                # No password provided - auto-generate and create
                generated_password = generate_accounting_password(
                    length=settings.accounting_password_length
                )
                logger.debug(f"Auto-registering accounting account for {email}")

                result = client.create_user(
                    email=email,
                    password=generated_password,
                    organization=None,
                )

                if result.success:
                    logger.info(
                        f"Created accounting account for {email} "
                        "with auto-generated password"
                    )
                    return (effective_url, generated_password)

                if result.conflict:
                    # Account exists but user didn't provide password - they need to
                    logger.info(f"Accounting account already exists for {email}")
                    raise AccountingAccountExistsError(email)

                # Other error
                logger.error(f"Failed to create accounting account: {result.error}")
                raise AccountingServiceUnavailableError(result.error or "Unknown error")

        finally:
            client.close()

    def register_user(self, register_data: UserRegister) -> RegistrationResponse:
        """Register a new user and return authentication tokens.

        This method handles the complete registration flow including:
        1. Input validation
        2. Username/email uniqueness check
        3. Accounting service integration (if configured)
        4. User creation in database
        5. Token generation

        Args:
            register_data: Registration data from the request

        Returns:
            RegistrationResponse with user info and tokens

        Raises:
            HTTPException: For validation errors
            AccountingAccountExistsError: If email exists in accounting service
            InvalidAccountingPasswordError: If provided accounting password is wrong
            AccountingServiceUnavailableError: If accounting service is unreachable
        """
        # Validate input data
        if not register_data.username or len(register_data.username) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username must be at least 3 characters long",
            )

        if not register_data.password or len(register_data.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long",
            )

        # Check if user already exists in SyftHub
        if self.user_repository.username_exists(register_data.username):
            raise UserAlreadyExistsError("username", register_data.username)

        if self.user_repository.email_exists(register_data.email):
            raise UserAlreadyExistsError("email", register_data.email)

        # Handle accounting service registration
        # This may raise AccountingAccountExistsError or InvalidAccountingPasswordError
        accounting_url, accounting_password = self._handle_accounting_registration(
            email=register_data.email,
            accounting_url=register_data.accounting_service_url,
            accounting_password=register_data.accounting_password,
        )

        # Generate password hash for SyftHub
        password_hash = hash_password(register_data.password)

        # Create user data
        user_data = UserCreate(
            username=register_data.username,
            email=register_data.email,
            full_name=register_data.full_name,
            is_active=True,
        )

        # Create user in database with accounting credentials
        user = self.user_repository.create_user(
            user_data=user_data,
            password_hash=password_hash,
            accounting_service_url=accounting_url,
            accounting_password=accounting_password,
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account",
            )

        # Create tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "username": user.username}
        )

        logger.info(f"Successfully registered user: {user.username} ({user.email})")

        return RegistrationResponse(
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

    def login_user(self, login_data: UserLogin) -> AuthResponse:
        """Authenticate user and return tokens."""
        # Get user by username or email
        user = None
        if "@" in login_data.username:
            user = self.user_repository.get_by_email(login_data.username)
        else:
            user = self.user_repository.get_by_username(login_data.username)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Verify password
        if not verify_password(login_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated",
            )

        # Create tokens
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

    def refresh_tokens(self, refresh_data: RefreshTokenRequest) -> AuthResponse:
        """Refresh access token using refresh token."""
        from syfthub.auth.security import verify_token

        # Verify refresh token
        payload = verify_token(refresh_data.refresh_token, token_type="refresh")
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        # Get user from token
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID in token",
            ) from None

        user = self.user_repository.get_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        # Create new tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role}
        )
        new_refresh_token = create_refresh_token(
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
            refresh_token=new_refresh_token,
            token_type="bearer",
        )

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.user_repository.get_by_username(username)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.user_repository.get_by_email(email)

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return self.user_repository.get_by_id(user_id)

    # Router-compatible methods
    def register(self, user_data: UserRegister) -> RegistrationResponse:
        """Register a new user - router-compatible wrapper."""
        return self.register_user(user_data)

    def login(self, username: str, password: str) -> AuthResponse:
        """Login user and return tokens with user info - router-compatible wrapper."""
        login_data = UserLogin(username=username, password=password)
        return self.login_user(login_data)

    def refresh_token(self, refresh_token: str) -> Token:
        """Refresh access token - router-compatible wrapper."""
        refresh_request = RefreshTokenRequest(refresh_token=refresh_token)
        auth_response = self.refresh_tokens(refresh_request)
        return Token(
            access_token=auth_response.access_token,
            refresh_token=auth_response.refresh_token,
            token_type=auth_response.token_type,
        )

    def change_password(
        self, current_user: User, current_password: str, new_password: str
    ) -> None:
        """Change user's password."""
        # Verify current password
        if not verify_password(current_password, current_user.password_hash):
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

        # Hash new password and update
        new_password_hash = hash_password(new_password)
        self.user_repository.update_password(current_user.id, new_password_hash)
