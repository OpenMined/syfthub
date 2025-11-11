"""Test authenticated item endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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

    # Reset counters
    import syfthub.api.endpoints.items as items_module
    import syfthub.auth.router as auth_module

    auth_module.user_id_counter = 1
    items_module.item_id_counter = 1


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


def test_list_items_public(client: TestClient, user1_token: str) -> None:
    """Test listing items as public endpoint."""
    # Create items (some available, some not)
    headers = {"Authorization": f"Bearer {user1_token}"}

    items_data = [
        {
            "name": "Public Item",
            "description": "Available item",
            "price": "10.00",
            "is_available": True,
        },
        {
            "name": "Private Item",
            "description": "Unavailable item",
            "price": "15.00",
            "is_available": False,
        },
    ]

    for item_data in items_data:
        client.post("/api/v1/items/", json=item_data, headers=headers)

    # Test public access (no auth) - should only see available items
    response = client.get("/api/v1/items/")
    assert response.status_code == 200

    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "Public Item"
    assert items[0]["is_available"] is True


def test_list_items_authenticated(client: TestClient, user1_token: str) -> None:
    """Test listing items as authenticated user."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create items
    items_data = [
        {
            "name": "Public Item",
            "description": "Available item",
            "price": "10.00",
            "is_available": True,
        },
        {
            "name": "Private Item",
            "description": "Unavailable item",
            "price": "15.00",
            "is_available": False,
        },
    ]

    for item_data in items_data:
        client.post("/api/v1/items/", json=item_data, headers=headers)

    # Test authenticated access - should see all items
    response = client.get("/api/v1/items/", headers=headers)
    assert response.status_code == 200

    items = response.json()
    assert len(items) == 2


def test_list_my_items(client: TestClient, user1_token: str, user2_token: str) -> None:
    """Test listing current user's items."""
    # User1 creates items
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    item_data = {"name": "User1 Item", "description": "Item by user1", "price": "10.00"}
    client.post("/api/v1/items/", json=item_data, headers=headers1)

    # User2 creates items
    headers2 = {"Authorization": f"Bearer {user2_token}"}
    item_data = {"name": "User2 Item", "description": "Item by user2", "price": "15.00"}
    client.post("/api/v1/items/", json=item_data, headers=headers2)

    # User1 lists their items
    response = client.get("/api/v1/items/my", headers=headers1)
    assert response.status_code == 200

    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "User1 Item"

    # User2 lists their items
    response = client.get("/api/v1/items/my", headers=headers2)
    assert response.status_code == 200

    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "User2 Item"


