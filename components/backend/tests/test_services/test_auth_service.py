"""Tests for AuthService."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from syfthub.database.connection import get_db_session
from syfthub.domain.exceptions import (
    UserAlreadyExistsError,
)
from syfthub.schemas.auth import RefreshTokenRequest, UserLogin, UserRegister
from syfthub.schemas.user import User
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


class TestAuthServiceRegistrationValidation:
    """Test input validation edge cases in register_user."""

    def test_register_username_too_short_raises_400(self, auth_service):
        """Username shorter than 3 chars raises HTTPException 400.

        UserRegister's Pydantic schema also enforces min_length, so we bypass
        it with a MagicMock to exercise the service-level guard directly.
        """
        mock_data = MagicMock()
        mock_data.username = "ab"
        mock_data.password = "longpassword1"

        with pytest.raises(HTTPException) as exc_info:
            auth_service.register_user(mock_data)
        assert exc_info.value.status_code == 400
        assert "Username must be at least 3 characters" in exc_info.value.detail

    def test_register_password_too_short_raises_400(self, auth_service):
        """Password shorter than 8 chars raises HTTPException 400."""
        mock_data = MagicMock()
        mock_data.username = "validuser"
        mock_data.password = "short"

        with pytest.raises(HTTPException) as exc_info:
            auth_service.register_user(mock_data)
        assert exc_info.value.status_code == 400
        assert "Password must be at least 8 characters" in exc_info.value.detail


class TestAuthServiceLoginEdgeCases:
    """Test edge cases in login_user."""

    def test_login_oauth_user_without_password_raises_401(self, auth_service):
        """User with no password_hash (OAuth-only account) gets 401 with Google hint."""
        login_data = UserLogin(username="oauthuser", password="anything")
        oauth_user = User(
            id=5,
            username="oauthuser",
            email="oauth@example.com",
            full_name="OAuth User",
            role="user",
            is_active=True,
            created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            age=25,
            password_hash=None,
        )
        with (
            patch.object(
                auth_service.user_repository, "get_by_username", return_value=oauth_user
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            auth_service.login_user(login_data)
        assert exc_info.value.status_code == 401
        assert "Google Sign-In" in exc_info.value.detail


class TestAuthServiceChangePassword:
    """Test change_password validation."""

    def test_change_password_new_too_short_raises_400(self, auth_service):
        """New password shorter than 8 chars raises HTTPException 400."""
        user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            role="user",
            is_active=True,
            created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            age=25,
            password_hash="current_hash",
        )
        with (
            patch("syfthub.services.auth_service.verify_password", return_value=True),
            pytest.raises(HTTPException) as exc_info,
        ):
            auth_service.change_password(user, "current_pass", "short")
        assert exc_info.value.status_code == 400
        assert "8 characters" in exc_info.value.detail


class TestGenerateUniqueUsername:
    """Tests for AuthService._generate_unique_username."""

    def test_returns_base_when_available(self, auth_service):
        """Returns the email prefix directly when it's not taken."""
        with patch.object(
            auth_service.user_repository, "username_exists", return_value=False
        ):
            result = auth_service._generate_unique_username("johndoe@example.com")
        assert result == "johndoe"

    def test_returns_suffixed_when_base_taken(self, auth_service):
        """Adds numeric suffix when base username is already taken."""
        with patch.object(
            auth_service.user_repository,
            "username_exists",
            side_effect=[True, False],
        ):
            result = auth_service._generate_unique_username("johndoe@example.com")
        assert result.startswith("johndoe")
        assert len(result) > len("johndoe")

    def test_short_email_prefix_gets_user_prefix(self, auth_service):
        """Email prefix shorter than 3 chars is prepended with 'user'."""
        with patch.object(
            auth_service.user_repository, "username_exists", return_value=False
        ):
            result = auth_service._generate_unique_username("ab@example.com")
        assert result == "userab"

    def test_sanitizes_special_chars_from_email(self, auth_service):
        """Non-alphanumeric chars (except _ and -) are stripped from email prefix."""
        with patch.object(
            auth_service.user_repository, "username_exists", return_value=False
        ):
            result = auth_service._generate_unique_username("john.doe+tag@example.com")
        assert result == "johndoetag"


