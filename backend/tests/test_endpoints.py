"""Test endpoint endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app


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


@pytest.fixture
def user1_token(client: TestClient) -> str:
    """Create user1 and return access token."""
    user_data = {
        "username": "user1",
        "email": "user1@example.com",
        "full_name": "User One",
        "password": "testpass123",
    }

    response = client.post("/api/v1/auth/register", json=user_data)
    return response.json()["access_token"]


@pytest.fixture
def user2_token(client: TestClient) -> str:
    """Create user2 and return access token."""
    user_data = {
        "username": "user2",
        "email": "user2@example.com",
        "full_name": "User Two",
        "password": "testpass123",
    }

    response = client.post("/api/v1/auth/register", json=user_data)
    return response.json()["access_token"]


@pytest.fixture
def admin_token(client: TestClient) -> str:
    """Create admin user and return access token."""
    user_data = {
        "username": "admin",
        "email": "admin@example.com",
        "full_name": "Admin User",
        "password": "adminpass123",
    }

    response = client.post("/api/v1/auth/register", json=user_data)

    # Manually promote to admin
    from syfthub.database.connection import get_db_session
    from syfthub.repositories.user import UserRepository
    from syfthub.schemas.auth import UserRole

    user_id = response.json()["user"]["id"]

    # Update user role to admin using repository
    session = next(get_db_session())
    try:
        user_repo = UserRepository(session)
        user_repo.update_user_role(user_id, UserRole.ADMIN)
    finally:
        session.close()

    return response.json()["access_token"]


def test_create_endpoint_requires_auth(client: TestClient) -> None:
    """Test that creating endpoints requires authentication."""
    endpoint_data = {
        "name": "Test Endpoint",
        "description": "Test description",
        "type": "model",
        "visibility": "public",
    }

    # Try without authentication
    response = client.post("/api/v1/endpoints", json=endpoint_data)
    assert response.status_code == 401


def test_create_endpoint_with_auth(client: TestClient, user1_token: str) -> None:
    """Test creating a endpoint with authentication."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    endpoint_data = {
        "name": "My First Endpoint",
        "description": "This is my first endpoint",
        "type": "model",
        "visibility": "public",
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "My First Endpoint"
    assert data["slug"] == "my-first-endpoint"
    assert data["description"] == "This is my first endpoint"
    assert data["visibility"] == "public"
    assert data["version"] == "0.1.0"  # Default version
    assert data["readme"] == ""  # Default empty readme
    assert data["stars_count"] == 0  # Default stars count
    assert data["policies"] == []  # Default empty policies
    assert data["connect"] == []  # Default empty connect list
    assert len(data["contributors"]) == 1  # Owner is auto-added as contributor
    assert "user_id" in data
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_endpoint_with_custom_slug(client: TestClient, user1_token: str) -> None:
    """Test creating a endpoint with custom slug."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    endpoint_data = {
        "name": "Custom Slug Test",
        "slug": "my-custom-slug",
        "description": "Testing custom slug",
        "type": "model",
        "visibility": "public",
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["slug"] == "my-custom-slug"


def test_create_endpoint_invalid_slug(client: TestClient, user1_token: str) -> None:
    """Test creating a endpoint with invalid slug."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Test various invalid slugs
    invalid_slugs = [
        "ab",  # too short
        "a" * 64,  # too long
        "-invalid",  # starts with hyphen
        "invalid-",  # ends with hyphen
        "invalid--slug",  # consecutive hyphens
        "Invalid-Slug",  # uppercase
        "invalid_slug",  # underscore
        "invalid slug",  # space
        "api",  # reserved slug
    ]

    for invalid_slug in invalid_slugs:
        endpoint_data = {
            "name": "Test Endpoint",
            "slug": invalid_slug,
            "description": "Test",
            "type": "model",
            "visibility": "public",
        }

        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 422 or response.status_code == 400


def test_create_duplicate_slug_same_user(client: TestClient, user1_token: str) -> None:
    """Test that duplicate slugs for same user are rejected."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    endpoint_data = {
        "name": "Test Endpoint",
        "slug": "test-endpoint",
        "description": "Test",
        "type": "model",
        "visibility": "public",
    }

    # Create first endpoint
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    # Try to create second with same slug
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 400
    assert "already taken" in response.json()["detail"]


def test_create_same_slug_different_users(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that different users can have same endpoint slug."""
    endpoint_data = {
        "name": "Test Endpoint",
        "slug": "test-endpoint",
        "description": "Test",
        "type": "model",
        "visibility": "public",
    }

    # User1 creates endpoint
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers1)
    assert response.status_code == 201

    # User2 creates endpoint with same slug
    headers2 = {"Authorization": f"Bearer {user2_token}"}
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers2)
    assert response.status_code == 201


