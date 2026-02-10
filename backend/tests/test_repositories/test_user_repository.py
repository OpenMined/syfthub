"""Tests for user repository."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import User, UserCreate, UserUpdate


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return Mock()


@pytest.fixture
def user_repo(mock_session):
    """Create a user repository with mock session."""
    return UserRepository(mock_session)


@pytest.fixture
def mock_user_model():
    """Create a mock user model."""
    return Mock(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        password_hash="hashed_password",
        is_active=True,
        role="user",
        accounting_service_url="https://ledger.example.com",
        accounting_api_token="at_token123",
        accounting_account_id="acc-uuid-123",
        auth_provider="local",
        google_id=None,
        avatar_url=None,
        domain=None,
        aggregator_url=None,
        last_heartbeat_at=None,
        heartbeat_expires_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestUserRepositoryGetByUsername:
    """Tests for get_by_username method."""

    def test_get_by_username_success(self, user_repo, mock_session, mock_user_model):
        """Test successful retrieval by username."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_model
        mock_session.execute.return_value = mock_result

        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            result = user_repo.get_by_username("testuser")

        assert result is not None
        mock_session.execute.assert_called_once()

    def test_get_by_username_not_found(self, user_repo, mock_session):
        """Test retrieval when user not found."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = user_repo.get_by_username("nonexistent")

        assert result is None

    def test_get_by_username_exception(self, user_repo, mock_session):
        """Test exception handling."""
        mock_session.execute.side_effect = Exception("Database error")

        result = user_repo.get_by_username("testuser")

        assert result is None


class TestUserRepositoryGetByEmail:
    """Tests for get_by_email method."""

    def test_get_by_email_success(self, user_repo, mock_session, mock_user_model):
        """Test successful retrieval by email."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_model
        mock_session.execute.return_value = mock_result

        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            result = user_repo.get_by_email("test@example.com")

        assert result is not None

    def test_get_by_email_not_found(self, user_repo, mock_session):
        """Test retrieval when user not found."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = user_repo.get_by_email("nonexistent@example.com")

        assert result is None

    def test_get_by_email_exception(self, user_repo, mock_session):
        """Test exception handling."""
        mock_session.execute.side_effect = Exception("Database error")

        result = user_repo.get_by_email("test@example.com")

        assert result is None


class TestUserRepositoryGetByGoogleId:
    """Tests for get_by_google_id method."""

    def test_get_by_google_id_success(self, user_repo, mock_session, mock_user_model):
        """Test successful retrieval by Google ID."""
        mock_user_model.google_id = "google-123"
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_user_model
        mock_session.execute.return_value = mock_result

        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            result = user_repo.get_by_google_id("google-123")

        assert result is not None

    def test_get_by_google_id_not_found(self, user_repo, mock_session):
        """Test retrieval when user not found."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = user_repo.get_by_google_id("nonexistent")

        assert result is None

    def test_get_by_google_id_exception(self, user_repo, mock_session):
        """Test exception handling."""
        mock_session.execute.side_effect = Exception("Database error")

        result = user_repo.get_by_google_id("google-123")

        assert result is None


class TestUserRepositoryCreateUser:
    """Tests for create_user method."""

    def test_create_user_success(self, user_repo, mock_session):
        """Test successful user creation."""
        user_data = Mock(spec=UserCreate)
        user_data.username = "newuser"
        user_data.email = "new@example.com"
        user_data.full_name = "New User"

        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            user_repo.create_user(
                user_data=user_data,
                password_hash="hashed_password",
                accounting_service_url="https://ledger.example.com",
                accounting_api_token="at_token",
                accounting_account_id="acc-123",
                auth_provider="local",
            )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    def test_create_user_exception(self, user_repo, mock_session):
        """Test exception handling during creation."""
        user_data = Mock(spec=UserCreate)
        user_data.username = "newuser"
        user_data.email = "new@example.com"
        user_data.full_name = "New User"

        mock_session.add.side_effect = Exception("Database error")

        result = user_repo.create_user(user_data=user_data, password_hash="hash")

        assert result is None
        mock_session.rollback.assert_called_once()


