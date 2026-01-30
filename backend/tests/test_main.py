"""Test main FastAPI application."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from syfthub.main import (
    PROXY_TIMEOUT_DATA_SOURCE,
    PROXY_TIMEOUT_MODEL,
    app,
    build_invocation_url,
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
            tags=[],
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
            tags=[],
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
            tags=[],
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
            tags=[],
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
            tags=[],
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
            tags=[],
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
            tags=[],
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
            tags=[],
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
            tags=[],
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
            tags=[],
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


class TestBuildInvocationUrl:
    """Tests for build_invocation_url helper function."""

    @pytest.fixture
    def user_with_domain(self):
        """Create a test user with domain configured."""
        return User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            domain="https://api.example.com",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def user_without_domain(self):
        """Create a test user without domain configured."""
        return User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            domain=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def org_with_domain(self):
        """Create a test organization with domain configured."""
        return Organization(
            id=1,
            name="Test Org",
            slug="test-org",
            description="A test org",
            avatar_url="",
            is_active=True,
            domain="https://api.testorg.com",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def test_build_url_from_user_with_domain(self, user_with_domain):
        """Test building URL from user owner with domain."""
        connections = [
            {
                "type": "rest_api",
                "enabled": True,
                "config": {"url": "v1"},
            }
        ]
        result = build_invocation_url(
            user_with_domain, connections, "my-endpoint", "testuser/my-endpoint"
        )
        assert result == "https://api.example.com/v1/api/v1/endpoints/my-endpoint/query"

    def test_build_url_from_org_with_domain(self, org_with_domain):
        """Test building URL from organization owner with domain."""
        connections = [
            {
                "type": "http",
                "enabled": True,
                "config": {"url": "api"},
            }
        ]
        result = build_invocation_url(
            org_with_domain, connections, "org-endpoint", "test-org/org-endpoint"
        )
        assert (
            result == "https://api.testorg.com/api/api/v1/endpoints/org-endpoint/query"
        )

    def test_build_url_skips_disabled_connections(self, user_with_domain):
        """Test that disabled connections are skipped."""
        connections = [
            {
                "type": "http",
                "enabled": False,
                "config": {"url": "disabled-path"},
            },
            {
                "type": "http",
                "enabled": True,
                "config": {"url": "enabled-path"},
            },
        ]
        result = build_invocation_url(
            user_with_domain, connections, "my-endpoint", "testuser/my-endpoint"
        )
        assert (
            result
            == "https://api.example.com/enabled-path/api/v1/endpoints/my-endpoint/query"
        )

    def test_build_url_defaults_enabled_to_true(self, user_with_domain):
        """Test that connections without enabled field default to True."""
        connections = [
            {
                "type": "http",
                "config": {"url": "default-enabled-path"},
            }
        ]
        result = build_invocation_url(
            user_with_domain, connections, "my-endpoint", "testuser/my-endpoint"
        )
        assert (
            result
            == "https://api.example.com/default-enabled-path/api/v1/endpoints/my-endpoint/query"
        )

    def test_build_url_fallback_to_first_connection(self, user_with_domain):
        """Test fallback to first connection when no enabled ones found."""
        connections = [
            {
                "type": "http",
                "enabled": False,
                "config": {"url": "fallback-path"},
            }
        ]
        result = build_invocation_url(
            user_with_domain, connections, "my-endpoint", "testuser/my-endpoint"
        )
        assert (
            result
            == "https://api.example.com/fallback-path/api/v1/endpoints/my-endpoint/query"
        )

    def test_build_url_no_domain_raises_error(self, user_without_domain):
        """Test that missing domain raises HTTPException."""
        from fastapi import HTTPException

        connections = [
            {
                "type": "http",
                "enabled": True,
                "config": {"url": "some-path"},
            }
        ]

        with pytest.raises(HTTPException) as exc_info:
            build_invocation_url(
                user_without_domain,
                connections,
                "my-endpoint",
                "testuser/my-endpoint",
            )

        assert exc_info.value.status_code == 400
        assert "no domain configured" in exc_info.value.detail

    def test_build_url_empty_connections_raises_error(self, user_with_domain):
        """Test that empty connections list raises HTTPException."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            build_invocation_url(
                user_with_domain, [], "my-endpoint", "testuser/my-endpoint"
            )

        assert exc_info.value.status_code == 400
        assert "no connections configured" in exc_info.value.detail

    def test_build_url_websocket_protocol(self, user_with_domain):
        """Test building URL with websocket connection type."""
        connections = [
            {
                "type": "websocket",
                "enabled": True,
                "config": {"url": "ws/v1"},
            }
        ]
        result = build_invocation_url(
            user_with_domain, connections, "my-endpoint", "testuser/my-endpoint"
        )
        assert (
            result == "wss://api.example.com/ws/v1/api/v1/endpoints/my-endpoint/query"
        )

    def test_build_url_empty_path(self, user_with_domain):
        """Test building URL when config.url is empty."""
        connections = [
            {
                "type": "http",
                "enabled": True,
                "config": {"url": ""},
            }
        ]
        result = build_invocation_url(
            user_with_domain, connections, "my-endpoint", "testuser/my-endpoint"
        )
        assert result == "https://api.example.com/api/v1/endpoints/my-endpoint/query"

    def test_build_url_with_leading_slash_in_path(self, user_with_domain):
        """Test building URL when config.url has leading slash."""
        connections = [
            {
                "type": "http",
                "enabled": True,
                "config": {"url": "/api/v2"},
            }
        ]
        result = build_invocation_url(
            user_with_domain, connections, "my-endpoint", "testuser/my-endpoint"
        )
        assert (
            result
            == "https://api.example.com/api/v2/api/v1/endpoints/my-endpoint/query"
        )


