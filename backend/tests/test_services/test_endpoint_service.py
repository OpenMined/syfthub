"""Tests for EndpointService."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from syfthub.database.connection import get_db_session
from syfthub.schemas.endpoint import (
    Endpoint,
    EndpointCreate,
    EndpointPublicResponse,
    EndpointResponse,
    EndpointType,
    EndpointUpdate,
    EndpointVisibility,
)
from syfthub.schemas.user import User
from syfthub.services.endpoint_service import EndpointService


@pytest.fixture
def db_session():
    """Get database session for testing."""
    session = next(get_db_session())
    yield session
    session.close()


@pytest.fixture
def endpoint_service(db_session):
    """Create EndpointService instance for testing."""
    return EndpointService(db_session)


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
        key_created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        age=25,
        public_key="public_key",
        password_hash="hashed_pass",
    )


@pytest.fixture
def sample_endpoint():
    """Sample endpoint for testing."""
    return Endpoint(
        id=1,
        name="Test Endpoint",
        slug="test-endpoint",
        description="A test endpoint",
        type=EndpointType.MODEL,
        visibility=EndpointVisibility.PUBLIC,
        version="1.0.0",
        readme="# Test Endpoint\n\nA test endpoint for unit tests.",
        tags=[],
        policies=[],
        connect=[],
        is_active=True,
        contributors=[],
        user_id=1,
        organization_id=None,
        stars_count=0,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
    )


class TestEndpointServiceCreate:
    """Test endpoint creation."""

    def test_create_user_endpoint_success(
        self,
        endpoint_service,
        sample_user,
        sample_endpoint,
    ):
        """Test successful user endpoint creation."""
        endpoint_data = EndpointCreate(
            name="Test Endpoint",
            slug="test-endpoint",
            description="A test endpoint",
            type=EndpointType.MODEL,
            visibility=EndpointVisibility.PUBLIC,
        )

        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "slug_exists_for_user",
                return_value=False,
            ),
            patch.object(
                endpoint_service.endpoint_repository,
                "create_endpoint",
                return_value=sample_endpoint,
            ),
        ):
            result = endpoint_service.create_endpoint(
                endpoint_data, 1, is_organization=False
            )

            assert isinstance(result, EndpointResponse)
            assert result.name == "Test Endpoint"
            assert result.slug == "test-endpoint"

    def test_create_user_endpoint_slug_exists(
        self,
        endpoint_service,
        sample_user,
    ):
        """Test user endpoint creation with existing slug."""
        endpoint_data = EndpointCreate(
            name="Test Endpoint",
            slug="existing-slug",
            description="A test endpoint",
            type=EndpointType.MODEL,
        )

        with patch.object(
            endpoint_service.endpoint_repository,
            "slug_exists_for_user",
            return_value=True,
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.create_endpoint(
                    endpoint_data, 1, is_organization=False
                )

            assert exc_info.value.status_code == 400
            assert "slug already exists" in str(exc_info.value.detail)

    def test_create_organization_endpoint_not_member(
        self, endpoint_service, sample_user
    ):
        """Test organization endpoint creation without membership."""
        endpoint_data = EndpointCreate(
            name="Test Endpoint",
            slug="test-endpoint",
            description="A test endpoint",
            type=EndpointType.MODEL,
        )

        with patch.object(
            endpoint_service.org_member_repository, "is_member", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.create_endpoint(
                    endpoint_data, 1, is_organization=True, current_user=sample_user
                )

            assert exc_info.value.status_code == 403
            assert "not a member of organization" in str(exc_info.value.detail)

    def test_create_organization_endpoint_slug_exists(
        self, endpoint_service, sample_user
    ):
        """Test organization endpoint creation with existing slug."""
        endpoint_data = EndpointCreate(
            name="Test Endpoint",
            slug="existing-slug",
            description="A test endpoint",
            type=EndpointType.MODEL,
        )

        with (
            patch.object(
                endpoint_service.org_member_repository, "is_member", return_value=True
            ),
            patch.object(
                endpoint_service.endpoint_repository,
                "slug_exists_for_organization",
                return_value=True,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.create_endpoint(
                    endpoint_data, 1, is_organization=True, current_user=sample_user
                )

            assert exc_info.value.status_code == 400
            assert "slug already exists for this organization" in str(
                exc_info.value.detail
            )

    def test_create_endpoint_failure(
        self,
        endpoint_service,
        sample_user,
    ):
        """Test endpoint creation failure."""
        endpoint_data = EndpointCreate(
            name="Test Endpoint",
            slug="test-endpoint",
            description="A test endpoint",
            type=EndpointType.MODEL,
        )

        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "slug_exists_for_user",
                return_value=False,
            ),
            patch.object(
                endpoint_service.endpoint_repository,
                "create_endpoint",
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.create_endpoint(
                    endpoint_data, 1, is_organization=False
                )

            assert exc_info.value.status_code == 500
            assert "Failed to create endpoint" in str(exc_info.value.detail)


class TestEndpointServiceGet:
    """Test endpoint retrieval."""

    def test_get_endpoint_by_user_and_slug(self, endpoint_service, sample_endpoint):
        """Test getting endpoint by user and slug."""
        with patch.object(
            endpoint_service.endpoint_repository,
            "get_by_user_and_slug",
            return_value=sample_endpoint,
        ):
            result = endpoint_service.get_endpoint_by_user_and_slug(1, "test-endpoint")

            assert result == sample_endpoint

    def test_get_endpoint_by_user_and_slug_not_found(self, endpoint_service):
        """Test getting non-existent endpoint by user and slug."""
        with patch.object(
            endpoint_service.endpoint_repository,
            "get_by_user_and_slug",
            return_value=None,
        ):
            result = endpoint_service.get_endpoint_by_user_and_slug(1, "nonexistent")

            assert result is None

    def test_get_endpoint_by_org_and_slug(self, endpoint_service, sample_endpoint):
        """Test getting endpoint by organization and slug."""
        with patch.object(
            endpoint_service.endpoint_repository,
            "get_by_organization_and_slug",
            return_value=sample_endpoint,
        ):
            result = endpoint_service.get_endpoint_by_org_and_slug(1, "test-endpoint")

            assert result == sample_endpoint

    def test_get_endpoint_by_org_and_slug_not_found(self, endpoint_service):
        """Test getting non-existent endpoint by organization and slug."""
        with patch.object(
            endpoint_service.endpoint_repository,
            "get_by_organization_and_slug",
            return_value=None,
        ):
            result = endpoint_service.get_endpoint_by_org_and_slug(1, "nonexistent")

            assert result is None

    def test_get_public_endpoints(self, endpoint_service):
        """Test getting public endpoints."""
        mock_public_endpoints = [
            EndpointPublicResponse(
                name="Public Endpoint",
                slug="public-endpoint",
                description="A public endpoint",
                type=EndpointType.MODEL,
                owner_username="testuser",
                contributors_count=1,
                version="1.0.0",
                readme="# Public Endpoint",
                tags=[],
                stars_count=5,
                policies=[],
                connect=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ]

        with patch.object(
            endpoint_service.endpoint_repository,
            "get_public_endpoints",
            return_value=mock_public_endpoints,
        ):
            result = endpoint_service.get_public_endpoints()

            assert len(result) == 1
            assert result[0].name == "Public Endpoint"


class TestEndpointServiceUpdate:
    """Test endpoint update."""

    def test_update_endpoint_success(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test successful endpoint update."""
        update_data = EndpointUpdate(name="Updated Endpoint")
        endpoint_dict = sample_endpoint.model_dump()
        endpoint_dict.update({"name": "Updated Endpoint"})
        updated_endpoint = Endpoint(**endpoint_dict)

        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_id",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=True),
            patch.object(
                endpoint_service.endpoint_repository,
                "update_endpoint",
                return_value=updated_endpoint,
            ),
        ):
            result = endpoint_service.update_endpoint(1, update_data, sample_user)

            assert result.name == "Updated Endpoint"

    def test_update_endpoint_not_found(self, endpoint_service, sample_user):
        """Test updating non-existent endpoint."""
        update_data = EndpointUpdate(name="Updated Endpoint")

        with patch.object(
            endpoint_service.endpoint_repository, "get_by_id", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.update_endpoint(999, update_data, sample_user)

            assert exc_info.value.status_code == 404
            assert "Endpoint not found" in str(exc_info.value.detail)

    def test_update_endpoint_permission_denied(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test permission denied for endpoint update."""
        update_data = EndpointUpdate(name="Updated Endpoint")

        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_id",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.update_endpoint(1, update_data, sample_user)

            assert exc_info.value.status_code == 403
            assert "Permission denied" in str(exc_info.value.detail)

    def test_update_endpoint_failure(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test endpoint update failure."""
        update_data = EndpointUpdate(name="Updated Endpoint")

        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_id",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=True),
            patch.object(
                endpoint_service.endpoint_repository,
                "update_endpoint",
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.update_endpoint(1, update_data, sample_user)

            assert exc_info.value.status_code == 500
            assert "Failed to update endpoint" in str(exc_info.value.detail)


class TestEndpointServiceLists:
    """Test endpoint list methods."""

    def test_get_user_endpoints_basic(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test getting user endpoints."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_user_endpoints",
                return_value=[sample_endpoint],
            ),
            patch.object(endpoint_service, "_can_access_endpoint", return_value=True),
            patch.object(endpoint_service, "_can_see_full_details", return_value=True),
        ):
            result = endpoint_service.get_user_endpoints(1, current_user=sample_user)

            assert len(result) == 1
            assert result[0].name == "Test Endpoint"

    def test_get_user_endpoints_no_access(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test getting user endpoints with no access."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_user_endpoints",
                return_value=[sample_endpoint],
            ),
            patch.object(endpoint_service, "_can_access_endpoint", return_value=False),
        ):
            result = endpoint_service.get_user_endpoints(1, current_user=sample_user)

            assert len(result) == 0

    def test_get_organization_endpoints_basic(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test getting organization endpoints."""
        endpoint_dict = sample_endpoint.model_dump()
        endpoint_dict.update(
            {"is_organization_owned": True, "organization_id": 1, "user_id": None}
        )
        org_endpoint = Endpoint(**endpoint_dict)

        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_organization_endpoints",
                return_value=[org_endpoint],
            ),
            patch.object(endpoint_service, "_can_access_endpoint", return_value=True),
            patch.object(endpoint_service, "_can_see_full_details", return_value=True),
        ):
            result = endpoint_service.get_organization_endpoints(
                1, current_user=sample_user
            )

            assert len(result) == 1
            assert result[0].name == "Test Endpoint"

    def test_get_organization_endpoints_no_access(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test getting organization endpoints with no access."""
        endpoint_dict = sample_endpoint.model_dump()
        endpoint_dict.update(
            {"is_organization_owned": True, "organization_id": 1, "user_id": None}
        )
        org_endpoint = Endpoint(**endpoint_dict)

        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_organization_endpoints",
                return_value=[org_endpoint],
            ),
            patch.object(endpoint_service, "_can_access_endpoint", return_value=False),
        ):
            result = endpoint_service.get_organization_endpoints(
                1, current_user=sample_user
            )

            assert len(result) == 0


