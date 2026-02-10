"""Tests for AuthService."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from syfthub.database.connection import get_db_session
from syfthub.domain.exceptions import (
    AccountingServiceUnavailableError,
    InvalidAccountingPasswordError,
    UserAlreadyExistsError,
)
from syfthub.schemas.auth import RefreshTokenRequest, UserLogin, UserRegister
from syfthub.schemas.user import User
from syfthub.services.auth_service import AuthService
from syfthub.services.unified_ledger_client import (
    LedgerResult,
    ProvisionResult,
)


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


class TestVerifyGoogleToken:
    """Tests for the _verify_google_token method."""

    def test_google_oauth_disabled(self, auth_service):
        """Test error when Google OAuth is disabled."""
        with patch("syfthub.services.auth_service.settings") as mock_settings:
            mock_settings.google_oauth_enabled = False

            with pytest.raises(HTTPException) as exc_info:
                auth_service._verify_google_token("fake_credential")

            assert exc_info.value.status_code == 503
            assert "not configured" in exc_info.value.detail


class TestGenerateUniqueUsername:
    """Tests for the _generate_unique_username method."""

    def test_username_from_email(self, auth_service):
        """Test generating username from email prefix."""
        with patch.object(
            auth_service.user_repository, "username_exists", return_value=False
        ):
            username = auth_service._generate_unique_username("testuser@example.com")
            assert username == "testuser"

    def test_username_sanitization(self, auth_service):
        """Test username is sanitized correctly."""
        with patch.object(
            auth_service.user_repository, "username_exists", return_value=False
        ):
            username = auth_service._generate_unique_username(
                "test.user+tag@example.com"
            )
            # Only alphanumeric and _- are kept
            assert username == "testusertag"

    def test_short_username_padded(self, auth_service):
        """Test short usernames get padded."""
        with patch.object(
            auth_service.user_repository, "username_exists", return_value=False
        ):
            username = auth_service._generate_unique_username("ab@example.com")
            # Too short, gets "user" prefix
            assert username == "userab"

    def test_username_collision_adds_suffix(self, auth_service):
        """Test username gets suffix when collision occurs."""
        # First call returns True (collision), second returns False (available)
        with patch.object(
            auth_service.user_repository,
            "username_exists",
            side_effect=[True, False],
        ):
            username = auth_service._generate_unique_username("testuser@example.com")
            # Should have a numeric suffix
            assert username.startswith("testuser")
            assert len(username) > len("testuser")

    def test_username_final_fallback(self, auth_service):
        """Test final fallback with longer suffix after many collisions."""
        # All 10 attempts fail, then final fallback
        with patch.object(
            auth_service.user_repository,
            "username_exists",
            side_effect=[True] * 11,  # All 10 + base fail, final always succeeds
        ):
            username = auth_service._generate_unique_username("testuser@example.com")
            # Should have a 4-digit suffix (1000-9999)
            assert username.startswith("testuser")
            # Extract suffix and check it's 4 digits
            suffix = username[len("testuser") :]
            assert len(suffix) == 4
            assert suffix.isdigit()


class TestHandleAccountingSetup:
    """Test accounting setup handling for Unified Global Ledger.

    These tests cover:
    - Auto-provisioning of new ledger accounts
    - Validation of provided API tokens
    - Handling of existing accounts (email conflict)
    """

    def test_accounting_setup_skipped_when_no_url(self, auth_service):
        """Test that accounting setup is skipped when no URL configured."""
        with patch("syfthub.services.auth_service.settings") as mock_settings:
            mock_settings.default_accounting_url = ""

            result = auth_service._handle_accounting_setup(
                email="test@example.com",
                accounting_url=None,
                accounting_api_token=None,
                accounting_account_id=None,
            )

            assert result == (None, None, None)

    # =========================================================================
    # AUTO-PROVISIONING (no API token provided)
    # =========================================================================

    def test_auto_provision_new_user_success(self, auth_service):
        """Test successful auto-provisioning of new ledger account.

        Scenario: New user without API token, ledger auto-provisions account.

        Expected: provision_ledger_user succeeds, returns token and account_id.
        """
        mock_provision_result = LedgerResult(
            success=True,
            data=ProvisionResult(
                user_id="user-uuid-123",
                account_id="acc-uuid-456",
                api_token="at_new_token_789",
                api_token_prefix="at_new_",
            ),
            status_code=201,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.provision_ledger_user",
                return_value=mock_provision_result,
            ) as mock_provision,
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            result = auth_service._handle_accounting_setup(
                email="newuser@example.com",
                accounting_url="http://ledger.example.com",
                accounting_api_token=None,
                accounting_account_id=None,
            )

            assert result == (
                "http://ledger.example.com",
                "at_new_token_789",
                "acc-uuid-456",
            )
            mock_provision.assert_called_once()

    def test_auto_provision_email_already_exists(self, auth_service):
        """Test auto-provisioning when email already exists in ledger.

        Scenario: User email already exists in ledger (409 conflict).

        Expected: Returns (url, None, None), user must configure manually.
        """
        mock_provision_result = LedgerResult(
            success=False,
            error="Email already exists in ledger",
            status_code=409,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.provision_ledger_user",
                return_value=mock_provision_result,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            result = auth_service._handle_accounting_setup(
                email="existing@example.com",
                accounting_url="http://ledger.example.com",
                accounting_api_token=None,
                accounting_account_id=None,
            )

            # Should return URL but no token/account - user must configure manually
            assert result == ("http://ledger.example.com", None, None)

    def test_auto_provision_service_error(self, auth_service):
        """Test auto-provisioning when ledger service errors.

        Scenario: Ledger service returns error during auto-provisioning.

        Expected: Returns (url, None, None), doesn't fail registration.
        """
        mock_provision_result = LedgerResult(
            success=False,
            error="Connection timeout",
            status_code=500,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.provision_ledger_user",
                return_value=mock_provision_result,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            result = auth_service._handle_accounting_setup(
                email="test@example.com",
                accounting_url="http://ledger.example.com",
                accounting_api_token=None,
                accounting_account_id=None,
            )

            # Should not fail, just return partial result
            assert result == ("http://ledger.example.com", None, None)

    # =========================================================================
    # API TOKEN VALIDATION (token provided)
    # =========================================================================

    def test_validate_api_token_success(self, auth_service):
        """Test successful validation of provided API token.

        Scenario: User provides valid API token.

        Expected: Token is validated, returns provided credentials.
        """
        mock_client = MagicMock()
        mock_client.validate_token.return_value = LedgerResult(
            success=True,
            status_code=200,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.UnifiedLedgerClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            result = auth_service._handle_accounting_setup(
                email="user@example.com",
                accounting_url="http://ledger.example.com",
                accounting_api_token="at_valid_token_123",
                accounting_account_id=None,
            )

            assert result == (
                "http://ledger.example.com",
                "at_valid_token_123",
                None,
            )
            mock_client.validate_token.assert_called_once()
            mock_client.close.assert_called_once()

    def test_validate_api_token_with_account_id(self, auth_service):
        """Test validation of API token with account ID.

        Scenario: User provides valid API token and account ID.

        Expected: Both token and account are validated.
        """
        mock_client = MagicMock()
        mock_client.validate_token.return_value = LedgerResult(
            success=True,
            status_code=200,
        )
        mock_client.get_account.return_value = LedgerResult(
            success=True,
            status_code=200,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.UnifiedLedgerClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            result = auth_service._handle_accounting_setup(
                email="user@example.com",
                accounting_url="http://ledger.example.com",
                accounting_api_token="at_valid_token_123",
                accounting_account_id="acc_valid_456",
            )

            assert result == (
                "http://ledger.example.com",
                "at_valid_token_123",
                "acc_valid_456",
            )
            mock_client.validate_token.assert_called_once()
            mock_client.get_account.assert_called_once_with("acc_valid_456")
            mock_client.close.assert_called_once()

    def test_validate_api_token_invalid(self, auth_service):
        """Test validation of invalid API token.

        Scenario: User provides invalid API token.

        Expected: Raises InvalidAccountingPasswordError.
        """
        mock_client = MagicMock()
        mock_client.validate_token.return_value = LedgerResult(
            success=False,
            error="Invalid or expired API token",
            status_code=401,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.UnifiedLedgerClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            with pytest.raises(InvalidAccountingPasswordError):
                auth_service._handle_accounting_setup(
                    email="user@example.com",
                    accounting_url="http://ledger.example.com",
                    accounting_api_token="at_invalid_token",
                    accounting_account_id=None,
                )

            mock_client.close.assert_called_once()

    def test_validate_api_token_invalid_account_id(self, auth_service):
        """Test validation when account ID is invalid.

        Scenario: Token is valid but account ID doesn't exist.

        Expected: Raises InvalidAccountingPasswordError.
        """
        mock_client = MagicMock()
        mock_client.validate_token.return_value = LedgerResult(
            success=True,
            status_code=200,
        )
        mock_client.get_account.return_value = LedgerResult(
            success=False,
            error="Account not found",
            status_code=404,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.UnifiedLedgerClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            with pytest.raises(InvalidAccountingPasswordError):
                auth_service._handle_accounting_setup(
                    email="user@example.com",
                    accounting_url="http://ledger.example.com",
                    accounting_api_token="at_valid_token",
                    accounting_account_id="acc_invalid_456",
                )

            mock_client.close.assert_called_once()

    def test_validate_api_token_service_error(self, auth_service):
        """Test validation when ledger service errors.

        Scenario: Ledger service returns error during validation.

        Expected: Raises AccountingServiceUnavailableError.
        """
        mock_client = MagicMock()
        mock_client.validate_token.return_value = LedgerResult(
            success=False,
            error="Service unavailable",
            status_code=503,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.UnifiedLedgerClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            with pytest.raises(AccountingServiceUnavailableError) as exc_info:
                auth_service._handle_accounting_setup(
                    email="user@example.com",
                    accounting_url="http://ledger.example.com",
                    accounting_api_token="at_some_token",
                    accounting_account_id=None,
                )

            assert "Service unavailable" in exc_info.value.detail
            mock_client.close.assert_called_once()

    def test_validate_api_token_unexpected_exception(self, auth_service):
        """Test validation when unexpected exception occurs.

        Scenario: Client raises unexpected exception during validation.

        Expected: Raises AccountingServiceUnavailableError wrapping the original.
        """
        mock_client = MagicMock()
        mock_client.validate_token.side_effect = RuntimeError("Unexpected error")

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.UnifiedLedgerClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.default_accounting_url = None
            mock_settings.accounting_timeout = 30.0

            with pytest.raises(AccountingServiceUnavailableError) as exc_info:
                auth_service._handle_accounting_setup(
                    email="user@example.com",
                    accounting_url="http://ledger.example.com",
                    accounting_api_token="at_some_token",
                    accounting_account_id=None,
                )

            assert "Unexpected error" in exc_info.value.detail
            mock_client.close.assert_called_once()

    # =========================================================================
    # DEFAULT URL HANDLING
    # =========================================================================

    def test_accounting_setup_uses_default_url(self, auth_service):
        """Test that default accounting URL is used when not provided."""
        mock_provision_result = LedgerResult(
            success=True,
            data=ProvisionResult(
                user_id="user-uuid-123",
                account_id="acc-uuid-456",
                api_token="at_new_token_789",
                api_token_prefix="at_new_",
            ),
            status_code=201,
        )

        with (
            patch("syfthub.services.auth_service.settings") as mock_settings,
            patch(
                "syfthub.services.auth_service.provision_ledger_user",
                return_value=mock_provision_result,
            ) as mock_provision,
        ):
            mock_settings.default_accounting_url = "http://default-ledger.com"
            mock_settings.accounting_timeout = 30.0

            result = auth_service._handle_accounting_setup(
                email="test@example.com",
                accounting_url=None,  # Not provided, should use default
                accounting_api_token=None,
                accounting_account_id=None,
            )

            # Verify default URL was used
            mock_provision.assert_called_once()
            call_kwargs = mock_provision.call_args[1]
            assert call_kwargs["base_url"] == "http://default-ledger.com"
            assert result[0] == "http://default-ledger.com"
