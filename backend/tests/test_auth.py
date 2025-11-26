"""Test authentication endpoints and functionality."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app

# Import database test fixtures


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


def test_register_user(client: TestClient) -> None:
    """Test user registration."""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
        "age": 25,
    }

    response = client.post("/api/v1/auth/register", json=user_data)
    print(f"Response status: {response.status_code}")
    print(f"Response text: {response.text}")
    assert response.status_code == 201

    data = response.json()
    assert "user" in data
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    user = data["user"]
    assert user["username"] == "testuser"
    assert user["email"] == "test@example.com"
    assert user["full_name"] == "Test User"
    assert user["role"] == "user"
    assert user["is_active"] is True


def test_register_duplicate_username(client: TestClient) -> None:
    """Test registering with duplicate username."""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
    }

    # Register first user
    response1 = client.post("/api/v1/auth/register", json=user_data)
    assert response1.status_code == 201

    # Try to register with same username
    user_data2 = user_data.copy()
    user_data2["email"] = "different@example.com"

    response2 = client.post("/api/v1/auth/register", json=user_data2)
    assert response2.status_code == 400
    assert "Username already exists" in response2.json()["detail"]


def test_register_duplicate_email(client: TestClient) -> None:
    """Test registering with duplicate email."""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
    }

    # Register first user
    response1 = client.post("/api/v1/auth/register", json=user_data)
    assert response1.status_code == 201

    # Try to register with same email
    user_data2 = user_data.copy()
    user_data2["username"] = "differentuser"

    response2 = client.post("/api/v1/auth/register", json=user_data2)
    assert response2.status_code == 400
    assert "Email already exists" in response2.json()["detail"]


def test_register_invalid_password(client: TestClient) -> None:
    """Test registration with invalid password."""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "short",  # Too short
    }

    response = client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 422


def test_login_success(client: TestClient) -> None:
    """Test successful login."""
    # First register a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
    }

    register_response = client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    # Now login
    login_data = {
        "username": "testuser",
        "password": "testpass123",
    }

    response = client.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_with_email(client: TestClient) -> None:
    """Test login using email instead of username."""
    # First register a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
    }

    register_response = client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    # Login with email
    login_data = {
        "username": "test@example.com",  # Using email as username
        "password": "testpass123",
    }

    response = client.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200


def test_login_invalid_credentials(client: TestClient) -> None:
    """Test login with invalid credentials."""
    login_data = {
        "username": "nonexistent",
        "password": "wrongpassword",
    }

    response = client.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


def test_refresh_token(client: TestClient) -> None:
    """Test token refresh functionality."""
    # Register and login a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
    }

    register_response = client.post("/api/v1/auth/register", json=user_data)
    refresh_token = register_response.json()["refresh_token"]

    # Refresh the token
    refresh_data = {"refresh_token": refresh_token}
    response = client.post("/api/v1/auth/refresh", json=refresh_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_refresh_invalid_token(client: TestClient) -> None:
    """Test refresh with invalid token."""
    refresh_data = {"refresh_token": "invalid_token"}
    response = client.post("/api/v1/auth/refresh", json=refresh_data)

    assert response.status_code == 401
    assert "Invalid refresh token" in response.json()["detail"]


def test_get_current_user_me(client: TestClient) -> None:
    """Test getting current user info."""
    # Register a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
        "age": 25,
    }

    register_response = client.post("/api/v1/auth/register", json=user_data)
    access_token = register_response.json()["access_token"]

    # Get current user info
    headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert data["age"] == 25
    assert data["role"] == "user"


def test_get_current_user_unauthorized(client: TestClient) -> None:
    """Test accessing protected endpoint without token."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_get_current_user_invalid_token(client: TestClient) -> None:
    """Test accessing protected endpoint with invalid token."""
    headers = {"Authorization": "Bearer invalid_token"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401


def test_change_password(client: TestClient) -> None:
    """Test password change functionality."""
    # Register a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "oldpass123",
    }

    register_response = client.post("/api/v1/auth/register", json=user_data)
    access_token = register_response.json()["access_token"]

    # Change password
    password_data = {
        "current_password": "oldpass123",
        "new_password": "newpass456",
    }

    headers = {"Authorization": f"Bearer {access_token}"}
    response = client.put(
        "/api/v1/auth/me/password", json=password_data, headers=headers
    )

    assert response.status_code == 204

    # Try logging in with new password
    login_data = {
        "username": "testuser",
        "password": "newpass456",
    }

    login_response = client.post("/api/v1/auth/login", data=login_data)
    assert login_response.status_code == 200


def test_change_password_wrong_current(client: TestClient) -> None:
    """Test password change with wrong current password."""
    # Register a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "correctpass123",
    }

    register_response = client.post("/api/v1/auth/register", json=user_data)
    access_token = register_response.json()["access_token"]

    # Try to change password with wrong current password
    password_data = {
        "current_password": "wrongpass123",
        "new_password": "newpass456",
    }

    headers = {"Authorization": f"Bearer {access_token}"}
    response = client.put(
        "/api/v1/auth/me/password", json=password_data, headers=headers
    )

    assert response.status_code == 400
    assert "Current password is incorrect" in response.json()["detail"]


def test_logout(client: TestClient) -> None:
    """Test logout functionality."""
    # Register a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
    }

    register_response = client.post("/api/v1/auth/register", json=user_data)
    access_token = register_response.json()["access_token"]

    # Logout
    headers = {"Authorization": f"Bearer {access_token}"}
    response = client.post("/api/v1/auth/logout", headers=headers)

    assert response.status_code == 204

    # Try to use the token after logout (should fail)
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