def test_list_my_endpoints(client: TestClient, user1_token: str) -> None:
    """Test listing current user's endpoints."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create multiple endpoints
    endpoints_data = [
        {"name": "Public Endpoint", "type": "model", "visibility": "public"},
        {"name": "Private Endpoint", "type": "model", "visibility": "private"},
        {"name": "Internal Endpoint", "type": "model", "visibility": "internal"},
    ]

    for endpoint_data in endpoints_data:
        client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)

    # List endpoints
    response = client.get("/api/v1/endpoints", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3


def test_list_my_endpoints_with_filters(client: TestClient, user1_token: str) -> None:
    """Test listing endpoints with filters."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoints
    endpoints_data = [
        {
            "name": "Widget Alpha",
            "description": "A widget",
            "type": "model",
            "visibility": "public",
        },
        {
            "name": "Widget Beta",
            "description": "Another widget",
            "type": "model",
            "visibility": "private",
        },
        {
            "name": "Tool Gamma",
            "description": "A tool",
            "type": "model",
            "visibility": "public",
        },
    ]

    for endpoint_data in endpoints_data:
        client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)

    # Test search filter
    response = client.get("/api/v1/endpoints?search=widget", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Test visibility filter
    response = client.get("/api/v1/endpoints?visibility=public", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_list_public_endpoints(client: TestClient, user1_token: str) -> None:
    """Test listing public endpoints."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoints with different visibility
    endpoints_data = [
        {"name": "Public Endpoint", "type": "model", "visibility": "public"},
        {"name": "Private Endpoint", "type": "model", "visibility": "private"},
        {"name": "Internal Endpoint", "type": "model", "visibility": "internal"},
    ]

    for endpoint_data in endpoints_data:
        client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)

    # List public endpoints (no auth required)
    response = client.get("/api/v1/endpoints/public")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Public Endpoint"


def test_get_endpoint_by_id(client: TestClient, user1_token: str) -> None:
    """Test getting a endpoint by ID."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoint
    endpoint_data = {"name": "Test Endpoint", "type": "model", "visibility": "public"}
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    endpoint_id = response.json()["id"]

    # Get endpoint by ID
    response = client.get(f"/api/v1/endpoints/{endpoint_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Test Endpoint"


def test_get_endpoint_visibility_controls(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test endpoint visibility controls."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers2 = {"Authorization": f"Bearer {user2_token}"}

    # User1 creates private endpoint
    endpoint_data = {
        "name": "Private Endpoint",
        "type": "model",
        "visibility": "private",
    }
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers1)
    endpoint_id = response.json()["id"]

    # User1 (owner) can access
    response = client.get(f"/api/v1/endpoints/{endpoint_id}", headers=headers1)
    assert response.status_code == 200

    # User2 cannot access (returns 404 to hide existence)
    response = client.get(f"/api/v1/endpoints/{endpoint_id}", headers=headers2)
    assert response.status_code == 404

    # Unauthenticated user cannot access
    response = client.get(f"/api/v1/endpoints/{endpoint_id}")
    assert response.status_code == 401


def test_get_endpoint_internal_visibility(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test internal endpoint visibility."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers2 = {"Authorization": f"Bearer {user2_token}"}

    # User1 creates internal endpoint
    endpoint_data = {
        "name": "Internal Endpoint",
        "type": "model",
        "visibility": "internal",
    }
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers1)
    endpoint_id = response.json()["id"]

    # Owner can access
    response = client.get(f"/api/v1/endpoints/{endpoint_id}", headers=headers1)
    assert response.status_code == 200

    # Other authenticated user can access
    response = client.get(f"/api/v1/endpoints/{endpoint_id}", headers=headers2)
    assert response.status_code == 200

    # Unauthenticated user cannot access
    response = client.get(f"/api/v1/endpoints/{endpoint_id}")
    assert response.status_code == 401


def test_update_endpoint(client: TestClient, user1_token: str) -> None:
    """Test updating a endpoint."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoint
    endpoint_data = {"name": "Original Name", "type": "model", "visibility": "public"}
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    endpoint_id = response.json()["id"]

    # Update endpoint
    update_data = {"name": "Updated Name", "description": "Updated description"}
    response = client.patch(
        f"/api/v1/endpoints/{endpoint_id}", json=update_data, headers=headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated description"
    assert data["visibility"] == "public"  # Unchanged


def test_update_endpoint_ownership(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that users can only update their own endpoints."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers2 = {"Authorization": f"Bearer {user2_token}"}

    # User1 creates endpoint
    endpoint_data = {"name": "User1 Endpoint", "type": "model", "visibility": "public"}
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers1)
    endpoint_id = response.json()["id"]

    # User2 tries to update User1's endpoint
    update_data = {"name": "Hacked Name"}
    response = client.patch(
        f"/api/v1/endpoints/{endpoint_id}", json=update_data, headers=headers2
    )
    assert response.status_code == 403

    # User1 can update their own endpoint
    response = client.patch(
        f"/api/v1/endpoints/{endpoint_id}", json=update_data, headers=headers1
    )
    assert response.status_code == 200


def test_delete_endpoint(client: TestClient, user1_token: str) -> None:
    """Test deleting a endpoint."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoint
    endpoint_data = {"name": "To Delete", "type": "model", "visibility": "public"}
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    endpoint_id = response.json()["id"]

    # Delete endpoint
    response = client.delete(f"/api/v1/endpoints/{endpoint_id}", headers=headers)
    assert response.status_code == 204

    # Verify deletion
    response = client.get(f"/api/v1/endpoints/{endpoint_id}", headers=headers)
    assert response.status_code == 404


def test_delete_endpoint_ownership(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that users can only delete their own endpoints."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers2 = {"Authorization": f"Bearer {user2_token}"}

    # User1 creates endpoint
    endpoint_data = {"name": "User1 Endpoint", "type": "model", "visibility": "public"}
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers1)
    endpoint_id = response.json()["id"]

    # User2 tries to delete User1's endpoint
    response = client.delete(f"/api/v1/endpoints/{endpoint_id}", headers=headers2)
    assert response.status_code == 403

    # User1 can delete their own endpoint
    response = client.delete(f"/api/v1/endpoints/{endpoint_id}", headers=headers1)
    assert response.status_code == 204


def test_admin_can_access_any_endpoint(
    client: TestClient, user1_token: str, admin_token: str
) -> None:
    """Test that admin can access any endpoint."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    # User1 creates private endpoint
    endpoint_data = {
        "name": "Private Endpoint",
        "type": "model",
        "visibility": "private",
    }
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers1)
    endpoint_id = response.json()["id"]

    # Admin can access private endpoint
    response = client.get(f"/api/v1/endpoints/{endpoint_id}", headers=headers_admin)
    assert response.status_code == 200

    # Admin can update any endpoint
    update_data = {"name": "Admin Updated"}
    response = client.patch(
        f"/api/v1/endpoints/{endpoint_id}", json=update_data, headers=headers_admin
    )
    assert response.status_code == 200

    # Admin can delete any endpoint
    response = client.delete(f"/api/v1/endpoints/{endpoint_id}", headers=headers_admin)
    assert response.status_code == 204


# Test GitHub-like URL routing
def test_list_user_endpoints_by_username(client: TestClient, user1_token: str) -> None:
    """Test listing user's endpoints by username."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create public endpoint
    endpoint_data = {"name": "Public Endpoint", "type": "model", "visibility": "public"}
    client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)

    # Create private endpoint
    endpoint_data = {
        "name": "Private Endpoint",
        "type": "model",
        "visibility": "private",
    }
    client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)

    # List user's public endpoints by username (no auth)
    response = client.get("/user1")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1  # Only public endpoint should be visible
    assert data[0]["name"] == "Public Endpoint"


def test_get_endpoint_by_username_and_slug(
    client: TestClient, user1_token: str
) -> None:
    """Test getting endpoint by username and slug."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create public endpoint
    endpoint_data = {
        "name": "My Endpoint",
        "slug": "my-endpoint",
        "type": "model",
        "visibility": "public",
    }
    client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)

    # Access by username/slug
    response = client.get("/user1/my-endpoint")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "My Endpoint"
    assert data["slug"] == "my-endpoint"


def test_get_private_endpoint_by_url_requires_auth(
    client: TestClient, user1_token: str
) -> None:
    """Test that private endpoints via URL require authentication."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create private endpoint
    endpoint_data = {
        "name": "Private Endpoint",
        "slug": "private-ds",
        "type": "model",
        "visibility": "private",
    }
    client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)

    # Unauthenticated access should fail
    response = client.get("/user1/private-ds")
    assert response.status_code == 401

    # Authenticated owner access should work
    response = client.get("/user1/private-ds", headers=headers)
    assert response.status_code == 200


