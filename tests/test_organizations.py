"""Tests for organization endpoints."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from syfthub.api.endpoints.organizations import (
    fake_org_members_db,
    fake_organizations_db,
    slug_to_organization_lookup,
    user_organizations_lookup,
)
from syfthub.auth.dependencies import fake_users_db, username_to_id
from syfthub.auth.security import token_blacklist
from syfthub.main import app
from syfthub.schemas.organization import Organization, OrganizationRole

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_test_data():
    """Clear all test data before each test."""
    # Clear organization data
    fake_organizations_db.clear()
    fake_org_members_db.clear()
    user_organizations_lookup.clear()
    slug_to_organization_lookup.clear()

    # Clear auth data
    fake_users_db.clear()
    username_to_id.clear()
    token_blacklist.clear()

    # Reset counters
    import syfthub.api.endpoints.organizations as org_module
    import syfthub.auth.router as auth_module

    auth_module.user_id_counter = 1
    org_module.organization_id_counter = 1
    org_module.member_id_counter = 1

    yield


@pytest.fixture
def auth_headers():
    """Get authentication headers for test user."""
    # Register and login a test user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpassword123",
    }
    response = client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201

    login_data = {"username": "testuser", "password": "testpassword123"}
    response = client.post("/api/v1/auth/login", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers():
    """Get authentication headers for admin user."""
    # Register admin user
    user_data = {
        "username": "admin",
        "email": "admin@example.com",
        "full_name": "Admin User",
        "password": "adminpass123",
    }
    response = client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201

    # Make the user admin by modifying the fake database
    user_id = response.json()["user"]["id"]
    fake_users_db[user_id].role = "admin"

    login_data = {"username": "admin", "password": "adminpass123"}
    response = client.post("/api/v1/auth/login", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_test_organization(
    org_id: int = 1, name: str = "Test Organization", slug: str = "test-org"
):
    """Helper function to create a test organization."""
    now = datetime.now(timezone.utc)
    org = Organization(
        id=org_id,
        name=name,
        slug=slug,
        description="A test organization",
        avatar_url="https://example.com/avatar.png",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    fake_organizations_db[org_id] = org
    slug_to_organization_lookup[slug] = org_id
    return org


class TestOrganizationCRUD:
    """Test organization CRUD operations."""

    def test_create_organization(self, auth_headers):
        """Test creating a new organization."""
        org_data = {
            "name": "My Organization",
            "description": "A great organization",
            "slug": "my-org",
        }

        response = client.post(
            "/api/v1/organizations/", json=org_data, headers=auth_headers
        )
        assert response.status_code == 201

        org = response.json()
        assert org["name"] == "My Organization"
        assert org["slug"] == "my-org"
        assert org["description"] == "A great organization"
        assert org["is_active"] is True

    def test_create_organization_auto_slug(self, auth_headers):
        """Test creating organization with auto-generated slug."""
        org_data = {
            "name": "Auto Slug Organization",
            "description": "Testing auto slug generation",
        }

        response = client.post(
            "/api/v1/organizations/", json=org_data, headers=auth_headers
        )
        assert response.status_code == 201

        org = response.json()
        assert org["slug"] == "auto-slug-organization"

    def test_create_organization_reserved_slug(self, auth_headers):
        """Test creating organization with reserved slug fails."""
        org_data = {
            "name": "API Organization",
            "slug": "api",  # Reserved slug
        }

        response = client.post(
            "/api/v1/organizations/", json=org_data, headers=auth_headers
        )
        assert response.status_code == 422  # Pydantic validation error
        assert "reserved slug" in str(response.json())

    def test_create_organization_duplicate_slug(self, auth_headers):
        """Test creating organization with duplicate slug fails."""
        # Create first organization
        first_org_data = {"name": "First Organization", "slug": "test-org"}
        client.post("/api/v1/organizations/", json=first_org_data, headers=auth_headers)

        # Try to create second organization with same slug
        org_data = {
            "name": "Duplicate Organization",
            "slug": "test-org",  # Already exists
        }

        response = client.post(
            "/api/v1/organizations/", json=org_data, headers=auth_headers
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_get_organization(self, auth_headers):
        """Test getting organization details."""
        # Create organization
        create_test_organization()

        # Add user as member
        fake_org_members_db[1] = {
            1: {  # Assuming user ID 1
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "owner",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }
        user_organizations_lookup[1] = {1}

        response = client.get("/api/v1/organizations/1", headers=auth_headers)
        assert response.status_code == 200

        org = response.json()
        assert org["name"] == "Test Organization"
        assert org["slug"] == "test-org"

    def test_get_organization_not_member(self, auth_headers):
        """Test getting organization when not a member fails."""
        # Create organization
        create_test_organization()

        response = client.get("/api/v1/organizations/1", headers=auth_headers)
        assert response.status_code == 404

    def test_update_organization(self, auth_headers):
        """Test updating organization."""
        # Create organization
        create_test_organization()

        # Add user as admin
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "admin",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        update_data = {"name": "Updated Organization"}
        response = client.put(
            "/api/v1/organizations/1", json=update_data, headers=auth_headers
        )
        assert response.status_code == 200

        org = response.json()
        assert org["name"] == "Updated Organization"

    def test_update_organization_not_admin(self, auth_headers):
        """Test updating organization without admin rights fails."""
        # Create organization
        create_test_organization()

        # Add user as member (not admin)
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "member",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        update_data = {"name": "Updated Organization"}
        response = client.put(
            "/api/v1/organizations/1", json=update_data, headers=auth_headers
        )
        assert response.status_code == 403

    def test_delete_organization(self, auth_headers):
        """Test deleting organization."""
        # Create organization
        create_test_organization()

        # Add user as owner
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "owner",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        response = client.delete("/api/v1/organizations/1", headers=auth_headers)
        assert response.status_code == 204

        # Verify soft delete
        assert fake_organizations_db[1].is_active is False

    def test_delete_organization_not_owner(self, auth_headers):
        """Test deleting organization without owner rights fails."""
        # Create organization
        create_test_organization()

        # Add user as admin (not owner)
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "admin",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        response = client.delete("/api/v1/organizations/1", headers=auth_headers)
        assert response.status_code == 403

    def test_list_my_organizations(self, auth_headers):
        """Test listing user's organizations."""
        # Create organization
        create_test_organization()

        # Add user to organization
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "member",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }
        user_organizations_lookup[1] = {1}

        response = client.get("/api/v1/organizations/", headers=auth_headers)
        assert response.status_code == 200

        orgs = response.json()
        assert len(orgs) == 1
        assert orgs[0]["name"] == "Test Organization"


