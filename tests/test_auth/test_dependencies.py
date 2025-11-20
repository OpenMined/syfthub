"""Tests for auth dependencies."""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from syfthub.auth.dependencies import (
    OwnershipChecker,
    RoleChecker,
    fake_users_db,
    get_current_active_user,
    get_current_user,
    get_optional_current_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    username_to_id,
)
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
def setup_fake_db(sample_user):
    """Setup fake database for testing."""
    fake_users_db.clear()
    username_to_id.clear()
    fake_users_db[sample_user.id] = sample_user
    username_to_id[sample_user.username] = sample_user.id
    yield
    fake_users_db.clear()
    username_to_id.clear()


class TestUserHelperFunctions:
    """Test user helper functions."""

    def test_get_user_by_id_found(self, setup_fake_db, sample_user):
        """Test getting user by ID when found."""
        user = get_user_by_id(sample_user.id)
        assert user == sample_user

    def test_get_user_by_id_not_found(self, setup_fake_db):
        """Test getting user by ID when not found."""
        user = get_user_by_id(999)
        assert user is None

    def test_get_user_by_username_found(self, setup_fake_db, sample_user):
        """Test getting user by username when found."""
        user = get_user_by_username(sample_user.username)
        assert user == sample_user

    def test_get_user_by_username_not_found(self, setup_fake_db):
        """Test getting user by username when not found."""
        user = get_user_by_username("nonexistent")
        assert user is None

    def test_get_user_by_email_found(self, setup_fake_db, sample_user):
        """Test getting user by email when found."""
        user = get_user_by_email(sample_user.email)
        assert user == sample_user

    def test_get_user_by_email_not_found(self, setup_fake_db):
        """Test getting user by email when not found."""
        user = get_user_by_email("nonexistent@example.com")
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
    async def test_get_current_user_no_credentials(self, setup_fake_db):
        """Test get_current_user with no credentials."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, setup_fake_db):
        """Test get_current_user with invalid token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid_token"
        )
        with patch("syfthub.auth.dependencies.verify_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_no_sub_claim(self, setup_fake_db):
        """Test get_current_user with token missing sub claim."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch("syfthub.auth.dependencies.verify_token", return_value={}):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_user_id(self, setup_fake_db):
        """Test get_current_user with invalid user ID in token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch(
            "syfthub.auth.dependencies.verify_token", return_value={"sub": "invalid"}
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self, setup_fake_db):
        """Test get_current_user with user not found in database."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch(
            "syfthub.auth.dependencies.verify_token", return_value={"sub": "999"}
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, setup_fake_db, sample_user):
        """Test get_current_user success case."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch("syfthub.auth.dependencies.verify_token", return_value={"sub": "1"}):
            user = await get_current_user(credentials)
            assert user == sample_user

    @pytest.mark.asyncio
    async def test_get_current_active_user_inactive(self, setup_fake_db):
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
    async def test_get_current_active_user_success(self, setup_fake_db, sample_user):
        """Test get_current_active_user success case."""
        user = await get_current_active_user(sample_user)
        assert user == sample_user

    @pytest.mark.asyncio
    async def test_get_optional_current_user_no_credentials(self, setup_fake_db):
        """Test get_optional_current_user with no credentials."""
        user = await get_optional_current_user(None)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_optional_current_user_invalid_token(self, setup_fake_db):
        """Test get_optional_current_user with invalid token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid_token"
        )
        with patch("syfthub.auth.dependencies.verify_token", return_value=None):
            user = await get_optional_current_user(credentials)
            assert user is None

    @pytest.mark.asyncio
    async def test_get_optional_current_user_success(self, setup_fake_db, sample_user):
        """Test get_optional_current_user success case."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )
        with patch("syfthub.auth.dependencies.verify_token", return_value={"sub": "1"}):
            user = await get_optional_current_user(credentials)
            assert user == sample_user