def test_nonexistent_user_or_endpoint(client: TestClient) -> None:
    """Test accessing non-existent user or endpoint."""
    # Non-existent user
    response = client.get("/nonexistentuser")
    assert response.status_code == 404

    # Non-existent endpoint
    response = client.get("/nonexistentuser/nonexistentendpoint")
    assert response.status_code == 404


def test_case_insensitive_username_lookup(client: TestClient, user1_token: str) -> None:
    """Test that username lookup is case insensitive."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoint
    endpoint_data = {"name": "Test Endpoint", "type": "model", "visibility": "public"}
    client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)

    # Test different cases
    for username in ["user1", "User1", "USER1", "uSeR1"]:
        response = client.get(f"/{username}")
        assert response.status_code == 200


def test_slug_generation_from_name(client: TestClient, user1_token: str) -> None:
    """Test automatic slug generation from name."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    test_cases = [
        ("Simple Name", "simple-name"),
        ("Complex Name With Spaces!", "complex-name-with-spaces"),
        ("Special-Characters#@$%", "special-characters"),
        ("A", "endpoint-a"),  # Too short, gets prefix
        ("Multiple    Spaces", "multiple-spaces"),
    ]

    for name, expected_slug in test_cases:
        endpoint_data = {"name": name, "type": "model", "visibility": "public"}
        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 201
        assert response.json()["slug"] == expected_slug


