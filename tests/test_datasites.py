"""Test datasite endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from syfthub.api.endpoints.datasites import (
    fake_datasites_db,
    slug_to_datasite_lookup,
    user_datasites_lookup,
)
from syfthub.api.endpoints.items import fake_items_db
from syfthub.auth.dependencies import fake_users_db, username_to_id
from syfthub.auth.security import token_blacklist
from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_databases() -> None:
    """Reset all databases before each test."""
    fake_users_db.clear()
    username_to_id.clear()
    token_blacklist.clear()
    fake_items_db.clear()
    fake_datasites_db.clear()
    user_datasites_lookup.clear()
    slug_to_datasite_lookup.clear()

    # Reset counters
    import syfthub.api.endpoints.datasites as datasites_module
    import syfthub.api.endpoints.items as items_module
    import syfthub.auth.router as auth_module

    auth_module.user_id_counter = 1
    items_module.item_id_counter = 1
    datasites_module.datasite_id_counter = 1


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
    from syfthub.schemas.auth import UserRole

    user_id = response.json()["user"]["id"]
    fake_users_db[user_id].role = UserRole.ADMIN

    return response.json()["access_token"]


def test_create_datasite_requires_auth(client: TestClient) -> None:
    """Test that creating datasites requires authentication."""
    datasite_data = {
        "name": "Test Datasite",
        "description": "Test description",
        "visibility": "public",
    }

    # Try without authentication
    response = client.post("/api/v1/datasites/", json=datasite_data)
    assert response.status_code == 401


def test_create_datasite_with_auth(client: TestClient, user1_token: str) -> None:
    """Test creating a datasite with authentication."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    datasite_data = {
        "name": "My First Datasite",
        "description": "This is my first datasite",
        "visibility": "public",
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "My First Datasite"
    assert data["slug"] == "my-first-datasite"
    assert data["description"] == "This is my first datasite"
    assert data["visibility"] == "public"
    assert data["version"] == "0.1.0"  # Default version
    assert data["readme"] == ""  # Default empty readme
    assert data["stars_count"] == 0  # Default stars count
    assert data["policies"] == []  # Default empty policies
    assert len(data["contributors"]) == 1  # Owner is auto-added as contributor
    assert "user_id" in data
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_datasite_with_custom_slug(client: TestClient, user1_token: str) -> None:
    """Test creating a datasite with custom slug."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    datasite_data = {
        "name": "Custom Slug Test",
        "slug": "my-custom-slug",
        "description": "Testing custom slug",
        "visibility": "public",
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["slug"] == "my-custom-slug"


def test_create_datasite_invalid_slug(client: TestClient, user1_token: str) -> None:
    """Test creating a datasite with invalid slug."""
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
        datasite_data = {
            "name": "Test Datasite",
            "slug": invalid_slug,
            "description": "Test",
            "visibility": "public",
        }

        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 422 or response.status_code == 400


def test_create_duplicate_slug_same_user(client: TestClient, user1_token: str) -> None:
    """Test that duplicate slugs for same user are rejected."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    datasite_data = {
        "name": "Test Datasite",
        "slug": "test-datasite",
        "description": "Test",
        "visibility": "public",
    }

    # Create first datasite
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    # Try to create second with same slug
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 400
    assert "already taken" in response.json()["detail"]


