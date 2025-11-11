"""Test item endpoints."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_items_db() -> None:
    """Reset the fake items database before each test."""
    from syfthub.api.endpoints.items import fake_items_db

    fake_items_db.clear()
    # Reset the counter
    import syfthub.api.endpoints.items as items_module

    items_module.item_id_counter = 1


def test_list_empty_items(client: TestClient) -> None:
    """Test listing items when database is empty."""
    response = client.get("/api/v1/items/")
    assert response.status_code == 200
    assert response.json() == []


def test_create_item(client: TestClient) -> None:
    """Test creating a new item."""
    item_data = {
        "name": "Test Item",
        "description": "A test item",
        "price": "19.99",
        "category": "test",
        "is_available": True,
    }

    response = client.post("/api/v1/items/", json=item_data)
    assert response.status_code == 201

    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Test Item"
    assert data["description"] == "A test item"
    assert Decimal(data["price"]) == Decimal("19.99")
    assert data["category"] == "test"
    assert data["is_available"] is True
    assert "created_at" in data
    assert "updated_at" in data


def test_get_item(client: TestClient) -> None:
    """Test getting a specific item."""
    # Create an item first
    item_data = {
        "name": "Widget",
        "description": "A useful widget",
        "price": "25.50",
        "category": "widgets",
    }

    create_response = client.post("/api/v1/items/", json=item_data)
    assert create_response.status_code == 201
    item_id = create_response.json()["id"]

    # Get the item
    response = client.get(f"/api/v1/items/{item_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == item_id
    assert data["name"] == "Widget"
    assert data["description"] == "A useful widget"
    assert Decimal(data["price"]) == Decimal("25.50")
    assert data["category"] == "widgets"


def test_get_nonexistent_item(client: TestClient) -> None:
    """Test getting an item that doesn't exist."""
    response = client.get("/api/v1/items/999")
    assert response.status_code == 404
    assert "Item not found" in response.json()["detail"]


def test_update_item(client: TestClient) -> None:
    """Test partially updating an item."""
    # Create an item first
    item_data = {
        "name": "Old Widget",
        "description": "An old widget",
        "price": "10.00",
        "category": "old",
    }

    create_response = client.post("/api/v1/items/", json=item_data)
    assert create_response.status_code == 201
    item_id = create_response.json()["id"]

    # Update the item (partial update)
    updated_data = {
        "name": "New Widget",
        "price": "15.00",
    }

    response = client.patch(f"/api/v1/items/{item_id}", json=updated_data)
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "New Widget"
    assert Decimal(data["price"]) == Decimal("15.00")
    assert data["description"] == "An old widget"  # Unchanged
    assert data["category"] == "old"  # Unchanged


def test_update_nonexistent_item(client: TestClient) -> None:
    """Test updating an item that doesn't exist."""
    item_data = {
        "name": "Ghost Item",
        "price": "99.99",
    }

    response = client.patch("/api/v1/items/999", json=item_data)
    assert response.status_code == 404
    assert "Item not found" in response.json()["detail"]


def test_delete_item(client: TestClient) -> None:
    """Test deleting an item."""
    # Create an item first
    item_data = {
        "name": "Temp Item",
        "description": "Temporary item",
        "price": "5.00",
    }

    create_response = client.post("/api/v1/items/", json=item_data)
    assert create_response.status_code == 201
    item_id = create_response.json()["id"]

    # Delete the item
    response = client.delete(f"/api/v1/items/{item_id}")
    assert response.status_code == 204

    # Verify item is deleted
    get_response = client.get(f"/api/v1/items/{item_id}")
    assert get_response.status_code == 404


def test_delete_nonexistent_item(client: TestClient) -> None:
    """Test deleting an item that doesn't exist."""
    response = client.delete("/api/v1/items/999")
    assert response.status_code == 404
    assert "Item not found" in response.json()["detail"]


def test_list_items_with_pagination(client: TestClient) -> None:
    """Test listing items with pagination."""
    # Create multiple items
    for i in range(15):
        item_data = {
            "name": f"Item {i + 1}",
            "description": f"Description for item {i + 1}",
            "price": f"{(i + 1) * 10}.00",
        }
        response = client.post("/api/v1/items/", json=item_data)
        assert response.status_code == 201

    # Test default pagination (first 10)
    response = client.get("/api/v1/items/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10

    # Test skip and limit
    response = client.get("/api/v1/items/?skip=5&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5


def test_search_items(client: TestClient) -> None:
    """Test searching items by name and description."""
    # Create test items
    items = [
        {"name": "Red Widget", "description": "A red colored widget", "price": "10.00"},
        {
            "name": "Blue Widget",
            "description": "A blue colored widget",
            "price": "15.00",
        },
        {"name": "Green Gadget", "description": "A useful gadget", "price": "20.00"},
    ]

    for item in items:
        response = client.post("/api/v1/items/", json=item)
        assert response.status_code == 201

    # Search for "widget"
    response = client.get("/api/v1/items/?search=widget")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Red Widget and Blue Widget

    # Search for "blue"
    response = client.get("/api/v1/items/?search=blue")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Blue Widget"


def test_get_item_metadata(client: TestClient) -> None:
    """Test getting item metadata."""
    # Create an item first
    item_data = {
        "name": "Metadata Item",
        "description": "Item with metadata",
        "price": "30.00",
        "is_available": False,
    }

    create_response = client.post("/api/v1/items/", json=item_data)
    assert create_response.status_code == 201
    item_id = create_response.json()["id"]

    # Get item metadata
    response = client.get(f"/api/v1/items/{item_id}/metadata")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == item_id
    assert "created_at" in data
    assert "updated_at" in data
    assert data["name_length"] == len("Metadata Item")
    assert data["has_description"] is True
    assert data["is_available"] is False


def test_get_metadata_nonexistent_item(client: TestClient) -> None:
    """Test getting metadata for an item that doesn't exist."""
    response = client.get("/api/v1/items/999/metadata")
    assert response.status_code == 404
    assert "Item not found" in response.json()["detail"]