class TestGoogleLogin:
    """Tests for AuthService.google_login."""

    def _make_user(self, **kwargs) -> User:
        defaults = {
            "id": 1,
            "username": "guser",
            "email": "guser@example.com",
            "full_name": "Google User",
            "role": "user",
            "is_active": True,
            "created_at": datetime.fromisoformat("2023-01-01T00:00:00"),
            "updated_at": datetime.fromisoformat("2023-01-01T00:00:00"),
            "age": 25,
            "password_hash": None,
        }
        defaults.update(kwargs)
        return User(**defaults)

    def test_login_existing_google_id_user(self, auth_service):
        """Existing user found by google_id gets tokens returned."""
        mock_idinfo = {
            "sub": "gid-123",
            "email": "guser@example.com",
            "name": "Google User",
            "picture": "https://g.com/pic.jpg",
        }
        existing_user = self._make_user()

        with (
            patch.object(
                auth_service, "_verify_google_token", return_value=mock_idinfo
            ),
            patch.object(
                auth_service.user_repository,
                "get_by_google_id",
                return_value=existing_user,
            ),
            patch(
                "syfthub.services.auth_service.create_access_token",
                return_value="access",
            ),
            patch(
                "syfthub.services.auth_service.create_refresh_token",
                return_value="refresh",
            ),
        ):
            result = auth_service.google_login("google_credential")

        assert result.access_token == "access"
        assert result.refresh_token == "refresh"
        assert result.user["username"] == "guser"

    def test_login_links_existing_email_account(self, auth_service):
        """User found by email (but not google_id) gets google account linked."""
        mock_idinfo = {
            "sub": "gid-new",
            "email": "existing@example.com",
            "name": "Existing User",
        }
        existing_by_email = self._make_user(email="existing@example.com")
        refreshed_user = self._make_user(email="existing@example.com")

        with (
            patch.object(
                auth_service, "_verify_google_token", return_value=mock_idinfo
            ),
            patch.object(
                auth_service.user_repository, "get_by_google_id", return_value=None
            ),
            patch.object(
                auth_service.user_repository,
                "get_by_email",
                return_value=existing_by_email,
            ),
            patch.object(
                auth_service.user_repository,
                "link_google_account",
                return_value=True,
            ),
            patch.object(
                auth_service.user_repository,
                "get_by_id",
                return_value=refreshed_user,
            ),
            patch(
                "syfthub.services.auth_service.create_access_token",
                return_value="access",
            ),
            patch(
                "syfthub.services.auth_service.create_refresh_token",
                return_value="refresh",
            ),
        ):
            result = auth_service.google_login("google_credential")

        assert result.access_token == "access"

    def test_login_creates_new_user(self, auth_service):
        """No existing user → new account is created."""
        mock_idinfo = {
            "sub": "gid-brand-new",
            "email": "newgoogle@example.com",
            "name": "Brand New",
        }
        new_user = self._make_user(email="newgoogle@example.com")

        with (
            patch.object(
                auth_service, "_verify_google_token", return_value=mock_idinfo
            ),
            patch.object(
                auth_service.user_repository, "get_by_google_id", return_value=None
            ),
            patch.object(
                auth_service.user_repository, "get_by_email", return_value=None
            ),
            patch.object(
                auth_service, "_generate_unique_username", return_value="newgoogle"
            ),
            patch.object(
                auth_service.user_repository, "create_user", return_value=new_user
            ),
            patch(
                "syfthub.services.auth_service.create_access_token",
                return_value="access",
            ),
            patch(
                "syfthub.services.auth_service.create_refresh_token",
                return_value="refresh",
            ),
        ):
            result = auth_service.google_login("google_credential")

        assert result.user["email"] == "newgoogle@example.com"

    def test_login_raises_401_for_inactive_user(self, auth_service):
        """Inactive user gets 401 even with valid Google token."""
        mock_idinfo = {"sub": "gid-123", "email": "inactive@example.com", "name": "X"}
        inactive_user = self._make_user(is_active=False)

        with (
            patch.object(
                auth_service, "_verify_google_token", return_value=mock_idinfo
            ),
            patch.object(
                auth_service.user_repository,
                "get_by_google_id",
                return_value=inactive_user,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            auth_service.google_login("google_credential")

        assert exc_info.value.status_code == 401
        assert "deactivated" in exc_info.value.detail

    def test_login_raises_401_when_missing_google_info(self, auth_service):
        """Token without sub or email raises 401."""
        mock_idinfo = {"name": "No Sub Or Email"}

        with (
            patch.object(
                auth_service, "_verify_google_token", return_value=mock_idinfo
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            auth_service.google_login("google_credential")

        assert exc_info.value.status_code == 401
        assert "missing user information" in exc_info.value.detail