class TestTimeoutConstants:
    """Tests for timeout configuration constants."""

    def test_data_source_timeout(self):
        """Test data source timeout is 30 seconds."""
        assert PROXY_TIMEOUT_DATA_SOURCE == 30.0

    def test_model_timeout(self):
        """Test model timeout is 120 seconds."""
        assert PROXY_TIMEOUT_MODEL == 120.0


class TestInvokeOwnerEndpoint:
    """Tests for the POST /{owner_slug}/{endpoint_slug} proxy endpoint."""

    @pytest.fixture
    def mock_endpoint_with_connection(self):
        """Create a test endpoint with connection configured."""
        return Endpoint(
            id=101,
            user_id=1,
            name="Test Model",
            slug="test-model",
            description="A test model endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            tags=[],
            stars_count=0,
            policies=[],
            connect=[
                {
                    "type": "http",
                    "enabled": True,
                    "description": "HTTP connection",
                    "config": {"url": ""},  # Path only, domain comes from owner
                }
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_data_source_endpoint(self):
        """Create a test data source endpoint."""
        return Endpoint(
            id=102,
            user_id=1,
            name="Test Data Source",
            slug="test-datasource",
            description="A test data source endpoint",
            type=EndpointType.DATA_SOURCE,
            visibility=EndpointVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            tags=[],
            stars_count=0,
            policies=[],
            connect=[
                {
                    "type": "http",
                    "enabled": True,
                    "config": {"url": ""},  # Path only, domain comes from owner
                }
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_user(self):
        """Create a test user."""
        return User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            domain="https://syftai-space:8080",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @patch("syfthub.main.validate_domain_for_ssrf")
    @patch("syfthub.main.httpx.AsyncClient")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_success(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_async_client,
        mock_ssrf_check,
        client,
        mock_endpoint_with_connection,
        mock_user,
    ):
        """Test successful endpoint invocation."""
        # Setup mocks
        mock_get_user.return_value = None  # Public endpoint, no auth needed
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = mock_endpoint_with_connection

        # Setup httpx mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "summary": {"message": {"content": "Hello from endpoint"}}
        }

        # Use AsyncMock for async context manager
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        # Make request
        response = client.post(
            "/testuser/test-model",
            json={
                "user_email": "test@example.com",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data

    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_owner_not_found(self, mock_get_user, mock_resolve, client):
        """Test endpoint invocation with non-existent owner."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (None, "")

        response = client.post(
            "/nonexistent/test-model",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_not_found(
        self, mock_get_user, mock_resolve, mock_get_endpoint, client, mock_user
    ):
        """Test endpoint invocation with non-existent endpoint."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = None

        response = client.post(
            "/testuser/nonexistent",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 404

    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_no_connection(
        self, mock_get_user, mock_resolve, mock_get_endpoint, client, mock_user
    ):
        """Test endpoint invocation with no connections configured."""
        endpoint_no_connection = Endpoint(
            id=101,
            user_id=1,
            name="No Connection",
            slug="no-connection",
            description="Endpoint without connection",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="",
            tags=[],
            stars_count=0,
            policies=[],
            connect=[],  # No connections
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = endpoint_no_connection

        response = client.post(
            "/testuser/no-connection",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 400
        assert "no connections configured" in response.json()["detail"]

    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_no_domain(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        client,
        mock_endpoint_with_connection,
    ):
        """Test endpoint invocation when owner has no domain configured."""
        user_without_domain = User(
            id=1,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            domain=None,  # No domain configured
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_get_user.return_value = None
        mock_resolve.return_value = (user_without_domain, "user")
        mock_get_endpoint.return_value = mock_endpoint_with_connection

        response = client.post(
            "/testuser/test-model",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 400
        assert "no domain configured" in response.json()["detail"]

    @patch("syfthub.main.validate_domain_for_ssrf")
    @patch("syfthub.main.httpx.AsyncClient")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_timeout(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_async_client,
        mock_ssrf_check,
        client,
        mock_endpoint_with_connection,
        mock_user,
    ):
        """Test endpoint invocation with timeout."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = mock_endpoint_with_connection

        # Simulate timeout with AsyncMock
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = httpx.TimeoutException("Timeout")
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        response = client.post(
            "/testuser/test-model",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 504
        assert "timed out" in response.json()["detail"]

    @patch("syfthub.main.validate_domain_for_ssrf")
    @patch("syfthub.main.httpx.AsyncClient")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_connection_error(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_async_client,
        mock_ssrf_check,
        client,
        mock_endpoint_with_connection,
        mock_user,
    ):
        """Test endpoint invocation with connection error."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = mock_endpoint_with_connection

        # Simulate connection error with AsyncMock
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = httpx.RequestError("Connection refused")
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        response = client.post(
            "/testuser/test-model",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 502
        assert "Failed to connect" in response.json()["detail"]

    @patch("syfthub.main.validate_domain_for_ssrf")
    @patch("syfthub.main.httpx.AsyncClient")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_403_forbidden(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_async_client,
        mock_ssrf_check,
        client,
        mock_endpoint_with_connection,
        mock_user,
    ):
        """Test endpoint invocation with 403 from target."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = mock_endpoint_with_connection

        # Simulate 403 response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "User not in visibility list"}

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        response = client.post(
            "/testuser/test-model",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 403
        assert "denied access" in response.json()["detail"]

    @patch("syfthub.main.validate_domain_for_ssrf")
    @patch("syfthub.main.httpx.AsyncClient")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_target_error(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_async_client,
        mock_ssrf_check,
        client,
        mock_endpoint_with_connection,
        mock_user,
    ):
        """Test endpoint invocation with error from target."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = mock_endpoint_with_connection

        # Simulate 500 response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}
        mock_response.text = "Internal server error"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        response = client.post(
            "/testuser/test-model",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 500
        assert "Target endpoint error" in response.json()["detail"]

    @patch("syfthub.main.validate_domain_for_ssrf")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_endpoint_invalid_json_body(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_ssrf_check,
        client,
        mock_user,
        mock_endpoint_with_connection,
    ):
        """Test endpoint invocation with invalid JSON body."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = mock_endpoint_with_connection

        response = client.post(
            "/testuser/test-model",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]


class TestMainEntryPoint:
    """Test main entry point function."""

    def test_main_function_exists(self):
        """Test that main function exists and is callable."""
        assert callable(main)
