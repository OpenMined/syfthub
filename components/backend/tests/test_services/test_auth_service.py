"""Tests for AuthService."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from syfthub.database.connection import get_db_session
from syfthub.domain.exceptions import (
    AccountingAccountExistsError,
    AccountingServiceUnavailableError,
    InvalidAccountingPasswordError,
    UserAlreadyExistsError,
)
from syfthub.schemas.auth import RefreshTokenRequest, UserLogin, UserRegister
from syfthub.schemas.user import User
from syfthub.services.accounting_client import AccountingUserResult
from syfthub.services.auth_service import AuthService


@pytest.fixture
def db_session():
    """Get database session for testing."""
    session = next(get_db_session())
    yield session
    session.close()


@pytest.fixture
def auth_service(db_session):
    """Create AuthService instance for testing."""
    return AuthService(db_session)


@pytest.fixture
def sample_user_register():
    """Sample user registration data."""
    return UserRegister(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        password="testpass123",
        age=25,
    )


@pytest.fixture
def sample_user_login():
    """Sample user login data."""
    return UserLogin(username="testuser", password="testpass123")


class TestAuthServiceRegistration:
    """Test user registration functionality."""

    def test_register_user_success(self, auth_service, sample_user_register):
        """Test successful user registration."""
        with (
            patch.object(
                auth_service.user_repository, "username_exists", return_value=False
            ),
            patch.object(
                auth_service.user_repository, "email_exists", return_value=False
            ),
            patch.object(auth_service.user_repository, "create_user") as mock_create,
            patch(
                "syfthub.services.auth_service.hash_password",
                return_value="hashed_pass",
            ),
            patch(
                "syfthub.services.auth_service.create_access_token",
                return_value="access_token",
            ),
            patch(
                "syfthub.services.auth_service.create_refresh_token",
                return_value="refresh_token",
            ),
        ):
            # Mock user creation
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_create.return_value = mock_user

            result = auth_service.register_user(sample_user_register)

            assert result.access_token == "access_token"
            assert result.refresh_token == "refresh_token"
            assert result.token_type == "bearer"
            assert result.user["id"] == 1
            assert result.user["username"] == "testuser"

    def test_register_user_duplicate_username(self, auth_service, sample_user_register):
        """Test registration with existing username fails."""
        with patch.object(
            auth_service.user_repository, "username_exists", return_value=True
        ):
            with pytest.raises(UserAlreadyExistsError) as exc_info:
                auth_service.register_user(sample_user_register)

            assert exc_info.value.field == "username"
            assert "Username already exists" in str(exc_info.value)

    def test_register_user_duplicate_email(self, auth_service, sample_user_register):
        """Test registration with existing email fails."""
        with (
            patch.object(
                auth_service.user_repository, "username_exists", return_value=False
            ),
            patch.object(
                auth_service.user_repository, "email_exists", return_value=True
            ),
        ):
            with pytest.raises(UserAlreadyExistsError) as exc_info:
                auth_service.register_user(sample_user_register)

            assert exc_info.value.field == "email"
            assert "Email already exists" in str(exc_info.value)

    def test_register_user_creation_failure(self, auth_service, sample_user_register):
        """Test registration when user creation fails."""
        with (
            patch.object(
                auth_service.user_repository, "username_exists", return_value=False
            ),
            patch.object(
                auth_service.user_repository, "email_exists", return_value=False
            ),
            patch.object(
                auth_service.user_repository, "create_user", return_value=None
            ),
            patch(
                "syfthub.services.auth_service.hash_password",
                return_value="hashed_pass",
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_service.register_user(sample_user_register)

            assert exc_info.value.status_code == 500
            assert "Failed to create user account" in str(exc_info.value.detail)


class TestAuthServiceLogin:
    """Test user login functionality."""

    def test_login_user_by_username_success(self, auth_service):
        """Test successful login by username."""
        login_data = UserLogin(username="testuser", password="testpass123")

        with (
            patch.object(
                auth_service.user_repository, "get_by_username"
            ) as mock_get_user,
            patch("syfthub.services.auth_service.verify_password", return_value=True),
            patch(
                "syfthub.services.auth_service.create_access_token",
                return_value="access_token",
            ),
            patch(
                "syfthub.services.auth_service.create_refresh_token",
                return_value="refresh_token",
            ),
        ):
            # Mock user
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_get_user.return_value = mock_user

            result = auth_service.login_user(login_data)

            assert result.access_token == "access_token"
            assert result.refresh_token == "refresh_token"
            assert result.user["username"] == "testuser"

    def test_login_user_by_email_success(self, auth_service):
        """Test successful login by email."""
        login_data = UserLogin(username="test@example.com", password="testpass123")

        with (
            patch.object(auth_service.user_repository, "get_by_email") as mock_get_user,
            patch("syfthub.services.auth_service.verify_password", return_value=True),
            patch(
                "syfthub.services.auth_service.create_access_token",
                return_value="access_token",
            ),
            patch(
                "syfthub.services.auth_service.create_refresh_token",
                return_value="refresh_token",
            ),
        ):
            # Mock user
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_get_user.return_value = mock_user

            result = auth_service.login_user(login_data)

            assert result.access_token == "access_token"
            assert result.user["email"] == "test@example.com"

    def test_login_user_not_found(self, auth_service, sample_user_login):
        """Test login with non-existent user."""
        with patch.object(
            auth_service.user_repository, "get_by_username", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_service.login_user(sample_user_login)

            assert exc_info.value.status_code == 401
            assert "Invalid credentials" in str(exc_info.value.detail)

    def test_login_user_invalid_password(self, auth_service, sample_user_login):
        """Test login with invalid password."""
        with (
            patch.object(
                auth_service.user_repository, "get_by_username"
            ) as mock_get_user,
            patch("syfthub.services.auth_service.verify_password", return_value=False),
        ):
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_get_user.return_value = mock_user

            with pytest.raises(HTTPException) as exc_info:
                auth_service.login_user(sample_user_login)

            assert exc_info.value.status_code == 401
            assert "Invalid credentials" in str(exc_info.value.detail)

    def test_login_user_inactive(self, auth_service, sample_user_login):
        """Test login with inactive user."""
        with (
            patch.object(
                auth_service.user_repository, "get_by_username"
            ) as mock_get_user,
            patch("syfthub.services.auth_service.verify_password", return_value=True),
        ):
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=False,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_get_user.return_value = mock_user

            with pytest.raises(HTTPException) as exc_info:
                auth_service.login_user(sample_user_login)

            assert exc_info.value.status_code == 401
            assert "Account is deactivated" in str(exc_info.value.detail)


class TestAuthServiceRefreshTokens:
    """Test token refresh functionality."""

    def test_refresh_tokens_success(self, auth_service):
        """Test successful token refresh."""
        refresh_data = RefreshTokenRequest(refresh_token="valid_refresh_token")

        with (
            patch("syfthub.auth.security.verify_token") as mock_verify,
            patch.object(auth_service.user_repository, "get_by_id") as mock_get_user,
            patch(
                "syfthub.services.auth_service.create_access_token",
                return_value="new_access_token",
            ),
            patch(
                "syfthub.services.auth_service.create_refresh_token",
                return_value="new_refresh_token",
            ),
        ):
            # Mock token verification
            mock_verify.return_value = {"sub": "1", "username": "testuser"}

            # Mock user
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_get_user.return_value = mock_user

            result = auth_service.refresh_tokens(refresh_data)

            assert result.access_token == "new_access_token"
            assert result.refresh_token == "new_refresh_token"
            assert result.user["id"] == 1
            assert result.user["username"] == "testuser"

    def test_refresh_tokens_invalid_token(self, auth_service):
        """Test refresh with invalid token."""
        refresh_data = RefreshTokenRequest(refresh_token="invalid_token")

        with patch("syfthub.auth.security.verify_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                auth_service.refresh_tokens(refresh_data)

            assert exc_info.value.status_code == 401
            assert "Invalid refresh token" in str(exc_info.value.detail)

    def test_refresh_tokens_no_user_id(self, auth_service):
        """Test refresh with token missing user ID."""
        refresh_data = RefreshTokenRequest(refresh_token="token_without_user_id")

        with patch(
            "syfthub.auth.security.verify_token", return_value={"username": "testuser"}
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_service.refresh_tokens(refresh_data)

            assert exc_info.value.status_code == 401
            assert "Invalid token payload" in str(exc_info.value.detail)

    def test_refresh_tokens_invalid_user_id(self, auth_service):
        """Test refresh with invalid user ID format."""
        refresh_data = RefreshTokenRequest(refresh_token="token_with_invalid_user_id")

        with patch(
            "syfthub.auth.security.verify_token",
            return_value={"sub": "invalid", "username": "testuser"},
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_service.refresh_tokens(refresh_data)

            assert exc_info.value.status_code == 401
            assert "Invalid user ID in token" in str(exc_info.value.detail)

    def test_refresh_tokens_user_not_found(self, auth_service):
        """Test refresh with non-existent user."""
        refresh_data = RefreshTokenRequest(refresh_token="token_for_deleted_user")

        with (
            patch(
                "syfthub.auth.security.verify_token",
                return_value={"sub": "999", "username": "deleteduser"},
            ),
            patch.object(auth_service.user_repository, "get_by_id", return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_service.refresh_tokens(refresh_data)

            assert exc_info.value.status_code == 401
            assert "User not found or inactive" in str(exc_info.value.detail)


class TestAuthServiceGetters:
    """Test getter methods."""

    def test_get_user_by_username(self, auth_service):
        """Test getting user by username."""
        with patch.object(auth_service.user_repository, "get_by_username") as mock_get:
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_get.return_value = mock_user

            result = auth_service.get_user_by_username("testuser")

            assert result == mock_user
            mock_get.assert_called_once_with("testuser")

    def test_get_user_by_email(self, auth_service):
        """Test getting user by email."""
        with patch.object(auth_service.user_repository, "get_by_email") as mock_get:
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_get.return_value = mock_user

            result = auth_service.get_user_by_email("test@example.com")

            assert result == mock_user
            mock_get.assert_called_once_with("test@example.com")

    def test_get_user_by_id(self, auth_service):
        """Test getting user by ID."""
        with patch.object(auth_service.user_repository, "get_by_id") as mock_get:
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                password_hash="hashed_pass",
            )
            mock_get.return_value = mock_user

            result = auth_service.get_user_by_id(1)

            assert result == mock_user
            mock_get.assert_called_once_with(1)


class TestHandleAccountingRegistration:
    """Test accounting registration handling.

    These tests cover the "try-create-first" approach which supports:
    - New users who want to set their own accounting password
    - New users who want auto-generated passwords
    - Existing accounting users linking their accounts
    """

    def test_accounting_registration_skipped_when_no_url(self, auth_service):
        """Test that accounting registration is skipped when no URL configured."""
        # When default_accounting_url is empty, should return (None, None)
        with patch("syfthub.services.auth_service.settings") as mock_settings:
            mock_settings.default_accounting_url = ""

            result = auth_service._handle_accounting_registration(
                email="test@example.com",
                accounting_url=None,
                accounting_password=None,
            )

            assert result == (None, None)

    # =========================================================================
    # NEW USER WITH CUSTOM PASSWORD (try-create-first succeeds)
    # =========================================================================

    def test_new_user_with_custom_accounting_password(self, auth_service):
        """Test new user can set their own accounting password.

        Scenario: User is new to both SyftHub and accounting service,
        but wants to set their own accounting password instead of auto-generated.

        Expected: create_user succeeds, returns user's chosen password.
        """
        mock_client = MagicMock()
        mock_client.create_user.return_value = AccountingUserResult(
            success=True,
            conflict=False,
            error=None,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.AccountingClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            result = auth_service._handle_accounting_registration(
                email="newuser@example.com",
                accounting_url="http://accounting.example.com",
                accounting_password="MyCustomPassword123!",
            )

            assert result == ("http://accounting.example.com", "MyCustomPassword123!")
            # Should try to create first
            mock_client.create_user.assert_called_once_with(
                email="newuser@example.com",
                password="MyCustomPassword123!",
                organization=None,
            )
            # Should NOT call validate (create succeeded)
            mock_client.validate_credentials.assert_not_called()
            mock_client.close.assert_called_once()

    # =========================================================================
    # EXISTING USER WITH CORRECT PASSWORD (try-create-first → conflict → validate)
    # =========================================================================

    def test_existing_user_with_correct_password(self, auth_service):
        """Test existing accounting user with correct password links successfully.

        Scenario: User already has an accounting account and provides correct password.

        Expected: create_user returns conflict, validate_credentials succeeds.
        """
        mock_client = MagicMock()
        # First call: create_user returns conflict (account exists)
        mock_client.create_user.return_value = AccountingUserResult(
            success=False,
            conflict=True,
            error=None,
        )
        # Second call: validate_credentials returns True
        mock_client.validate_credentials.return_value = True

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.AccountingClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            result = auth_service._handle_accounting_registration(
                email="existing@example.com",
                accounting_url="http://accounting.example.com",
                accounting_password="existing_password",
            )

            assert result == ("http://accounting.example.com", "existing_password")
            # Should try to create first
            mock_client.create_user.assert_called_once_with(
                email="existing@example.com",
                password="existing_password",
                organization=None,
            )
            # Should fall back to validate after conflict
            mock_client.validate_credentials.assert_called_once_with(
                "existing@example.com", "existing_password"
            )
            mock_client.close.assert_called_once()

    # =========================================================================
    # EXISTING USER WITH WRONG PASSWORD (try-create-first → conflict → validate fails)
    # =========================================================================

    def test_existing_user_with_wrong_password(self, auth_service):
        """Test existing accounting user with wrong password fails.

        Scenario: User already has an accounting account but provides wrong password.

        Expected: create_user returns conflict, validate_credentials fails,
        raises InvalidAccountingPasswordError.
        """
        mock_client = MagicMock()
        # First call: create_user returns conflict (account exists)
        mock_client.create_user.return_value = AccountingUserResult(
            success=False,
            conflict=True,
            error=None,
        )
        # Second call: validate_credentials returns False (wrong password)
        mock_client.validate_credentials.return_value = False

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.AccountingClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            with pytest.raises(InvalidAccountingPasswordError):
                auth_service._handle_accounting_registration(
                    email="existing@example.com",
                    accounting_url="http://accounting.example.com",
                    accounting_password="wrong_password",
                )

            # Should try to create first
            mock_client.create_user.assert_called_once()
            # Should fall back to validate after conflict
            mock_client.validate_credentials.assert_called_once()
            mock_client.close.assert_called_once()

    # =========================================================================
    # ACCOUNTING SERVICE ERROR WITH PROVIDED PASSWORD
    # =========================================================================

    def test_accounting_service_error_with_provided_password(self, auth_service):
        """Test accounting service error when password is provided.

        Scenario: User provides password but accounting service returns error.

        Expected: raises AccountingServiceUnavailableError.
        """
        mock_client = MagicMock()
        mock_client.create_user.return_value = AccountingUserResult(
            success=False,
            conflict=False,
            error="Connection timeout",
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.AccountingClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            with pytest.raises(AccountingServiceUnavailableError) as exc_info:
                auth_service._handle_accounting_registration(
                    email="test@example.com",
                    accounting_url="http://accounting.example.com",
                    accounting_password="some_password",
                )

            assert "Connection timeout" in exc_info.value.detail
            mock_client.close.assert_called_once()

    # =========================================================================
    # NEW USER WITH AUTO-GENERATED PASSWORD (no password provided)
    # =========================================================================

    def test_new_user_with_auto_generated_password(self, auth_service):
        """Test automatic accounting account creation with generated password.

        Scenario: New user doesn't provide accounting password.

        Expected: Password is auto-generated, account is created.
        """
        mock_client = MagicMock()
        mock_client.create_user.return_value = AccountingUserResult(
            success=True,
            conflict=False,
            error=None,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.AccountingClient",
                return_value=mock_client,
            ),
            patch(
                "syfthub.services.auth_service.generate_accounting_password",
                return_value="generated_password_123",
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0
            mock_settings.accounting_password_length = 32

            result = auth_service._handle_accounting_registration(
                email="newuser@example.com",
                accounting_url="http://accounting.example.com",
                accounting_password=None,
            )

            assert result == ("http://accounting.example.com", "generated_password_123")
            mock_client.create_user.assert_called_once()
            mock_client.close.assert_called_once()

    # =========================================================================
    # EXISTING USER WITHOUT PASSWORD (must provide password)
    # =========================================================================

    def test_existing_user_without_password_fails(self, auth_service):
        """Test existing accounting user must provide password.

        Scenario: User has existing accounting account but doesn't provide password.

        Expected: create_user returns conflict, raises AccountingAccountExistsError.
        """
        mock_client = MagicMock()
        mock_client.create_user.return_value = AccountingUserResult(
            success=False,
            conflict=True,
            error=None,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.AccountingClient",
                return_value=mock_client,
            ),
            patch(
                "syfthub.services.auth_service.generate_accounting_password",
                return_value="generated_password",
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0
            mock_settings.accounting_password_length = 32

            with pytest.raises(AccountingAccountExistsError) as exc_info:
                auth_service._handle_accounting_registration(
                    email="existing@example.com",
                    accounting_url="http://accounting.example.com",
                    accounting_password=None,
                )

            assert exc_info.value.email == "existing@example.com"
            mock_client.close.assert_called_once()

    # =========================================================================
    # ACCOUNTING SERVICE ERROR WITHOUT PASSWORD
    # =========================================================================

    def test_accounting_service_error_without_password(self, auth_service):
        """Test accounting service error when no password provided.

        Scenario: New user, no password, but accounting service returns error.

        Expected: raises AccountingServiceUnavailableError.
        """
        mock_client = MagicMock()
        mock_client.create_user.return_value = AccountingUserResult(
            success=False,
            conflict=False,
            error="Service unavailable",
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.AccountingClient",
                return_value=mock_client,
            ),
            patch(
                "syfthub.services.auth_service.generate_accounting_password",
                return_value="generated_password",
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0
            mock_settings.accounting_password_length = 32

            with pytest.raises(AccountingServiceUnavailableError) as exc_info:
                auth_service._handle_accounting_registration(
                    email="test@example.com",
                    accounting_url="http://accounting.example.com",
                    accounting_password=None,
                )

            assert "Service unavailable" in exc_info.value.detail
            mock_client.close.assert_called_once()

    # =========================================================================
    # DEFAULT URL HANDLING
    # =========================================================================

    def test_accounting_registration_uses_default_url(self, auth_service):
        """Test that default accounting URL is used when not provided."""
        mock_client = MagicMock()
        mock_client.create_user.return_value = AccountingUserResult(
            success=True,
            conflict=False,
            error=None,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.AccountingClient",
                return_value=mock_client,
            ) as mock_client_class,
            patch(
                "syfthub.services.auth_service.generate_accounting_password",
                return_value="generated_password",
            ),
        ):
            mock_settings.default_accounting_url = "http://default-accounting.com"
            mock_settings.accounting_timeout = 30.0
            mock_settings.accounting_password_length = 32

            result = auth_service._handle_accounting_registration(
                email="test@example.com",
                accounting_url=None,  # Not provided, should use default
                accounting_password=None,
            )

            # Verify default URL was used
            mock_client_class.assert_called_once_with(
                base_url="http://default-accounting.com",
                timeout=30.0,
            )
            assert result[0] == "http://default-accounting.com"