class TestOrganizationMembers:
    """Test organization member management."""

    def test_add_organization_member(self, auth_headers):
        """Test adding member to organization."""
        # Create organization
        create_test_organization()

        # Make user owner
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "owner",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        member_data = {"user_id": 2, "role": "member"}

        response = client.post(
            "/api/v1/organizations/1/members", json=member_data, headers=auth_headers
        )
        assert response.status_code == 201

        member = response.json()
        assert member["user_id"] == 2
        assert member["role"] == "member"

    def test_add_organization_member_not_admin(self, auth_headers):
        """Test adding member without admin rights fails."""
        # Create organization
        create_test_organization()

        # Make user regular member
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "member",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        member_data = {"user_id": 2, "role": "member"}

        response = client.post(
            "/api/v1/organizations/1/members", json=member_data, headers=auth_headers
        )
        assert response.status_code == 403

    def test_list_organization_members(self, auth_headers):
        """Test listing organization members."""
        # Create organization
        create_test_organization()

        # Add user as member
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "owner",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        response = client.get("/api/v1/organizations/1/members", headers=auth_headers)
        assert response.status_code == 200

        members = response.json()
        assert len(members) == 1
        assert members[0]["role"] == "owner"

    def test_update_organization_member(self, auth_headers):
        """Test updating organization member role."""
        # Create organization
        create_test_organization()

        # Add users
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "owner",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            },
            2: {
                "id": 2,
                "organization_id": 1,
                "user_id": 2,
                "role": "member",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            },
        }

        update_data = {"role": "admin"}
        response = client.put(
            "/api/v1/organizations/1/members/2", json=update_data, headers=auth_headers
        )
        assert response.status_code == 200

        member = response.json()
        assert member["role"] == "admin"

    def test_remove_organization_member(self, auth_headers):
        """Test removing organization member."""
        # Create organization
        create_test_organization()

        # Add users
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "owner",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            },
            2: {
                "id": 2,
                "organization_id": 1,
                "user_id": 2,
                "role": "member",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            },
        }

        response = client.delete(
            "/api/v1/organizations/1/members/2", headers=auth_headers
        )
        assert response.status_code == 204

        # Verify soft delete
        assert fake_org_members_db[1][2]["is_active"] is False

    def test_remove_last_owner_fails(self, auth_headers):
        """Test removing last owner fails."""
        # Create organization
        create_test_organization()

        # Add single owner
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "owner",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        response = client.delete(
            "/api/v1/organizations/1/members/1", headers=auth_headers
        )
        assert response.status_code == 400
        assert "last owner" in response.json()["detail"]


