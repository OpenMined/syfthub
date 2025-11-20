"""Test main FastAPI application."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from syfthub.main import (
    app,
    can_access_datasite_with_org,
    get_datasite_by_owner_and_slug,
    get_owner_datasites,
    main,
    resolve_owner,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.datasite import Datasite, DatasiteVisibility
from syfthub.schemas.organization import Organization
from syfthub.schemas.user import User


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_root_endpoint(client: TestClient) -> None:
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Welcome to Syfthub API"
    assert "version" in data
    assert data["docs"] == "/docs"


def test_health_check(client: TestClient) -> None:
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_docs_endpoint(client: TestClient) -> None:
    """Test that the docs endpoint is accessible."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_openapi_endpoint(client: TestClient) -> None:
    """Test that the OpenAPI spec is accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert data["info"]["title"] == "Syfthub API"


class TestUtilityFunctions:
    """Test utility functions in main.py."""

    def test_resolve_owner_user_found(self):
        """Test resolving owner when user exists."""
        # Setup
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        # Create mock repositories
        mock_user_repo = Mock()
        mock_org_repo = Mock()
        mock_user_repo.get_by_username.return_value = test_user
        mock_org_repo.get_by_slug.return_value = None

        # Test
        owner, owner_type = resolve_owner("testuser", mock_user_repo, mock_org_repo)

        # Verify
        assert owner == test_user
        assert owner_type == "user"
        mock_user_repo.get_by_username.assert_called_once_with("testuser")

    def test_resolve_owner_organization_found(self):
        """Test resolving owner when organization exists."""
        # Setup
        test_org = Organization(
            id=1,
            name="Test Org",
            slug="test-org",
            description="A test org",
            avatar_url="",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repositories
        mock_user_repo = Mock()
        mock_org_repo = Mock()
        mock_user_repo.get_by_username.return_value = None
        mock_org_repo.get_by_slug.return_value = test_org

        # Test
        owner, owner_type = resolve_owner("test-org", mock_user_repo, mock_org_repo)

        # Verify
        assert owner == test_org
        assert owner_type == "organization"
        mock_user_repo.get_by_username.assert_called_once_with("test-org")
        mock_org_repo.get_by_slug.assert_called_once_with("test-org")

    def test_resolve_owner_organization_inactive(self):
        """Test resolving owner when organization exists but is inactive."""
        # Setup
        test_org = Organization(
            id=1,
            name="Test Org",
            slug="test-org",
            description="A test org",
            avatar_url="",
            is_active=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        # Create mock repositories
        mock_user_repo = Mock()
        mock_org_repo = Mock()
        mock_user_repo.get_by_username.return_value = None
        mock_org_repo.get_by_slug.return_value = test_org

        # Test
        owner, owner_type = resolve_owner("test-org", mock_user_repo, mock_org_repo)

        # Verify
        assert owner is None
        assert owner_type == ""

    def test_resolve_owner_not_found(self):
        """Test resolving owner when neither user nor org exists."""
        # Setup
        mock_user_repo = Mock()
        mock_org_repo = Mock()
        mock_user_repo.get_by_username.return_value = None
        mock_org_repo.get_by_slug.return_value = None

        # Test
        owner, owner_type = resolve_owner("nonexistent", mock_user_repo, mock_org_repo)

        # Verify
        assert owner is None
        assert owner_type == ""

    def test_get_owner_datasites_user(self):
        """Test getting datasites for a user owner."""
        # Setup user
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Setup datasites
        datasite1 = Datasite(
            id=101,
            user_id=1,
            name="Datasite 1",
            slug="datasite1",
            description="Test datasite 1",
            visibility=DatasiteVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repository
        mock_datasite_repo = Mock()
        mock_datasite_repo.get_user_datasites.return_value = [datasite1]

        # Test
        datasites = get_owner_datasites(test_user, "user", mock_datasite_repo)

        # Verify
        assert len(datasites) == 1
        assert datasites[0].id == 101
        mock_datasite_repo.get_user_datasites.assert_called_once_with(1)

    def test_get_owner_datasites_organization(self):
        """Test getting datasites for an organization owner."""
        # Setup organization
        test_org = Organization(
            id=1,
            name="Test Org",
            slug="test-org",
            description="A test org",
            avatar_url="",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Setup datasite
        datasite1 = Datasite(
            id=101,
            user_id=None,
            organization_id=1,
            name="Org Datasite",
            slug="org-datasite",
            description="Test org datasite",
            visibility=DatasiteVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repository
        mock_datasite_repo = Mock()
        mock_datasite_repo.get_organization_datasites.return_value = [datasite1]

        # Test
        datasites = get_owner_datasites(test_org, "organization", mock_datasite_repo)

        # Verify
        assert len(datasites) == 1
        assert datasites[0].id == 101
        mock_datasite_repo.get_organization_datasites.assert_called_once_with(1)

    def test_get_owner_datasites_invalid_type(self):
        """Test getting datasites with invalid owner type."""
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repository
        mock_datasite_repo = Mock()

        datasites = get_owner_datasites(test_user, "invalid", mock_datasite_repo)
        assert datasites == []

    def test_get_datasite_by_owner_and_slug_user(self):
        """Test getting datasite by user owner and slug."""
        # Setup
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        test_datasite = Datasite(
            id=101,
            user_id=1,
            name="Test Datasite",
            slug="test-datasite",
            description="A test datasite",
            visibility=DatasiteVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repository
        mock_datasite_repo = Mock()
        mock_datasite_repo.get_by_user_and_slug.return_value = test_datasite

        # Test
        result = get_datasite_by_owner_and_slug(
            test_user, "user", "test-datasite", mock_datasite_repo
        )

        # Verify
        assert result == test_datasite
        mock_datasite_repo.get_by_user_and_slug.assert_called_once_with(
            1, "test-datasite"
        )

    def test_get_datasite_by_owner_and_slug_organization(self):
        """Test getting datasite by organization owner and slug."""
        # Setup
        test_org = Organization(
            id=1,
            name="Test Org",
            slug="test-org",
            description="A test org",
            avatar_url="",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        test_datasite = Datasite(
            id=101,
            user_id=None,
            organization_id=1,
            name="Org Datasite",
            slug="test-datasite",
            description="Test org datasite",
            visibility=DatasiteVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repository
        mock_datasite_repo = Mock()
        mock_datasite_repo.get_by_organization_and_slug.return_value = test_datasite

        # Test
        result = get_datasite_by_owner_and_slug(
            test_org, "organization", "test-datasite", mock_datasite_repo
        )

        # Verify
        assert result == test_datasite
        mock_datasite_repo.get_by_organization_and_slug.assert_called_once_with(
            1, "test-datasite"
        )

    def test_get_datasite_by_owner_and_slug_invalid_type(self):
        """Test getting datasite with invalid owner type."""
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repository
        mock_datasite_repo = Mock()

        result = get_datasite_by_owner_and_slug(
            test_user, "invalid", "test-datasite", mock_datasite_repo
        )
        assert result is None

    def test_can_access_datasite_with_org_public(self):
        """Test access to public datasite."""
        datasite = Datasite(
            id=101,
            user_id=1,
            name="Public Datasite",
            slug="public-datasite",
            description="A public datasite",
            visibility=DatasiteVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Test with no user
        assert can_access_datasite_with_org(datasite, None, "user") is True

        # Test with user
        test_user = User(
            id=2,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert can_access_datasite_with_org(datasite, test_user, "user") is True

    def test_can_access_datasite_with_org_unauthenticated_private(self):
        """Test unauthenticated access to private datasite."""
        datasite = Datasite(
            id=101,
            user_id=1,
            name="Private Datasite",
            slug="private-datasite",
            description="A private datasite",
            visibility=DatasiteVisibility.PRIVATE,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert can_access_datasite_with_org(datasite, None, "user") is False

    def test_can_access_datasite_with_org_admin_access(self):
        """Test admin access to any datasite."""
        datasite = Datasite(
            id=101,
            user_id=1,
            name="Private Datasite",
            slug="private-datasite",
            description="A private datasite",
            visibility=DatasiteVisibility.PRIVATE,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        admin_user = User(
            id=2,
            username="admin",
            email="admin@example.com",
            full_name="Admin User",
            age=30,
            role=UserRole.ADMIN,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert can_access_datasite_with_org(datasite, admin_user, "user") is True

    @patch("syfthub.main.can_access_datasite")
    def test_can_access_datasite_with_org_user_owned(self, mock_can_access):
        """Test access to user-owned datasite."""
        datasite = Datasite(
            id=101,
            user_id=1,
            name="User Datasite",
            slug="user-datasite",
            description="A user datasite",
            visibility=DatasiteVisibility.PRIVATE,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        test_user = User(
            id=2,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_can_access.return_value = True

        result = can_access_datasite_with_org(datasite, test_user, "user")

        assert result is True
        mock_can_access.assert_called_once_with(datasite, test_user)

    @patch("syfthub.main.is_organization_member")
    def test_can_access_datasite_with_org_org_internal(self, mock_is_member):
        """Test access to organization internal datasite."""
        datasite = Datasite(
            id=101,
            user_id=None,
            organization_id=1,
            name="Org Datasite",
            slug="org-datasite",
            description="An org datasite",
            visibility=DatasiteVisibility.INTERNAL,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        test_user = User(
            id=2,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_is_member.return_value = True
        mock_member_repo = MagicMock()

        result = can_access_datasite_with_org(
            datasite, test_user, "organization", mock_member_repo
        )

        assert result is True
        mock_is_member.assert_called_once_with(1, 2, mock_member_repo)

    @patch("syfthub.main.is_organization_member")
    def test_can_access_datasite_with_org_org_private(self, mock_is_member):
        """Test access to organization private datasite."""
        datasite = Datasite(
            id=101,
            user_id=None,
            organization_id=1,
            name="Org Datasite",
            slug="org-datasite",
            description="An org datasite",
            visibility=DatasiteVisibility.PRIVATE,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        test_user = User(
            id=2,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            public_key="test_public_key",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_is_member.return_value = False
        mock_member_repo = MagicMock()

        result = can_access_datasite_with_org(
            datasite, test_user, "organization", mock_member_repo
        )

        assert result is False
        mock_is_member.assert_called_once_with(1, 2, mock_member_repo)


class TestMainEntryPoint:
    """Test main entry point function."""

    def test_main_function_exists(self):
        """Test that main function exists and is callable."""
        assert callable(main)
