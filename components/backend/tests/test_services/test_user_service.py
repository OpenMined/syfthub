"""Tests for UserService."""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from syfthub.database.connection import get_db_session
from syfthub.schemas.user import User, UserResponse, UserUpdate
from syfthub.services.user_service import UserService


@pytest.fixture
def db_session():
    """Get database session for testing."""
    session = next(get_db_session())
    yield session
    session.close()


@pytest.fixture
def user_service(db_session):
    """Create UserService instance for testing."""
    return UserService(db_session)


@pytest.fixture
def sample_user():
    """Sample user for testing."""
    return User(
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


@pytest.fixture
def admin_user():
    """Sample admin user for testing."""
    return User(
        id=2,
        username="admin",
        email="admin@example.com",
        full_name="Admin User",
        role="admin",
        is_active=True,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        age=30,
        password_hash="admin_hashed_pass",
    )


class TestUserServiceGetProfile:
    """Test user profile retrieval."""

    def test_get_user_profile_success(self, user_service, sample_user):
        """Test successful user profile retrieval."""
        with patch.object(
            user_service.user_repository, "get_by_id", return_value=sample_user
        ):
            result = user_service.get_user_profile(1)

            assert result is not None
            assert isinstance(result, UserResponse)
            assert result.id == 1
            assert result.username == "testuser"
            assert result.email == "test@example.com"

    def test_get_user_profile_not_found(self, user_service):
        """Test user profile not found."""
        with patch.object(user_service.user_repository, "get_by_id", return_value=None):
            result = user_service.get_user_profile(999)

            assert result is None

    def test_get_user_by_username_success(self, user_service, sample_user):
        """Test successful user retrieval by username."""
        with patch.object(
            user_service.user_repository, "get_by_username", return_value=sample_user
        ):
            result = user_service.get_user_by_username("testuser")

            assert result is not None
            assert isinstance(result, UserResponse)
            assert result.username == "testuser"

    def test_get_user_by_username_not_found(self, user_service):
        """Test user by username not found."""
        with patch.object(
            user_service.user_repository, "get_by_username", return_value=None
        ):
            result = user_service.get_user_by_username("nonexistent")

            assert result is None


class TestUserServiceGetUsersList:
    """Test users list retrieval."""

    def test_get_users_list_default(self, user_service, sample_user):
        """Test get users list with default parameters."""
        mock_users = [sample_user]
        with patch.object(
            user_service.user_repository, "get_all", return_value=mock_users
        ):
            result = user_service.get_users_list()

            assert len(result) == 1
            assert isinstance(result[0], UserResponse)
            assert result[0].username == "testuser"

    def test_get_users_list_with_pagination(self, user_service, sample_user):
        """Test get users list with pagination."""
        mock_users = [sample_user]
        with patch.object(
            user_service.user_repository, "get_all", return_value=mock_users
        ) as mock_get_all:
            result = user_service.get_users_list(skip=10, limit=5)

            mock_get_all.assert_called_once_with(
                skip=10, limit=5, filters={"is_active": True}
            )
            assert len(result) == 1

    def test_get_users_list_include_inactive(self, user_service, sample_user):
        """Test get users list including inactive users."""
        mock_users = [sample_user]
        with patch.object(
            user_service.user_repository, "get_all", return_value=mock_users
        ) as mock_get_all:
            result = user_service.get_users_list(active_only=False)

            mock_get_all.assert_called_once_with(skip=0, limit=10, filters=None)
            assert len(result) == 1


class TestUserServiceUpdateProfile:
    """Test user profile update."""

    def test_update_user_profile_own_profile(self, user_service, sample_user):
        """Test user updating their own profile."""
        update_data = UserUpdate(
            full_name="Updated Name", avatar_url="https://example.com/avatar.png"
        )
        user_dict = sample_user.model_dump()
        user_dict.update(
            {
                "full_name": "Updated Name",
                "avatar_url": "https://example.com/avatar.png",
            }
        )
        updated_user = User(**user_dict)

        with (
            patch.object(
                user_service.user_repository, "email_exists", return_value=False
            ),
            patch.object(
                user_service.user_repository, "update_user", return_value=updated_user
            ),
        ):
            result = user_service.update_user_profile(1, update_data, sample_user)

            assert isinstance(result, UserResponse)
            assert result.full_name == "Updated Name"
            assert result.avatar_url == "https://example.com/avatar.png"

    def test_update_user_profile_admin_updates_other(
        self, user_service, sample_user, admin_user
    ):
        """Test admin updating another user's profile."""
        update_data = UserUpdate(full_name="Admin Updated")
        user_dict = sample_user.model_dump()
        user_dict.update({"full_name": "Admin Updated"})
        updated_user = User(**user_dict)

        with (
            patch.object(
                user_service.user_repository, "email_exists", return_value=False
            ),
            patch.object(
                user_service.user_repository, "update_user", return_value=updated_user
            ),
        ):
            result = user_service.update_user_profile(1, update_data, admin_user)

            assert result.full_name == "Admin Updated"

    def test_update_user_profile_permission_denied(self, user_service, sample_user):
        """Test permission denied when updating another user's profile."""
        user_dict = sample_user.model_dump()
        user_dict.update({"id": 2, "username": "otheruser"})
        User(**user_dict)
        update_data = UserUpdate(full_name="Should Fail")

        with pytest.raises(HTTPException) as exc_info:
            user_service.update_user_profile(2, update_data, sample_user)

        assert exc_info.value.status_code == 403
        assert "Permission denied" in str(exc_info.value.detail)

    def test_update_user_profile_email_exists(self, user_service, sample_user):
        """Test updating with existing email."""
        update_data = UserUpdate(email="existing@example.com")
        user_dict = sample_user.model_dump()
        user_dict.update({"id": 3, "email": "existing@example.com"})
        existing_user = User(**user_dict)

        with (
            patch.object(
                user_service.user_repository, "email_exists", return_value=True
            ),
            patch.object(
                user_service.user_repository, "get_by_email", return_value=existing_user
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                user_service.update_user_profile(1, update_data, sample_user)

            assert exc_info.value.status_code == 400
            assert "Email already exists" in str(exc_info.value.detail)

    def test_update_user_profile_user_not_found(self, user_service, admin_user):
        """Test updating non-existent user."""
        update_data = UserUpdate(full_name="Updated")

        with (
            patch.object(
                user_service.user_repository, "email_exists", return_value=False
            ),
            patch.object(
                user_service.user_repository, "update_user", return_value=None
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                user_service.update_user_profile(999, update_data, admin_user)

            assert exc_info.value.status_code == 404
            assert "User not found" in str(exc_info.value.detail)


class TestUserServiceDeactivateUser:
    """Test user deactivation."""

    def test_deactivate_user_admin_success(self, user_service, admin_user):
        """Test admin successfully deactivating a user."""
        with patch.object(
            user_service.user_repository, "deactivate_user", return_value=True
        ):
            result = user_service.deactivate_user(1, admin_user)

            assert result is True

    def test_deactivate_user_not_admin(self, user_service, sample_user):
        """Test non-admin trying to deactivate user."""
        with pytest.raises(HTTPException) as exc_info:
            user_service.deactivate_user(2, sample_user)

        assert exc_info.value.status_code == 403
        assert "admin role required" in str(exc_info.value.detail)

    def test_deactivate_user_self_deactivation(self, user_service, admin_user):
        """Test admin trying to deactivate their own account."""
        with pytest.raises(HTTPException) as exc_info:
            user_service.deactivate_user(2, admin_user)

        assert exc_info.value.status_code == 400
        assert "Cannot deactivate your own account" in str(exc_info.value.detail)

    def test_deactivate_user_not_found(self, user_service, admin_user):
        """Test deactivating non-existent user."""
        with patch.object(
            user_service.user_repository, "deactivate_user", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                user_service.deactivate_user(999, admin_user)

            assert exc_info.value.status_code == 404
            assert "User not found" in str(exc_info.value.detail)


class TestUserServiceSearch:
    """Test user search functionality."""

    def test_search_users_success(self, user_service, sample_user):
        """Test successful user search."""
        mock_users = [sample_user]
        with patch.object(
            user_service.user_repository, "get_all", return_value=mock_users
        ):
            result = user_service.search_users("test")

            assert len(result) == 1
            assert result[0].username == "testuser"

    def test_search_users_no_matches(self, user_service, sample_user):
        """Test search with no matches."""
        mock_users = [sample_user]
        with patch.object(
            user_service.user_repository, "get_all", return_value=mock_users
        ):
            result = user_service.search_users("nomatch")

            assert len(result) == 0

    def test_search_users_limit(self, user_service, sample_user):
        """Test search respects limit."""
        # Create multiple users
        mock_users = []
        for i in range(1, 6):
            user_data = sample_user.model_dump()
            user_data.update({"id": i, "username": f"test{i}"})
            mock_users.append(User(**user_data))

        with patch.object(
            user_service.user_repository, "get_all", return_value=mock_users
        ):
            result = user_service.search_users("test", limit=3)

            assert len(result) == 3


class TestUserServiceStats:
    """Test user statistics."""

    def test_get_user_stats_success(self, user_service, sample_user):
        """Test getting user statistics."""
        with patch.object(
            user_service.user_repository, "get_by_id", return_value=sample_user
        ):
            result = user_service.get_user_stats(1)

            assert result["user_id"] == 1
            assert result["username"] == "testuser"
            assert result["is_active"] is True
            assert "endpoints_count" in result
            assert "organizations_count" in result

    def test_get_user_stats_not_found(self, user_service):
        """Test getting stats for non-existent user."""
        with patch.object(user_service.user_repository, "get_by_id", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                user_service.get_user_stats(999)

            assert exc_info.value.status_code == 404


class TestUserServiceAvailability:
    """Test username and email availability."""

    def test_username_available_true(self, user_service):
        """Test username is available."""
        with patch.object(
            user_service.user_repository, "username_exists", return_value=False
        ):
            result = user_service.username_available("newuser")

            assert result is True

    def test_username_available_false(self, user_service):
        """Test username is not available."""
        with patch.object(
            user_service.user_repository, "username_exists", return_value=True
        ):
            result = user_service.username_available("existinguser")

            assert result is False

    def test_email_available_true(self, user_service):
        """Test email is available."""
        with patch.object(
            user_service.user_repository, "email_exists", return_value=False
        ):
            result = user_service.email_available("new@example.com")

            assert result is True

    def test_email_available_false(self, user_service):
        """Test email is not available."""
        with patch.object(
            user_service.user_repository, "email_exists", return_value=True
        ):
            result = user_service.email_available("existing@example.com")

            assert result is False