def test_get_item_public_available(client: TestClient, user1_token: str) -> None:
    """Test getting available item without authentication."""
    # Create available item
    headers = {"Authorization": f"Bearer {user1_token}"}
    item_data = {
        "name": "Public Item",
        "description": "Available item",
        "price": "10.00",
        "is_available": True,
    }
    response = client.post("/api/v1/items/", json=item_data, headers=headers)
    item_id = response.json()["id"]

    # Access without authentication
    response = client.get(f"/api/v1/items/{item_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Public Item"


def test_get_item_private_requires_auth(client: TestClient, user1_token: str) -> None:
    """Test getting unavailable item requires authentication and ownership."""
    # Create unavailable item
    headers = {"Authorization": f"Bearer {user1_token}"}
    item_data = {
        "name": "Private Item",
        "description": "Unavailable item",
        "price": "10.00",
        "is_available": False,
    }
    response = client.post("/api/v1/items/", json=item_data, headers=headers)
    item_id = response.json()["id"]

    # Try to access without authentication
    response = client.get(f"/api/v1/items/{item_id}")
    assert response.status_code == 401

    # Access with authentication (owner)
    response = client.get(f"/api/v1/items/{item_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Private Item"


def test_get_item_private_ownership(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that users can only access their own unavailable items."""
    # User1 creates unavailable item
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    item_data = {
        "name": "User1 Private",
        "description": "User1's unavailable item",
        "price": "10.00",
        "is_available": False,
    }
    response = client.post("/api/v1/items/", json=item_data, headers=headers1)
    item_id = response.json()["id"]

    # User2 tries to access User1's private item
    headers2 = {"Authorization": f"Bearer {user2_token}"}
    response = client.get(f"/api/v1/items/{item_id}", headers=headers2)
    assert response.status_code == 403


def test_get_item_admin_can_access_any(
    client: TestClient, user1_token: str, admin_token: str
) -> None:
    """Test that admin can access any item."""
    # User1 creates unavailable item
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    item_data = {
        "name": "User1 Private",
        "description": "User1's unavailable item",
        "price": "10.00",
        "is_available": False,
    }
    response = client.post("/api/v1/items/", json=item_data, headers=headers1)
    item_id = response.json()["id"]

    # Admin accesses User1's private item
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    response = client.get(f"/api/v1/items/{item_id}", headers=headers_admin)
    assert response.status_code == 200
    assert response.json()["name"] == "User1 Private"


def test_create_item_requires_auth(client: TestClient, user1_token: str) -> None:
    """Test that creating items requires authentication."""
    item_data = {
        "name": "Test Item",
        "description": "Test description",
        "price": "10.00",
    }

    # Try without authentication
    response = client.post("/api/v1/items/", json=item_data)
    assert response.status_code == 401

    # Try with authentication
    headers = {"Authorization": f"Bearer {user1_token}"}
    response = client.post("/api/v1/items/", json=item_data, headers=headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Test Item"
    assert "user_id" in data  # Should include user_id


def test_update_item_ownership(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that users can only update their own items."""
    # User1 creates item
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    item_data = {
        "name": "User1 Item",
        "description": "Original description",
        "price": "10.00",
    }
    response = client.post("/api/v1/items/", json=item_data, headers=headers1)
    item_id = response.json()["id"]

    # User2 tries to update User1's item
    headers2 = {"Authorization": f"Bearer {user2_token}"}
    update_data = {"name": "Hacked Item"}
    response = client.patch(
        f"/api/v1/items/{item_id}", json=update_data, headers=headers2
    )
    assert response.status_code == 403

    # User1 updates their own item
    response = client.patch(
        f"/api/v1/items/{item_id}", json=update_data, headers=headers1
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Hacked Item"


def test_update_item_admin_can_update_any(
    client: TestClient, user1_token: str, admin_token: str
) -> None:
    """Test that admin can update any item."""
    # User1 creates item
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    item_data = {
        "name": "User1 Item",
        "description": "Original description",
        "price": "10.00",
    }
    response = client.post("/api/v1/items/", json=item_data, headers=headers1)
    item_id = response.json()["id"]

    # Admin updates User1's item
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    update_data = {"name": "Admin Updated Item"}
    response = client.patch(
        f"/api/v1/items/{item_id}", json=update_data, headers=headers_admin
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Admin Updated Item"


def test_delete_item_ownership(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that users can only delete their own items."""
    # User1 creates item
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    item_data = {"name": "User1 Item", "description": "To be deleted", "price": "10.00"}
    response = client.post("/api/v1/items/", json=item_data, headers=headers1)
    item_id = response.json()["id"]

    # User2 tries to delete User1's item
    headers2 = {"Authorization": f"Bearer {user2_token}"}
    response = client.delete(f"/api/v1/items/{item_id}", headers=headers2)
    assert response.status_code == 403

    # User1 deletes their own item
    response = client.delete(f"/api/v1/items/{item_id}", headers=headers1)
    assert response.status_code == 204

    # Verify item is deleted
    response = client.get(f"/api/v1/items/{item_id}")
    assert response.status_code == 404


def test_delete_item_admin_can_delete_any(
    client: TestClient, user1_token: str, admin_token: str
) -> None:
    """Test that admin can delete any item."""
    # User1 creates item
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    item_data = {
        "name": "User1 Item",
        "description": "To be deleted by admin",
        "price": "10.00",
    }
    response = client.post("/api/v1/items/", json=item_data, headers=headers1)
    item_id = response.json()["id"]

    # Admin deletes User1's item
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    response = client.delete(f"/api/v1/items/{item_id}", headers=headers_admin)
    assert response.status_code == 204


def test_item_metadata_follows_same_rules(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    """Test that item metadata follows the same access rules as items."""
    # User1 creates unavailable item
    headers1 = {"Authorization": f"Bearer {user1_token}"}
    item_data = {
        "name": "Private Item",
        "description": "Private metadata",
        "price": "10.00",
        "is_available": False,
    }
    response = client.post("/api/v1/items/", json=item_data, headers=headers1)
    item_id = response.json()["id"]

    # Try to access metadata without authentication
    response = client.get(f"/api/v1/items/{item_id}/metadata")
    assert response.status_code == 401

    # User2 tries to access User1's private item metadata
    headers2 = {"Authorization": f"Bearer {user2_token}"}
    response = client.get(f"/api/v1/items/{item_id}/metadata", headers=headers2)
    assert response.status_code == 403

    # User1 accesses their own item metadata
    response = client.get(f"/api/v1/items/{item_id}/metadata", headers=headers1)
    assert response.status_code == 200

    metadata = response.json()
    assert "user_id" in metadata
    assert "name_length" in metadata
    assert metadata["name_length"] == len("Private Item")


def test_item_search_and_pagination(client: TestClient, user1_token: str) -> None:
    """Test item search and pagination with authentication."""
    headers = {"Authorization": f"Bearer {user1_token}"}

    # Create multiple items
    items = [
        {"name": "Widget Alpha", "description": "First widget", "price": "10.00"},
        {"name": "Widget Beta", "description": "Second widget", "price": "15.00"},
        {"name": "Gadget Gamma", "description": "Different product", "price": "20.00"},
    ]

    for item_data in items:
        client.post("/api/v1/items/", json=item_data, headers=headers)

    # Test search in /my endpoint
    response = client.get("/api/v1/items/my?search=widget", headers=headers)
    assert response.status_code == 200

    items = response.json()
    assert len(items) == 2
    assert all("widget" in item["name"].lower() for item in items)

    # Test pagination in /my endpoint
    response = client.get("/api/v1/items/my?limit=2", headers=headers)
    assert response.status_code == 200

    items = response.json()
    assert len(items) == 2
