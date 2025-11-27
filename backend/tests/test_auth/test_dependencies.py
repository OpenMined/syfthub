"""Tests for auth dependencies."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from syfthub.auth.db_dependencies import (
    OwnershipChecker,
    RoleChecker,
    get_current_active_user,
    get_current_user,
    get_optional_current_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import User


@pytest.fixture
def sample_user():
    """Create a sample user for testing."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        role=UserRole.USER,
        is_active=True,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        age=25,
        public_key="public_key",
        password_hash="hashed_pass",
    )


@pytest.fixture
def mock_user_repo(sample_user):
    """Create a mock UserRepository for testing."""
    repo = MagicMock(spec=UserRepository)
    repo.get_by_id.return_value = sample_user
    repo.get_by_username.return_value = sample_user
    repo.get_by_email.return_value = sample_user
    return repo


class TestUserHelperFunctions:
    """Test user helper functions."""

    def test_get_user_by_id_found(self, mock_user_repo, sample_user):
        """Test getting user by ID when found."""
        user = get_user_by_id(sample_user.id, mock_user_repo)
        assert user == sample_user
        mock_user_repo.get_by_id.assert_called_once_with(sample_user.id)

    def test_get_user_by_id_not_found(self, mock_user_repo):
        """Test getting user by ID when not found."""
        mock_user_repo.get_by_id.return_value = None
        user = get_user_by_id(999, mock_user_repo)
        assert user is None

    def test_get_user_by_username_found(self, mock_user_repo, sample_user):
        """Test getting user by username when found."""
        user = get_user_by_username(sample_user.username, mock_user_repo)
        assert user == sample_user
        mock_user_repo.get_by_username.assert_called_once_with(sample_user.username)

    def test_get_user_by_username_not_found(self, mock_user_repo):
        """Test getting user by username when not found."""
        mock_user_repo.get_by_username.return_value = None
        user = get_user_by_username("nonexistent", mock_user_repo)
        assert user is None

    def test_get_user_by_email_found(self, mock_user_repo, sample_user):
        """Test getting user by email when found."""
        user = get_user_by_email(sample_user.email, mock_user_repo)
        assert user == sample_user
        mock_user_repo.get_by_email.assert_called_once_with(sample_user.email)

    def test_get_user_by_email_not_found(self, mock_user_repo):
        """Test getting user by email when not found."""
        mock_user_repo.get_by_email.return_value = None
        user = get_user_by_email("nonexistent@example.com", mock_user_repo)
        assert user is None


class TestRoleChecker:
    """Test RoleChecker dependency."""

    def test_role_checker_allowed(self, sample_user):
        """Test role checker with allowed role."""
        checker = RoleChecker([UserRole.USER, UserRole.ADMIN])
        result = checker(sample_user)
        assert result is True

    def test_role_checker_forbidden(self, sample_user):
        """Test role checker with forbidden role."""
        checker = RoleChecker([UserRole.ADMIN])
        with pytest.raises(HTTPException) as exc_info:
            checker(sample_user)
        assert exc_info.value.status_code == 403


class TestOwnershipChecker:
    """Test OwnershipChecker dependency."""

    def test_ownership_checker_owner(self, sample_user):
        """Test ownership checker with resource owner."""
        checker = OwnershipChecker()
        result = checker(sample_user, sample_user.id)
        assert result is True

    def test_ownership_checker_admin(self):
        """Test ownership checker with admin user."""
        admin_user = User(
            id=2,
            username="admin",
            email="admin@example.com",
            full_name="Admin User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            age=30,
            public_key="admin_key",
            password_hash="admin_hash",
        )
        checker = OwnershipChecker()
        result = checker(admin_user, 999)  # Different user ID
        assert result is True

    def test_ownership_checker_forbidden(self, sample_user):
        """Test ownership checker with non-owner."""
        checker = OwnershipChecker()
        with pytest.raises(HTTPException) as exc_info:
            checker(sample_user, 999)  # Different user ID
        assert exc_info.value.status_code == 403


class TestAsyncAuthFunctions:
    """Test async authentication functions."""

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self, mock_user_repo):
        """Test get_current_user with no credentials."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None, mock_user_repo)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_user_repo):
        """Test get_current_user with invalid token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid_token"
        )
        with patch("syfthub.auth.db_dependencies.verify_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials, mock_user_repo)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_no_sub_claim(self, mock_user_repo):
        """Test get_current_user with token missing sub claim."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch("syfthub.auth.db_dependencies.verify_token", return_value={}):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials, mock_user_repo)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_user_id(self, mock_user_repo):
        """Test get_current_user with invalid user ID in token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch(
            "syfthub.auth.db_dependencies.verify_token", return_value={"sub": "invalid"}
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials, mock_user_repo)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self, mock_user_repo):
        """Test get_current_user with user not found in database."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        # Override mock to return None for user ID 999
        mock_user_repo.get_by_id.return_value = None
        with patch(
            "syfthub.auth.db_dependencies.verify_token", return_value={"sub": "999"}
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials, mock_user_repo)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_user_repo, sample_user):
        """Test get_current_user success case."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch(
            "syfthub.auth.db_dependencies.verify_token", return_value={"sub": "1"}
        ):
            user = await get_current_user(credentials, mock_user_repo)
            assert user == sample_user

    @pytest.mark.asyncio
    async def test_get_current_active_user_inactive(self, _mock_user_repo):
        """Test get_current_active_user with inactive user."""
        inactive_user = User(
            id=2,
            username="inactive",
            email="inactive@example.com",
            full_name="Inactive User",
            role=UserRole.USER,
            is_active=False,  # Inactive user
            created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
            age=25,
            public_key="inactive_key",
            password_hash="inactive_hash",
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(inactive_user)
        assert exc_info.value.status_code == 400
        assert "Inactive user" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_current_active_user_success(
        self,
        _mock_user_repo,
        sample_user,
    ):
        """Test get_current_active_user success case."""
        user = await get_current_active_user(sample_user)
        assert user == sample_user

    @pytest.mark.asyncio
    async def test_get_optional_current_user_no_credentials(self, mock_user_repo):
        """Test get_optional_current_user with no credentials."""
        user = await get_optional_current_user(None, mock_user_repo)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_optional_current_user_invalid_token(self, mock_user_repo):
        """Test get_optional_current_user with invalid token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid_token"
        )
        with patch("syfthub.auth.db_dependencies.verify_token", return_value=None):
            user = await get_optional_current_user(credentials, mock_user_repo)
            assert user is None

    @pytest.mark.asyncio
    async def test_get_optional_current_user_success(self, mock_user_repo, sample_user):
        """Test get_optional_current_user success case."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch(
            "syfthub.auth.db_dependencies.verify_token", return_value={"sub": "1"}
        ):
            user = await get_optional_current_user(credentials, mock_user_repo)
            assert user == sample_user
