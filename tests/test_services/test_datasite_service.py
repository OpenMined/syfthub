"""Tests for DatasiteService."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from syfthub.database.connection import get_db_session
from syfthub.schemas.datasite import (
    Datasite,
    DatasiteCreate,
    DatasitePublicResponse,
    DatasiteResponse,
    DatasiteUpdate,
    DatasiteVisibility,
)
from syfthub.schemas.user import User
from syfthub.services.datasite_service import DatasiteService


@pytest.fixture
def db_session():
    """Get database session for testing."""
    session = next(get_db_session())
    yield session
    session.close()


@pytest.fixture
def datasite_service(db_session):
    """Create DatasiteService instance for testing."""
    return DatasiteService(db_session)


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
def sample_datasite():
    """Sample datasite for testing."""
    return Datasite(
        id=1,
        name="Test Datasite",
        slug="test-datasite",
        description="A test datasite",
        visibility=DatasiteVisibility.PUBLIC,
        is_organization_owned=False,
        user_id=1,
        organization_id=None,
        stars_count=0,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
    )


class TestDatasiteServiceCreate:
    """Test datasite creation."""

    def test_create_user_datasite_success(
        self, datasite_service, sample_user, sample_datasite
    ):
        """Test successful user datasite creation."""
        datasite_data = DatasiteCreate(
            name="Test Datasite",
            slug="test-datasite",
            description="A test datasite",
            visibility=DatasiteVisibility.PUBLIC,
        )

        with (
            patch.object(
                datasite_service.datasite_repository,
                "slug_exists_for_user",
                return_value=False,
            ),
            patch.object(
                datasite_service.datasite_repository,
                "create_datasite",
                return_value=sample_datasite,
            ),
        ):
            result = datasite_service.create_datasite(
                datasite_data, 1, is_organization=False
            )

            assert isinstance(result, DatasiteResponse)
            assert result.name == "Test Datasite"
            assert result.slug == "test-datasite"

    def test_create_user_datasite_slug_exists(self, datasite_service, sample_user):
        """Test user datasite creation with existing slug."""
        datasite_data = DatasiteCreate(
            name="Test Datasite", slug="existing-slug", description="A test datasite"
        )

        with patch.object(
            datasite_service.datasite_repository,
            "slug_exists_for_user",
            return_value=True,
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.create_datasite(
                    datasite_data, 1, is_organization=False
                )

            assert exc_info.value.status_code == 400
            assert "slug already exists" in str(exc_info.value.detail)

    def test_create_organization_datasite_not_member(
        self, datasite_service, sample_user
    ):
        """Test organization datasite creation without membership."""
        datasite_data = DatasiteCreate(
            name="Test Datasite", slug="test-datasite", description="A test datasite"
        )

        with patch.object(
            datasite_service.org_member_repository, "is_member", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.create_datasite(
                    datasite_data, 1, is_organization=True, current_user=sample_user
                )

            assert exc_info.value.status_code == 403
            assert "not a member of organization" in str(exc_info.value.detail)

    def test_create_organization_datasite_slug_exists(
        self, datasite_service, sample_user
    ):
        """Test organization datasite creation with existing slug."""
        datasite_data = DatasiteCreate(
            name="Test Datasite", slug="existing-slug", description="A test datasite"
        )

        with (
            patch.object(
                datasite_service.org_member_repository, "is_member", return_value=True
            ),
            patch.object(
                datasite_service.datasite_repository,
                "slug_exists_for_organization",
                return_value=True,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.create_datasite(
                    datasite_data, 1, is_organization=True, current_user=sample_user
                )

            assert exc_info.value.status_code == 400
            assert "slug already exists for this organization" in str(
                exc_info.value.detail
            )

    def test_create_datasite_failure(self, datasite_service, sample_user):
        """Test datasite creation failure."""
        datasite_data = DatasiteCreate(
            name="Test Datasite", slug="test-datasite", description="A test datasite"
        )

        with (
            patch.object(
                datasite_service.datasite_repository,
                "slug_exists_for_user",
                return_value=False,
            ),
            patch.object(
                datasite_service.datasite_repository,
                "create_datasite",
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.create_datasite(
                    datasite_data, 1, is_organization=False
                )

            assert exc_info.value.status_code == 500
            assert "Failed to create datasite" in str(exc_info.value.detail)


class TestDatasiteServiceGet:
    """Test datasite retrieval."""

    def test_get_datasite_by_user_and_slug(self, datasite_service, sample_datasite):
        """Test getting datasite by user and slug."""
        with patch.object(
            datasite_service.datasite_repository,
            "get_by_user_and_slug",
            return_value=sample_datasite,
        ):
            result = datasite_service.get_datasite_by_user_and_slug(1, "test-datasite")

            assert result == sample_datasite

    def test_get_datasite_by_user_and_slug_not_found(self, datasite_service):
        """Test getting non-existent datasite by user and slug."""
        with patch.object(
            datasite_service.datasite_repository,
            "get_by_user_and_slug",
            return_value=None,
        ):
            result = datasite_service.get_datasite_by_user_and_slug(1, "nonexistent")

            assert result is None

    def test_get_datasite_by_org_and_slug(self, datasite_service, sample_datasite):
        """Test getting datasite by organization and slug."""
        with patch.object(
            datasite_service.datasite_repository,
            "get_by_organization_and_slug",
            return_value=sample_datasite,
        ):
            result = datasite_service.get_datasite_by_org_and_slug(1, "test-datasite")

            assert result == sample_datasite

    def test_get_datasite_by_org_and_slug_not_found(self, datasite_service):
        """Test getting non-existent datasite by organization and slug."""
        with patch.object(
            datasite_service.datasite_repository,
            "get_by_organization_and_slug",
            return_value=None,
        ):
            result = datasite_service.get_datasite_by_org_and_slug(1, "nonexistent")

            assert result is None

    def test_get_public_datasites(self, datasite_service):
        """Test getting public datasites."""
        mock_public_datasites = [
            DatasitePublicResponse(
                name="Public Datasite",
                slug="public-datasite",
                description="A public datasite",
                contributors=[1],
                version="1.0.0",
                readme="# Public Datasite",
                stars_count=5,
                policies=[],
                connect=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ]

        with patch.object(
            datasite_service.datasite_repository,
            "get_public_datasites",
            return_value=mock_public_datasites,
        ):
            result = datasite_service.get_public_datasites()

            assert len(result) == 1
            assert result[0].name == "Public Datasite"


class TestDatasiteServiceUpdate:
    """Test datasite update."""

    def test_update_datasite_success(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test successful datasite update."""
        update_data = DatasiteUpdate(name="Updated Datasite")
        datasite_dict = sample_datasite.model_dump()
        datasite_dict.update({"name": "Updated Datasite"})
        updated_datasite = Datasite(**datasite_dict)

        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_by_id",
                return_value=sample_datasite,
            ),
            patch.object(datasite_service, "_can_modify_datasite", return_value=True),
            patch.object(
                datasite_service.datasite_repository,
                "update_datasite",
                return_value=updated_datasite,
            ),
        ):
            result = datasite_service.update_datasite(1, update_data, sample_user)

            assert result.name == "Updated Datasite"

    def test_update_datasite_not_found(self, datasite_service, sample_user):
        """Test updating non-existent datasite."""
        update_data = DatasiteUpdate(name="Updated Datasite")

        with patch.object(
            datasite_service.datasite_repository, "get_by_id", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.update_datasite(999, update_data, sample_user)

            assert exc_info.value.status_code == 404
            assert "Datasite not found" in str(exc_info.value.detail)

    def test_update_datasite_permission_denied(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test permission denied for datasite update."""
        update_data = DatasiteUpdate(name="Updated Datasite")

        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_by_id",
                return_value=sample_datasite,
            ),
            patch.object(datasite_service, "_can_modify_datasite", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.update_datasite(1, update_data, sample_user)

            assert exc_info.value.status_code == 403
            assert "Permission denied" in str(exc_info.value.detail)

    def test_update_datasite_failure(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test datasite update failure."""
        update_data = DatasiteUpdate(name="Updated Datasite")

        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_by_id",
                return_value=sample_datasite,
            ),
            patch.object(datasite_service, "_can_modify_datasite", return_value=True),
            patch.object(
                datasite_service.datasite_repository,
                "update_datasite",
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.update_datasite(1, update_data, sample_user)

            assert exc_info.value.status_code == 500
            assert "Failed to update datasite" in str(exc_info.value.detail)


class TestDatasiteServiceLists:
    """Test datasite list methods."""

    def test_get_user_datasites_basic(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test getting user datasites."""
        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_user_datasites",
                return_value=[sample_datasite],
            ),
            patch.object(datasite_service, "_can_access_datasite", return_value=True),
            patch.object(datasite_service, "_can_see_full_details", return_value=True),
        ):
            result = datasite_service.get_user_datasites(1, current_user=sample_user)

            assert len(result) == 1
            assert result[0].name == "Test Datasite"

    def test_get_user_datasites_no_access(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test getting user datasites with no access."""
        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_user_datasites",
                return_value=[sample_datasite],
            ),
            patch.object(datasite_service, "_can_access_datasite", return_value=False),
        ):
            result = datasite_service.get_user_datasites(1, current_user=sample_user)

            assert len(result) == 0

    def test_get_organization_datasites_basic(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test getting organization datasites."""
        datasite_dict = sample_datasite.model_dump()
        datasite_dict.update(
            {"is_organization_owned": True, "organization_id": 1, "user_id": None}
        )
        org_datasite = Datasite(**datasite_dict)

        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_organization_datasites",
                return_value=[org_datasite],
            ),
            patch.object(datasite_service, "_can_access_datasite", return_value=True),
            patch.object(datasite_service, "_can_see_full_details", return_value=True),
        ):
            result = datasite_service.get_organization_datasites(
                1, current_user=sample_user
            )

            assert len(result) == 1
            assert result[0].name == "Test Datasite"

    def test_get_organization_datasites_no_access(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test getting organization datasites with no access."""
        datasite_dict = sample_datasite.model_dump()
        datasite_dict.update(
            {"is_organization_owned": True, "organization_id": 1, "user_id": None}
        )
        org_datasite = Datasite(**datasite_dict)

        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_organization_datasites",
                return_value=[org_datasite],
            ),
            patch.object(datasite_service, "_can_access_datasite", return_value=False),
        ):
            result = datasite_service.get_organization_datasites(
                1, current_user=sample_user
            )

            assert len(result) == 0


