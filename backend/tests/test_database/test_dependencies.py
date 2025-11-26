"""Tests for database dependencies."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from syfthub.auth.db_dependencies import (
    get_current_active_user,
    get_current_user,
    get_optional_current_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
)
from syfthub.repositories import UserRepository
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import User


class TestUserDependencies:
    """Tests for user dependency functions."""

    def test_get_user_by_id(self, test_session: Session, sample_user_data: dict):
        """Test get_user_by_id dependency."""
        # Create user
        user_repo = UserRepository(test_session)
        created_user = user_repo.create(sample_user_data)

        # Test dependency
        result = get_user_by_id(created_user.id, user_repo)
        assert result is not None
        assert result.id == created_user.id
        assert result.username == "testuser"

    def test_get_user_by_id_not_found(self, test_session: Session):
        """Test get_user_by_id with non-existent ID."""
        user_repo = UserRepository(test_session)
        result = get_user_by_id(999, user_repo)
        assert result is None

    def test_get_user_by_username(self, test_session: Session, sample_user_data: dict):
        """Test get_user_by_username dependency."""
        # Create user
        user_repo = UserRepository(test_session)
        user_repo.create(sample_user_data)

        # Test dependency
        result = get_user_by_username("testuser", user_repo)
        assert result is not None
        assert result.username == "testuser"

    def test_get_user_by_email(self, test_session: Session, sample_user_data: dict):
        """Test get_user_by_email dependency."""
        # Create user
        user_repo = UserRepository(test_session)
        user_repo.create(sample_user_data)

        # Test dependency
        result = get_user_by_email("test@example.com", user_repo)
        assert result is not None
        assert result.email == "test@example.com"


class TestAuthenticationDependencies:
    """Tests for authentication dependency functions."""

    @pytest.fixture
    def mock_user(self) -> User:
        """Mock user for testing."""
        from tests.test_utils import get_test_user_data

        user_data = get_test_user_data(
            {
                "id": 1,
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "age": 25,
                "role": UserRole.USER,
                "password_hash": "hashed_password",
                "is_active": True,
            }
        )
        return User(**user_data)

    @pytest.mark.asyncio
    async def test_get_current_user_success(
        self, test_session: Session, mock_user: User
    ):
        """Test successful authentication."""
        user_repo = UserRepository(test_session)

        # Mock credentials
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )

        # Mock token verification and user repository
        with patch("syfthub.auth.db_dependencies.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": "1", "type": "access"}

            # Create the user in the database
            user_data = {
                "id": mock_user.id,
                "username": mock_user.username,
                "email": mock_user.email,
                "full_name": mock_user.full_name,
                "age": mock_user.age,
                "role": mock_user.role.value,
                "password_hash": mock_user.password_hash,
                "public_key": mock_user.public_key,
                "is_active": mock_user.is_active,
                "created_at": mock_user.created_at,
                "updated_at": mock_user.updated_at,
                "key_created_at": mock_user.key_created_at,
            }
            created_user = user_repo.create(user_data)

            result = await get_current_user(credentials, user_repo)
            assert result.id == created_user.id
            assert result.username == "testuser"

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self, test_session: Session):
        """Test authentication with no credentials."""
        user_repo = UserRepository(test_session)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None, user_repo)

        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, test_session: Session):
        """Test authentication with invalid token."""
        user_repo = UserRepository(test_session)

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid_token"
        )

        with patch("syfthub.auth.db_dependencies.verify_token") as mock_verify:
            mock_verify.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials, user_repo)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self, test_session: Session):
        """Test authentication when user doesn't exist in database."""
        user_repo = UserRepository(test_session)

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )

        with patch("syfthub.auth.db_dependencies.verify_token") as mock_verify:
            mock_verify.return_value = {
                "sub": "999",
                "type": "access",
            }  # Non-existent user

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials, user_repo)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_active_user_success(self, mock_user: User):
        """Test getting active user when user is active."""
        result = await get_current_active_user(mock_user)
        assert result.id == mock_user.id
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_get_current_active_user_inactive(self, mock_user: User):
        """Test getting active user when user is inactive."""
        mock_user.is_active = False

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(mock_user)

        assert exc_info.value.status_code == 400
        assert "Inactive user" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_optional_current_user_success(
        self, test_session: Session, mock_user: User
    ):
        """Test optional authentication with valid credentials."""
        user_repo = UserRepository(test_session)

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )

        with patch("syfthub.auth.db_dependencies.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": "1", "type": "access"}

            # Create user in database
            user_data = {
                "id": mock_user.id,
                "username": mock_user.username,
                "email": mock_user.email,
                "full_name": mock_user.full_name,
                "age": mock_user.age,
                "role": mock_user.role.value,
                "password_hash": mock_user.password_hash,
                "public_key": mock_user.public_key,
                "is_active": mock_user.is_active,
                "created_at": mock_user.created_at,
                "updated_at": mock_user.updated_at,
                "key_created_at": mock_user.key_created_at,
            }
            created_user = user_repo.create(user_data)

            result = await get_optional_current_user(credentials, user_repo)
            assert result is not None
            assert result.id == created_user.id

    @pytest.mark.asyncio
    async def test_get_optional_current_user_no_credentials(
        self, test_session: Session
    ):
        """Test optional authentication with no credentials."""
        user_repo = UserRepository(test_session)

        result = await get_optional_current_user(None, user_repo)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_optional_current_user_invalid_token(self, test_session: Session):
        """Test optional authentication with invalid token."""
        user_repo = UserRepository(test_session)

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid_token"
        )

        with patch("syfthub.auth.db_dependencies.verify_token") as mock_verify:
            mock_verify.return_value = None

            result = await get_optional_current_user(credentials, user_repo)
            assert result is None
