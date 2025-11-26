"""Tests for AuthService."""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from syfthub.database.connection import get_db_session
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
                "syfthub.services.auth_service.generate_ed25519_key_pair"
            ) as mock_keygen,
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
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
                password_hash="hashed_pass",
            )
            mock_create.return_value = mock_user

            # Mock key pair - import Ed25519KeyPair at the top if needed
            from syfthub.schemas.auth import Ed25519KeyPair

            mock_key_pair = Ed25519KeyPair(
                public_key="public_key", private_key="private_key"
            )
            mock_keygen.return_value = mock_key_pair

            result = auth_service.register_user(sample_user_register)

            assert result.access_token == "access_token"
            assert result.refresh_token == "refresh_token"
            assert result.token_type == "bearer"
            assert result.user["id"] == 1
            assert result.user["username"] == "testuser"
            assert result.keys == mock_key_pair

    def test_register_user_duplicate_username(self, auth_service, sample_user_register):
        """Test registration with existing username fails."""
        with patch.object(
            auth_service.user_repository, "username_exists", return_value=True
        ):
            with pytest.raises(HTTPException) as exc_info:
                auth_service.register_user(sample_user_register)

            assert exc_info.value.status_code == 400
            assert "Username already exists" in str(exc_info.value.detail)

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
            with pytest.raises(HTTPException) as exc_info:
                auth_service.register_user(sample_user_register)

            assert exc_info.value.status_code == 400
            assert "Email already exists" in str(exc_info.value.detail)

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
            patch("syfthub.services.auth_service.generate_ed25519_key_pair"),
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
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
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
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
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
                public_key="public_key",
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
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
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
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
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


class TestAuthServiceSignatureVerification:
    """Test Ed25519 signature verification."""

    def test_verify_ed25519_signature_success(self, auth_service):
        """Test successful signature verification."""
        with (
            patch.object(
                auth_service.user_repository, "get_by_username"
            ) as mock_get_user,
            patch("syfthub.auth.security.verify_ed25519_signature", return_value=True),
        ):
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="valid_public_key",
                password_hash="hashed_pass",
            )
            mock_get_user.return_value = mock_user

            result = auth_service.verify_ed25519_signature(
                "testuser", "signature", "message"
            )

            assert result == mock_user

    def test_verify_ed25519_signature_user_not_found(self, auth_service):
        """Test signature verification with non-existent user."""
        with patch.object(
            auth_service.user_repository, "get_by_username", return_value=None
        ):
            result = auth_service.verify_ed25519_signature(
                "nonexistent", "signature", "message"
            )

            assert result is None

    def test_verify_ed25519_signature_user_inactive(self, auth_service):
        """Test signature verification with inactive user."""
        with patch.object(
            auth_service.user_repository, "get_by_username"
        ) as mock_get_user:
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=False,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
                password_hash="hashed_pass",
            )
            mock_get_user.return_value = mock_user

            result = auth_service.verify_ed25519_signature(
                "testuser", "signature", "message"
            )

            assert result is None

    def test_verify_ed25519_signature_invalid_signature(self, auth_service):
        """Test signature verification with invalid signature."""
        with (
            patch.object(
                auth_service.user_repository, "get_by_username"
            ) as mock_get_user,
            patch("syfthub.auth.security.verify_ed25519_signature", return_value=False),
        ):
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                full_name="Test User",
                role="user",
                is_active=True,
                created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="valid_public_key",
                password_hash="hashed_pass",
            )
            mock_get_user.return_value = mock_user

            result = auth_service.verify_ed25519_signature(
                "testuser", "bad_signature", "message"
            )

            assert result is None


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
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
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
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
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
                key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
                age=25,
                public_key="public_key",
                password_hash="hashed_pass",
            )
            mock_get.return_value = mock_user

            result = auth_service.get_user_by_id(1)

            assert result == mock_user
            mock_get.assert_called_once_with(1)
