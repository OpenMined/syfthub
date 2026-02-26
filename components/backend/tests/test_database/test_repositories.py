"""Tests for repository classes."""

from sqlalchemy.orm import Session

from syfthub.repositories import (
    EndpointRepository,
    UserRepository,
)
from syfthub.repositories.endpoint import EndpointStarRepository
from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.endpoint import EndpointVisibility
from syfthub.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationRole,
    OrganizationUpdate,
)
from syfthub.schemas.user import UserUpdate


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
        assert user.avatar_url is None
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

        # Create multiple users
        user1_data = sample_user_data.copy()
        user2_data = sample_user_data.copy()
        user2_data["username"] = "testuser2"
        user2_data["email"] = "test2@example.com"

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

        update_data = {
            "full_name": "Updated Name",
            "avatar_url": "https://example.com/avatar.png",
        }
        updated_user = user_repo.update(created_user.id, update_data)

        assert updated_user is not None
        assert updated_user.full_name == "Updated Name"
        assert updated_user.avatar_url == "https://example.com/avatar.png"
        assert updated_user.username == "testuser"  # Unchanged

    def test_update_user_not_found(self, test_session: Session):
        """Test updating non-existent user."""
        user_repo = UserRepository(test_session)
        result = user_repo.update(999, {"full_name": "New Name"})
        assert result is None

    def test_update_user_domain_set(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test setting domain via update_user."""
        user_repo = UserRepository(test_session)
        created_user = user_repo.create(sample_user_data)

        update_data = UserUpdate(domain="https://example.com")
        updated_user = user_repo.update_user(created_user.id, update_data)

        assert updated_user is not None
        assert updated_user.domain == "https://example.com"

    def test_update_user_domain_cleared_to_none(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test that domain can be explicitly cleared to None via update_user."""
        user_repo = UserRepository(test_session)
        created_user = user_repo.create(sample_user_data)

        # First set a domain
        user_repo.update_user(created_user.id, UserUpdate(domain="https://example.com"))

        # Now clear it by explicitly passing domain=None (must be in model_fields_set)
        update_data = UserUpdate.model_validate({"domain": None})
        assert "domain" in update_data.model_fields_set
        updated_user = user_repo.update_user(created_user.id, update_data)

        assert updated_user is not None
        assert updated_user.domain is None

    def test_update_user_domain_not_cleared_when_omitted(
        self, test_session: Session, sample_user_data: dict
    ):
        """Test that domain is not cleared when it is simply omitted from the update."""
        user_repo = UserRepository(test_session)
        created_user = user_repo.create(sample_user_data)

        # Set a domain
        user_repo.update_user(created_user.id, UserUpdate(domain="https://example.com"))

        # Update something else — domain should be untouched
        update_data = UserUpdate(full_name="New Name")
        assert "domain" not in update_data.model_fields_set
        updated_user = user_repo.update_user(created_user.id, update_data)

        assert updated_user is not None
        assert updated_user.domain == "https://example.com"

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


class TestEndpointRepository:
    """Tests for EndpointRepository."""

    def test_create_endpoint(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test creating a endpoint through repository."""
        # Create user first
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        # Create endpoint
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint_repo = EndpointRepository(test_session)
        endpoint = endpoint_repo.create(endpoint_data)

        assert endpoint.id is not None
        assert endpoint.user_id == user.id
        assert endpoint.name == "Test Endpoint"
        assert endpoint.slug == "test-endpoint"
        assert endpoint.description == "A test endpoint"
        assert endpoint.visibility == EndpointVisibility.PUBLIC
        assert endpoint.is_active is True

    def test_get_endpoint_by_user_and_slug(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting endpoint by user ID and slug."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id

        endpoint_repo = EndpointRepository(test_session)
        created_endpoint = endpoint_repo.create(endpoint_data)

        # Test
        retrieved_endpoint = endpoint_repo.get_by_user_and_slug(
            user.id, "test-endpoint"
        )
        assert retrieved_endpoint is not None
        assert retrieved_endpoint.id == created_endpoint.id
        assert retrieved_endpoint.slug == "test-endpoint"

    def test_get_endpoints_by_user_id(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting endpoints by user ID."""
        # Create two users
        user_repo = UserRepository(test_session)
        user1 = user_repo.create(sample_user_data)

        user2_data = sample_user_data.copy()
        user2_data["username"] = "testuser2"
        user2_data["email"] = "test2@example.com"
        user2 = user_repo.create(user2_data)

        # Create endpoints for both users
        endpoint_repo = EndpointRepository(test_session)

        # Endpoints for user1
        for i in range(3):
            endpoint_data = sample_endpoint_data.copy()
            endpoint_data["user_id"] = user1.id
            endpoint_data["name"] = f"User1 Endpoint {i}"
            endpoint_data["slug"] = f"user1-endpoint-{i}"
            endpoint_repo.create(endpoint_data)

        # Endpoints for user2
        for i in range(2):
            endpoint_data = sample_endpoint_data.copy()
            endpoint_data["user_id"] = user2.id
            endpoint_data["name"] = f"User2 Endpoint {i}"
            endpoint_data["slug"] = f"user2-endpoint-{i}"
            endpoint_repo.create(endpoint_data)

        # Test getting endpoints by user
        user1_endpoints = endpoint_repo.get_by_user_id(user1.id)
        user2_endpoints = endpoint_repo.get_by_user_id(user2.id)

        assert len(user1_endpoints) == 3
        assert len(user2_endpoints) == 2
        assert all("User1" in ds.name for ds in user1_endpoints)
        assert all("User2" in ds.name for ds in user2_endpoints)

    def test_get_public_endpoints_by_user_id(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting only public endpoints by user ID."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create public endpoint
        public_data = sample_endpoint_data.copy()
        public_data["user_id"] = user.id
        public_data["visibility"] = EndpointVisibility.PUBLIC.value
        public_data["slug"] = "public-endpoint"
        endpoint_repo.create(public_data)

        # Create private endpoint
        private_data = sample_endpoint_data.copy()
        private_data["user_id"] = user.id
        private_data["visibility"] = EndpointVisibility.PRIVATE.value
        private_data["slug"] = "private-endpoint"
        endpoint_repo.create(private_data)

        # Create inactive public endpoint
        inactive_data = sample_endpoint_data.copy()
        inactive_data["user_id"] = user.id
        inactive_data["visibility"] = EndpointVisibility.PUBLIC.value
        inactive_data["is_active"] = False
        inactive_data["slug"] = "inactive-endpoint"
        endpoint_repo.create(inactive_data)

        # Test getting only public active endpoints
        public_endpoints = endpoint_repo.get_public_by_user_id(user.id)

        assert len(public_endpoints) == 1
        assert public_endpoints[0].slug == "public-endpoint"
        assert public_endpoints[0].visibility == EndpointVisibility.PUBLIC

    def test_slug_exists_for_user(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test checking if slug exists for user."""
        # Create two users
        user_repo = UserRepository(test_session)
        user1 = user_repo.create(sample_user_data)

        user2_data = sample_user_data.copy()
        user2_data["username"] = "testuser2"
        user2_data["email"] = "test2@example.com"
        user2 = user_repo.create(user2_data)

        # Create endpoint for user1
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user1.id
        endpoint_repo = EndpointRepository(test_session)
        endpoint_repo.create(endpoint_data)

        # Test slug existence
        assert endpoint_repo.slug_exists_for_user(user1.id, "test-endpoint") is True
        assert endpoint_repo.slug_exists_for_user(user1.id, "nonexistent-slug") is False
        assert endpoint_repo.slug_exists_for_user(user2.id, "test-endpoint") is False

    def test_update_endpoint(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test updating a endpoint."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id

        endpoint_repo = EndpointRepository(test_session)
        created_endpoint = endpoint_repo.create(endpoint_data)

        # Test update
        update_data = {
            "name": "Updated Endpoint",
            "visibility": EndpointVisibility.PRIVATE.value,
        }
        updated_endpoint = endpoint_repo.update(created_endpoint.id, update_data)

        assert updated_endpoint is not None
        assert updated_endpoint.name == "Updated Endpoint"
        assert updated_endpoint.visibility == EndpointVisibility.PRIVATE
        assert updated_endpoint.slug == "test-endpoint"  # Unchanged

    def test_endpoint_with_connect_field(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test creating and retrieving endpoint with connect field."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        # Create endpoint with connect configurations
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint_data["connect"] = [
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

        endpoint_repo = EndpointRepository(test_session)
        created_endpoint = endpoint_repo.create(endpoint_data)

        # Test that connect field is correctly stored and retrieved
        assert created_endpoint.connect is not None
        assert len(created_endpoint.connect) == 2

        # Verify first connection
        http_conn = created_endpoint.connect[0]
        assert http_conn.type == "http"
        assert http_conn.enabled is True
        assert http_conn.description == "HTTP API connection"
        assert http_conn.config["url"] == "https://api.example.com"

        # Verify second connection
        webrtc_conn = created_endpoint.connect[1]
        assert webrtc_conn.type == "webrtc"
        assert webrtc_conn.enabled is False
        assert webrtc_conn.config["signaling_server"] == "wss://signal.example.com"

        # Test retrieval by ID
        retrieved_endpoint = endpoint_repo.get_by_id(created_endpoint.id)
        assert retrieved_endpoint is not None
        assert len(retrieved_endpoint.connect) == 2
        assert retrieved_endpoint.connect[0].type == "http"
        assert retrieved_endpoint.connect[1].type == "webrtc"

    def test_endpoint_default_empty_connect(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test that endpoint defaults to empty connect list when not specified."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        # Note: not setting connect field, should default to empty list

        endpoint_repo = EndpointRepository(test_session)
        created_endpoint = endpoint_repo.create(endpoint_data)

        # Test that connect field defaults to empty list
        assert created_endpoint.connect is not None
        assert len(created_endpoint.connect) == 0
        assert created_endpoint.connect == []

    def test_delete_endpoint(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test deleting a endpoint."""
        # Setup
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id

        endpoint_repo = EndpointRepository(test_session)
        created_endpoint = endpoint_repo.create(endpoint_data)

        # Test delete
        result = endpoint_repo.delete(created_endpoint.id)
        assert result is True

        # Verify deletion
        retrieved_endpoint = endpoint_repo.get_by_id(created_endpoint.id)
        assert retrieved_endpoint is None

    def test_delete_endpoint_not_found(self, test_session: Session):
        """Test deleting a non-existent endpoint."""
        endpoint_repo = EndpointRepository(test_session)
        result = endpoint_repo.delete(999)
        assert result is False

    def test_update_endpoint_not_found(self, test_session: Session):
        """Test updating a non-existent endpoint."""
        endpoint_repo = EndpointRepository(test_session)
        result = endpoint_repo.update(999, name="New Name")
        assert result is None

    def test_get_by_id_not_found(self, test_session: Session):
        """Test getting endpoint by non-existent ID."""
        endpoint_repo = EndpointRepository(test_session)
        result = endpoint_repo.get_by_id(999)
        assert result is None

    def test_get_by_user_and_slug_not_found(self, test_session: Session):
        """Test getting endpoint by user and slug when not found."""
        endpoint_repo = EndpointRepository(test_session)
        result = endpoint_repo.get_by_user_and_slug(999, "nonexistent-slug")
        assert result is None

    def test_get_user_endpoints_with_visibility_filter(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting user endpoints with visibility filter."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create public endpoint
        public_data = sample_endpoint_data.copy()
        public_data["user_id"] = user.id
        public_data["visibility"] = EndpointVisibility.PUBLIC.value
        public_data["slug"] = "public-ds"
        endpoint_repo.create(public_data)

        # Create private endpoint
        private_data = sample_endpoint_data.copy()
        private_data["user_id"] = user.id
        private_data["visibility"] = EndpointVisibility.PRIVATE.value
        private_data["slug"] = "private-ds"
        endpoint_repo.create(private_data)

        # Test with visibility filter
        public_only = endpoint_repo.get_user_endpoints(
            user.id, visibility=EndpointVisibility.PUBLIC
        )
        assert len(public_only) == 1
        assert public_only[0].visibility == EndpointVisibility.PUBLIC

    def test_get_user_endpoints_with_search(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting user endpoints with search query."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create endpoints with different names
        ds1 = sample_endpoint_data.copy()
        ds1["user_id"] = user.id
        ds1["name"] = "Machine Learning Project"
        ds1["slug"] = "ml-project"
        endpoint_repo.create(ds1)

        ds2 = sample_endpoint_data.copy()
        ds2["user_id"] = user.id
        ds2["name"] = "Data Analysis"
        ds2["slug"] = "data-analysis"
        endpoint_repo.create(ds2)

        # Search for "Machine"
        results = endpoint_repo.get_user_endpoints(user.id, search="Machine")
        assert len(results) == 1
        assert "Machine" in results[0].name

    def test_get_public_endpoints(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting public endpoints with owner username."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create public endpoint
        public_data = sample_endpoint_data.copy()
        public_data["user_id"] = user.id
        public_data["visibility"] = EndpointVisibility.PUBLIC.value
        public_data["slug"] = "public-ds"
        endpoint_repo.create(public_data)

        # Get public endpoints
        public_endpoints = endpoint_repo.get_public_endpoints()
        assert len(public_endpoints) == 1
        assert public_endpoints[0].owner_username == "testuser"

    def test_get_trending_endpoints(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting trending endpoints sorted by stars."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create endpoints with different star counts
        ds1 = sample_endpoint_data.copy()
        ds1["user_id"] = user.id
        ds1["name"] = "Popular Project"
        ds1["slug"] = "popular"
        ds1["stars_count"] = 100
        endpoint_repo.create(ds1)

        ds2 = sample_endpoint_data.copy()
        ds2["user_id"] = user.id
        ds2["name"] = "Less Popular"
        ds2["slug"] = "less-popular"
        ds2["stars_count"] = 10
        endpoint_repo.create(ds2)

        # Get trending (sorted by stars desc)
        trending = endpoint_repo.get_trending_endpoints()
        assert len(trending) == 2
        assert trending[0].stars_count >= trending[1].stars_count

    def test_get_trending_endpoints_with_min_stars(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting trending endpoints with minimum stars filter."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create endpoints with different star counts
        ds1 = sample_endpoint_data.copy()
        ds1["user_id"] = user.id
        ds1["name"] = "Popular"
        ds1["slug"] = "popular"
        ds1["stars_count"] = 100
        endpoint_repo.create(ds1)

        ds2 = sample_endpoint_data.copy()
        ds2["user_id"] = user.id
        ds2["name"] = "Unpopular"
        ds2["slug"] = "unpopular"
        ds2["stars_count"] = 5
        endpoint_repo.create(ds2)

        # Get trending with min_stars filter
        trending = endpoint_repo.get_trending_endpoints(min_stars=50)
        assert len(trending) == 1
        assert trending[0].stars_count >= 50

    def test_increment_stars(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test incrementing stars count."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint_data["stars_count"] = 5
        created = endpoint_repo.create(endpoint_data)

        # Increment stars
        result = endpoint_repo.increment_stars(created.id)
        assert result is True

        # Verify increment
        updated = endpoint_repo.get_by_id(created.id)
        assert updated.stars_count == 6

    def test_increment_stars_not_found(self, test_session: Session):
        """Test incrementing stars for non-existent endpoint."""
        endpoint_repo = EndpointRepository(test_session)
        result = endpoint_repo.increment_stars(999)
        assert result is False

    def test_decrement_stars(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test decrementing stars count."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint_data["stars_count"] = 5
        created = endpoint_repo.create(endpoint_data)

        # Decrement stars
        result = endpoint_repo.decrement_stars(created.id)
        assert result is True

        # Verify decrement
        updated = endpoint_repo.get_by_id(created.id)
        assert updated.stars_count == 4

    def test_decrement_stars_not_found(self, test_session: Session):
        """Test decrementing stars for non-existent endpoint."""
        endpoint_repo = EndpointRepository(test_session)
        result = endpoint_repo.decrement_stars(999)
        assert result is False

    def test_decrement_stars_at_zero(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test decrementing stars when already at zero."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint_data["stars_count"] = 0
        created = endpoint_repo.create(endpoint_data)

        # Decrement should succeed but not go below 0
        result = endpoint_repo.decrement_stars(created.id)
        assert result is True

        updated = endpoint_repo.get_by_id(created.id)
        assert updated.stars_count == 0

    def test_hard_delete_endpoint(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test hard deleting an endpoint (removes from database)."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        created = endpoint_repo.create(endpoint_data)

        # Hard delete
        result = endpoint_repo.delete_endpoint(created.id)
        assert result is True

        # Should not be found by get_by_id (endpoint no longer exists)
        found = endpoint_repo.get_by_id(created.id)
        assert found is None

    def test_hard_delete_endpoint_not_found(self, test_session: Session):
        """Test hard deleting non-existent endpoint."""
        endpoint_repo = EndpointRepository(test_session)
        result = endpoint_repo.delete_endpoint(999)
        assert result is False

    def test_get_all_with_filters(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test get_all with filters."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create endpoints with different visibilities
        public_data = sample_endpoint_data.copy()
        public_data["user_id"] = user.id
        public_data["visibility"] = EndpointVisibility.PUBLIC.value
        public_data["slug"] = "public-ds"
        endpoint_repo.create(public_data)

        private_data = sample_endpoint_data.copy()
        private_data["user_id"] = user.id
        private_data["visibility"] = EndpointVisibility.PRIVATE.value
        private_data["slug"] = "private-ds"
        endpoint_repo.create(private_data)

        # Get all with filter
        public_only = endpoint_repo.get_all(filters={"visibility": "public"})
        assert len(public_only) == 1

    def test_count_endpoints(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test counting endpoints."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create multiple endpoints
        for i in range(5):
            ds = sample_endpoint_data.copy()
            ds["user_id"] = user.id
            ds["slug"] = f"endpoint-{i}"
            endpoint_repo.create(ds)

        count = endpoint_repo.count()
        assert count == 5

    def test_count_endpoints_with_filter(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test counting endpoints with filters."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)

        # Create public and private endpoints
        for i in range(3):
            ds = sample_endpoint_data.copy()
            ds["user_id"] = user.id
            ds["slug"] = f"public-{i}"
            ds["visibility"] = EndpointVisibility.PUBLIC.value
            endpoint_repo.create(ds)

        for i in range(2):
            ds = sample_endpoint_data.copy()
            ds["user_id"] = user.id
            ds["slug"] = f"private-{i}"
            ds["visibility"] = EndpointVisibility.PRIVATE.value
            endpoint_repo.create(ds)

        public_count = endpoint_repo.count(filters={"visibility": "public"})
        assert public_count == 3


class TestEndpointStarRepository:
    """Tests for EndpointStarRepository."""

    def test_star_endpoint(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test starring a endpoint."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint = endpoint_repo.create(endpoint_data)

        star_repo = EndpointStarRepository(test_session)
        result = star_repo.star_endpoint(user.id, endpoint.id)
        assert result is True

    def test_star_endpoint_already_starred(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test starring a endpoint that's already starred."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint = endpoint_repo.create(endpoint_data)

        star_repo = EndpointStarRepository(test_session)
        star_repo.star_endpoint(user.id, endpoint.id)

        # Try to star again
        result = star_repo.star_endpoint(user.id, endpoint.id)
        assert result is False

    def test_unstar_endpoint(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test unstarring a endpoint."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint = endpoint_repo.create(endpoint_data)

        star_repo = EndpointStarRepository(test_session)
        star_repo.star_endpoint(user.id, endpoint.id)

        result = star_repo.unstar_endpoint(user.id, endpoint.id)
        assert result is True

    def test_unstar_endpoint_not_starred(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test unstarring a endpoint that wasn't starred."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint = endpoint_repo.create(endpoint_data)

        star_repo = EndpointStarRepository(test_session)
        result = star_repo.unstar_endpoint(user.id, endpoint.id)
        assert result is False

    def test_is_starred(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test checking if a endpoint is starred."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        endpoint_data = sample_endpoint_data.copy()
        endpoint_data["user_id"] = user.id
        endpoint = endpoint_repo.create(endpoint_data)

        star_repo = EndpointStarRepository(test_session)
        assert star_repo.is_starred(user.id, endpoint.id) is False

        star_repo.star_endpoint(user.id, endpoint.id)
        assert star_repo.is_starred(user.id, endpoint.id) is True

    def test_get_user_starred_endpoints(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting endpoints starred by a user."""
        user_repo = UserRepository(test_session)
        user = user_repo.create(sample_user_data)

        endpoint_repo = EndpointRepository(test_session)
        star_repo = EndpointStarRepository(test_session)

        # Create and star multiple endpoints
        for i in range(3):
            ds_data = sample_endpoint_data.copy()
            ds_data["user_id"] = user.id
            ds_data["slug"] = f"endpoint-{i}"
            ds = endpoint_repo.create(ds_data)
            star_repo.star_endpoint(user.id, ds.id)

        starred = star_repo.get_user_starred_endpoints(user.id)
        assert len(starred) == 3

    def test_get_endpoint_stargazers(
        self, test_session: Session, sample_user_data: dict, sample_endpoint_data: dict
    ):
        """Test getting users who starred an endpoint."""
        user_repo = UserRepository(test_session)

        # Create first user
        user1 = user_repo.create(sample_user_data)

        # Create second user
        user2_data = sample_user_data.copy()
        user2_data["username"] = "user2"
        user2_data["email"] = "user2@example.com"
        user2 = user_repo.create(user2_data)

        # Create endpoint
        endpoint_repo = EndpointRepository(test_session)
        ds_data = sample_endpoint_data.copy()
        ds_data["user_id"] = user1.id
        endpoint = endpoint_repo.create(ds_data)

        # Both users star the endpoint
        star_repo = EndpointStarRepository(test_session)
        star_repo.star_endpoint(user1.id, endpoint.id)
        star_repo.star_endpoint(user2.id, endpoint.id)

        stargazers = star_repo.get_endpoint_stargazers(endpoint.id)
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
        user_repo = UserRepository(test_session)
        user1 = user_repo.create(sample_user_data)

        user2_data = sample_user_data.copy()
        user2_data["username"] = "user2"
        user2_data["email"] = "user2@example.com"
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
        user_repo = UserRepository(test_session)
        user1 = user_repo.create(sample_user_data)

        user2_data = sample_user_data.copy()
        user2_data["username"] = "user2"
        user2_data["email"] = "user2@example.com"
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