class TestDatasiteServiceDelete:
    """Test datasite deletion."""

    def test_delete_datasite_success(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test successful datasite deletion."""
        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_by_id",
                return_value=sample_datasite,
            ),
            patch.object(datasite_service, "_can_modify_datasite", return_value=True),
            patch.object(
                datasite_service.datasite_repository,
                "delete_datasite",
                return_value=True,
            ),
        ):
            result = datasite_service.delete_datasite(1, sample_user)

            assert result is True

    def test_delete_datasite_not_found(self, datasite_service, sample_user):
        """Test deleting non-existent datasite."""
        with patch.object(
            datasite_service.datasite_repository, "get_by_id", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.delete_datasite(999, sample_user)

            assert exc_info.value.status_code == 404
            assert "Datasite not found" in str(exc_info.value.detail)

    def test_delete_datasite_permission_denied(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test permission denied for datasite deletion."""
        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_by_id",
                return_value=sample_datasite,
            ),
            patch.object(datasite_service, "_can_modify_datasite", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.delete_datasite(1, sample_user)

            assert exc_info.value.status_code == 403
            assert "Permission denied" in str(exc_info.value.detail)

    def test_delete_datasite_failure(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test datasite deletion failure."""
        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_by_id",
                return_value=sample_datasite,
            ),
            patch.object(datasite_service, "_can_modify_datasite", return_value=True),
            patch.object(
                datasite_service.datasite_repository,
                "delete_datasite",
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.delete_datasite(1, sample_user)

            assert exc_info.value.status_code == 500
            assert "Failed to delete datasite" in str(exc_info.value.detail)


class TestDatasiteServiceStar:
    """Test datasite star functionality."""

    def test_star_datasite_success(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test successful datasite starring."""
        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_by_id",
                return_value=sample_datasite,
            ),
            patch.object(datasite_service, "_can_access_datasite", return_value=True),
            patch.object(
                datasite_service.star_repository, "star_datasite", return_value=True
            ),
            patch.object(datasite_service.datasite_repository, "increment_stars"),
        ):
            result = datasite_service.star_datasite(1, sample_user)

            assert result is True

    def test_star_datasite_not_found(self, datasite_service, sample_user):
        """Test starring non-existent datasite."""
        with patch.object(
            datasite_service.datasite_repository, "get_by_id", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.star_datasite(999, sample_user)

            assert exc_info.value.status_code == 404
            assert "Datasite not found" in str(exc_info.value.detail)

    def test_star_datasite_no_access(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test starring datasite without access."""
        with (
            patch.object(
                datasite_service.datasite_repository,
                "get_by_id",
                return_value=sample_datasite,
            ),
            patch.object(datasite_service, "_can_access_datasite", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                datasite_service.star_datasite(1, sample_user)

            assert exc_info.value.status_code == 404
            assert "Datasite not found" in str(exc_info.value.detail)

    def test_unstar_datasite_success(self, datasite_service, sample_user):
        """Test successful datasite unstarring."""
        with (
            patch.object(
                datasite_service.star_repository, "unstar_datasite", return_value=True
            ),
            patch.object(datasite_service.datasite_repository, "decrement_stars"),
        ):
            result = datasite_service.unstar_datasite(1, sample_user)

            assert result is True

    def test_unstar_datasite_not_starred(self, datasite_service, sample_user):
        """Test unstarring not-starred datasite."""
        with patch.object(
            datasite_service.star_repository, "unstar_datasite", return_value=False
        ):
            result = datasite_service.unstar_datasite(1, sample_user)

            assert result is False

    def test_is_datasite_starred(self, datasite_service, sample_user):
        """Test checking if datasite is starred."""
        with patch.object(
            datasite_service.star_repository, "is_starred", return_value=True
        ):
            result = datasite_service.is_datasite_starred(1, sample_user)

            assert result is True


class TestDatasiteServicePermissions:
    """Test datasite permission methods."""

    def test_can_access_datasite_public(self, datasite_service, sample_datasite):
        """Test access to public datasite."""
        sample_datasite.visibility = DatasiteVisibility.PUBLIC

        result = datasite_service._can_access_datasite(sample_datasite, None, "user")
        assert result is True

    def test_can_access_datasite_unauthenticated_private(
        self, datasite_service, sample_datasite
    ):
        """Test unauthenticated access to private datasite."""
        sample_datasite.visibility = DatasiteVisibility.PRIVATE

        result = datasite_service._can_access_datasite(sample_datasite, None, "user")
        assert result is False

    def test_can_access_datasite_admin(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test admin access to any datasite."""
        sample_datasite.visibility = DatasiteVisibility.PRIVATE
        admin_user_data = sample_user.model_dump()
        admin_user_data.update({"id": 2, "role": "admin"})
        admin_user = User(**admin_user_data)

        result = datasite_service._can_access_datasite(
            sample_datasite, admin_user, "user"
        )
        assert result is True

    def test_can_access_user_datasite_owner(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test user access to their own datasite."""
        sample_datasite.visibility = DatasiteVisibility.PRIVATE
        sample_datasite.user_id = sample_user.id

        result = datasite_service._can_access_datasite(
            sample_datasite, sample_user, "user"
        )
        assert result is True

    def test_can_access_org_datasite_member(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test organization member access to org datasite."""
        sample_datasite.visibility = DatasiteVisibility.INTERNAL
        sample_datasite.organization_id = 1
        sample_datasite.user_id = None

        with patch.object(
            datasite_service.org_member_repository, "is_member", return_value=True
        ):
            result = datasite_service._can_access_datasite(
                sample_datasite, sample_user, "organization"
            )
            assert result is True

    def test_can_access_org_datasite_non_member(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test non-member access to org datasite."""
        sample_datasite.visibility = DatasiteVisibility.PRIVATE
        sample_datasite.organization_id = 1
        sample_datasite.user_id = None

        with patch.object(
            datasite_service.org_member_repository, "is_member", return_value=False
        ):
            result = datasite_service._can_access_datasite(
                sample_datasite, sample_user, "organization"
            )
            assert result is False

    def test_can_see_full_details_public_unauthenticated(
        self, datasite_service, sample_datasite
    ):
        """Test unauthenticated user seeing public datasite details."""
        sample_datasite.visibility = DatasiteVisibility.PUBLIC

        result = datasite_service._can_see_full_details(sample_datasite, None, "user")
        assert result is True

    def test_can_see_full_details_admin(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test admin seeing any datasite details."""
        admin_user_data = sample_user.model_dump()
        admin_user_data.update({"id": 2, "role": "admin"})
        admin_user = User(**admin_user_data)

        result = datasite_service._can_see_full_details(
            sample_datasite, admin_user, "user"
        )
        assert result is True

    def test_can_see_full_details_owner(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test owner seeing their datasite details."""
        sample_datasite.user_id = sample_user.id

        result = datasite_service._can_see_full_details(
            sample_datasite, sample_user, "user"
        )
        assert result is True

    def test_can_see_full_details_org_member(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test organization member seeing org datasite details."""
        sample_datasite.organization_id = 1
        sample_datasite.user_id = None

        with patch.object(
            datasite_service.org_member_repository, "is_member", return_value=True
        ):
            result = datasite_service._can_see_full_details(
                sample_datasite, sample_user, "organization"
            )
            assert result is True

    def test_can_see_full_details_non_owner_user_datasite(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test non-owner cannot see private user datasite details."""
        sample_datasite.visibility = DatasiteVisibility.PRIVATE
        sample_datasite.user_id = 999  # Different user

        result = datasite_service._can_see_full_details(
            sample_datasite, sample_user, "user"
        )
        assert result is False  # User datasites require ownership

    def test_can_see_full_details_fallback_public_orphaned(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test fallback to public visibility for orphaned datasite."""
        sample_datasite.visibility = DatasiteVisibility.PUBLIC
        sample_datasite.user_id = None  # Orphaned datasite

        result = datasite_service._can_see_full_details(
            sample_datasite, sample_user, "user"
        )
        assert result is True  # Falls back to public visibility check

    def test_can_modify_datasite_admin(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test admin can modify any datasite."""
        admin_user_data = sample_user.model_dump()
        admin_user_data.update({"id": 2, "role": "admin"})
        admin_user = User(**admin_user_data)

        result = datasite_service._can_modify_datasite(sample_datasite, admin_user)
        assert result is True

    def test_can_modify_datasite_owner(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test owner can modify their datasite."""
        sample_datasite.user_id = sample_user.id

        result = datasite_service._can_modify_datasite(sample_datasite, sample_user)
        assert result is True

    def test_can_modify_datasite_org_owner(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test organization owner can modify org datasite."""
        sample_datasite.organization_id = 1
        sample_datasite.user_id = None

        from syfthub.schemas.organization import OrganizationRole

        with patch.object(
            datasite_service.org_member_repository,
            "get_member_role",
            return_value=OrganizationRole.OWNER,
        ):
            result = datasite_service._can_modify_datasite(sample_datasite, sample_user)
            assert result is True

    def test_can_modify_datasite_org_admin(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test organization admin can modify org datasite."""
        sample_datasite.organization_id = 1
        sample_datasite.user_id = None

        from syfthub.schemas.organization import OrganizationRole

        with patch.object(
            datasite_service.org_member_repository,
            "get_member_role",
            return_value=OrganizationRole.ADMIN,
        ):
            result = datasite_service._can_modify_datasite(sample_datasite, sample_user)
            assert result is True

    def test_can_modify_datasite_org_member_cannot(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test organization member cannot modify org datasite."""
        sample_datasite.organization_id = 1
        sample_datasite.user_id = None

        from syfthub.schemas.organization import OrganizationRole

        with patch.object(
            datasite_service.org_member_repository,
            "get_member_role",
            return_value=OrganizationRole.MEMBER,
        ):
            result = datasite_service._can_modify_datasite(sample_datasite, sample_user)
            assert result is False

    def test_can_modify_datasite_no_permissions(
        self, datasite_service, sample_datasite, sample_user
    ):
        """Test user with no permissions cannot modify datasite."""
        sample_datasite.user_id = 999  # Different user
        sample_datasite.organization_id = None

        result = datasite_service._can_modify_datasite(sample_datasite, sample_user)
        assert result is False