class TestEndpointServiceDelete:
    """Test endpoint deletion."""

    def test_delete_endpoint_success(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test successful endpoint deletion."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_id",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=True),
            patch.object(
                endpoint_service.endpoint_repository,
                "delete_endpoint",
                return_value=True,
            ),
        ):
            result = endpoint_service.delete_endpoint(1, sample_user)

            assert result is True

    def test_delete_endpoint_not_found(self, endpoint_service, sample_user):
        """Test deleting non-existent endpoint."""
        with patch.object(
            endpoint_service.endpoint_repository, "get_by_id", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.delete_endpoint(999, sample_user)

            assert exc_info.value.status_code == 404
            assert "Endpoint not found" in str(exc_info.value.detail)

    def test_delete_endpoint_permission_denied(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test permission denied for endpoint deletion."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_id",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.delete_endpoint(1, sample_user)

            assert exc_info.value.status_code == 403
            assert "Permission denied" in str(exc_info.value.detail)

    def test_delete_endpoint_failure(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test endpoint deletion failure."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_id",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=True),
            patch.object(
                endpoint_service.endpoint_repository,
                "delete_endpoint",
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.delete_endpoint(1, sample_user)

            assert exc_info.value.status_code == 500
            assert "Failed to delete endpoint" in str(exc_info.value.detail)


class TestEndpointServiceDeleteBySlug:
    """Test endpoint deletion by slug."""

    def test_delete_endpoint_by_slug_success(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test successful endpoint deletion by slug."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_user_and_slug",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=True),
            patch.object(
                endpoint_service.endpoint_repository,
                "delete_endpoint",
                return_value=True,
            ),
        ):
            result = endpoint_service.delete_endpoint_by_slug(
                "test-endpoint", sample_user
            )

            assert result is True

    def test_delete_endpoint_by_slug_not_found(self, endpoint_service, sample_user):
        """Test deleting non-existent endpoint by slug."""
        with patch.object(
            endpoint_service.endpoint_repository,
            "get_by_user_and_slug",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.delete_endpoint_by_slug("nonexistent", sample_user)

            assert exc_info.value.status_code == 404
            assert "Endpoint not found" in str(exc_info.value.detail)

    def test_delete_endpoint_by_slug_permission_denied(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test permission denied for endpoint deletion by slug."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_user_and_slug",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.delete_endpoint_by_slug("test-endpoint", sample_user)

            assert exc_info.value.status_code == 403
            assert "Permission denied" in str(exc_info.value.detail)

    def test_delete_endpoint_by_slug_failure(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test endpoint deletion by slug failure."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_user_and_slug",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=True),
            patch.object(
                endpoint_service.endpoint_repository,
                "delete_endpoint",
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.delete_endpoint_by_slug("test-endpoint", sample_user)

            assert exc_info.value.status_code == 500
            assert "Failed to delete endpoint" in str(exc_info.value.detail)

    def test_delete_endpoint_by_slug_uses_correct_user_id(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test that delete_endpoint_by_slug looks up using the current user's ID."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_user_and_slug",
                return_value=sample_endpoint,
            ) as mock_get,
            patch.object(endpoint_service, "_can_modify_endpoint", return_value=True),
            patch.object(
                endpoint_service.endpoint_repository,
                "delete_endpoint",
                return_value=True,
            ),
        ):
            endpoint_service.delete_endpoint_by_slug("test-endpoint", sample_user)

            # Verify the lookup was called with the correct user ID
            mock_get.assert_called_once_with(sample_user.id, "test-endpoint")


class TestEndpointServiceStar:
    """Test endpoint star functionality."""

    def test_star_endpoint_success(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test successful endpoint starring."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_id",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_access_endpoint", return_value=True),
            patch.object(
                endpoint_service.star_repository, "star_endpoint", return_value=True
            ),
            patch.object(endpoint_service.endpoint_repository, "increment_stars"),
        ):
            result = endpoint_service.star_endpoint(1, sample_user)

            assert result is True

    def test_star_endpoint_not_found(self, endpoint_service, sample_user):
        """Test starring non-existent endpoint."""
        with patch.object(
            endpoint_service.endpoint_repository, "get_by_id", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.star_endpoint(999, sample_user)

            assert exc_info.value.status_code == 404
            assert "Endpoint not found" in str(exc_info.value.detail)

    def test_star_endpoint_no_access(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test starring endpoint without access."""
        with (
            patch.object(
                endpoint_service.endpoint_repository,
                "get_by_id",
                return_value=sample_endpoint,
            ),
            patch.object(endpoint_service, "_can_access_endpoint", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                endpoint_service.star_endpoint(1, sample_user)

            assert exc_info.value.status_code == 404
            assert "Endpoint not found" in str(exc_info.value.detail)

    def test_unstar_endpoint_success(self, endpoint_service, sample_user):
        """Test successful endpoint unstarring."""
        with (
            patch.object(
                endpoint_service.star_repository, "unstar_endpoint", return_value=True
            ),
            patch.object(endpoint_service.endpoint_repository, "decrement_stars"),
        ):
            result = endpoint_service.unstar_endpoint(1, sample_user)

            assert result is True

    def test_unstar_endpoint_not_starred(self, endpoint_service, sample_user):
        """Test unstarring not-starred endpoint."""
        with patch.object(
            endpoint_service.star_repository, "unstar_endpoint", return_value=False
        ):
            result = endpoint_service.unstar_endpoint(1, sample_user)

            assert result is False

    def test_is_endpoint_starred(self, endpoint_service, sample_user):
        """Test checking if endpoint is starred."""
        with patch.object(
            endpoint_service.star_repository, "is_starred", return_value=True
        ):
            result = endpoint_service.is_endpoint_starred(1, sample_user)

            assert result is True


class TestEndpointServicePermissions:
    """Test endpoint permission methods."""

    def test_can_access_endpoint_public(self, endpoint_service, sample_endpoint):
        """Test access to public endpoint."""
        sample_endpoint.visibility = EndpointVisibility.PUBLIC

        result = endpoint_service._can_access_endpoint(sample_endpoint, None, "user")
        assert result is True

    def test_can_access_endpoint_unauthenticated_private(
        self, endpoint_service, sample_endpoint
    ):
        """Test unauthenticated access to private endpoint."""
        sample_endpoint.visibility = EndpointVisibility.PRIVATE

        result = endpoint_service._can_access_endpoint(sample_endpoint, None, "user")
        assert result is False

    def test_can_access_endpoint_admin(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test admin access to any endpoint."""
        sample_endpoint.visibility = EndpointVisibility.PRIVATE
        admin_user_data = sample_user.model_dump()
        admin_user_data.update({"id": 2, "role": "admin"})
        admin_user = User(**admin_user_data)

        result = endpoint_service._can_access_endpoint(
            sample_endpoint, admin_user, "user"
        )
        assert result is True

    def test_can_access_user_endpoint_owner(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test user access to their own endpoint."""
        sample_endpoint.visibility = EndpointVisibility.PRIVATE
        sample_endpoint.user_id = sample_user.id

        result = endpoint_service._can_access_endpoint(
            sample_endpoint, sample_user, "user"
        )
        assert result is True

    def test_can_access_org_endpoint_member(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test organization member access to org endpoint."""
        sample_endpoint.visibility = EndpointVisibility.INTERNAL
        sample_endpoint.organization_id = 1
        sample_endpoint.user_id = None

        with patch.object(
            endpoint_service.org_member_repository, "is_member", return_value=True
        ):
            result = endpoint_service._can_access_endpoint(
                sample_endpoint, sample_user, "organization"
            )
            assert result is True

    def test_can_access_org_endpoint_non_member(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test non-member access to org endpoint."""
        sample_endpoint.visibility = EndpointVisibility.PRIVATE
        sample_endpoint.organization_id = 1
        sample_endpoint.user_id = None

        with patch.object(
            endpoint_service.org_member_repository, "is_member", return_value=False
        ):
            result = endpoint_service._can_access_endpoint(
                sample_endpoint, sample_user, "organization"
            )
            assert result is False

    def test_can_see_full_details_public_unauthenticated(
        self, endpoint_service, sample_endpoint
    ):
        """Test unauthenticated user seeing public endpoint details."""
        sample_endpoint.visibility = EndpointVisibility.PUBLIC

        result = endpoint_service._can_see_full_details(sample_endpoint, None, "user")
        assert result is True

    def test_can_see_full_details_admin(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test admin seeing any endpoint details."""
        admin_user_data = sample_user.model_dump()
        admin_user_data.update({"id": 2, "role": "admin"})
        admin_user = User(**admin_user_data)

        result = endpoint_service._can_see_full_details(
            sample_endpoint, admin_user, "user"
        )
        assert result is True

    def test_can_see_full_details_owner(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test owner seeing their endpoint details."""
        sample_endpoint.user_id = sample_user.id

        result = endpoint_service._can_see_full_details(
            sample_endpoint, sample_user, "user"
        )
        assert result is True

    def test_can_see_full_details_org_member(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test organization member seeing org endpoint details."""
        sample_endpoint.organization_id = 1
        sample_endpoint.user_id = None

        with patch.object(
            endpoint_service.org_member_repository, "is_member", return_value=True
        ):
            result = endpoint_service._can_see_full_details(
                sample_endpoint, sample_user, "organization"
            )
            assert result is True

    def test_can_see_full_details_non_owner_user_endpoint(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test non-owner cannot see private user endpoint details."""
        sample_endpoint.visibility = EndpointVisibility.PRIVATE
        sample_endpoint.user_id = 999  # Different user

        result = endpoint_service._can_see_full_details(
            sample_endpoint, sample_user, "user"
        )
        assert result is False  # User endpoints require ownership

    def test_can_see_full_details_fallback_public_orphaned(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test fallback to public visibility for orphaned endpoint."""
        sample_endpoint.visibility = EndpointVisibility.PUBLIC
        sample_endpoint.user_id = None  # Orphaned endpoint

        result = endpoint_service._can_see_full_details(
            sample_endpoint, sample_user, "user"
        )
        assert result is True  # Falls back to public visibility check

    def test_can_modify_endpoint_admin(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test admin can modify any endpoint."""
        admin_user_data = sample_user.model_dump()
        admin_user_data.update({"id": 2, "role": "admin"})
        admin_user = User(**admin_user_data)

        result = endpoint_service._can_modify_endpoint(sample_endpoint, admin_user)
        assert result is True

    def test_can_modify_endpoint_owner(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test owner can modify their endpoint."""
        sample_endpoint.user_id = sample_user.id

        result = endpoint_service._can_modify_endpoint(sample_endpoint, sample_user)
        assert result is True

    def test_can_modify_endpoint_org_owner(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test organization owner can modify org endpoint."""
        sample_endpoint.organization_id = 1
        sample_endpoint.user_id = None

        from syfthub.schemas.organization import OrganizationRole

        with patch.object(
            endpoint_service.org_member_repository,
            "get_member_role",
            return_value=OrganizationRole.OWNER,
        ):
            result = endpoint_service._can_modify_endpoint(sample_endpoint, sample_user)
            assert result is True

    def test_can_modify_endpoint_org_admin(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test organization admin can modify org endpoint."""
        sample_endpoint.organization_id = 1
        sample_endpoint.user_id = None

        from syfthub.schemas.organization import OrganizationRole

        with patch.object(
            endpoint_service.org_member_repository,
            "get_member_role",
            return_value=OrganizationRole.ADMIN,
        ):
            result = endpoint_service._can_modify_endpoint(sample_endpoint, sample_user)
            assert result is True

    def test_can_modify_endpoint_org_member_cannot(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test organization member cannot modify org endpoint."""
        sample_endpoint.organization_id = 1
        sample_endpoint.user_id = None

        from syfthub.schemas.organization import OrganizationRole

        with patch.object(
            endpoint_service.org_member_repository,
            "get_member_role",
            return_value=OrganizationRole.MEMBER,
        ):
            result = endpoint_service._can_modify_endpoint(sample_endpoint, sample_user)
            assert result is False

    def test_can_modify_endpoint_no_permissions(
        self, endpoint_service, sample_endpoint, sample_user
    ):
        """Test user with no permissions cannot modify endpoint."""
        sample_endpoint.user_id = 999  # Different user
        sample_endpoint.organization_id = None

        result = endpoint_service._can_modify_endpoint(sample_endpoint, sample_user)
        assert result is False


class TestEndpointServiceSearch:
    """Test endpoint search functionality."""

    def test_search_endpoints_rag_not_available(self, endpoint_service):
        """Test search returns empty when RAG is not available."""
        # Replace rag_service with a mock that has is_available=False
        mock_rag = MagicMock()
        mock_rag.is_available = False
        endpoint_service.rag_service = mock_rag

        result = endpoint_service.search_endpoints("test query")

        assert result.results == []
        assert result.total == 0
        assert result.query == "test query"

    def test_search_endpoints_empty_results(self, endpoint_service):
        """Test search with no matching results."""
        mock_rag = MagicMock()
        mock_rag.is_available = True
        mock_rag.search.return_value = []
        endpoint_service.rag_service = mock_rag

        result = endpoint_service.search_endpoints("no match query")

        assert result.results == []
        assert result.total == 0
        assert result.query == "no match query"

    def test_search_endpoints_with_results(self, endpoint_service):
        """Test successful search with results."""
        mock_public_response = EndpointPublicResponse(
            name="Test Endpoint",
            slug="test-endpoint",
            description="A test endpoint",
            type=EndpointType.MODEL,
            owner_username="testuser",
            contributors_count=1,
            version="1.0.0",
            readme="# Test",
            tags=["test"],
            stars_count=5,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_rag = MagicMock()
        mock_rag.is_available = True
        mock_rag.search.return_value = [(1, 0.95)]
        endpoint_service.rag_service = mock_rag

        with patch.object(
            endpoint_service.endpoint_repository,
            "get_public_endpoints_by_ids",
            return_value=[mock_public_response],
        ):
            result = endpoint_service.search_endpoints("test query", top_k=5)

            assert len(result.results) == 1
            assert result.results[0].name == "Test Endpoint"
            assert result.results[0].relevance_score == 0.95
            assert result.query == "test query"

    def test_search_endpoints_filter_by_type(self, endpoint_service):
        """Test search with endpoint type filter."""
        model_response = EndpointPublicResponse(
            name="Model Endpoint",
            slug="model-endpoint",
            description="A model endpoint",
            type=EndpointType.MODEL,
            owner_username="testuser",
            contributors_count=1,
            version="1.0.0",
            readme="# Model",
            tags=["model"],
            stars_count=5,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        datasource_response = EndpointPublicResponse(
            name="Data Source Endpoint",
            slug="datasource-endpoint",
            description="A data source endpoint",
            type=EndpointType.DATA_SOURCE,
            owner_username="testuser",
            contributors_count=1,
            version="1.0.0",
            readme="# Data Source",
            tags=["data"],
            stars_count=3,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_rag = MagicMock()
        mock_rag.is_available = True
        mock_rag.search.return_value = [(1, 0.95), (2, 0.85)]
        endpoint_service.rag_service = mock_rag

        with patch.object(
            endpoint_service.endpoint_repository,
            "get_public_endpoints_by_ids",
            return_value=[model_response, datasource_response],
        ):
            # Filter by MODEL type
            result = endpoint_service.search_endpoints(
                "test query", endpoint_type=EndpointType.MODEL
            )

            assert len(result.results) == 1
            assert result.results[0].type == EndpointType.MODEL

    def test_search_endpoints_respects_top_k(self, endpoint_service):
        """Test search respects top_k limit."""
        responses = [
            EndpointPublicResponse(
                name=f"Endpoint {i}",
                slug=f"endpoint-{i}",
                description=f"Endpoint {i} description",
                type=EndpointType.MODEL,
                owner_username="testuser",
                contributors_count=1,
                version="1.0.0",
                readme=f"# Endpoint {i}",
                tags=["test"],
                stars_count=i,
                policies=[],
                connect=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]

        mock_rag = MagicMock()
        mock_rag.is_available = True
        mock_rag.search.return_value = [(i, 0.9 - i * 0.1) for i in range(5)]
        endpoint_service.rag_service = mock_rag

        with patch.object(
            endpoint_service.endpoint_repository,
            "get_public_endpoints_by_ids",
            return_value=responses,
        ):
            # Limit to 2 results
            result = endpoint_service.search_endpoints("test query", top_k=2)

            assert len(result.results) == 2
