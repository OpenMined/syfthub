"""Authentication business logic service."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any, Optional, Tuple

from fastapi import HTTPException, status

from syfthub.auth.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from syfthub.core.config import settings
from syfthub.domain.exceptions import (
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
from syfthub.services.base import BaseService
from syfthub.services.unified_ledger_client import (
    UnifiedLedgerClient,
    provision_ledger_user,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AuthService(BaseService):
    """Authentication service for handling user authentication operations."""

    def __init__(self, session: Session):
        """Initialize auth service."""
        super().__init__(session)
        self.user_repository = UserRepository(session)

    def _handle_accounting_setup(
        self,
        email: str,
        accounting_url: Optional[str],
        accounting_api_token: Optional[str],
        accounting_account_id: Optional[str],
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Handle Unified Global Ledger setup during user signup.

        This method implements auto-provisioning:
        1. If no API token is provided, try to auto-provision a new ledger account
        2. If auto-provisioning succeeds, use the generated API token and account
        3. If the email already exists in the ledger, skip (user can configure later)
        4. If an API token is explicitly provided, validate it as before

        Note: For auto-provisioning, a random password is generated for the ledger
        account. Users authenticate via API tokens, not passwords, so this is only
        used internally by the ledger service.

        Args:
            email: User's email address
            accounting_url: Ledger service URL (from request or config)
            accounting_api_token: API token for the ledger (at_* format)
            accounting_account_id: UUID of the user's ledger account

        Returns:
            Tuple of (accounting_url, accounting_api_token, accounting_account_id)

        Raises:
            InvalidAccountingPasswordError: If API token is invalid
            AccountingServiceUnavailableError: If ledger service is unreachable
        """
        # Determine the accounting URL to use
        effective_url = accounting_url or settings.default_accounting_url

        # If no accounting URL configured, skip accounting integration
        if not effective_url:
            logger.debug(
                "No accounting URL configured, skipping accounting integration"
            )
            return (None, None, None)

        # If no API token provided, try auto-provisioning
        if not accounting_api_token:
            logger.info(f"Auto-provisioning ledger account for {email}")

            # Generate a random password for the ledger account.
            # Users authenticate via API tokens, not passwords, so this is only
            # used internally by the ledger service.
            ledger_password = secrets.token_urlsafe(32)

            result = provision_ledger_user(
                base_url=effective_url,
                email=email,
                password=ledger_password,
                timeout=settings.accounting_timeout,
            )

            if result.success and result.data:
                # Auto-provisioning succeeded
                logger.info(
                    f"Auto-provisioned ledger account for {email}: "
                    f"account_id={result.data.account_id}"
                )
                return (
                    effective_url,
                    result.data.api_token,
                    result.data.account_id,
                )

            if result.status_code == 409:
                # Email already exists in ledger - user must configure manually
                logger.info(
                    f"Email {email} already exists in ledger, "
                    "user must configure credentials manually"
                )
                return (effective_url, None, None)

            # Other error - log but don't fail registration
            logger.warning(
                f"Failed to auto-provision ledger account for {email}: {result.error}"
            )
            return (effective_url, None, None)

        # API token was explicitly provided - validate it
        logger.info(f"Validating ledger credentials for {email} at {effective_url}")

        client = UnifiedLedgerClient(
            base_url=effective_url,
            api_token=accounting_api_token,
            timeout=settings.accounting_timeout,
        )

        try:
            # Validate the API token
            result = client.validate_token()

            if not result.success:
                if result.status_code == 401:
                    logger.warning(f"Invalid ledger API token for {email}")
                    raise InvalidAccountingPasswordError()
                logger.error(f"Ledger service error: {result.error}")
                raise AccountingServiceUnavailableError(result.error or "Unknown error")

            # If account ID provided, validate it exists
            if accounting_account_id:
                account_result = client.get_account(accounting_account_id)
                if not account_result.success:
                    logger.warning(
                        f"Invalid account ID {accounting_account_id} for {email}"
                    )
                    raise InvalidAccountingPasswordError()

            logger.info(f"Validated ledger credentials for {email}")
            return (effective_url, accounting_api_token, accounting_account_id)

        except (InvalidAccountingPasswordError, AccountingServiceUnavailableError):
            raise
        except Exception as e:
            logger.error(f"Failed to validate ledger credentials: {e}")
            raise AccountingServiceUnavailableError(str(e)) from e
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

        # Handle accounting service setup (Unified Global Ledger)
        # This attempts auto-provisioning if no API token is provided
        # May raise InvalidAccountingPasswordError or AccountingServiceUnavailableError
        accounting_url, accounting_api_token, accounting_account_id = (
            self._handle_accounting_setup(
                email=register_data.email,
                accounting_url=register_data.accounting_service_url,
                accounting_api_token=getattr(
                    register_data, "accounting_api_token", None
                ),
                accounting_account_id=getattr(
                    register_data, "accounting_account_id", None
                ),
            )
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
            accounting_api_token=accounting_api_token,
            accounting_account_id=accounting_account_id,
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

        # Check if user has a password (OAuth users don't)
        if not user.password_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please use Google Sign-In for this account",
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
        if not current_user.password_hash or not verify_password(
            current_password, current_user.password_hash
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

        # Hash new password and update
        new_password_hash = hash_password(new_password)
        self.user_repository.update_password(current_user.id, new_password_hash)

    def _verify_google_token(self, credential: str) -> dict[str, Any]:
        """Verify Google ID token and extract user info.

        Args:
            credential: Google ID token (JWT) from Google Sign-In

        Returns:
            Dictionary with user info from Google token

        Raises:
            HTTPException: If token is invalid or verification fails
        """
        import urllib3
        from google.auth.transport import urllib3 as google_urllib3
        from google.oauth2 import id_token

        if not settings.google_oauth_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google OAuth is not configured",
            )

        try:
            # Verify the Google ID token
            http = urllib3.PoolManager()
            request = google_urllib3.Request(http)  # type: ignore[no-untyped-call]
            idinfo = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
                credential,
                request,
                settings.google_client_id,
            )

            # Verify the token is from Google
            if idinfo.get("iss") not in [
                "accounts.google.com",
                "https://accounts.google.com",
            ]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token issuer",
                )

            return dict(idinfo)

        except ValueError as e:
            logger.warning(f"Invalid Google token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token",
            ) from e

    def _generate_unique_username(self, email: str) -> str:
        """Generate a unique username from email.

        Args:
            email: User's email address

        Returns:
            A unique username based on the email prefix
        """
        import secrets

        # Extract email prefix and sanitize
        base_username = email.split("@")[0].lower()
        base_username = "".join(c for c in base_username if c.isalnum() or c in "_-")

        # Ensure minimum length
        if len(base_username) < 3:
            base_username = f"user{base_username}"

        # Try the base username first
        if not self.user_repository.username_exists(base_username):
            return base_username

        # Add random suffix until we find a unique one
        for _ in range(10):
            suffix = secrets.randbelow(900) + 100  # 100-999
            username = f"{base_username}{suffix}"
            if not self.user_repository.username_exists(username):
                return username

        # Final fallback with longer random suffix
        suffix = secrets.randbelow(9000) + 1000  # 1000-9999
        return f"{base_username}{suffix}"

    def google_login(self, credential: str) -> AuthResponse:
        """Authenticate or register user via Google OAuth.

        This method handles both login and registration for Google OAuth:
        1. Verify the Google ID token
        2. Check if user exists by google_id
        3. If not, check if user exists by email (account linking)
        4. If no user found, create a new account
        5. Return authentication tokens

        Args:
            credential: Google ID token from Google Sign-In

        Returns:
            AuthResponse with user info and tokens

        Raises:
            HTTPException: For various auth errors
        """
        # Verify Google token
        idinfo = self._verify_google_token(credential)

        google_id = idinfo.get("sub")
        email = idinfo.get("email", "").lower()
        full_name = idinfo.get("name", "")
        avatar_url = idinfo.get("picture")

        if not google_id or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token: missing user information",
            )

        # Try to find existing user by google_id
        user = self.user_repository.get_by_google_id(google_id)

        if not user:
            # Try to find by email (for account linking)
            user = self.user_repository.get_by_email(email)

            if user:
                # Link Google account to existing user
                logger.info(f"Linking Google account to existing user: {email}")
                self.user_repository.link_google_account(
                    user_id=user.id,
                    google_id=google_id,
                    avatar_url=avatar_url,
                )
                # Refresh user data
                user = self.user_repository.get_by_id(user.id)
            else:
                # Create new user
                logger.info(f"Creating new user via Google OAuth: {email}")
                username = self._generate_unique_username(email)

                user_data = UserCreate(
                    username=username,
                    email=email,
                    full_name=full_name or email.split("@")[0],
                    is_active=True,
                )

                user = self.user_repository.create_user(
                    user_data=user_data,
                    password_hash=None,  # OAuth users don't have passwords
                    auth_provider="google",
                    google_id=google_id,
                    avatar_url=avatar_url,
                )

                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to create user account",
                    )

        # At this point, user should never be None
        # (either found by google_id, linked by email, or created new)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve user account",
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

        logger.info(f"Google OAuth login successful: {user.username} ({user.email})")

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
