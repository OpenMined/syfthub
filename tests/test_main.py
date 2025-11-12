"""Test main FastAPI application."""

from datetime import datetime, timezone
from unittest.mock import patch

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

    @patch("syfthub.main.get_user_by_username")
    @patch("syfthub.main.get_organization_by_slug")
    def test_resolve_owner_user_found(self, mock_get_org, mock_get_user):
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
        mock_get_user.return_value = test_user
        mock_get_org.return_value = None

        # Test
        owner, owner_type = resolve_owner("testuser")

        # Verify
        assert owner == test_user
        assert owner_type == "user"
        mock_get_user.assert_called_once_with("testuser")

    @patch("syfthub.main.get_user_by_username")
    @patch("syfthub.main.get_organization_by_slug")
    def test_resolve_owner_organization_found(self, mock_get_org, mock_get_user):
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
        mock_get_user.return_value = None
        mock_get_org.return_value = test_org

        # Test
        owner, owner_type = resolve_owner("test-org")

        # Verify
        assert owner == test_org
        assert owner_type == "organization"
        mock_get_user.assert_called_once_with("test-org")
        mock_get_org.assert_called_once_with("test-org")

    @patch("syfthub.main.get_user_by_username")
    @patch("syfthub.main.get_organization_by_slug")
    def test_resolve_owner_organization_inactive(self, mock_get_org, mock_get_user):
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
        mock_get_user.return_value = None
        mock_get_org.return_value = test_org

        # Test
        owner, owner_type = resolve_owner("test-org")

        # Verify
        assert owner is None
        assert owner_type == ""

    @patch("syfthub.main.get_user_by_username")
    @patch("syfthub.main.get_organization_by_slug")
    def test_resolve_owner_not_found(self, mock_get_org, mock_get_user):
        """Test resolving owner when neither user nor org exists."""
        # Setup
        mock_get_user.return_value = None
        mock_get_org.return_value = None

        # Test
        owner, owner_type = resolve_owner("nonexistent")

        # Verify
        assert owner is None
        assert owner_type == ""

    @patch("syfthub.main.user_datasites_lookup", {1: {101, 102}})
    @patch("syfthub.main.fake_datasites_db")
    def test_get_owner_datasites_user(self, mock_db):
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

        mock_db.__getitem__.side_effect = lambda x: datasite1 if x == 101 else None
        mock_db.__contains__.side_effect = lambda x: x == 101
        mock_db.values.return_value = [datasite1]

        # Test
        datasites = get_owner_datasites(test_user, "user")

        # Verify
        assert len(datasites) == 1
        assert datasites[0].id == 101

    @patch("syfthub.main.fake_datasites_db")
    def test_get_owner_datasites_organization(self, mock_db):
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

        mock_db.values.return_value = [datasite1]

        # Test
        datasites = get_owner_datasites(test_org, "organization")

        # Verify
        assert len(datasites) == 1
        assert datasites[0].id == 101

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
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        datasites = get_owner_datasites(test_user, "invalid")
        assert datasites == []

    @patch("syfthub.main.get_datasite_by_slug")
    def test_get_datasite_by_owner_and_slug_user(self, mock_get_datasite):
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

        mock_get_datasite.return_value = test_datasite

        # Test
        result = get_datasite_by_owner_and_slug(test_user, "user", "test-datasite")

        # Verify
        assert result == test_datasite
        mock_get_datasite.assert_called_once_with(1, "test-datasite")

    @patch("syfthub.main.fake_datasites_db")
    def test_get_datasite_by_owner_and_slug_organization(self, mock_db):
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

        mock_db.values.return_value = [test_datasite]

        # Test
        result = get_datasite_by_owner_and_slug(
            test_org, "organization", "test-datasite"
        )

        # Verify
        assert result == test_datasite

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
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        result = get_datasite_by_owner_and_slug(test_user, "invalid", "test-datasite")
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
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_is_member.return_value = True

        result = can_access_datasite_with_org(datasite, test_user, "organization")

        assert result is True
        mock_is_member.assert_called_once_with(1, 2)

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
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_is_member.return_value = False

        result = can_access_datasite_with_org(datasite, test_user, "organization")

        assert result is False
        mock_is_member.assert_called_once_with(1, 2)


class TestMainEntryPoint:
    """Test main entry point function."""

    def test_main_function_exists(self):
        """Test that main function exists and is callable."""
        assert callable(main)