class TestUserRepositoryUpdateUser:
    """Tests for update_user method."""

    def test_update_user_success(self, user_repo, mock_session, mock_user_model):
        """Test successful user update."""
        mock_session.get.return_value = mock_user_model

        user_update = Mock(spec=UserUpdate)
        user_update.username = "newusername"
        user_update.email = "newemail@example.com"
        user_update.full_name = "New Name"
        user_update.avatar_url = "https://example.com/avatar.png"
        user_update.is_active = True
        user_update.accounting_service_url = "https://new-ledger.example.com"
        user_update.accounting_api_token = "at_new_token"
        user_update.accounting_account_id = "new-acc-123"
        user_update.domain = "example.com"
        user_update.aggregator_url = "https://aggregator.example.com"

        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            user_repo.update_user(1, user_update)

        assert mock_session.commit.called

    def test_update_user_not_found(self, user_repo, mock_session):
        """Test update when user not found."""
        mock_session.get.return_value = None

        user_update = Mock(spec=UserUpdate)
        user_update.username = "newusername"

        result = user_repo.update_user(999, user_update)

        assert result is None

    def test_update_user_exception(self, user_repo, mock_session, mock_user_model):
        """Test exception handling during update."""
        mock_session.get.return_value = mock_user_model
        mock_session.commit.side_effect = Exception("Database error")

        user_update = Mock(spec=UserUpdate)
        user_update.username = "newusername"
        user_update.email = None
        user_update.full_name = None
        user_update.avatar_url = None
        user_update.is_active = None
        user_update.accounting_service_url = None
        user_update.accounting_api_token = None
        user_update.accounting_account_id = None
        user_update.domain = None
        user_update.aggregator_url = None

        result = user_repo.update_user(1, user_update)

        assert result is None
        mock_session.rollback.assert_called_once()


class TestUserRepositoryUpdatePassword:
    """Tests for update_password method."""

    def test_update_password_success(self, user_repo, mock_session, mock_user_model):
        """Test successful password update."""
        mock_session.get.return_value = mock_user_model

        result = user_repo.update_password(1, "new_hashed_password")

        assert result is True
        mock_session.commit.assert_called_once()

    def test_update_password_not_found(self, user_repo, mock_session):
        """Test password update when user not found."""
        mock_session.get.return_value = None

        result = user_repo.update_password(999, "new_hashed_password")

        assert result is False

    def test_update_password_exception(self, user_repo, mock_session, mock_user_model):
        """Test exception handling during password update."""
        mock_session.get.return_value = mock_user_model
        mock_session.commit.side_effect = Exception("Database error")

        result = user_repo.update_password(1, "new_hashed_password")

        assert result is False
        mock_session.rollback.assert_called_once()


class TestUserRepositoryLinkGoogleAccount:
    """Tests for link_google_account method."""

    def test_link_google_account_success(
        self, user_repo, mock_session, mock_user_model
    ):
        """Test successful Google account linking."""
        mock_user_model.avatar_url = None
        mock_session.get.return_value = mock_user_model

        result = user_repo.link_google_account(
            1, "google-123", "https://example.com/avatar.png"
        )

        assert result is True
        assert mock_user_model.google_id == "google-123"
        mock_session.commit.assert_called_once()

    def test_link_google_account_without_avatar(
        self, user_repo, mock_session, mock_user_model
    ):
        """Test linking without avatar when user already has one."""
        mock_user_model.avatar_url = "https://existing.com/avatar.png"
        mock_session.get.return_value = mock_user_model

        result = user_repo.link_google_account(
            1, "google-123", "https://new.com/avatar.png"
        )

        assert result is True
        assert mock_user_model.avatar_url == "https://existing.com/avatar.png"

    def test_link_google_account_not_found(self, user_repo, mock_session):
        """Test linking when user not found."""
        mock_session.get.return_value = None

        result = user_repo.link_google_account(999, "google-123")

        assert result is False

    def test_link_google_account_exception(
        self, user_repo, mock_session, mock_user_model
    ):
        """Test exception handling during linking."""
        mock_session.get.return_value = mock_user_model
        mock_session.commit.side_effect = Exception("Database error")

        result = user_repo.link_google_account(1, "google-123")

        assert result is False
        mock_session.rollback.assert_called_once()