def test_create_endpoint_with_custom_attributes(
    client: TestClient, user1_token: str
) -> None:
    """Test creating a endpoint with custom version and readme."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    endpoint_data = {
        "name": "Advanced Endpoint",
        "description": "A endpoint with custom attributes",
        "type": "model",
        "visibility": "public",
        "version": "1.2.3",
        "readme": "# My Project\n\nThis is a sample README with markdown.",
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Advanced Endpoint"
    assert data["version"] == "1.2.3"
    assert data["readme"] == "# My Project\n\nThis is a sample README with markdown."
    assert len(data["contributors"]) == 1


def test_create_endpoint_invalid_version(client: TestClient, user1_token: str) -> None:
    """Test creating a endpoint with invalid version format."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    invalid_versions = [
        "1.2",  # Missing patch version
        "v1.2.3",  # Prefix not allowed
        "1.2.3-alpha",  # Pre-release not supported
        "invalid",  # Not semantic version
    ]

    for invalid_version in invalid_versions:
        endpoint_data = {
            "name": "Test Endpoint",
            "type": "model",
            "version": invalid_version,
            "visibility": "public",
        }

        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 422  # Validation error


def test_update_endpoint_new_attributes(client: TestClient, user1_token: str) -> None:
    """Test updating endpoint with new attributes."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoint
    endpoint_data = {
        "name": "Original Endpoint",
        "type": "model",
        "visibility": "public",
    }
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    endpoint_id = response.json()["id"]

    # Update with new attributes
    update_data = {
        "version": "2.0.0",
        "readme": "# Updated README\n\nThis endpoint has been updated.",
    }
    response = client.patch(
        f"/api/v1/endpoints/{endpoint_id}", json=update_data, headers=headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == "2.0.0"
    assert data["readme"] == "# Updated README\n\nThis endpoint has been updated."


def test_create_endpoint_with_contributors(
    client: TestClient, user1_token: str
) -> None:
    """Test creating a endpoint with explicit contributors list."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Simulate adding additional contributor IDs
    endpoint_data = {
        "name": "Collaborative Endpoint",
        "type": "model",
        "visibility": "public",
        "contributors": [1, 2, 3],  # Mock user IDs
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    # Owner should still be in contributors even if not explicitly added
    assert 1 in data["contributors"]  # Assuming user1 has ID 1
    assert len(data["contributors"]) >= 1


def test_endpoint_public_response_includes_new_fields(
    client: TestClient, user1_token: str
) -> None:
    """Test that public endpoint response includes new fields."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoint with all new fields
    endpoint_data = {
        "name": "Public Endpoint",
        "description": "A public endpoint for testing",
        "type": "model",
        "visibility": "public",
        "version": "3.1.4",
        "readme": "# Public Project\n\nThis is publicly accessible.",
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    # Test public listing endpoint
    response = client.get("/api/v1/endpoints/public")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    public_endpoint = data[0]

    # Verify new fields are included in public response
    assert public_endpoint["version"] == "3.1.4"
    assert (
        public_endpoint["readme"] == "# Public Project\n\nThis is publicly accessible."
    )
    # Note: contributors field is NOT in EndpointPublicResponse for privacy reasons
    assert "contributors" not in public_endpoint


def test_endpoint_version_filter_capability(
    client: TestClient, user1_token: str
) -> None:
    """Test creating endpoints with different versions for future filtering."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoints with different versions
    versions = ["1.0.0", "1.1.0", "2.0.0"]
    for version in versions:
        endpoint_data = {
            "name": f"Endpoint v{version}",
            "type": "model",
            "visibility": "public",
            "version": version,
        }
        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 201
        assert response.json()["version"] == version


def test_endpoint_stars_count_default(client: TestClient, user1_token: str) -> None:
    """Test that new endpoints start with 0 stars."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    endpoint_data = {
        "name": "New Endpoint",
        "description": "Testing stars functionality",
        "type": "model",
        "visibility": "public",
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["stars_count"] == 0


def test_trending_endpoints_endpoint(client: TestClient, user1_token: str) -> None:
    """Test the trending endpoints endpoint (sorted by stars)."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoints with different star counts (simulated)
    endpoints_data = [
        {"name": "Popular Endpoint", "type": "model", "visibility": "public"},
        {"name": "Average Endpoint", "type": "model", "visibility": "public"},
        {"name": "New Endpoint", "type": "model", "visibility": "public"},
    ]

    created_ids = []
    for endpoint_data in endpoints_data:
        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    # Simulate different star counts by directly updating the database
    from syfthub.database.connection import get_db_session
    from syfthub.repositories.endpoint import EndpointRepository

    session = next(get_db_session())
    try:
        endpoint_repo = EndpointRepository(session)
        # Update star counts directly
        endpoint_repo.update(created_ids[0], stars_count=10)  # Most popular
        endpoint_repo.update(created_ids[1], stars_count=5)  # Moderate
        # Leave created_ids[2] with 0 stars
    finally:
        session.close()

    # Test trending endpoint
    response = client.get("/api/v1/endpoints/trending")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3

    # Should be sorted by stars count (descending)
    assert data[0]["name"] == "Popular Endpoint"
    assert data[0]["stars_count"] == 10
    assert data[1]["name"] == "Average Endpoint"
    assert data[1]["stars_count"] == 5
    assert data[2]["name"] == "New Endpoint"
    assert data[2]["stars_count"] == 0


def test_trending_endpoints_with_min_stars_filter(
    client: TestClient, user1_token: str
) -> None:
    """Test trending endpoints with minimum stars filter."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoints
    endpoints_data = [
        {"name": "High Stars Endpoint", "type": "model", "visibility": "public"},
        {"name": "Low Stars Endpoint", "type": "model", "visibility": "public"},
    ]

    created_ids = []
    for endpoint_data in endpoints_data:
        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    # Simulate star counts by directly updating the database
    from syfthub.database.connection import get_db_session
    from syfthub.repositories.endpoint import EndpointRepository

    session = next(get_db_session())
    try:
        endpoint_repo = EndpointRepository(session)
        # Update star counts directly
        endpoint_repo.update(created_ids[0], stars_count=15)
        endpoint_repo.update(created_ids[1], stars_count=2)
    finally:
        session.close()

    # Test with min_stars filter
    response = client.get("/api/v1/endpoints/trending?min_stars=10")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "High Stars Endpoint"
    assert data[0]["stars_count"] == 15


def test_public_endpoint_response_includes_stars(
    client: TestClient, user1_token: str
) -> None:
    """Test that public responses include stars count."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create a endpoint
    endpoint_data = {
        "name": "Public Endpoint with Stars",
        "description": "Testing public response",
        "type": "model",
        "visibility": "public",
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201
    endpoint_id = response.json()["id"]

    # Simulate some stars by updating the database directly
    from syfthub.database.connection import get_db_session
    from syfthub.repositories.endpoint import EndpointRepository

    session = next(get_db_session())
    try:
        endpoint_repo = EndpointRepository(session)
        endpoint_repo.update(endpoint_id, stars_count=42)
    finally:
        session.close()

    # Test public listing endpoint
    response = client.get("/api/v1/endpoints/public")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert "stars_count" in data[0]
    assert data[0]["stars_count"] == 42

    # Test GitHub-style URL access
    response = client.get("/user1/public-endpoint-with-stars")
    assert response.status_code == 200

    data = response.json()
    assert "stars_count" in data
    assert data["stars_count"] == 42


def test_trending_endpoints_pagination(client: TestClient, user1_token: str) -> None:
    """Test pagination in trending endpoints endpoint."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create multiple endpoints
    for i in range(5):
        endpoint_data = {
            "name": f"Endpoint {i}",
            "type": "model",
            "visibility": "public",
        }
        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 201

    # Test pagination
    response = client.get("/api/v1/endpoints/trending?skip=0&limit=3")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3

    response = client.get("/api/v1/endpoints/trending?skip=3&limit=3")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2  # Remaining endpoints


def test_create_endpoint_with_policies(client: TestClient, user1_token: str) -> None:
    """Test creating a endpoint with policies."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Policy-Enabled Endpoint",
        "description": "A endpoint with custom policies",
        "type": "model",
        "visibility": "public",
        "policies": [
            {
                "type": "data_retention",
                "version": "1.0",
                "enabled": True,
                "description": "Automatic data cleanup after retention period",
                "config": {
                    "retention_days": 365,
                    "auto_cleanup": True,
                    "notification_days": [30, 7, 1],
                },
            },
            {
                "type": "access_control",
                "version": "2.1",
                "enabled": True,
                "description": "Role-based access restrictions",
                "config": {
                    "require_approval": True,
                    "allowed_roles": ["researcher", "analyst"],
                    "max_concurrent_users": 5,
                },
            },
        ],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Policy-Enabled Endpoint"
    assert len(data["policies"]) == 2

    # Check first policy
    retention_policy = data["policies"][0]
    assert retention_policy["type"] == "data_retention"
    assert retention_policy["version"] == "1.0"
    assert retention_policy["enabled"] is True
    assert retention_policy["config"]["retention_days"] == 365
    assert retention_policy["config"]["auto_cleanup"] is True

    # Check second policy
    access_policy = data["policies"][1]
    assert access_policy["type"] == "access_control"
    assert access_policy["version"] == "2.1"
    assert access_policy["config"]["max_concurrent_users"] == 5


def test_create_endpoint_default_empty_policies(
    client: TestClient, user1_token: str
) -> None:
    """Test that endpoints default to empty policies list."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    endpoint_data = {
        "name": "No Policies Endpoint",
        "type": "model",
        "visibility": "public",
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["policies"] == []


def test_create_endpoint_with_minimal_policy(
    client: TestClient, user1_token: str
) -> None:
    """Test creating endpoint with minimal policy (only type required)."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Minimal Policy Endpoint",
        "type": "model",
        "visibility": "public",
        "policies": [{"type": "simple_policy"}],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    policy = data["policies"][0]
    assert policy["type"] == "simple_policy"
    assert policy["version"] == "1.0"  # Default version
    assert policy["enabled"] is True  # Default enabled
    assert policy["description"] == ""  # Default empty description
    assert policy["config"] == {}  # Default empty config


def test_create_endpoint_invalid_policy_type(
    client: TestClient, user1_token: str
) -> None:
    """Test creating endpoint with invalid policy type."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Invalid Policy Endpoint",
        "type": "model",
        "visibility": "public",
        "policies": [
            {
                "type": "",  # Empty type should fail validation
                "config": {"test": "value"},
            }
        ],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 422  # Validation error


def test_update_endpoint_policies(client: TestClient, user1_token: str) -> None:
    """Test updating endpoint policies."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoint with initial policy
    endpoint_data = {
        "name": "Updateable Policies Endpoint",
        "type": "model",
        "visibility": "public",
        "policies": [
            {"type": "initial_policy", "description": "Initial policy configuration"}
        ],
    }
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    endpoint_id = response.json()["id"]

    # Update with new policies
    update_data = {
        "policies": [
            {
                "type": "updated_policy",
                "version": "2.0",
                "enabled": False,
                "description": "Updated policy configuration",
                "config": {
                    "new_setting": "value",
                    "complex_config": {"nested": True, "items": [1, 2, 3]},
                },
            }
        ]
    }
    response = client.patch(
        f"/api/v1/endpoints/{endpoint_id}", json=update_data, headers=headers
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["policies"]) == 1
    policy = data["policies"][0]
    assert policy["type"] == "updated_policy"
    assert policy["version"] == "2.0"
    assert policy["enabled"] is False
    assert policy["config"]["new_setting"] == "value"
    assert policy["config"]["complex_config"]["nested"] is True


def test_public_endpoint_response_includes_policies(
    client: TestClient, user1_token: str
) -> None:
    """Test that public responses include policies."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Public Policies Endpoint",
        "type": "model",
        "visibility": "public",
        "policies": [
            {
                "type": "public_policy",
                "description": "A policy visible to all users",
                "config": {"public_setting": True},
            }
        ],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    # Test public listing endpoint
    response = client.get("/api/v1/endpoints/public")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert "policies" in data[0]
    assert len(data[0]["policies"]) == 1
    assert data[0]["policies"][0]["type"] == "public_policy"


def test_policy_version_validation(client: TestClient, user1_token: str) -> None:
    """Test policy version format validation."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Valid versions
    valid_versions = ["1.0", "2.5", "10.15"]
    for version in valid_versions:
        endpoint_data = {
            "name": f"Version Test {version}",
            "type": "model",
            "visibility": "public",
            "policies": [{"type": "test_policy", "version": version}],
        }
        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 201
        assert response.json()["policies"][0]["version"] == version

    # Invalid versions
    invalid_versions = ["1", "1.0.0", "v1.0", "1.0-alpha"]
    for version in invalid_versions:
        endpoint_data = {
            "name": "Invalid Version Test",
            "type": "model",
            "visibility": "public",
            "policies": [{"type": "test_policy", "version": version}],
        }
        response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
        assert response.status_code == 422  # Validation error


def test_complex_policy_configurations(client: TestClient, user1_token: str) -> None:
    """Test policies with complex nested configurations."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Complex Config Endpoint",
        "type": "model",
        "visibility": "public",
        "policies": [
            {
                "type": "complex_policy",
                "description": "Policy with complex nested configuration",
                "config": {
                    "string_value": "test",
                    "number_value": 42,
                    "boolean_value": True,
                    "array_value": ["item1", "item2", "item3"],
                    "nested_object": {
                        "level1": {
                            "level2": {
                                "deep_setting": "deep_value",
                                "deep_array": [1, 2, 3],
                            }
                        }
                    },
                    "null_value": None,
                },
            }
        ],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    config = data["policies"][0]["config"]
    assert config["string_value"] == "test"
    assert config["number_value"] == 42
    assert config["boolean_value"] is True
    assert config["array_value"] == ["item1", "item2", "item3"]
    assert config["nested_object"]["level1"]["level2"]["deep_setting"] == "deep_value"
    assert config["null_value"] is None


def test_create_endpoint_with_connections(client: TestClient, user1_token: str) -> None:
    """Test creating a endpoint with connection configurations."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Connection-Enabled Endpoint",
        "description": "A endpoint with connection methods",
        "type": "model",
        "visibility": "public",
        "connect": [
            {
                "type": "http",
                "enabled": True,
                "description": "Public HTTP API access",
                "config": {
                    "url": "https://api.example.com",
                    "auth_required": False,
                    "rate_limit": "1000/hour",
                },
            },
            {
                "type": "webrtc",
                "enabled": True,
                "description": "WebRTC connection for real-time access",
                "config": {
                    "signaling_server": "wss://signal.example.com",
                    "ice_servers": ["stun:stun.l.google.com:19302"],
                    "requires_negotiation": True,
                },
            },
        ],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Connection-Enabled Endpoint"
    assert len(data["connect"]) == 2

    # Check first connection
    http_connection = data["connect"][0]
    assert http_connection["type"] == "http"
    assert http_connection["enabled"] is True
    assert http_connection["description"] == "Public HTTP API access"
    assert http_connection["config"]["url"] == "https://api.example.com"
    assert http_connection["config"]["auth_required"] is False

    # Check second connection
    webrtc_connection = data["connect"][1]
    assert webrtc_connection["type"] == "webrtc"
    assert webrtc_connection["enabled"] is True
    assert webrtc_connection["config"]["requires_negotiation"] is True


def test_create_endpoint_default_empty_connections(
    client: TestClient, user1_token: str
) -> None:
    """Test that endpoints default to empty connections list."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    endpoint_data = {
        "name": "No Connections Endpoint",
        "type": "model",
        "visibility": "public",
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["connect"] == []


def test_create_endpoint_with_minimal_connection(
    client: TestClient, user1_token: str
) -> None:
    """Test creating endpoint with minimal connection (only type required)."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Minimal Connection Endpoint",
        "type": "model",
        "visibility": "public",
        "connect": [{"type": "simple_connection"}],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    connection = data["connect"][0]
    assert connection["type"] == "simple_connection"
    assert connection["enabled"] is True  # Default enabled
    assert connection["description"] == ""  # Default empty description
    assert connection["config"] == {}  # Default empty config


def test_create_endpoint_invalid_connection_type(
    client: TestClient, user1_token: str
) -> None:
    """Test creating endpoint with invalid connection type."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Invalid Connection Endpoint",
        "type": "model",
        "visibility": "public",
        "connect": [
            {
                "type": "",  # Empty type should fail validation
                "config": {"test": "value"},
            }
        ],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 422  # Validation error


def test_update_endpoint_connections(client: TestClient, user1_token: str) -> None:
    """Test updating endpoint connections."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create endpoint with initial connection
    endpoint_data = {
        "name": "Updateable Connections Endpoint",
        "type": "model",
        "visibility": "public",
        "connect": [
            {"type": "initial_connection", "description": "Initial connection setup"}
        ],
    }
    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    endpoint_id = response.json()["id"]

    # Update with new connections
    update_data = {
        "connect": [
            {
                "type": "ngrok",
                "enabled": True,
                "description": "Temporary ngrok tunnel",
                "config": {
                    "tunnel_url": "https://abc123.ngrok.io",
                    "expires": "2024-12-31T23:59:59Z",
                    "tunnel_type": "http",
                },
            }
        ]
    }
    response = client.patch(
        f"/api/v1/endpoints/{endpoint_id}", json=update_data, headers=headers
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["connect"]) == 1
    connection = data["connect"][0]
    assert connection["type"] == "ngrok"
    assert connection["enabled"] is True
    assert connection["config"]["tunnel_url"] == "https://abc123.ngrok.io"


def test_public_endpoint_response_includes_connections(
    client: TestClient, user1_token: str
) -> None:
    """Test that public responses include connections."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Public Connections Endpoint",
        "type": "model",
        "visibility": "public",
        "connect": [
            {
                "type": "public_api",
                "description": "A connection visible to all users",
                "config": {"endpoint": "https://api.public.example.com"},
            }
        ],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    # Test public listing endpoint
    response = client.get("/api/v1/endpoints/public")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert "connect" in data[0]
    assert len(data[0]["connect"]) == 1
    assert data[0]["connect"][0]["type"] == "public_api"


def test_complex_connection_configurations(
    client: TestClient, user1_token: str
) -> None:
    """Test connections with complex nested configurations."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    endpoint_data = {
        "name": "Complex Connection Config Endpoint",
        "type": "model",
        "visibility": "public",
        "connect": [
            {
                "type": "advanced_connection",
                "description": "Connection with complex nested configuration",
                "config": {
                    "servers": [
                        {"host": "server1.example.com", "port": 8080, "ssl": True},
                        {"host": "server2.example.com", "port": 8081, "ssl": False},
                    ],
                    "auth": {
                        "type": "oauth2",
                        "client_id": "abc123",
                        "scopes": ["read", "write", "admin"],
                    },
                    "features": {
                        "real_time": True,
                        "batch_processing": False,
                        "max_connections": 100,
                    },
                    "metadata": {"version": "2.1", "region": "us-east-1"},
                },
            }
        ],
    }

    response = client.post("/api/v1/endpoints", json=endpoint_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    config = data["connect"][0]["config"]
    assert len(config["servers"]) == 2
    assert config["servers"][0]["host"] == "server1.example.com"
    assert config["auth"]["type"] == "oauth2"
    assert config["features"]["max_connections"] == 100
    assert config["metadata"]["region"] == "us-east-1"
