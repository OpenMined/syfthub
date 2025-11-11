"""Test user endpoints."""

import pytest
from fastapi.testclient import TestClient

from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_users_db() -> None:
    """Reset the fake users database before each test."""
    from syfthub.api.endpoints.users import fake_users_db

    fake_users_db.clear()
    # Reset the counter - we need to modify the global variable
    import syfthub.api.endpoints.users as users_module

    users_module.user_id_counter = 1


def test_list_empty_users(client: TestClient) -> None:
    """Test listing users when database is empty."""
    response = client.get("/api/v1/users/")
    assert response.status_code == 200
    assert response.json() == []


def test_create_user(client: TestClient) -> None:
    """Test creating a new user."""
    user_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "age": 30,
        "is_active": True,
    }

    response = client.post("/api/v1/users/", json=user_data)
    assert response.status_code == 201

    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "John Doe"
    assert data["email"] == "john@example.com"
    assert data["age"] == 30
    assert data["is_active"] is True


def test_create_user_duplicate_email(client: TestClient) -> None:
    """Test creating a user with duplicate email."""
    user_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "is_active": True,
    }

    # Create first user
    response = client.post("/api/v1/users/", json=user_data)
    assert response.status_code == 201

    # Try to create second user with same email
    response = client.post("/api/v1/users/", json=user_data)
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]


def test_get_user(client: TestClient) -> None:
    """Test getting a specific user."""
    # Create a user first
    user_data = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "age": 25,
    }

    create_response = client.post("/api/v1/users/", json=user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]

    # Get the user
    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == user_id
    assert data["name"] == "Jane Doe"
    assert data["email"] == "jane@example.com"
    assert data["age"] == 25


def test_get_nonexistent_user(client: TestClient) -> None:
    """Test getting a user that doesn't exist."""
    response = client.get("/api/v1/users/999")
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]


def test_update_user(client: TestClient) -> None:
    """Test updating a user."""
    # Create a user first
    user_data = {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "age": 35,
    }

    create_response = client.post("/api/v1/users/", json=user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]

    # Update the user
    updated_data = {
        "name": "Robert Smith",
        "email": "robert@example.com",
        "age": 36,
    }

    response = client.put(f"/api/v1/users/{user_id}", json=updated_data)
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Robert Smith"
    assert data["email"] == "robert@example.com"
    assert data["age"] == 36


def test_update_nonexistent_user(client: TestClient) -> None:
    """Test updating a user that doesn't exist."""
    user_data = {
        "name": "Ghost User",
        "email": "ghost@example.com",
    }

    response = client.put("/api/v1/users/999", json=user_data)
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]


def test_delete_user(client: TestClient) -> None:
    """Test deleting a user."""
    # Create a user first
    user_data = {
        "name": "Temp User",
        "email": "temp@example.com",
    }

    create_response = client.post("/api/v1/users/", json=user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]

    # Delete the user
    response = client.delete(f"/api/v1/users/{user_id}")
    assert response.status_code == 204

    # Verify user is deleted
    get_response = client.get(f"/api/v1/users/{user_id}")
    assert get_response.status_code == 404


def test_delete_nonexistent_user(client: TestClient) -> None:
    """Test deleting a user that doesn't exist."""
    response = client.delete("/api/v1/users/999")
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]


def test_list_users(client: TestClient) -> None:
    """Test listing multiple users."""
    # Create multiple users
    users = [
        {"name": "User 1", "email": "user1@example.com"},
        {"name": "User 2", "email": "user2@example.com"},
        {"name": "User 3", "email": "user3@example.com"},
    ]

    for user in users:
        response = client.post("/api/v1/users/", json=user)
        assert response.status_code == 201

    # List all users
    response = client.get("/api/v1/users/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3
    assert data[0]["name"] == "User 1"
    assert data[1]["name"] == "User 2"
    assert data[2]["name"] == "User 3"