class TestUserRepositoryUpdateUserRole:
    """Tests for update_user_role method."""

    def test_update_user_role_success(self, user_repo, mock_session, mock_user_model):
        """Test successful role update."""
        mock_session.get.return_value = mock_user_model

        result = user_repo.update_user_role(1, "admin")

        assert result is True
        assert mock_user_model.role == "admin"
        mock_session.commit.assert_called_once()

    def test_update_user_role_not_found(self, user_repo, mock_session):
        """Test role update when user not found."""
        mock_session.get.return_value = None

        result = user_repo.update_user_role(999, "admin")

        assert result is False

    def test_update_user_role_exception(self, user_repo, mock_session, mock_user_model):
        """Test exception handling during role update."""
        mock_session.get.return_value = mock_user_model
        mock_session.commit.side_effect = Exception("Database error")

        result = user_repo.update_user_role(1, "admin")

        assert result is False
        mock_session.rollback.assert_called_once()


class TestUserRepositoryDeactivateUser:
    """Tests for deactivate_user method."""

    def test_deactivate_user_success(self, user_repo, mock_session, mock_user_model):
        """Test successful user deactivation."""
        mock_session.get.return_value = mock_user_model

        result = user_repo.deactivate_user(1)

        assert result is True
        assert mock_user_model.is_active is False
        mock_session.commit.assert_called_once()

    def test_deactivate_user_not_found(self, user_repo, mock_session):
        """Test deactivation when user not found."""
        mock_session.get.return_value = None

        result = user_repo.deactivate_user(999)

        assert result is False

    def test_deactivate_user_exception(self, user_repo, mock_session, mock_user_model):
        """Test exception handling during deactivation."""
        mock_session.get.return_value = mock_user_model
        mock_session.commit.side_effect = Exception("Database error")

        result = user_repo.deactivate_user(1)

        assert result is False
        mock_session.rollback.assert_called_once()


class TestUserRepositoryActivateUser:
    """Tests for activate_user method."""

    def test_activate_user_success(self, user_repo, mock_session, mock_user_model):
        """Test successful user activation."""
        mock_user_model.is_active = False
        mock_session.get.return_value = mock_user_model

        result = user_repo.activate_user(1)

        assert result is True
        assert mock_user_model.is_active is True
        mock_session.commit.assert_called_once()

    def test_activate_user_not_found(self, user_repo, mock_session):
        """Test activation when user not found."""
        mock_session.get.return_value = None

        result = user_repo.activate_user(999)

        assert result is False

    def test_activate_user_exception(self, user_repo, mock_session, mock_user_model):
        """Test exception handling during activation."""
        mock_session.get.return_value = mock_user_model
        mock_session.commit.side_effect = Exception("Database error")

        result = user_repo.activate_user(1)

        assert result is False
        mock_session.rollback.assert_called_once()


class TestUserRepositoryUpdateHeartbeat:
    """Tests for update_heartbeat method."""

    def test_update_heartbeat_success(self, user_repo, mock_session, mock_user_model):
        """Test successful heartbeat update."""
        mock_session.get.return_value = mock_user_model
        now = datetime.now(timezone.utc)
        expires = datetime.now(timezone.utc)

        result = user_repo.update_heartbeat(1, "example.com", now, expires)

        assert result is True
        assert mock_user_model.domain == "example.com"
        mock_session.commit.assert_called_once()

    def test_update_heartbeat_not_found(self, user_repo, mock_session):
        """Test heartbeat update when user not found."""
        mock_session.get.return_value = None
        now = datetime.now(timezone.utc)
        expires = datetime.now(timezone.utc)

        result = user_repo.update_heartbeat(999, "example.com", now, expires)

        assert result is False

    def test_update_heartbeat_exception(self, user_repo, mock_session, mock_user_model):
        """Test exception handling during heartbeat update."""
        mock_session.get.return_value = mock_user_model
        mock_session.commit.side_effect = SQLAlchemyError("Database error")
        now = datetime.now(timezone.utc)
        expires = datetime.now(timezone.utc)

        result = user_repo.update_heartbeat(1, "example.com", now, expires)

        assert result is False
        mock_session.rollback.assert_called_once()


