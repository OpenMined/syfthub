"""Test main FastAPI application."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from syfthub.main import (
    app,
    can_access_endpoint_with_org,
    get_endpoint_by_owner_and_slug,
    get_owner_endpoints,
    main,
    resolve_owner,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.endpoint import Endpoint, EndpointType, EndpointVisibility
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

    def test_get_owner_endpoints_user(self):
        """Test getting endpoints for a user owner."""
        # Setup user
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Setup endpoints
        endpoint1 = Endpoint(
            id=101,
            user_id=1,
            name="Endpoint 1",
            slug="endpoint1",
            description="Test endpoint 1",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PUBLIC,
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
        mock_endpoint_repo = Mock()
        mock_endpoint_repo.get_user_endpoints.return_value = [endpoint1]

        # Test
        endpoints = get_owner_endpoints(test_user, "user", mock_endpoint_repo)

        # Verify
        assert len(endpoints) == 1
        assert endpoints[0].id == 101
        mock_endpoint_repo.get_user_endpoints.assert_called_once_with(1)

    def test_get_owner_endpoints_organization(self):
        """Test getting endpoints for an organization owner."""
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

        # Setup endpoint
        endpoint1 = Endpoint(
            id=101,
            user_id=None,
            organization_id=1,
            name="Org Endpoint",
            slug="org-endpoint",
            description="Test org endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PUBLIC,
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
        mock_endpoint_repo = Mock()
        mock_endpoint_repo.get_organization_endpoints.return_value = [endpoint1]

        # Test
        endpoints = get_owner_endpoints(test_org, "organization", mock_endpoint_repo)

        # Verify
        assert len(endpoints) == 1
        assert endpoints[0].id == 101
        mock_endpoint_repo.get_organization_endpoints.assert_called_once_with(1)

    def test_get_owner_endpoints_invalid_type(self):
        """Test getting endpoints with invalid owner type."""
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repository
        mock_endpoint_repo = Mock()

        endpoints = get_owner_endpoints(test_user, "invalid", mock_endpoint_repo)
        assert endpoints == []

    def test_get_endpoint_by_owner_and_slug_user(self):
        """Test getting endpoint by user owner and slug."""
        # Setup
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        test_endpoint = Endpoint(
            id=101,
            user_id=1,
            name="Test Endpoint",
            slug="test-endpoint",
            description="A test endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PUBLIC,
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
        mock_endpoint_repo = Mock()
        mock_endpoint_repo.get_by_user_and_slug.return_value = test_endpoint

        # Test
        result = get_endpoint_by_owner_and_slug(
            test_user, "user", "test-endpoint", mock_endpoint_repo
        )

        # Verify
        assert result == test_endpoint
        mock_endpoint_repo.get_by_user_and_slug.assert_called_once_with(
            1, "test-endpoint"
        )

    def test_get_endpoint_by_owner_and_slug_organization(self):
        """Test getting endpoint by organization owner and slug."""
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

        test_endpoint = Endpoint(
            id=101,
            user_id=None,
            organization_id=1,
            name="Org Endpoint",
            slug="test-endpoint",
            description="Test org endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PUBLIC,
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
        mock_endpoint_repo = Mock()
        mock_endpoint_repo.get_by_organization_and_slug.return_value = test_endpoint

        # Test
        result = get_endpoint_by_owner_and_slug(
            test_org, "organization", "test-endpoint", mock_endpoint_repo
        )

        # Verify
        assert result == test_endpoint
        mock_endpoint_repo.get_by_organization_and_slug.assert_called_once_with(
            1, "test-endpoint"
        )

    def test_get_endpoint_by_owner_and_slug_invalid_type(self):
        """Test getting endpoint with invalid owner type."""
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Create mock repository
        mock_endpoint_repo = Mock()

        result = get_endpoint_by_owner_and_slug(
            test_user, "invalid", "test-endpoint", mock_endpoint_repo
        )
        assert result is None

    def test_can_access_endpoint_with_org_public(self):
        """Test access to public endpoint."""
        endpoint = Endpoint(
            id=101,
            user_id=1,
            name="Public Endpoint",
            slug="public-endpoint",
            description="A public endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PUBLIC,
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
        assert can_access_endpoint_with_org(endpoint, None, "user") is True

        # Test with user
        test_user = User(
            id=2,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert can_access_endpoint_with_org(endpoint, test_user, "user") is True

    def test_can_access_endpoint_with_org_unauthenticated_private(self):
        """Test unauthenticated access to private endpoint."""
        endpoint = Endpoint(
            id=101,
            user_id=1,
            name="Private Endpoint",
            slug="private-endpoint",
            description="A private endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PRIVATE,
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

        assert can_access_endpoint_with_org(endpoint, None, "user") is False

    def test_can_access_endpoint_with_org_admin_access(self):
        """Test admin access to any endpoint."""
        endpoint = Endpoint(
            id=101,
            user_id=1,
            name="Private Endpoint",
            slug="private-endpoint",
            description="A private endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PRIVATE,
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
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert can_access_endpoint_with_org(endpoint, admin_user, "user") is True

    @patch("syfthub.main.can_access_endpoint")
    def test_can_access_endpoint_with_org_user_owned(self, mock_can_access):
        """Test access to user-owned endpoint."""
        endpoint = Endpoint(
            id=101,
            user_id=1,
            name="User Endpoint",
            slug="user-endpoint",
            description="A user endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PRIVATE,
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
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_can_access.return_value = True

        result = can_access_endpoint_with_org(endpoint, test_user, "user")

        assert result is True
        mock_can_access.assert_called_once_with(endpoint, test_user)

    @patch("syfthub.main.is_organization_member")
    def test_can_access_endpoint_with_org_org_internal(self, mock_is_member):
        """Test access to organization internal endpoint."""
        endpoint = Endpoint(
            id=101,
            user_id=None,
            organization_id=1,
            name="Org Endpoint",
            slug="org-endpoint",
            description="An org endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.INTERNAL,
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
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_is_member.return_value = True
        mock_member_repo = MagicMock()

        result = can_access_endpoint_with_org(
            endpoint, test_user, "organization", mock_member_repo
        )

        assert result is True
        mock_is_member.assert_called_once_with(1, 2, mock_member_repo)

    @patch("syfthub.main.is_organization_member")
    def test_can_access_endpoint_with_org_org_private(self, mock_is_member):
        """Test access to organization private endpoint."""
        endpoint = Endpoint(
            id=101,
            user_id=None,
            organization_id=1,
            name="Org Endpoint",
            slug="org-endpoint",
            description="An org endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PRIVATE,
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
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_is_member.return_value = False
        mock_member_repo = MagicMock()

        result = can_access_endpoint_with_org(
            endpoint, test_user, "organization", mock_member_repo
        )

        assert result is False
        mock_is_member.assert_called_once_with(1, 2, mock_member_repo)


class TestMainEntryPoint:
    """Test main entry point function."""

    def test_main_function_exists(self):
        """Test that main function exists and is callable."""
        assert callable(main)