def test_create_same_slug_different_users(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that different users can have same datasite slug."""
    datasite_data = {
        "name": "Test Datasite",
        "slug": "test-datasite",
        "description": "Test",
        "visibility": "public",
    }

    # User1 creates datasite
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers1)
    assert response.status_code == 201

    # User2 creates datasite with same slug
    headers2 = {"Authorization": f"Bearer {user2_token}"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers2)
    assert response.status_code == 201


def test_list_my_datasites(client: TestClient, user1_token: str) -> None:
    """Test listing current user's datasites."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create multiple datasites
    datasites_data = [
        {"name": "Public Datasite", "visibility": "public"},
        {"name": "Private Datasite", "visibility": "private"},
        {"name": "Internal Datasite", "visibility": "internal"},
    ]

    for datasite_data in datasites_data:
        client.post("/api/v1/datasites/", json=datasite_data, headers=headers)

    # List datasites
    response = client.get("/api/v1/datasites/", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3


def test_list_my_datasites_with_filters(client: TestClient, user1_token: str) -> None:
    """Test listing datasites with filters."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasites
    datasites_data = [
        {"name": "Widget Alpha", "description": "A widget", "visibility": "public"},
        {
            "name": "Widget Beta",
            "description": "Another widget",
            "visibility": "private",
        },
        {"name": "Tool Gamma", "description": "A tool", "visibility": "public"},
    ]

    for datasite_data in datasites_data:
        client.post("/api/v1/datasites/", json=datasite_data, headers=headers)

    # Test search filter
    response = client.get("/api/v1/datasites/?search=widget", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Test visibility filter
    response = client.get("/api/v1/datasites/?visibility=public", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_list_public_datasites(client: TestClient, user1_token: str) -> None:
    """Test listing public datasites."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasites with different visibility
    datasites_data = [
        {"name": "Public Datasite", "visibility": "public"},
        {"name": "Private Datasite", "visibility": "private"},
        {"name": "Internal Datasite", "visibility": "internal"},
    ]

    for datasite_data in datasites_data:
        client.post("/api/v1/datasites/", json=datasite_data, headers=headers)

    # List public datasites (no auth required)
    response = client.get("/api/v1/datasites/public")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Public Datasite"


def test_get_datasite_by_id(client: TestClient, user1_token: str) -> None:
    """Test getting a datasite by ID."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasite
    datasite_data = {"name": "Test Datasite", "visibility": "public"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    datasite_id = response.json()["id"]

    # Get datasite by ID
    response = client.get(f"/api/v1/datasites/{datasite_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Test Datasite"


def test_get_datasite_visibility_controls(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test datasite visibility controls."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers2 = {"Authorization": f"Bearer {user2_token}"}

    # User1 creates private datasite
    datasite_data = {"name": "Private Datasite", "visibility": "private"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers1)
    datasite_id = response.json()["id"]

    # User1 (owner) can access
    response = client.get(f"/api/v1/datasites/{datasite_id}", headers=headers1)
    assert response.status_code == 200

    # User2 cannot access (returns 404 to hide existence)
    response = client.get(f"/api/v1/datasites/{datasite_id}", headers=headers2)
    assert response.status_code == 404

    # Unauthenticated user cannot access
    response = client.get(f"/api/v1/datasites/{datasite_id}")
    assert response.status_code == 401


def test_get_datasite_internal_visibility(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test internal datasite visibility."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers2 = {"Authorization": f"Bearer {user2_token}"}

    # User1 creates internal datasite
    datasite_data = {"name": "Internal Datasite", "visibility": "internal"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers1)
    datasite_id = response.json()["id"]

    # Owner can access
    response = client.get(f"/api/v1/datasites/{datasite_id}", headers=headers1)
    assert response.status_code == 200

    # Other authenticated user can access
    response = client.get(f"/api/v1/datasites/{datasite_id}", headers=headers2)
    assert response.status_code == 200

    # Unauthenticated user cannot access
    response = client.get(f"/api/v1/datasites/{datasite_id}")
    assert response.status_code == 401


def test_update_datasite(client: TestClient, user1_token: str) -> None:
    """Test updating a datasite."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasite
    datasite_data = {"name": "Original Name", "visibility": "public"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    datasite_id = response.json()["id"]

    # Update datasite
    update_data = {"name": "Updated Name", "description": "Updated description"}
    response = client.patch(
        f"/api/v1/datasites/{datasite_id}", json=update_data, headers=headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated description"
    assert data["visibility"] == "public"  # Unchanged


def test_update_datasite_ownership(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that users can only update their own datasites."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers2 = {"Authorization": f"Bearer {user2_token}"}

    # User1 creates datasite
    datasite_data = {"name": "User1 Datasite", "visibility": "public"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers1)
    datasite_id = response.json()["id"]

    # User2 tries to update User1's datasite
    update_data = {"name": "Hacked Name"}
    response = client.patch(
        f"/api/v1/datasites/{datasite_id}", json=update_data, headers=headers2
    )
    assert response.status_code == 403

    # User1 can update their own datasite
    response = client.patch(
        f"/api/v1/datasites/{datasite_id}", json=update_data, headers=headers1
    )
    assert response.status_code == 200


def test_delete_datasite(client: TestClient, user1_token: str) -> None:
    """Test deleting a datasite."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasite
    datasite_data = {"name": "To Delete", "visibility": "public"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    datasite_id = response.json()["id"]

    # Delete datasite
    response = client.delete(f"/api/v1/datasites/{datasite_id}", headers=headers)
    assert response.status_code == 204

    # Verify deletion
    response = client.get(f"/api/v1/datasites/{datasite_id}", headers=headers)
    assert response.status_code == 404


def test_delete_datasite_ownership(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that users can only delete their own datasites."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers2 = {"Authorization": f"Bearer {user2_token}"}

    # User1 creates datasite
    datasite_data = {"name": "User1 Datasite", "visibility": "public"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers1)
    datasite_id = response.json()["id"]

    # User2 tries to delete User1's datasite
    response = client.delete(f"/api/v1/datasites/{datasite_id}", headers=headers2)
    assert response.status_code == 403

    # User1 can delete their own datasite
    response = client.delete(f"/api/v1/datasites/{datasite_id}", headers=headers1)
    assert response.status_code == 204


def test_admin_can_access_any_datasite(
    client: TestClient, user1_token: str, admin_token: str
) -> None:
    """Test that admin can access any datasite."""
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    # User1 creates private datasite
    datasite_data = {"name": "Private Datasite", "visibility": "private"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers1)
    datasite_id = response.json()["id"]

    # Admin can access private datasite
    response = client.get(f"/api/v1/datasites/{datasite_id}", headers=headers_admin)
    assert response.status_code == 200

    # Admin can update any datasite
    update_data = {"name": "Admin Updated"}
    response = client.patch(
        f"/api/v1/datasites/{datasite_id}", json=update_data, headers=headers_admin
    )
    assert response.status_code == 200

    # Admin can delete any datasite
    response = client.delete(f"/api/v1/datasites/{datasite_id}", headers=headers_admin)
    assert response.status_code == 204


# Test GitHub-like URL routing
def test_list_user_datasites_by_username(client: TestClient, user1_token: str) -> None:
    """Test listing user's datasites by username."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create public datasite
    datasite_data = {"name": "Public Datasite", "visibility": "public"}
    client.post("/api/v1/datasites/", json=datasite_data, headers=headers)

    # Create private datasite
    datasite_data = {"name": "Private Datasite", "visibility": "private"}
    client.post("/api/v1/datasites/", json=datasite_data, headers=headers)

    # List user's public datasites by username (no auth)
    response = client.get("/user1")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1  # Only public datasite should be visible
    assert data[0]["name"] == "Public Datasite"


def test_get_datasite_by_username_and_slug(
    client: TestClient, user1_token: str
) -> None:
    """Test getting datasite by username and slug."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create public datasite
    datasite_data = {
        "name": "My Datasite",
        "slug": "my-datasite",
        "visibility": "public",
    }
    client.post("/api/v1/datasites/", json=datasite_data, headers=headers)

    # Access by username/slug
    response = client.get("/user1/my-datasite")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "My Datasite"
    assert data["slug"] == "my-datasite"


def test_get_private_datasite_by_url_requires_auth(
    client: TestClient, user1_token: str
) -> None:
    """Test that private datasites via URL require authentication."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create private datasite
    datasite_data = {
        "name": "Private Datasite",
        "slug": "private-ds",
        "visibility": "private",
    }
    client.post("/api/v1/datasites/", json=datasite_data, headers=headers)

    # Unauthenticated access should fail
    response = client.get("/user1/private-ds")
    assert response.status_code == 401

    # Authenticated owner access should work
    response = client.get("/user1/private-ds", headers=headers)
    assert response.status_code == 200


def test_nonexistent_user_or_datasite(client: TestClient) -> None:
    """Test accessing non-existent user or datasite."""
    # Non-existent user
    response = client.get("/nonexistentuser")
    assert response.status_code == 404

    # Non-existent datasite
    response = client.get("/nonexistentuser/nonexistentdatasite")
    assert response.status_code == 404


def test_case_insensitive_username_lookup(client: TestClient, user1_token: str) -> None:
    """Test that username lookup is case insensitive."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasite
    datasite_data = {"name": "Test Datasite", "visibility": "public"}
    client.post("/api/v1/datasites/", json=datasite_data, headers=headers)

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
        ("A", "datasite-a"),  # Too short, gets prefix
        ("Multiple    Spaces", "multiple-spaces"),
    ]

    for name, expected_slug in test_cases:
        datasite_data = {"name": name, "visibility": "public"}
        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 201
        assert response.json()["slug"] == expected_slug


def test_create_datasite_with_custom_attributes(
    client: TestClient, user1_token: str
) -> None:
    """Test creating a datasite with custom version and readme."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    datasite_data = {
        "name": "Advanced Datasite",
        "description": "A datasite with custom attributes",
        "visibility": "public",
        "version": "1.2.3",
        "readme": "# My Project\n\nThis is a sample README with markdown.",
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Advanced Datasite"
    assert data["version"] == "1.2.3"
    assert data["readme"] == "# My Project\n\nThis is a sample README with markdown."
    assert len(data["contributors"]) == 1


def test_create_datasite_invalid_version(client: TestClient, user1_token: str) -> None:
    """Test creating a datasite with invalid version format."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    invalid_versions = [
        "1.2",  # Missing patch version
        "v1.2.3",  # Prefix not allowed
        "1.2.3-alpha",  # Pre-release not supported
        "invalid",  # Not semantic version
    ]

    for invalid_version in invalid_versions:
        datasite_data = {
            "name": "Test Datasite",
            "version": invalid_version,
            "visibility": "public",
        }

        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 422  # Validation error


def test_update_datasite_new_attributes(client: TestClient, user1_token: str) -> None:
    """Test updating datasite with new attributes."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasite
    datasite_data = {"name": "Original Datasite", "visibility": "public"}
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    datasite_id = response.json()["id"]

    # Update with new attributes
    update_data = {
        "version": "2.0.0",
        "readme": "# Updated README\n\nThis datasite has been updated.",
    }
    response = client.patch(
        f"/api/v1/datasites/{datasite_id}", json=update_data, headers=headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == "2.0.0"
    assert data["readme"] == "# Updated README\n\nThis datasite has been updated."


def test_create_datasite_with_contributors(
    client: TestClient, user1_token: str
) -> None:
    """Test creating a datasite with explicit contributors list."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Simulate adding additional contributor IDs
    datasite_data = {
        "name": "Collaborative Datasite",
        "visibility": "public",
        "contributors": [1, 2, 3],  # Mock user IDs
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    # Owner should still be in contributors even if not explicitly added
    assert 1 in data["contributors"]  # Assuming user1 has ID 1
    assert len(data["contributors"]) >= 1


def test_datasite_public_response_includes_new_fields(
    client: TestClient, user1_token: str
) -> None:
    """Test that public datasite response includes new fields."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasite with all new fields
    datasite_data = {
        "name": "Public Datasite",
        "description": "A public datasite for testing",
        "visibility": "public",
        "version": "3.1.4",
        "readme": "# Public Project\n\nThis is publicly accessible.",
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    # Test public listing endpoint
    response = client.get("/api/v1/datasites/public")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    public_datasite = data[0]

    # Verify new fields are included in public response
    assert public_datasite["version"] == "3.1.4"
    assert (
        public_datasite["readme"] == "# Public Project\n\nThis is publicly accessible."
    )
    assert "contributors" in public_datasite


def test_datasite_version_filter_capability(
    client: TestClient, user1_token: str
) -> None:
    """Test creating datasites with different versions for future filtering."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasites with different versions
    versions = ["1.0.0", "1.1.0", "2.0.0"]
    for version in versions:
        datasite_data = {
            "name": f"Datasite v{version}",
            "visibility": "public",
            "version": version,
        }
        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 201
        assert response.json()["version"] == version


def test_datasite_stars_count_default(client: TestClient, user1_token: str) -> None:
    """Test that new datasites start with 0 stars."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    datasite_data = {
        "name": "New Datasite",
        "description": "Testing stars functionality",
        "visibility": "public",
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["stars_count"] == 0


def test_trending_datasites_endpoint(client: TestClient, user1_token: str) -> None:
    """Test the trending datasites endpoint (sorted by stars)."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasites with different star counts (simulated)
    datasites_data = [
        {"name": "Popular Datasite", "visibility": "public"},
        {"name": "Average Datasite", "visibility": "public"},
        {"name": "New Datasite", "visibility": "public"},
    ]

    created_ids = []
    for datasite_data in datasites_data:
        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    # Simulate different star counts by manually updating the fake database
    from syfthub.api.endpoints.datasites import fake_datasites_db

    if created_ids[0] in fake_datasites_db:
        fake_datasites_db[created_ids[0]].stars_count = 10  # Most popular
    if created_ids[1] in fake_datasites_db:
        fake_datasites_db[created_ids[1]].stars_count = 5  # Moderate
    # Leave created_ids[2] with 0 stars

    # Test trending endpoint
    response = client.get("/api/v1/datasites/trending")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3

    # Should be sorted by stars count (descending)
    assert data[0]["name"] == "Popular Datasite"
    assert data[0]["stars_count"] == 10
    assert data[1]["name"] == "Average Datasite"
    assert data[1]["stars_count"] == 5
    assert data[2]["name"] == "New Datasite"
    assert data[2]["stars_count"] == 0


def test_trending_datasites_with_min_stars_filter(
    client: TestClient, user1_token: str
) -> None:
    """Test trending datasites with minimum stars filter."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasites
    datasites_data = [
        {"name": "High Stars Datasite", "visibility": "public"},
        {"name": "Low Stars Datasite", "visibility": "public"},
    ]

    created_ids = []
    for datasite_data in datasites_data:
        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    # Simulate star counts
    from syfthub.api.endpoints.datasites import fake_datasites_db

    if created_ids[0] in fake_datasites_db:
        fake_datasites_db[created_ids[0]].stars_count = 15
    if created_ids[1] in fake_datasites_db:
        fake_datasites_db[created_ids[1]].stars_count = 2

    # Test with min_stars filter
    response = client.get("/api/v1/datasites/trending?min_stars=10")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "High Stars Datasite"
    assert data[0]["stars_count"] == 15


def test_public_datasite_response_includes_stars(
    client: TestClient, user1_token: str
) -> None:
    """Test that public responses include stars count."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create a datasite
    datasite_data = {
        "name": "Public Datasite with Stars",
        "description": "Testing public response",
        "visibility": "public",
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201
    datasite_id = response.json()["id"]

    # Simulate some stars
    from syfthub.api.endpoints.datasites import fake_datasites_db

    if datasite_id in fake_datasites_db:
        fake_datasites_db[datasite_id].stars_count = 42

    # Test public listing endpoint
    response = client.get("/api/v1/datasites/public")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert "stars_count" in data[0]
    assert data[0]["stars_count"] == 42

    # Test GitHub-style URL access
    response = client.get("/user1/public-datasite-with-stars")
    assert response.status_code == 200

    data = response.json()
    assert "stars_count" in data
    assert data["stars_count"] == 42


def test_trending_datasites_pagination(client: TestClient, user1_token: str) -> None:
    """Test pagination in trending datasites endpoint."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create multiple datasites
    for i in range(5):
        datasite_data = {
            "name": f"Datasite {i}",
            "visibility": "public",
        }
        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 201

    # Test pagination
    response = client.get("/api/v1/datasites/trending?skip=0&limit=3")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3

    response = client.get("/api/v1/datasites/trending?skip=3&limit=3")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2  # Remaining datasites


def test_create_datasite_with_policies(client: TestClient, user1_token: str) -> None:
    """Test creating a datasite with policies."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    datasite_data = {
        "name": "Policy-Enabled Datasite",
        "description": "A datasite with custom policies",
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

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Policy-Enabled Datasite"
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


def test_create_datasite_default_empty_policies(
    client: TestClient, user1_token: str
) -> None:
    """Test that datasites default to empty policies list."""
    headers = {"Authorization": f"Bearer {user1_token}"}
    datasite_data = {
        "name": "No Policies Datasite",
        "visibility": "public",
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["policies"] == []


def test_create_datasite_with_minimal_policy(
    client: TestClient, user1_token: str
) -> None:
    """Test creating datasite with minimal policy (only type required)."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    datasite_data = {
        "name": "Minimal Policy Datasite",
        "visibility": "public",
        "policies": [{"type": "simple_policy"}],
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    policy = data["policies"][0]
    assert policy["type"] == "simple_policy"
    assert policy["version"] == "1.0"  # Default version
    assert policy["enabled"] is True  # Default enabled
    assert policy["description"] == ""  # Default empty description
    assert policy["config"] == {}  # Default empty config


def test_create_datasite_invalid_policy_type(
    client: TestClient, user1_token: str
) -> None:
    """Test creating datasite with invalid policy type."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    datasite_data = {
        "name": "Invalid Policy Datasite",
        "visibility": "public",
        "policies": [
            {
                "type": "",  # Empty type should fail validation
                "config": {"test": "value"},
            }
        ],
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 422  # Validation error


def test_update_datasite_policies(client: TestClient, user1_token: str) -> None:
    """Test updating datasite policies."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create datasite with initial policy
    datasite_data = {
        "name": "Updateable Policies Datasite",
        "visibility": "public",
        "policies": [
            {"type": "initial_policy", "description": "Initial policy configuration"}
        ],
    }
    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    datasite_id = response.json()["id"]

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
        f"/api/v1/datasites/{datasite_id}", json=update_data, headers=headers
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


def test_public_datasite_response_includes_policies(
    client: TestClient, user1_token: str
) -> None:
    """Test that public responses include policies."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    datasite_data = {
        "name": "Public Policies Datasite",
        "visibility": "public",
        "policies": [
            {
                "type": "public_policy",
                "description": "A policy visible to all users",
                "config": {"public_setting": True},
            }
        ],
    }

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    # Test public listing endpoint
    response = client.get("/api/v1/datasites/public")
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
        datasite_data = {
            "name": f"Version Test {version}",
            "visibility": "public",
            "policies": [{"type": "test_policy", "version": version}],
        }
        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 201
        assert response.json()["policies"][0]["version"] == version

    # Invalid versions
    invalid_versions = ["1", "1.0.0", "v1.0", "1.0-alpha"]
    for version in invalid_versions:
        datasite_data = {
            "name": "Invalid Version Test",
            "visibility": "public",
            "policies": [{"type": "test_policy", "version": version}],
        }
        response = client.post(
            "/api/v1/datasites/", json=datasite_data, headers=headers
        )
        assert response.status_code == 422  # Validation error


def test_complex_policy_configurations(client: TestClient, user1_token: str) -> None:
    """Test policies with complex nested configurations."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    datasite_data = {
        "name": "Complex Config Datasite",
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

    response = client.post("/api/v1/datasites/", json=datasite_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    config = data["policies"][0]["config"]
    assert config["string_value"] == "test"
    assert config["number_value"] == 42
    assert config["boolean_value"] is True
    assert config["array_value"] == ["item1", "item2", "item3"]
    assert config["nested_object"]["level1"]["level2"]["deep_setting"] == "deep_value"
    assert config["null_value"] is None