class TestOrganizationAuth:
    """Test organization authentication and authorization."""

    def test_create_organization_requires_auth(self):
        """Test creating organization without auth fails."""
        org_data = {"name": "Unauthorized Organization"}
        response = client.post("/api/v1/organizations/", json=org_data)
        assert response.status_code == 401

    def test_admin_can_access_any_organization(self, admin_headers):
        """Test admin can access any organization."""
        # Create organization
        create_test_organization()

        response = client.get("/api/v1/organizations/1", headers=admin_headers)
        assert response.status_code == 200

    def test_member_self_removal(self, auth_headers):
        """Test member can remove themselves."""
        # Create organization
        create_test_organization()

        # Add user as member
        fake_org_members_db[1] = {
            1: {
                "id": 1,
                "organization_id": 1,
                "user_id": 1,
                "role": "member",
                "is_active": True,
                "joined_at": datetime.now(timezone.utc),
            }
        }

        response = client.delete(
            "/api/v1/organizations/1/members/1", headers=auth_headers
        )
        assert response.status_code == 204


class TestOrganizationSchemas:
    """Test organization schema validation."""

    def test_organization_role_enum(self):
        """Test organization role enum values."""
        assert OrganizationRole.OWNER == "owner"
        assert OrganizationRole.ADMIN == "admin"
        assert OrganizationRole.MEMBER == "member"

    def test_invalid_slug_validation(self, auth_headers):
        """Test various invalid slug scenarios."""
        invalid_slugs = [
            "UPPERCASE",  # Must be lowercase
            "slug-",  # Can't end with hyphen
            "-slug",  # Can't start with hyphen
            "sl--ug",  # No consecutive hyphens
            "ab",  # Too short
            "a" * 64,  # Too long
        ]

        for invalid_slug in invalid_slugs:
            org_data = {"name": "Test Organization", "slug": invalid_slug}
            response = client.post(
                "/api/v1/organizations/", json=org_data, headers=auth_headers
            )
            assert response.status_code == 422


class TestOrganizationHelpers:
    """Test organization helper functions."""

    def test_organization_lookup_functions(self):
        """Test organization lookup helper functions."""
        from syfthub.api.endpoints.organizations import (
            get_organization_by_id,
            get_organization_by_slug,
            get_user_role_in_organization,
            is_organization_member,
        )

        # Create organization for testing
        create_test_organization()

        # Test get by ID
        org = get_organization_by_id(1)
        assert org is not None
        assert org.name == "Test Organization"

        # Test get by slug
        org = get_organization_by_slug("test-org")
        assert org is not None
        assert org.name == "Test Organization"

        # Test role checking with no membership
        role = get_user_role_in_organization(1, 1)
        assert role is None

        # Test membership checking
        is_member = is_organization_member(1, 1)
        assert is_member is False

        # Add membership
        fake_org_members_db[1] = {
            1: {
                "role": "owner",
                "is_active": True,
            }
        }

        # Test with membership
        role = get_user_role_in_organization(1, 1)
        assert role == OrganizationRole.OWNER

        is_member = is_organization_member(1, 1)
        assert is_member is True
