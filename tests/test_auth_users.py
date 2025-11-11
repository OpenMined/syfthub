"""Test authenticated user endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.dependencies import fake_users_db, username_to_id
from syfthub.auth.security import token_blacklist
from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_auth_db() -> None:
    """Reset the authentication database before each test."""
    fake_users_db.clear()
    username_to_id.clear()
    token_blacklist.clear()

    # Reset counters
    import syfthub.auth.router as auth_module

    auth_module.user_id_counter = 1


@pytest.fixture
def regular_user_token(client: TestClient) -> str:
    """Create a regular user and return access token."""
    user_data = {
        "username": "regularuser",
        "email": "regular@example.com",
        "full_name": "Regular User",
        "password": "testpass123",
        "age": 25,
    }

    response = client.post("/api/v1/auth/register", json=user_data)
    return response.json()["access_token"]


@pytest.fixture
def admin_user_token(client: TestClient) -> str:
    """Create an admin user and return access token."""
    # Create regular user first
    user_data = {
        "username": "adminuser",
        "email": "admin@example.com",
        "full_name": "Admin User",
        "password": "adminpass123",
    }

    response = client.post("/api/v1/auth/register", json=user_data)

    # Manually promote to admin (in production this would be done differently)
    from syfthub.schemas.auth import UserRole

    user_id = response.json()["user"]["id"]
    fake_users_db[user_id].role = UserRole.ADMIN

    return response.json()["access_token"]


def test_list_users_admin_only(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that only admins can list all users."""
    # Regular user should not be able to list users
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.get("/api/v1/users/", headers=headers)
    assert response.status_code == 403

    # Admin should be able to list users
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = client.get("/api/v1/users/", headers=admin_headers)
    assert response.status_code == 200

    users = response.json()
    assert len(users) == 2  # regular user and admin user
    assert any(user["username"] == "regularuser" for user in users)
    assert any(user["username"] == "adminuser" for user in users)


def test_get_current_user_profile(client: TestClient, regular_user_token: str) -> None:
    """Test getting current user's profile via /users/me."""
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.get("/api/v1/users/me", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "regularuser"
    assert data["email"] == "regular@example.com"
    assert data["full_name"] == "Regular User"
    assert data["role"] == "user"


def test_update_current_user_profile(
    client: TestClient, regular_user_token: str
) -> None:
    """Test updating current user's profile via /users/me."""
    update_data = {
        "full_name": "Updated User Name",
        "age": 30,
    }

    headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.put("/api/v1/users/me", json=update_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated User Name"
    assert data["age"] == 30
    assert data["username"] == "regularuser"  # Should not change


def test_get_user_by_id_self(client: TestClient, regular_user_token: str) -> None:
    """Test that users can get their own profile by ID."""
    # First get the user ID from /me
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    me_response = client.get("/api/v1/users/me", headers=headers)
    user_id = me_response.json()["id"]

    # Now get user by ID
    response = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["username"] == "regularuser"


def test_get_user_by_id_other_user_forbidden(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that regular users cannot get other users' profiles."""
    # Get admin user ID
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    admin_me_response = client.get("/api/v1/users/me", headers=admin_headers)
    admin_user_id = admin_me_response.json()["id"]

    # Regular user tries to get admin profile
    regular_headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.get(f"/api/v1/users/{admin_user_id}", headers=regular_headers)
    assert response.status_code == 403


def test_get_user_by_id_admin_can_access_any(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that admin can get any user's profile."""
    # Get regular user ID
    regular_headers = {"Authorization": f"Bearer {regular_user_token}"}
    regular_me_response = client.get("/api/v1/users/me", headers=regular_headers)
    regular_user_id = regular_me_response.json()["id"]

    # Admin gets regular user profile
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = client.get(f"/api/v1/users/{regular_user_id}", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["username"] == "regularuser"


def test_update_user_by_id_self(client: TestClient, regular_user_token: str) -> None:
    """Test that users can update their own profile by ID."""
    # Get user ID
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    me_response = client.get("/api/v1/users/me", headers=headers)
    user_id = me_response.json()["id"]

    # Update user
    update_data = {"full_name": "Self Updated Name"}
    response = client.put(f"/api/v1/users/{user_id}", json=update_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Self Updated Name"


def test_update_user_by_id_other_user_forbidden(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that regular users cannot update other users' profiles."""
    # Get admin user ID
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    admin_me_response = client.get("/api/v1/users/me", headers=admin_headers)
    admin_user_id = admin_me_response.json()["id"]

    # Regular user tries to update admin profile
    regular_headers = {"Authorization": f"Bearer {regular_user_token}"}
    update_data = {"full_name": "Hacked Name"}
    response = client.put(
        f"/api/v1/users/{admin_user_id}", json=update_data, headers=regular_headers
    )
    assert response.status_code == 403


def test_deactivate_user_admin_only(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that only admin can deactivate users."""
    # Get regular user ID
    regular_headers = {"Authorization": f"Bearer {regular_user_token}"}
    regular_me_response = client.get("/api/v1/users/me", headers=regular_headers)
    regular_user_id = regular_me_response.json()["id"]

    # Regular user tries to deactivate themselves (should fail)
    response = client.patch(
        f"/api/v1/users/{regular_user_id}/deactivate", headers=regular_headers
    )
    assert response.status_code == 403

    # Admin deactivates regular user (should succeed)
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = client.patch(
        f"/api/v1/users/{regular_user_id}/deactivate", headers=admin_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert data["is_active"] is False


def test_activate_user_admin_only(client: TestClient, admin_user_token: str) -> None:
    """Test that only admin can activate users."""
    # First deactivate a user
    regular_headers = {"Authorization": f"Bearer {admin_user_token}"}

    # Create and deactivate a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
    }

    register_response = client.post("/api/v1/auth/register", json=user_data)
    user_id = register_response.json()["user"]["id"]

    # Deactivate
    deactivate_response = client.patch(
        f"/api/v1/users/{user_id}/deactivate", headers=regular_headers
    )
    assert deactivate_response.status_code == 200

    # Activate
    activate_response = client.patch(
        f"/api/v1/users/{user_id}/activate", headers=regular_headers
    )
    assert activate_response.status_code == 200

    data = activate_response.json()
    assert data["is_active"] is True


def test_delete_user_self(client: TestClient, regular_user_token: str) -> None:
    """Test that users can delete their own account."""
    # Get user ID
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    me_response = client.get("/api/v1/users/me", headers=headers)
    user_id = me_response.json()["id"]

    # Delete own account
    response = client.delete(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 204

    # Verify user is deleted
    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 401


def test_delete_user_admin_can_delete_any(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that admin can delete any user."""
    # Get regular user ID
    regular_headers = {"Authorization": f"Bearer {regular_user_token}"}
    regular_me_response = client.get("/api/v1/users/me", headers=regular_headers)
    regular_user_id = regular_me_response.json()["id"]

    # Admin deletes regular user
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = client.delete(f"/api/v1/users/{regular_user_id}", headers=admin_headers)
    assert response.status_code == 204

    # Verify user is deleted
    response = client.get("/api/v1/users/me", headers=regular_headers)
    assert response.status_code == 401


def test_access_users_without_auth(client: TestClient) -> None:
    """Test that user endpoints require authentication."""
    # All user endpoints should require authentication
    endpoints = [
        "/api/v1/users/",
        "/api/v1/users/me",
        "/api/v1/users/1",
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 401
