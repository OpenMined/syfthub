"""Tests for OrganizationService."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from syfthub.database.connection import get_db_session
from syfthub.schemas.organization import (
    Organization,
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationResponse,
    OrganizationRole,
    OrganizationUpdate,
)
from syfthub.schemas.user import User
from syfthub.services.organization_service import OrganizationService


@pytest.fixture
def db_session():
    """Get database session for testing."""
    session = next(get_db_session())
    yield session
    session.close()


@pytest.fixture
def org_service(db_session):
    """Create OrganizationService instance for testing."""
    return OrganizationService(db_session)


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
        age=25,
        password_hash="hashed_pass",
    )


@pytest.fixture
def admin_user():
    """Sample admin user for testing."""
    return User(
        id=2,
        username="admin",
        email="admin@example.com",
        full_name="Admin User",
        role="admin",
        is_active=True,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        age=30,
        password_hash="admin_hashed_pass",
    )


@pytest.fixture
def sample_organization():
    """Sample organization for testing."""
    return Organization(
        id=1,
        name="Test Organization",
        slug="test-org",
        description="A test organization",
        avatar_url="https://example.com/avatar.png",
        is_active=True,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
    )


class TestOrganizationServiceCreate:
    """Test organization creation."""

    def test_create_organization_success(
        self, org_service, sample_user, sample_organization
    ):
        """Test successful organization creation."""
        org_data = OrganizationCreate(
            name="Test Organization", slug="test-org", description="A test organization"
        )

        with (
            patch.object(
                org_service.org_repository,
                "create_organization",
                return_value=sample_organization,
            ),
            patch.object(
                org_service.member_repository, "add_member", return_value=Mock()
            ),
        ):
            result = org_service.create_organization(org_data, sample_user)

            assert isinstance(result, OrganizationResponse)
            assert result.name == "Test Organization"
            assert result.slug == "test-org"

    def test_create_organization_failure(self, org_service, sample_user):
        """Test organization creation failure."""
        org_data = OrganizationCreate(
            name="Test Organization", slug="test-org", description="A test organization"
        )

        with patch.object(
            org_service.org_repository, "create_organization", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                org_service.create_organization(org_data, sample_user)

            assert exc_info.value.status_code == 500
            assert "Failed to create organization" in str(exc_info.value.detail)


class TestOrganizationServiceGet:
    """Test organization retrieval."""

    def test_get_organization_success(self, org_service, sample_organization):
        """Test successful organization retrieval."""
        with patch.object(
            org_service.org_repository, "get_by_slug", return_value=sample_organization
        ):
            result = org_service.get_organization_by_slug("test-org")

            assert result is not None
            assert isinstance(result, OrganizationResponse)
            assert result.slug == "test-org"

    def test_get_organization_not_found(self, org_service):
        """Test organization not found."""
        with patch.object(org_service.org_repository, "get_by_slug", return_value=None):
            result = org_service.get_organization_by_slug("nonexistent")

            assert result is None


class TestOrganizationServiceUpdate:
    """Test organization update."""

    def test_update_organization_owner_success(
        self, org_service, sample_organization, sample_user
    ):
        """Test owner successfully updating organization."""
        org_data = OrganizationUpdate(name="Updated Organization")
        org_dict = sample_organization.model_dump()
        org_dict.update({"name": "Updated Organization"})
        updated_org = Organization(**org_dict)

        with (
            patch.object(org_service, "_can_manage_organization", return_value=True),
            patch.object(
                org_service.org_repository,
                "update_organization",
                return_value=updated_org,
            ),
        ):
            result = org_service.update_organization(1, org_data, sample_user)

            assert result.name == "Updated Organization"

    def test_update_organization_permission_denied(self, org_service, sample_user):
        """Test permission denied for organization update."""
        org_data = OrganizationUpdate(name="Updated Organization")

        with patch.object(org_service, "_can_manage_organization", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                org_service.update_organization(1, org_data, sample_user)

            assert exc_info.value.status_code == 403
            assert "Permission denied" in str(exc_info.value.detail)

    def test_update_organization_not_found(self, org_service, sample_user):
        """Test updating non-existent organization."""
        org_data = OrganizationUpdate(name="Updated Organization")

        with (
            patch.object(org_service, "_can_manage_organization", return_value=True),
            patch.object(
                org_service.org_repository, "update_organization", return_value=None
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                org_service.update_organization(999, org_data, sample_user)

            assert exc_info.value.status_code == 404
            assert "Organization not found" in str(exc_info.value.detail)


class TestOrganizationServiceMembers:
    """Test organization member management."""

    def test_add_member_success(self, org_service, sample_user):
        """Test successfully adding member."""
        member_data = OrganizationMemberCreate(
            user_id=2, role=OrganizationRole.MEMBER, is_active=True
        )
        mock_member_response = OrganizationMemberResponse(
            id=1,
            user_id=2,
            organization_id=1,
            role=OrganizationRole.MEMBER,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )

        with (
            patch.object(org_service, "_can_manage_organization", return_value=True),
            patch.object(
                org_service.member_repository,
                "add_member",
                return_value=mock_member_response,
            ),
        ):
            result = org_service.add_member(1, member_data, sample_user)

            assert result.user_id == 2
            assert result.role == OrganizationRole.MEMBER

    def test_add_member_permission_denied(self, org_service, sample_user):
        """Test permission denied for adding member."""
        member_data = OrganizationMemberCreate(
            user_id=2, role=OrganizationRole.MEMBER, is_active=True
        )

        with patch.object(org_service, "_can_manage_organization", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                org_service.add_member(1, member_data, sample_user)

            assert exc_info.value.status_code == 403

    def test_add_member_failure(self, org_service, sample_user):
        """Test member addition failure."""
        member_data = OrganizationMemberCreate(
            user_id=2, role=OrganizationRole.MEMBER, is_active=True
        )

        with (
            patch.object(org_service, "_can_manage_organization", return_value=True),
            patch.object(
                org_service.member_repository, "add_member", return_value=None
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                org_service.add_member(1, member_data, sample_user)

            assert exc_info.value.status_code == 400

    def test_remove_member_success(self, org_service, sample_user):
        """Test successfully removing member."""
        with (
            patch.object(org_service, "_can_manage_organization", return_value=True),
            patch.object(
                org_service.member_repository, "remove_member", return_value=True
            ),
        ):
            result = org_service.remove_member(1, 2, sample_user)

            assert result is True

    def test_remove_member_permission_denied(self, org_service, sample_user):
        """Test permission denied for removing member."""
        with patch.object(org_service, "_can_manage_organization", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                org_service.remove_member(1, 2, sample_user)

            assert exc_info.value.status_code == 403

    def test_remove_member_not_found(self, org_service, sample_user):
        """Test removing non-existent member."""
        with (
            patch.object(org_service, "_can_manage_organization", return_value=True),
            patch.object(
                org_service.member_repository, "remove_member", return_value=False
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                org_service.remove_member(1, 999, sample_user)

            assert exc_info.value.status_code == 404
            assert "Member not found" in str(exc_info.value.detail)


class TestOrganizationServiceMemberInfo:
    """Test member information methods."""

    def test_is_member_true(self, org_service):
        """Test is_member returns True."""
        with patch.object(
            org_service.member_repository, "is_member", return_value=True
        ):
            result = org_service.is_member(1, 2)

            assert result is True

    def test_is_member_false(self, org_service):
        """Test is_member returns False."""
        with patch.object(
            org_service.member_repository, "is_member", return_value=False
        ):
            result = org_service.is_member(1, 2)

            assert result is False

    def test_get_member_role_owner(self, org_service):
        """Test getting member role."""
        with patch.object(
            org_service.member_repository,
            "get_member_role",
            return_value=OrganizationRole.OWNER,
        ):
            result = org_service.get_member_role(1, 2)

            assert result == OrganizationRole.OWNER

    def test_get_member_role_none(self, org_service):
        """Test getting member role for non-member."""
        with patch.object(
            org_service.member_repository, "get_member_role", return_value=None
        ):
            result = org_service.get_member_role(1, 2)

            assert result is None

    def test_get_organization_members_success(self, org_service, sample_user):
        """Test getting organization members."""
        mock_members = [
            OrganizationMemberResponse(
                id=1,
                user_id=1,
                organization_id=1,
                role=OrganizationRole.OWNER,
                is_active=True,
                joined_at=datetime.now(timezone.utc),
            )
        ]

        with (
            patch.object(org_service, "_can_view_organization", return_value=True),
            patch.object(
                org_service.member_repository,
                "get_organization_members",
                return_value=mock_members,
            ),
        ):
            result = org_service.get_organization_members(1, sample_user)

            assert len(result) == 1
            assert result[0].user_id == 1

    def test_get_organization_members_permission_denied(self, org_service, sample_user):
        """Test permission denied for getting members."""
        with patch.object(org_service, "_can_view_organization", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                org_service.get_organization_members(1, sample_user)

            assert exc_info.value.status_code == 403

    def test_get_user_organizations(self, org_service):
        """Test getting user organizations."""
        mock_orgs = [
            OrganizationResponse(
                id=1,
                name="Test Organization",
                slug="test-org",
                description="A test organization",
                avatar_url="https://example.com/avatar.png",
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ]

        with patch.object(
            org_service.member_repository,
            "get_user_organizations",
            return_value=mock_orgs,
        ):
            result = org_service.get_user_organizations(1)

            assert len(result) == 1
            assert result[0].name == "Test Organization"


class TestOrganizationServicePermissions:
    """Test permission checking methods."""

    def test_can_manage_organization_admin_user(self, org_service, admin_user):
        """Test admin user can manage any organization."""
        result = org_service._can_manage_organization(1, admin_user)

        assert result is True

    def test_can_manage_organization_owner(self, org_service, sample_user):
        """Test organization owner can manage."""
        with patch.object(
            org_service.member_repository,
            "get_member_role",
            return_value=OrganizationRole.OWNER,
        ):
            result = org_service._can_manage_organization(1, sample_user)

            assert result is True

    def test_can_manage_organization_admin_role(self, org_service, sample_user):
        """Test organization admin can manage."""
        with patch.object(
            org_service.member_repository,
            "get_member_role",
            return_value=OrganizationRole.ADMIN,
        ):
            result = org_service._can_manage_organization(1, sample_user)

            assert result is True

    def test_can_manage_organization_member_cannot(self, org_service, sample_user):
        """Test organization member cannot manage."""
        with patch.object(
            org_service.member_repository,
            "get_member_role",
            return_value=OrganizationRole.MEMBER,
        ):
            result = org_service._can_manage_organization(1, sample_user)

            assert result is False

    def test_can_manage_organization_non_member(self, org_service, sample_user):
        """Test non-member cannot manage."""
        with patch.object(
            org_service.member_repository, "get_member_role", return_value=None
        ):
            result = org_service._can_manage_organization(1, sample_user)

            assert result is False

    def test_can_view_organization_admin_user(self, org_service, admin_user):
        """Test admin user can view any organization."""
        result = org_service._can_view_organization(1, admin_user)

        assert result is True

    def test_can_view_organization_member(self, org_service, sample_user):
        """Test organization member can view."""
        with patch.object(
            org_service.member_repository, "is_member", return_value=True
        ):
            result = org_service._can_view_organization(1, sample_user)

            assert result is True

    def test_can_view_organization_non_member(self, org_service, sample_user):
        """Test non-member cannot view."""
        with patch.object(
            org_service.member_repository, "is_member", return_value=False
        ):
            result = org_service._can_view_organization(1, sample_user)

            assert result is False
