"""Test authenticated user endpoints."""

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
        "avatar_url": "https://example.com/avatar.png",
    }

    headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.put("/api/v1/users/me", json=update_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated User Name"
    assert data["avatar_url"] == "https://example.com/avatar.png"
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
    if response.status_code != 204:
        print(f"Delete response: {response.text}")
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


def test_get_accounting_credentials(
    client: TestClient, regular_user_token: str
) -> None:
    """Test getting current user's accounting credentials."""
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.get("/api/v1/users/me/accounting", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert "email" in data
    assert "password" in data
    assert data["email"] == "regular@example.com"


def test_check_username_availability(client: TestClient) -> None:
    """Test checking username availability."""
    # Check availability of a new username (should be available)
    response = client.get("/api/v1/users/check-username/newuser123")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["username"] == "newuser123"


def test_check_username_availability_taken(
    client: TestClient, regular_user_token: str
) -> None:
    """Test checking availability of a taken username."""
    # The regular_user_token fixture creates 'regularuser'
    response = client.get("/api/v1/users/check-username/regularuser")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["username"] == "regularuser"


def test_check_email_availability(client: TestClient) -> None:
    """Test checking email availability."""
    # Check availability of a new email (should be available)
    response = client.get("/api/v1/users/check-email/newemail@example.com")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["email"] == "newemail@example.com"


def test_check_email_availability_taken(
    client: TestClient, regular_user_token: str
) -> None:
    """Test checking availability of a taken email."""
    # The regular_user_token fixture creates 'regular@example.com'
    response = client.get("/api/v1/users/check-email/regular@example.com")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["email"] == "regular@example.com"


def test_get_user_not_found(client: TestClient, admin_user_token: str) -> None:
    """Test getting a non-existent user returns 404."""
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = client.get("/api/v1/users/99999", headers=headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_update_user_with_aggregator_url(
    client: TestClient, regular_user_token: str
) -> None:
    """Test updating user profile with aggregator_url."""
    update_data = {
        "aggregator_url": "https://my-aggregator.example.com/api/v1",
    }

    headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.put("/api/v1/users/me", json=update_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["aggregator_url"] == "https://my-aggregator.example.com/api/v1"

    # Test updating to a different aggregator_url
    update_data2 = {"aggregator_url": "https://another-aggregator.example.com"}
    response = client.put("/api/v1/users/me", json=update_data2, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["aggregator_url"] == "https://another-aggregator.example.com"


def test_delete_nonexistent_user(client: TestClient, admin_user_token: str) -> None:
    """Test deleting a non-existent user returns 404."""
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = client.delete("/api/v1/users/99999", headers=headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_update_user_by_id_not_found(client: TestClient, admin_user_token: str) -> None:
    """Test updating a non-existent user by ID returns 404."""
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    update_data = {"full_name": "New Name"}
    response = client.put("/api/v1/users/99999", json=update_data, headers=headers)
    assert response.status_code == 404


def test_deactivate_nonexistent_user(client: TestClient, admin_user_token: str) -> None:
    """Test deactivating a non-existent user returns 404."""
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = client.patch("/api/v1/users/99999/deactivate", headers=headers)
    assert response.status_code == 404


def test_activate_nonexistent_user(client: TestClient, admin_user_token: str) -> None:
    """Test activating a non-existent user returns 404."""
    headers = {"Authorization": f"Bearer {admin_user_token}"}
    response = client.patch("/api/v1/users/99999/activate", headers=headers)
    assert response.status_code == 404


def test_regular_user_cannot_activate(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that regular users cannot activate other users."""
    # Get admin user ID
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    admin_me = client.get("/api/v1/users/me", headers=admin_headers)
    admin_id = admin_me.json()["id"]

    # Regular user tries to activate
    regular_headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.patch(
        f"/api/v1/users/{admin_id}/activate", headers=regular_headers
    )
    assert response.status_code == 403


def test_regular_user_cannot_delete_other(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that regular users cannot delete other users."""
    # Get admin user ID
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    admin_me = client.get("/api/v1/users/me", headers=admin_headers)
    admin_id = admin_me.json()["id"]

    # Regular user tries to delete admin
    regular_headers = {"Authorization": f"Bearer {regular_user_token}"}
    response = client.delete(f"/api/v1/users/{admin_id}", headers=regular_headers)
    assert response.status_code == 403


def test_update_profile_duplicate_username(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that updating profile with existing username fails."""
    # Regular user tries to change username to admin's username
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    update_data = {"username": "adminuser"}  # This username exists
    response = client.put("/api/v1/users/me", json=update_data, headers=headers)
    assert response.status_code == 400
    assert "username" in response.json()["detail"].lower()


def test_update_profile_duplicate_email(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that updating profile with existing email fails."""
    # Regular user tries to change email to admin's email
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    update_data = {"email": "admin@example.com"}  # This email exists
    response = client.put("/api/v1/users/me", json=update_data, headers=headers)
    assert response.status_code == 400
    assert "email" in response.json()["detail"].lower()


def test_update_profile_with_own_username(
    client: TestClient, regular_user_token: str
) -> None:
    """Test that updating profile with own username is allowed."""
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    # Update with current username should not fail
    update_data = {"username": "regularuser", "full_name": "Still Regular User"}
    response = client.put("/api/v1/users/me", json=update_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "regularuser"
    assert data["full_name"] == "Still Regular User"


def test_update_profile_with_own_email(
    client: TestClient, regular_user_token: str
) -> None:
    """Test that updating profile with own email is allowed."""
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    # Update with current email should not fail
    update_data = {"email": "regular@example.com", "full_name": "Updated Name"}
    response = client.put("/api/v1/users/me", json=update_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "regular@example.com"
    assert data["full_name"] == "Updated Name"


def test_admin_can_update_other_user(
    client: TestClient, regular_user_token: str, admin_user_token: str
) -> None:
    """Test that admin can update another user's profile."""
    # Get regular user ID
    regular_headers = {"Authorization": f"Bearer {regular_user_token}"}
    me_response = client.get("/api/v1/users/me", headers=regular_headers)
    user_id = me_response.json()["id"]

    # Admin updates regular user's profile
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}
    update_data = {"full_name": "Admin Updated Name"}
    response = client.put(
        f"/api/v1/users/{user_id}", json=update_data, headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Admin Updated Name"


def test_list_users_returns_both_active_and_inactive(
    client: TestClient, admin_user_token: str
) -> None:
    """Test that listing users returns both active and inactive users for admin."""
    admin_headers = {"Authorization": f"Bearer {admin_user_token}"}

    # Create a user
    user_data = {
        "username": "inactiveuser",
        "email": "inactive@example.com",
        "full_name": "Inactive User",
        "password": "testpass123",
    }
    register_response = client.post("/api/v1/auth/register", json=user_data)
    user_id = register_response.json()["user"]["id"]

    # Deactivate the user
    client.patch(f"/api/v1/users/{user_id}/deactivate", headers=admin_headers)

    # List all users - should include both active and inactive
    response = client.get("/api/v1/users/", headers=admin_headers)
    assert response.status_code == 200
    users = response.json()
    usernames = [u["username"] for u in users]
    assert "inactiveuser" in usernames
    assert "adminuser" in usernames


def test_update_user_full_profile(client: TestClient, regular_user_token: str) -> None:
    """Test updating multiple fields at once."""
    headers = {"Authorization": f"Bearer {regular_user_token}"}
    update_data = {
        "full_name": "Completely New Name",
        "avatar_url": "https://example.com/new-avatar.jpg",
        "domain": "https://example.com",
    }
    response = client.put("/api/v1/users/me", json=update_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Completely New Name"
    assert data["avatar_url"] == "https://example.com/new-avatar.jpg"
    assert data["domain"] == "https://example.com"
