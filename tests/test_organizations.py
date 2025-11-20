"""Tests for organization endpoints."""

from typing import Optional

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app
from syfthub.schemas.organization import OrganizationRole


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    from syfthub.database.connection import create_tables, drop_tables

    # Ensure clean database
    drop_tables()
    create_tables()

    client = TestClient(app)

    yield client

    # Clean up
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data() -> None:
    """Reset authentication data before each test."""
    token_blacklist.clear()

    yield


@pytest.fixture
def auth_headers(client):
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
def admin_headers(client):
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

    # Make the user admin using repository
    user_id = response.json()["user"]["id"]
    from syfthub.database.connection import get_db_session
    from syfthub.repositories.user import UserRepository

    session = next(get_db_session())
    try:
        user_repo = UserRepository(session)
        user_repo.update_user_role(user_id, "admin")
    finally:
        session.close()

    login_data = {"username": "admin", "password": "adminpass123"}
    response = client.post("/api/v1/auth/login", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_test_organization(
    name: str = "Test Organization",
    slug: str = "test-org",
    creator_user_id: int = 1,
    client_instance=None,
):
    """Helper function to create a test organization and add creator as owner using repository."""
    from syfthub.database.connection import get_db_session
    from syfthub.repositories.organization import (
        OrganizationMemberRepository,
        OrganizationRepository,
    )
    from syfthub.schemas.organization import (
        OrganizationCreate,
        OrganizationMemberCreate,
        OrganizationRole,
    )

    # Ensure creator user exists
    if client_instance:
        create_test_user(creator_user_id, client_instance=client_instance)

    session = next(get_db_session())
    try:
        # Create organization
        org_repo = OrganizationRepository(session)
        org_data = OrganizationCreate(
            name=name,
            slug=slug,
            description="A test organization",
            avatar_url="https://example.com/avatar.png",
            is_active=True,
        )
        org = org_repo.create_organization(org_data)

        if org:
            # Add creator as owner
            member_repo = OrganizationMemberRepository(session)
            member_data = OrganizationMemberCreate(
                user_id=creator_user_id, role=OrganizationRole.OWNER, is_active=True
            )
            member_repo.add_member(member_data, org.id)

        return org
    finally:
        session.close()


def create_test_user(
    user_id: int,
    username: Optional[str] = None,
    email: Optional[str] = None,
    client_instance=None,
):
    """Helper function to create a test user using API."""
    if username is None:
        username = f"user{user_id}"
    if email is None:
        email = f"user{user_id}@example.com"

    if client_instance is None:
        from starlette.testclient import TestClient

        from syfthub.main import app

        client_instance = TestClient(app)

    user_data = {
        "username": username,
        "email": email,
        "full_name": f"Test User {user_id}",
        "password": "password123",
    }

    response = client_instance.post("/api/v1/auth/register", json=user_data)
    if response.status_code == 201:
        return response.json()["user"]
    elif response.status_code == 400 and "already exists" in response.text:
        # User already exists, that's fine
        return {"id": user_id, "username": username}
    return None


def add_test_organization_member(org_id: int, user_id: int, role: str = "member"):
    """Helper function to add a member to an organization using repository."""
    from syfthub.database.connection import get_db_session
    from syfthub.repositories.organization import OrganizationMemberRepository
    from syfthub.schemas.organization import OrganizationMemberCreate, OrganizationRole

    # Ensure user exists
    create_test_user(user_id)

    session = next(get_db_session())
    try:
        member_repo = OrganizationMemberRepository(session)
        member_data = OrganizationMemberCreate(
            user_id=user_id, role=OrganizationRole(role), is_active=True
        )
        return member_repo.add_member(member_data, org_id)
    finally:
        session.close()


class TestOrganizationCRUD:
    """Test organization CRUD operations."""

    def test_create_organization(self, client, auth_headers):
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

    def test_create_organization_auto_slug(self, client, auth_headers):
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

    def test_create_organization_reserved_slug(self, client, auth_headers):
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

    def test_create_organization_duplicate_slug(self, client, auth_headers):
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

    def test_get_organization(self, client, auth_headers):
        """Test getting organization details."""
        # Create organization with user as owner
        org = create_test_organization(creator_user_id=1, client_instance=client)
        assert org is not None, "Failed to create test organization"

        response = client.get(f"/api/v1/organizations/{org.id}", headers=auth_headers)
        assert response.status_code == 200

        org_response = response.json()
        assert org_response["name"] == "Test Organization"
        assert org_response["slug"] == "test-org"

    def test_get_organization_not_member(self, client, auth_headers):
        """Test getting organization when not a member fails."""
        # Create organization with different user as owner (not test user)
        org = create_test_organization(creator_user_id=999, client_instance=client)

        response = client.get(f"/api/v1/organizations/{org.id}", headers=auth_headers)
        assert response.status_code == 404

    def test_update_organization(self, client, auth_headers):
        """Test updating organization."""
        # Create organization with user as owner
        org = create_test_organization(creator_user_id=1, client_instance=client)

        update_data = {"name": "Updated Organization"}
        response = client.put(
            f"/api/v1/organizations/{org.id}", json=update_data, headers=auth_headers
        )
        assert response.status_code == 200

        org_response = response.json()
        assert org_response["name"] == "Updated Organization"

    def test_update_organization_not_admin(self, client, auth_headers):
        """Test updating organization without admin rights fails."""
        # Create organization with a different user as owner (user 2)
        org = create_test_organization(creator_user_id=2)

        # Add test user (user 1) as member (not admin)
        add_test_organization_member(org.id, user_id=1, role="member")

        update_data = {"name": "Updated Organization"}
        response = client.put(
            f"/api/v1/organizations/{org.id}", json=update_data, headers=auth_headers
        )
        assert response.status_code == 403

    def test_delete_organization(self, client, auth_headers):
        """Test deleting organization."""
        # Create organization with user as owner
        org = create_test_organization(creator_user_id=1, client_instance=client)

        response = client.delete(
            f"/api/v1/organizations/{org.id}", headers=auth_headers
        )
        assert response.status_code == 204

        # Verify organization is not accessible anymore
        response = client.get(f"/api/v1/organizations/{org.id}", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_organization_not_owner(self, client, auth_headers):
        """Test deleting organization without owner rights fails."""
        # Create organization with user 2 as owner
        org = create_test_organization(creator_user_id=2, client_instance=client)

        # Add test user (user 1) as admin (not owner)
        add_test_organization_member(org.id, user_id=1, role="admin")

        response = client.delete(
            f"/api/v1/organizations/{org.id}", headers=auth_headers
        )
        assert response.status_code == 403

    def test_list_my_organizations(self, client, auth_headers):
        """Test listing user's organizations."""
        # Create organization with user as member
        create_test_organization(creator_user_id=1, client_instance=client)

        response = client.get("/api/v1/organizations/", headers=auth_headers)
        assert response.status_code == 200

        orgs = response.json()
        assert len(orgs) == 1
        assert orgs[0]["name"] == "Test Organization"


class TestOrganizationMembers:
    """Test organization member management."""

    def test_add_organization_member(self, client, auth_headers):
        """Test adding member to organization."""
        # Create organization with user as owner
        org = create_test_organization(creator_user_id=1, client_instance=client)

        # Ensure user 2 exists
        create_test_user(2)

        member_data = {"user_id": 2, "role": "member"}

        response = client.post(
            f"/api/v1/organizations/{org.id}/members",
            json=member_data,
            headers=auth_headers,
        )
        assert response.status_code == 201

        member = response.json()
        assert member["user_id"] == 2
        assert member["role"] == "member"

    def test_add_organization_member_not_admin(self, client, auth_headers):
        """Test adding member without admin rights fails."""
        # Create organization with user 2 as owner
        org = create_test_organization(creator_user_id=2, client_instance=client)

        # Make test user (user 1) regular member
        add_test_organization_member(org.id, user_id=1, role="member")

        member_data = {"user_id": 3, "role": "member"}

        response = client.post(
            f"/api/v1/organizations/{org.id}/members",
            json=member_data,
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_list_organization_members(self, client, auth_headers):
        """Test listing organization members."""
        # Create organization with user as owner
        org = create_test_organization(creator_user_id=1, client_instance=client)

        response = client.get(
            f"/api/v1/organizations/{org.id}/members", headers=auth_headers
        )
        assert response.status_code == 200

        members = response.json()
        assert len(members) == 1
        assert members[0]["role"] == "owner"

    def test_update_organization_member(self, client, auth_headers):
        """Test updating organization member role."""
        # Create organization with user 1 as owner
        org = create_test_organization(creator_user_id=1, client_instance=client)

        # Add user 2 as member
        add_test_organization_member(org.id, user_id=2, role="member")

        update_data = {"role": "admin"}
        response = client.put(
            f"/api/v1/organizations/{org.id}/members/2",
            json=update_data,
            headers=auth_headers,
        )
        assert response.status_code == 200

        member = response.json()
        assert member["role"] == "admin"

    def test_remove_organization_member(self, client, auth_headers):
        """Test removing organization member."""
        # Create organization with user 1 as owner
        org = create_test_organization(creator_user_id=1, client_instance=client)

        # Add user 2 as member
        add_test_organization_member(org.id, user_id=2, role="member")

        response = client.delete(
            f"/api/v1/organizations/{org.id}/members/2", headers=auth_headers
        )
        assert response.status_code == 204

        # Verify member is removed by trying to list members
        response = client.get(
            f"/api/v1/organizations/{org.id}/members", headers=auth_headers
        )
        assert response.status_code == 200
        members = response.json()
        assert len(members) == 1  # Only owner should remain
        assert members[0]["user_id"] == 1  # Owner

    def test_remove_last_owner_fails(self, client, auth_headers):
        """Test removing last owner fails."""
        # Create organization with user as owner
        org = create_test_organization(creator_user_id=1, client_instance=client)

        response = client.delete(
            f"/api/v1/organizations/{org.id}/members/1", headers=auth_headers
        )
        assert response.status_code == 400
        assert "last owner" in response.json()["detail"]


class TestOrganizationAuth:
    """Test organization authentication and authorization."""

    def test_create_organization_requires_auth(self, client):
        """Test creating organization without auth fails."""
        org_data = {"name": "Unauthorized Organization"}
        response = client.post("/api/v1/organizations/", json=org_data)
        assert response.status_code == 401

    def test_admin_can_access_any_organization(self, client, admin_headers):
        """Test admin can access any organization."""
        # Create organization
        org = create_test_organization(creator_user_id=999)

        response = client.get(f"/api/v1/organizations/{org.id}", headers=admin_headers)
        assert response.status_code == 200

    def test_member_self_removal(self, client, auth_headers):
        """Test member can remove themselves."""
        # Create organization with user 2 as owner
        org = create_test_organization(creator_user_id=2, client_instance=client)

        # Add test user (user 1) as member
        add_test_organization_member(org.id, user_id=1, role="member")

        response = client.delete(
            f"/api/v1/organizations/{org.id}/members/1", headers=auth_headers
        )
        assert response.status_code == 204


class TestOrganizationSchemas:
    """Test organization schema validation."""

    def test_organization_role_enum(self):
        """Test organization role enum values."""
        assert OrganizationRole.OWNER == "owner"
        assert OrganizationRole.ADMIN == "admin"
        assert OrganizationRole.MEMBER == "member"

    def test_invalid_slug_validation(self, client, auth_headers):
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

    def test_organization_lookup_functions(self, client):
        """Test organization lookup helper functions."""
        from syfthub.api.endpoints.organizations import (
            get_organization_by_id,
            get_organization_by_slug,
            get_user_role_in_organization,
            is_organization_member,
        )
        from syfthub.database.connection import get_db_session
        from syfthub.repositories.organization import (
            OrganizationMemberRepository,
            OrganizationRepository,
        )

        # Create organization for testing
        org = create_test_organization(
            creator_user_id=100, client_instance=client
        )  # Use unique user ID
        assert org is not None, "Failed to create test organization"

        session = next(get_db_session())
        try:
            org_repo = OrganizationRepository(session)
            member_repo = OrganizationMemberRepository(session)

            # Test get by ID
            test_org = get_organization_by_id(org.id, org_repo)
            assert test_org is not None
            assert test_org.name == "Test Organization"

            # Test get by slug
            test_org = get_organization_by_slug("test-org", org_repo)
            assert test_org is not None
            assert test_org.name == "Test Organization"

            # Test with non-existent user (should return None/False)
            role = get_user_role_in_organization(org.id, 999, member_repo)
            assert role is None

            is_member_result = is_organization_member(org.id, 999, member_repo)
            assert is_member_result is False
        finally:
            session.close()
