"""Tests for repository classes."""

from sqlalchemy.orm import Session

from syfthub.repositories import (
    DatasiteRepository,
    UserRepository,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.datasite import DatasiteVisibility


class TestUserRepository:
    """Tests for UserRepository."""

    def test_create_user(self, test_session: Session, sample_user_data: dict):
        """Test creating a user through repository."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.age == 25
        assert user.role == UserRole.USER
        assert user.is_active is True

    def test_get_user_by_id(self, test_session: Session, sample_user_data: dict):
        """Test getting user by ID."""
        user_repo = UserRepository(test_session)
        created_user = user_repo.create(sample_user_data)

        retrieved_user = user_repo.get_by_id(created_user.id)
        assert retrieved_user is not None
        assert retrieved_user.id == created_user.id
        assert retrieved_user.username == "testuser"

    def test_get_user_by_id_not_found(self, test_session: Session):
        """Test getting user by non-existent ID."""
        user_repo = UserRepository(test_session)
        user = user_repo.get_by_id(999)
        assert user is None

    def test_get_user_by_username(self, test_session: Session, sample_user_data: dict):
        """Test getting user by username."""
        user_repo = UserRepository(test_session)
        user_repo.create(sample_user_data)

        retrieved_user = user_repo.get_by_username("testuser")
        assert retrieved_user is not None
        assert retrieved_user.username == "testuser"

    def test_get_user_by_username_case_insensitive(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test getting user by username is case insensitive."""
        user_repo = UserRepository(test_session)
        user_repo.create(sample_user_data)

        retrieved_user = user_repo.get_by_username("TESTUSER")
        assert retrieved_user is not None
        assert retrieved_user.username == "testuser"

    def test_get_user_by_email(self, test_session: Session, sample_user_data: dict):
        """Test getting user by email."""
        user_repo = UserRepository(test_session)
        user_repo.create(sample_user_data)

        retrieved_user = user_repo.get_by_email("test@example.com")
        assert retrieved_user is not None
        assert retrieved_user.email == "test@example.com"

    def test_get_all_users(self, test_session: Session, sample_user_data: dict):
        """Test getting all users."""
        user_repo = UserRepository(test_session)

        from tests.test_utils import generate_unique_test_keys

        # Create multiple users with unique keys
        user1_data = sample_user_data.copy()
        user2_data = sample_user_data.copy()
        user2_data["username"] = "testuser2"
        user2_data["email"] = "test2@example.com"
        unique_keys_2 = generate_unique_test_keys()
        user2_data["public_key"] = unique_keys_2["public_key"]

        user_repo.create(user1_data)
        user_repo.create(user2_data)

        all_users = user_repo.get_all()
        assert len(all_users) == 2
        usernames = [user.username for user in all_users]
        assert "testuser" in usernames
        assert "testuser2" in usernames

    def test_update_user(self, test_session: Session, sample_user_data: dict):
        """Test updating a user."""
        user_repo = UserRepository(test_session)
        created_user = user_repo.create(sample_user_data)

        update_data = {"full_name": "Updated Name", "age": 30}
        updated_user = user_repo.update(created_user.id, update_data)

        assert updated_user is not None
        assert updated_user.full_name == "Updated Name"
        assert updated_user.age == 30
        assert updated_user.username == "testuser"  # Unchanged

    def test_update_user_not_found(self, test_session: Session):
        """Test updating non-existent user."""
        user_repo = UserRepository(test_session)
        result = user_repo.update(999, {"full_name": "New Name"})
        assert result is None

    def test_delete_user(self, test_session: Session, sample_user_data: dict):
        """Test deleting a user."""
        user_repo = UserRepository(test_session)
        created_user = user_repo.create(sample_user_data)

        result = user_repo.delete(created_user.id)
        assert result is True

        # Verify user is deleted
        retrieved_user = user_repo.get_by_id(created_user.id)
        assert retrieved_user is None

    def test_delete_user_not_found(self, test_session: Session):
        """Test deleting non-existent user."""
        user_repo = UserRepository(test_session)
        result = user_repo.delete(999)
        assert result is False

    def test_exists_username(self, test_session: Session, sample_user_data: dict):
        """Test checking if username exists."""
        user_repo = UserRepository(test_session)
        user_repo.create(sample_user_data)

        assert user_repo.exists_username("testuser") is True
        assert user_repo.exists_username("nonexistent") is False

    def test_exists_email(self, test_session: Session, sample_user_data: dict):
        """Test checking if email exists."""
        user_repo = UserRepository(test_session)
        user_repo.create(sample_user_data)

        assert user_repo.exists_email("test@example.com") is True
        assert user_repo.exists_email("nonexistent@example.com") is False


class TestDatasiteRepository:
    """Tests for DatasiteRepository."""

    def test_create_datasite(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test creating a datasite through repository."""
        # Create user first
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        # Create datasite
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite_repo = DatasiteRepository(test_session)
        datasite = datasite_repo.create(datasite_data)

        assert datasite.id is not None
        assert datasite.user_id == user.id
        assert datasite.name == "Test Datasite"
        assert datasite.slug == "test-datasite"
        assert datasite.description == "A test datasite"
        assert datasite.visibility == DatasiteVisibility.PUBLIC
        assert datasite.is_active is True

    def test_get_datasite_by_user_and_slug(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting datasite by user ID and slug."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id

        datasite_repo = DatasiteRepository(test_session)
        created_datasite = datasite_repo.create(datasite_data)

        # Test
        retrieved_datasite = datasite_repo.get_by_user_and_slug(
            user.id, "test-datasite"
        )
        assert retrieved_datasite is not None
        assert retrieved_datasite.id == created_datasite.id
        assert retrieved_datasite.slug == "test-datasite"

    def test_get_datasites_by_user_id(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting datasites by user ID."""
        # Create two users
        user_repo = UserRepository(test_session)
        user1 = user_repo.create(sample_user_data)

        from tests.test_utils import generate_unique_test_keys

        user2_data = sample_user_data.copy()
        user2_data["username"] = "testuser2"
        user2_data["email"] = "test2@example.com"
        unique_keys_2 = generate_unique_test_keys()
        user2_data["public_key"] = unique_keys_2["public_key"]
        user2 = user_repo.create(user2_data)

        # Create datasites for both users
        datasite_repo = DatasiteRepository(test_session)

        # Datasites for user1
        for i in range(3):
            datasite_data = sample_datasite_data.copy()
            datasite_data["user_id"] = user1.id
            datasite_data["name"] = f"User1 Datasite {i}"
            datasite_data["slug"] = f"user1-datasite-{i}"
            datasite_repo.create(datasite_data)

        # Datasites for user2
        for i in range(2):
            datasite_data = sample_datasite_data.copy()
            datasite_data["user_id"] = user2.id
            datasite_data["name"] = f"User2 Datasite {i}"
            datasite_data["slug"] = f"user2-datasite-{i}"
            datasite_repo.create(datasite_data)

        # Test getting datasites by user
        user1_datasites = datasite_repo.get_by_user_id(user1.id)
        user2_datasites = datasite_repo.get_by_user_id(user2.id)

        assert len(user1_datasites) == 3
        assert len(user2_datasites) == 2
        assert all("User1" in ds.name for ds in user1_datasites)
        assert all("User2" in ds.name for ds in user2_datasites)

    def test_get_public_datasites_by_user_id(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting only public datasites by user ID."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create public datasite
        public_data = sample_datasite_data.copy()
        public_data["user_id"] = user.id
        public_data["visibility"] = DatasiteVisibility.PUBLIC.value
        public_data["slug"] = "public-datasite"
        datasite_repo.create(public_data)

        # Create private datasite
        private_data = sample_datasite_data.copy()
        private_data["user_id"] = user.id
        private_data["visibility"] = DatasiteVisibility.PRIVATE.value
        private_data["slug"] = "private-datasite"
        datasite_repo.create(private_data)

        # Create inactive public datasite
        inactive_data = sample_datasite_data.copy()
        inactive_data["user_id"] = user.id
        inactive_data["visibility"] = DatasiteVisibility.PUBLIC.value
        inactive_data["is_active"] = False
        inactive_data["slug"] = "inactive-datasite"
        datasite_repo.create(inactive_data)

        # Test getting only public active datasites
        public_datasites = datasite_repo.get_public_by_user_id(user.id)

        assert len(public_datasites) == 1
        assert public_datasites[0].slug == "public-datasite"
        assert public_datasites[0].visibility == DatasiteVisibility.PUBLIC

    def test_slug_exists_for_user(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test checking if slug exists for user."""
        # Create two users
        user_repo = UserRepository(test_session)
        user1 = user_repo.create(sample_user_data)

        from tests.test_utils import generate_unique_test_keys

        user2_data = sample_user_data.copy()
        user2_data["username"] = "testuser2"
        user2_data["email"] = "test2@example.com"
        unique_keys_2 = generate_unique_test_keys()
        user2_data["public_key"] = unique_keys_2["public_key"]
        user2 = user_repo.create(user2_data)

        # Create datasite for user1
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user1.id
        datasite_repo = DatasiteRepository(test_session)
        datasite_repo.create(datasite_data)

        # Test slug existence
        assert datasite_repo.slug_exists_for_user(user1.id, "test-datasite") is True
        assert datasite_repo.slug_exists_for_user(user1.id, "nonexistent-slug") is False
        assert datasite_repo.slug_exists_for_user(user2.id, "test-datasite") is False

    def test_update_datasite(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test updating a datasite."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id

        datasite_repo = DatasiteRepository(test_session)
        created_datasite = datasite_repo.create(datasite_data)

        # Test update
        update_data = {
            "name": "Updated Datasite",
            "visibility": DatasiteVisibility.PRIVATE.value,
        }
        updated_datasite = datasite_repo.update(created_datasite.id, update_data)

        assert updated_datasite is not None
        assert updated_datasite.name == "Updated Datasite"
        assert updated_datasite.visibility == DatasiteVisibility.PRIVATE
        assert updated_datasite.slug == "test-datasite"  # Unchanged

    def test_datasite_with_connect_field(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test creating and retrieving datasite with connect field."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        # Create datasite with connect configurations
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite_data["connect"] = [
            {
                "type": "http",
                "enabled": True,
                "description": "HTTP API connection",
                "config": {"url": "https://api.example.com", "auth_required": False},
            },
            {
                "type": "webrtc",
                "enabled": False,
                "description": "WebRTC connection",
                "config": {"signaling_server": "wss://signal.example.com"},
            },
        ]

        datasite_repo = DatasiteRepository(test_session)
        created_datasite = datasite_repo.create(datasite_data)

        # Test that connect field is correctly stored and retrieved
        assert created_datasite.connect is not None
        assert len(created_datasite.connect) == 2

        # Verify first connection
        http_conn = created_datasite.connect[0]
        assert http_conn.type == "http"
        assert http_conn.enabled is True
        assert http_conn.description == "HTTP API connection"
        assert http_conn.config["url"] == "https://api.example.com"

        # Verify second connection
        webrtc_conn = created_datasite.connect[1]
        assert webrtc_conn.type == "webrtc"
        assert webrtc_conn.enabled is False
        assert webrtc_conn.config["signaling_server"] == "wss://signal.example.com"

        # Test retrieval by ID
        retrieved_datasite = datasite_repo.get_by_id(created_datasite.id)
        assert retrieved_datasite is not None
        assert len(retrieved_datasite.connect) == 2
        assert retrieved_datasite.connect[0].type == "http"
        assert retrieved_datasite.connect[1].type == "webrtc"

    def test_datasite_default_empty_connect(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test that datasite defaults to empty connect list when not specified."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        # Note: not setting connect field, should default to empty list

        datasite_repo = DatasiteRepository(test_session)
        created_datasite = datasite_repo.create(datasite_data)

        # Test that connect field defaults to empty list
        assert created_datasite.connect is not None
        assert len(created_datasite.connect) == 0
        assert created_datasite.connect == []

    def test_delete_datasite(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test deleting a datasite."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id

        datasite_repo = DatasiteRepository(test_session)
        created_datasite = datasite_repo.create(datasite_data)

        # Test delete
        result = datasite_repo.delete(created_datasite.id)
        assert result is True

        # Verify deletion
        retrieved_datasite = datasite_repo.get_by_id(created_datasite.id)
        assert retrieved_datasite is None