class TestUserRepositoryDelete:
    """Tests for delete method."""

    def test_delete_success(self, user_repo, mock_session, mock_user_model):
        """Test successful user deletion."""
        mock_session.get.return_value = mock_user_model

        result = user_repo.delete(1)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_user_model)
        mock_session.commit.assert_called_once()

    def test_delete_not_found(self, user_repo, mock_session):
        """Test deletion when user not found."""
        mock_session.get.return_value = None

        result = user_repo.delete(999)

        assert result is False

    def test_delete_exception(self, user_repo, mock_session, mock_user_model):
        """Test exception handling during deletion."""
        mock_session.get.return_value = mock_user_model
        mock_session.delete.side_effect = Exception("Database error")

        result = user_repo.delete(1)

        assert result is False
        mock_session.rollback.assert_called_once()


class TestUserRepositoryCreate:
    """Tests for create method."""

    def test_create_with_data_dict(self, user_repo, mock_session):
        """Test create with data dictionary."""
        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            user_repo.create(data={"username": "testuser", "email": "test@example.com"})

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_create_with_kwargs(self, user_repo, mock_session):
        """Test create with keyword arguments."""
        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            user_repo.create(username="testuser", email="test@example.com")

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_create_exception(self, user_repo, mock_session):
        """Test exception handling during create."""
        mock_session.add.side_effect = Exception("Database error")

        result = user_repo.create(username="testuser", email="test@example.com")

        assert result is None
        mock_session.rollback.assert_called_once()


class TestUserRepositoryGetAll:
    """Tests for get_all method."""

    def test_get_all_success(self, user_repo, mock_session, mock_user_model):
        """Test successful retrieval of all users."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = [mock_user_model]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            result = user_repo.get_all()

        assert len(result) == 1

    def test_get_all_exception(self, user_repo, mock_session):
        """Test exception handling during get_all."""
        mock_session.execute.side_effect = Exception("Database error")

        result = user_repo.get_all()

        assert result == []


class TestUserRepositoryUpdate:
    """Tests for update method."""

    def test_update_with_data_dict(self, user_repo, mock_session, mock_user_model):
        """Test update with data dictionary."""
        mock_session.get.return_value = mock_user_model

        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            user_repo.update(1, data={"username": "newname"})

        mock_session.commit.assert_called_once()

    def test_update_with_kwargs(self, user_repo, mock_session, mock_user_model):
        """Test update with keyword arguments."""
        mock_session.get.return_value = mock_user_model

        with patch.object(User, "model_validate", return_value=Mock(spec=User)):
            user_repo.update(1, username="newname")

        mock_session.commit.assert_called_once()

    def test_update_not_found(self, user_repo, mock_session):
        """Test update when user not found."""
        mock_session.get.return_value = None

        result = user_repo.update(999, username="newname")

        assert result is None

    def test_update_exception(self, user_repo, mock_session, mock_user_model):
        """Test exception handling during update."""
        mock_session.get.return_value = mock_user_model
        mock_session.commit.side_effect = Exception("Database error")

        result = user_repo.update(1, username="newname")

        assert result is None
        mock_session.rollback.assert_called_once()


class TestUserRepositoryHelperMethods:
    """Tests for helper methods."""

    def test_username_exists(self, user_repo):
        """Test username_exists method."""
        with patch.object(user_repo, "exists", return_value=True):
            result = user_repo.username_exists("testuser")

        assert result is True

    def test_email_exists(self, user_repo):
        """Test email_exists method."""
        with patch.object(user_repo, "exists", return_value=True):
            result = user_repo.email_exists("test@example.com")

        assert result is True

    def test_exists_username_alias(self, user_repo):
        """Test exists_username alias method."""
        with patch.object(user_repo, "username_exists", return_value=True):
            result = user_repo.exists_username("testuser")

        assert result is True

    def test_exists_email_alias(self, user_repo):
        """Test exists_email alias method."""
        with patch.object(user_repo, "email_exists", return_value=True):
            result = user_repo.exists_email("test@example.com")

        assert result is True

    def test_count(self, user_repo, mock_session):
        """Test count method."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = [Mock(), Mock()]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = user_repo.count()

        assert result == 2
