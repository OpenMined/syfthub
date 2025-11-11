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
