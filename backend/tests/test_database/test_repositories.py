"""Tests for repository classes."""

from sqlalchemy.orm import Session

from syfthub.repositories import (
    DatasiteRepository,
    UserRepository,
)
from syfthub.repositories.datasite import DatasiteStarRepository
from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.datasite import DatasiteVisibility
from syfthub.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationRole,
    OrganizationUpdate,
)


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

    def test_delete_datasite_not_found(self, test_session: Session):
        """Test deleting a non-existent datasite."""
        datasite_repo = DatasiteRepository(test_session)
        result = datasite_repo.delete(999)
        assert result is False

    def test_update_datasite_not_found(self, test_session: Session):
        """Test updating a non-existent datasite."""
        datasite_repo = DatasiteRepository(test_session)
        result = datasite_repo.update(999, name="New Name")
        assert result is None

    def test_get_by_id_not_found(self, test_session: Session):
        """Test getting datasite by non-existent ID."""
        datasite_repo = DatasiteRepository(test_session)
        result = datasite_repo.get_by_id(999)
        assert result is None

    def test_get_by_user_and_slug_not_found(self, test_session: Session):
        """Test getting datasite by user and slug when not found."""
        datasite_repo = DatasiteRepository(test_session)
        result = datasite_repo.get_by_user_and_slug(999, "nonexistent-slug")
        assert result is None

    def test_get_user_datasites_with_visibility_filter(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting user datasites with visibility filter."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create public datasite
        public_data = sample_datasite_data.copy()
        public_data["user_id"] = user.id
        public_data["visibility"] = DatasiteVisibility.PUBLIC.value
        public_data["slug"] = "public-ds"
        datasite_repo.create(public_data)

        # Create private datasite
        private_data = sample_datasite_data.copy()
        private_data["user_id"] = user.id
        private_data["visibility"] = DatasiteVisibility.PRIVATE.value
        private_data["slug"] = "private-ds"
        datasite_repo.create(private_data)

        # Test with visibility filter
        public_only = datasite_repo.get_user_datasites(
            user.id, visibility=DatasiteVisibility.PUBLIC
        )
        assert len(public_only) == 1
        assert public_only[0].visibility == DatasiteVisibility.PUBLIC

    def test_get_user_datasites_with_search(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting user datasites with search query."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create datasites with different names
        ds1 = sample_datasite_data.copy()
        ds1["user_id"] = user.id
        ds1["name"] = "Machine Learning Project"
        ds1["slug"] = "ml-project"
        datasite_repo.create(ds1)

        ds2 = sample_datasite_data.copy()
        ds2["user_id"] = user.id
        ds2["name"] = "Data Analysis"
        ds2["slug"] = "data-analysis"
        datasite_repo.create(ds2)

        # Search for "Machine"
        results = datasite_repo.get_user_datasites(user.id, search="Machine")
        assert len(results) == 1
        assert "Machine" in results[0].name

    def test_get_public_datasites(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting public datasites with owner username."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create public datasite
        public_data = sample_datasite_data.copy()
        public_data["user_id"] = user.id
        public_data["visibility"] = DatasiteVisibility.PUBLIC.value
        public_data["slug"] = "public-ds"
        datasite_repo.create(public_data)

        # Get public datasites
        public_datasites = datasite_repo.get_public_datasites()
        assert len(public_datasites) == 1
        assert public_datasites[0].owner_username == "testuser"

    def test_get_trending_datasites(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting trending datasites sorted by stars."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create datasites with different star counts
        ds1 = sample_datasite_data.copy()
        ds1["user_id"] = user.id
        ds1["name"] = "Popular Project"
        ds1["slug"] = "popular"
        ds1["stars_count"] = 100
        datasite_repo.create(ds1)

        ds2 = sample_datasite_data.copy()
        ds2["user_id"] = user.id
        ds2["name"] = "Less Popular"
        ds2["slug"] = "less-popular"
        ds2["stars_count"] = 10
        datasite_repo.create(ds2)

        # Get trending (sorted by stars desc)
        trending = datasite_repo.get_trending_datasites()
        assert len(trending) == 2
        assert trending[0].stars_count >= trending[1].stars_count

    def test_get_trending_datasites_with_min_stars(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting trending datasites with minimum stars filter."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create datasites with different star counts
        ds1 = sample_datasite_data.copy()
        ds1["user_id"] = user.id
        ds1["name"] = "Popular"
        ds1["slug"] = "popular"
        ds1["stars_count"] = 100
        datasite_repo.create(ds1)

        ds2 = sample_datasite_data.copy()
        ds2["user_id"] = user.id
        ds2["name"] = "Unpopular"
        ds2["slug"] = "unpopular"
        ds2["stars_count"] = 5
        datasite_repo.create(ds2)

        # Get trending with min_stars filter
        trending = datasite_repo.get_trending_datasites(min_stars=50)
        assert len(trending) == 1
        assert trending[0].stars_count >= 50

    def test_increment_stars(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test incrementing stars count."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite_data["stars_count"] = 5
        created = datasite_repo.create(datasite_data)

        # Increment stars
        result = datasite_repo.increment_stars(created.id)
        assert result is True

        # Verify increment
        updated = datasite_repo.get_by_id(created.id)
        assert updated.stars_count == 6

    def test_increment_stars_not_found(self, test_session: Session):
        """Test incrementing stars for non-existent datasite."""
        datasite_repo = DatasiteRepository(test_session)
        result = datasite_repo.increment_stars(999)
        assert result is False

    def test_decrement_stars(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test decrementing stars count."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite_data["stars_count"] = 5
        created = datasite_repo.create(datasite_data)

        # Decrement stars
        result = datasite_repo.decrement_stars(created.id)
        assert result is True

        # Verify decrement
        updated = datasite_repo.get_by_id(created.id)
        assert updated.stars_count == 4

    def test_decrement_stars_not_found(self, test_session: Session):
        """Test decrementing stars for non-existent datasite."""
        datasite_repo = DatasiteRepository(test_session)
        result = datasite_repo.decrement_stars(999)
        assert result is False

    def test_decrement_stars_at_zero(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test decrementing stars when already at zero."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite_data["stars_count"] = 0
        created = datasite_repo.create(datasite_data)

        # Decrement should succeed but not go below 0
        result = datasite_repo.decrement_stars(created.id)
        assert result is True

        updated = datasite_repo.get_by_id(created.id)
        assert updated.stars_count == 0

    def test_soft_delete_datasite(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test soft deleting a datasite (setting is_active=False)."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        created = datasite_repo.create(datasite_data)

        # Soft delete
        result = datasite_repo.delete_datasite(created.id)
        assert result is True

        # Should not be found by get_by_id (which filters is_active)
        found = datasite_repo.get_by_id(created.id)
        assert found is None

    def test_soft_delete_datasite_not_found(self, test_session: Session):
        """Test soft deleting non-existent datasite."""
        datasite_repo = DatasiteRepository(test_session)
        result = datasite_repo.delete_datasite(999)
        assert result is False

    def test_get_all_with_filters(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test get_all with filters."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create datasites with different visibilities
        public_data = sample_datasite_data.copy()
        public_data["user_id"] = user.id
        public_data["visibility"] = DatasiteVisibility.PUBLIC.value
        public_data["slug"] = "public-ds"
        datasite_repo.create(public_data)

        private_data = sample_datasite_data.copy()
        private_data["user_id"] = user.id
        private_data["visibility"] = DatasiteVisibility.PRIVATE.value
        private_data["slug"] = "private-ds"
        datasite_repo.create(private_data)

        # Get all with filter
        public_only = datasite_repo.get_all(filters={"visibility": "public"})
        assert len(public_only) == 1

    def test_count_datasites(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test counting datasites."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create multiple datasites
        for i in range(5):
            ds = sample_datasite_data.copy()
            ds["user_id"] = user.id
            ds["slug"] = f"datasite-{i}"
            datasite_repo.create(ds)

        count = datasite_repo.count()
        assert count == 5

    def test_count_datasites_with_filter(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test counting datasites with filters."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)

        # Create public and private datasites
        for i in range(3):
            ds = sample_datasite_data.copy()
            ds["user_id"] = user.id
            ds["slug"] = f"public-{i}"
            ds["visibility"] = DatasiteVisibility.PUBLIC.value
            datasite_repo.create(ds)

        for i in range(2):
            ds = sample_datasite_data.copy()
            ds["user_id"] = user.id
            ds["slug"] = f"private-{i}"
            ds["visibility"] = DatasiteVisibility.PRIVATE.value
            datasite_repo.create(ds)

        public_count = datasite_repo.count(filters={"visibility": "public"})
        assert public_count == 3


class TestDatasiteStarRepository:
    """Tests for DatasiteStarRepository."""

    def test_star_datasite(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test starring a datasite."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite = datasite_repo.create(datasite_data)

        star_repo = DatasiteStarRepository(test_session)
        result = star_repo.star_datasite(user.id, datasite.id)
        assert result is True

    def test_star_datasite_already_starred(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test starring a datasite that's already starred."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite = datasite_repo.create(datasite_data)

        star_repo = DatasiteStarRepository(test_session)
        star_repo.star_datasite(user.id, datasite.id)

        # Try to star again
        result = star_repo.star_datasite(user.id, datasite.id)
        assert result is False

    def test_unstar_datasite(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test unstarring a datasite."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite = datasite_repo.create(datasite_data)

        star_repo = DatasiteStarRepository(test_session)
        star_repo.star_datasite(user.id, datasite.id)

        result = star_repo.unstar_datasite(user.id, datasite.id)
        assert result is True

    def test_unstar_datasite_not_starred(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test unstarring a datasite that wasn't starred."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite = datasite_repo.create(datasite_data)

        star_repo = DatasiteStarRepository(test_session)
        result = star_repo.unstar_datasite(user.id, datasite.id)
        assert result is False

    def test_is_starred(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test checking if a datasite is starred."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        datasite_data = sample_datasite_data.copy()
        datasite_data["user_id"] = user.id
        datasite = datasite_repo.create(datasite_data)

        star_repo = DatasiteStarRepository(test_session)
        assert star_repo.is_starred(user.id, datasite.id) is False

        star_repo.star_datasite(user.id, datasite.id)
        assert star_repo.is_starred(user.id, datasite.id) is True

    def test_get_user_starred_datasites(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting datasites starred by a user."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        datasite_repo = DatasiteRepository(test_session)
        star_repo = DatasiteStarRepository(test_session)

        # Create and star multiple datasites
        for i in range(3):
            ds_data = sample_datasite_data.copy()
            ds_data["user_id"] = user.id
            ds_data["slug"] = f"datasite-{i}"
            ds = datasite_repo.create(ds_data)
            star_repo.star_datasite(user.id, ds.id)

        starred = star_repo.get_user_starred_datasites(user.id)
        assert len(starred) == 3

    def test_get_datasite_stargazers(
        self, test_session: Session, sample_user_data: dict, sample_datasite_data: dict
    ):
        """Test getting users who starred a datasite."""
        from tests.test_utils import generate_unique_test_keys

        user_repo = UserRepository(test_session)

        # Create first user
        user1 = user_repo.create(sample_user_data)

        # Create second user
        user2_data = sample_user_data.copy()
        user2_data["username"] = "user2"
        user2_data["email"] = "user2@example.com"
        user2_data["public_key"] = generate_unique_test_keys()["public_key"]
        user2 = user_repo.create(user2_data)

        # Create datasite
        datasite_repo = DatasiteRepository(test_session)
        ds_data = sample_datasite_data.copy()
        ds_data["user_id"] = user1.id
        datasite = datasite_repo.create(ds_data)

        # Both users star the datasite
        star_repo = DatasiteStarRepository(test_session)
        star_repo.star_datasite(user1.id, datasite.id)
        star_repo.star_datasite(user2.id, datasite.id)

        stargazers = star_repo.get_datasite_stargazers(datasite.id)
        assert len(stargazers) == 2


class TestOrganizationRepository:
    """Tests for OrganizationRepository."""

    def test_create_organization(self, test_session: Session):
        """Test creating an organization."""
        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(
            name="Test Organization",
            slug="test-org",
            description="A test organization",
        )

        org = org_repo.create_organization(org_data)
        assert org is not None
        assert org.name == "Test Organization"
        assert org.slug == "test-org"
        assert org.is_active is True

    def test_create_organization_auto_slug(self, test_session: Session):
        """Test creating organization with auto-generated slug."""
        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(
            name="My Cool Organization",
            description="A test organization",
        )

        org = org_repo.create_organization(org_data)
        assert org is not None
        assert org.slug is not None
        assert "my-cool-organization" in org.slug.lower()

    def test_get_organization_by_id(self, test_session: Session):
        """Test getting organization by ID."""
        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        created = org_repo.create_organization(org_data)

        found = org_repo.get_by_id(created.id)
        assert found is not None
        assert found.id == created.id

    def test_get_organization_by_id_not_found(self, test_session: Session):
        """Test getting organization by non-existent ID."""
        org_repo = OrganizationRepository(test_session)
        found = org_repo.get_by_id(999)
        assert found is None

    def test_get_organization_by_slug(self, test_session: Session):
        """Test getting organization by slug."""
        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org_repo.create_organization(org_data)

        found = org_repo.get_by_slug("test-org")
        assert found is not None
        assert found.slug == "test-org"

    def test_get_organization_by_slug_not_found(self, test_session: Session):
        """Test getting organization by non-existent slug."""
        org_repo = OrganizationRepository(test_session)
        found = org_repo.get_by_slug("nonexistent")
        assert found is None

    def test_update_organization(self, test_session: Session):
        """Test updating an organization."""
        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        created = org_repo.create_organization(org_data)

        update_data = OrganizationUpdate(
            name="Updated Organization",
            description="Updated description",
        )
        updated = org_repo.update_organization(created.id, update_data)

        assert updated is not None
        assert updated.name == "Updated Organization"
        assert updated.description == "Updated description"

    def test_update_organization_not_found(self, test_session: Session):
        """Test updating non-existent organization."""
        org_repo = OrganizationRepository(test_session)
        update_data = OrganizationUpdate(name="New Name")
        result = org_repo.update_organization(999, update_data)
        assert result is None

    def test_slug_exists(self, test_session: Session):
        """Test checking if slug exists."""
        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org_repo.create_organization(org_data)

        assert org_repo.slug_exists("test-org") is True
        assert org_repo.slug_exists("nonexistent") is False

    def test_slug_exists_with_exclude(self, test_session: Session):
        """Test checking if slug exists with exclusion."""
        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        created = org_repo.create_organization(org_data)

        # Should return False when excluding the org that has the slug
        assert org_repo.slug_exists("test-org", exclude_org_id=created.id) is False

    def test_generate_slug_from_name_short(self, test_session: Session):
        """Test slug generation for short names."""
        org_repo = OrganizationRepository(test_session)
        slug = org_repo._generate_slug_from_name("AB")
        assert slug.startswith("org-")

    def test_generate_slug_from_name_long(self, test_session: Session):
        """Test slug generation for long names."""
        org_repo = OrganizationRepository(test_session)
        long_name = "A" * 100  # Very long name
        slug = org_repo._generate_slug_from_name(long_name)
        assert len(slug) <= 63

    def test_generate_slug_unique(self, test_session: Session):
        """Test slug generation ensures uniqueness."""
        org_repo = OrganizationRepository(test_session)

        # Create first org
        org_data1 = OrganizationCreate(name="Test Org")
        org1 = org_repo.create_organization(org_data1)

        # Create second org with same name - should get unique slug
        org_data2 = OrganizationCreate(name="Test Org")
        org2 = org_repo.create_organization(org_data2)

        assert org1.slug != org2.slug


class TestOrganizationMemberRepository:
    """Tests for OrganizationMemberRepository."""

    def test_add_member(self, test_session: Session, sample_user_data: dict):
        """Test adding a member to organization."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        member_data = OrganizationMemberCreate(
            user_id=user.id,
            role=OrganizationRole.MEMBER,
        )
        member = member_repo.add_member(member_data, org.id)

        assert member is not None
        assert member.user_id == user.id
        assert member.organization_id == org.id

    def test_add_member_already_exists(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test adding a member that already exists."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        member_data = OrganizationMemberCreate(
            user_id=user.id,
            role=OrganizationRole.MEMBER,
        )
        member_repo.add_member(member_data, org.id)

        # Try to add again
        result = member_repo.add_member(member_data, org.id)
        assert result is None

    def test_remove_member(self, test_session: Session, sample_user_data: dict):
        """Test removing a member from organization."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        member_data = OrganizationMemberCreate(
            user_id=user.id,
            role=OrganizationRole.MEMBER,
        )
        member_repo.add_member(member_data, org.id)

        result = member_repo.remove_member(org.id, user.id)
        assert result is True

    def test_remove_member_not_found(self, test_session: Session):
        """Test removing a non-existent member."""
        member_repo = OrganizationMemberRepository(test_session)
        result = member_repo.remove_member(999, 999)
        assert result is False

    def test_update_member_role(self, test_session: Session, sample_user_data: dict):
        """Test updating a member's role."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        member_data = OrganizationMemberCreate(
            user_id=user.id,
            role=OrganizationRole.MEMBER,
        )
        member_repo.add_member(member_data, org.id)

        result = member_repo.update_member_role(org.id, user.id, OrganizationRole.ADMIN)
        assert result is True

    def test_update_member_role_not_found(self, test_session: Session):
        """Test updating role for non-existent member."""
        member_repo = OrganizationMemberRepository(test_session)
        result = member_repo.update_member_role(999, 999, OrganizationRole.ADMIN)
        assert result is False

    def test_is_member(self, test_session: Session, sample_user_data: dict):
        """Test checking if user is member of organization."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        assert member_repo.is_member(org.id, user.id) is False

        member_data = OrganizationMemberCreate(
            user_id=user.id,
            role=OrganizationRole.MEMBER,
        )
        member_repo.add_member(member_data, org.id)
        assert member_repo.is_member(org.id, user.id) is True

    def test_get_member_role(self, test_session: Session, sample_user_data: dict):
        """Test getting a member's role."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        member_data = OrganizationMemberCreate(
            user_id=user.id,
            role=OrganizationRole.ADMIN,
        )
        member_repo.add_member(member_data, org.id)

        role = member_repo.get_member_role(org.id, user.id)
        assert role == OrganizationRole.ADMIN

    def test_get_member_role_not_found(self, test_session: Session):
        """Test getting role for non-member."""
        member_repo = OrganizationMemberRepository(test_session)
        role = member_repo.get_member_role(999, 999)
        assert role is None

    def test_get_organization_members(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test getting all members of an organization."""
        from tests.test_utils import generate_unique_test_keys

        user_repo = UserRepository(test_session)
        user1 = user_repo.create(sample_user_data)

        user2_data = sample_user_data.copy()
        user2_data["username"] = "user2"
        user2_data["email"] = "user2@example.com"
        user2_data["public_key"] = generate_unique_test_keys()["public_key"]
        user2 = user_repo.create(user2_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        member_repo.add_member(
            OrganizationMemberCreate(user_id=user1.id, role=OrganizationRole.OWNER),
            org.id,
        )
        member_repo.add_member(
            OrganizationMemberCreate(user_id=user2.id, role=OrganizationRole.MEMBER),
            org.id,
        )

        members = member_repo.get_organization_members(org.id)
        assert len(members) == 2

    def test_get_user_organizations(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test getting organizations a user belongs to."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        org_repo = OrganizationRepository(test_session)
        member_repo = OrganizationMemberRepository(test_session)

        # Create multiple orgs and add user to them
        for i in range(3):
            org_data = OrganizationCreate(name=f"Org {i}", slug=f"org-{i}")
            org = org_repo.create_organization(org_data)
            member_repo.add_member(
                OrganizationMemberCreate(user_id=user.id, role=OrganizationRole.MEMBER),
                org.id,
            )

        user_orgs = member_repo.get_user_organizations(user.id)
        assert len(user_orgs) == 3

    def test_count_owners(self, test_session: Session, sample_user_data: dict):
        """Test counting owners of an organization."""
        from tests.test_utils import generate_unique_test_keys

        user_repo = UserRepository(test_session)
        user1 = user_repo.create(sample_user_data)

        user2_data = sample_user_data.copy()
        user2_data["username"] = "user2"
        user2_data["email"] = "user2@example.com"
        user2_data["public_key"] = generate_unique_test_keys()["public_key"]
        user2 = user_repo.create(user2_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        member_repo.add_member(
            OrganizationMemberCreate(user_id=user1.id, role=OrganizationRole.OWNER),
            org.id,
        )
        member_repo.add_member(
            OrganizationMemberCreate(user_id=user2.id, role=OrganizationRole.MEMBER),
            org.id,
        )

        owner_count = member_repo.count_owners(org.id)
        assert owner_count == 1

    def test_update_member(self, test_session: Session, sample_user_data: dict):
        """Test updating member data."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        org_repo = OrganizationRepository(test_session)
        org_data = OrganizationCreate(name="Test Org", slug="test-org")
        org = org_repo.create_organization(org_data)

        member_repo = OrganizationMemberRepository(test_session)
        member_repo.add_member(
            OrganizationMemberCreate(user_id=user.id, role=OrganizationRole.MEMBER),
            org.id,
        )

        updated = member_repo.update_member(
            org.id, user.id, {"role": OrganizationRole.ADMIN}
        )
        assert updated is not None

    def test_update_member_not_found(self, test_session: Session):
        """Test updating non-existent member."""
        member_repo = OrganizationMemberRepository(test_session)
        result = member_repo.update_member(999, 999, {"role": OrganizationRole.ADMIN})
        assert result is None
