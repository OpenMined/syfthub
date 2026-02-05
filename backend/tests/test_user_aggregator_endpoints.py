"""Tests for user aggregator API endpoints."""

import pytest
from fastapi.testclient import TestClient

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


def get_auth_token(client: TestClient) -> str:
    """Helper to get auth token by registering a user."""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpass123",
    }
    response = client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201
    return response.json()["access_token"]


class TestListUserAggregators:
    """Tests for GET /users/me/aggregators endpoint."""

    def test_list_aggregators_success(self, client: TestClient):
        """Test listing aggregators returns 200."""
        token = get_auth_token(client)

        # Create an aggregator first
        agg_data = {
            "name": "Test Aggregator",
            "url": "https://aggregator.example.com",
            "is_default": False,
        }
        client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        # List aggregators
        response = client.get(
            "/api/v1/users/me/aggregators",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "aggregators" in data
        assert "default_aggregator_id" in data
        assert len(data["aggregators"]) == 1

    def test_list_aggregators_empty(self, client: TestClient):
        """Test listing aggregators when none exist."""
        token = get_auth_token(client)

        response = client.get(
            "/api/v1/users/me/aggregators",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["aggregators"] == []
        assert data["default_aggregator_id"] is None

    def test_list_aggregators_unauthorized(self, client: TestClient):
        """Test 401 when not authenticated."""
        response = client.get("/api/v1/users/me/aggregators")
        assert response.status_code == 401


class TestCreateUserAggregator:
    """Tests for POST /users/me/aggregators endpoint."""

    def test_create_aggregator_success(self, client: TestClient):
        """Test creating an aggregator returns 201."""
        token = get_auth_token(client)

        agg_data = {
            "name": "Test Aggregator",
            "url": "https://aggregator.example.com",
            "is_default": False,
        }

        response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Aggregator"
        assert data["url"] == "https://aggregator.example.com"
        assert data["is_default"] is True  # First aggregator becomes default

    def test_create_aggregator_invalid_url(self, client: TestClient):
        """Test 400 for invalid URL."""
        token = get_auth_token(client)

        agg_data = {
            "name": "Test Aggregator",
            "url": "not-a-valid-url",
            "is_default": False,
        }

        response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422

    def test_create_aggregator_missing_name(self, client: TestClient):
        """Test 400 for missing name."""
        token = get_auth_token(client)

        agg_data = {
            "url": "https://aggregator.example.com",
            "is_default": False,
        }

        response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422

    def test_create_aggregator_unauthorized(self, client: TestClient):
        """Test 401 when not authenticated."""
        agg_data = {
            "name": "Test Aggregator",
            "url": "https://aggregator.example.com",
            "is_default": False,
        }

        response = client.post("/api/v1/users/me/aggregators", json=agg_data)
        assert response.status_code == 401


class TestGetUserAggregator:
    """Tests for GET /users/me/aggregators/{id} endpoint."""

    def test_get_aggregator_success(self, client: TestClient):
        """Test getting an aggregator returns 200."""
        token = get_auth_token(client)

        # Create aggregator
        agg_data = {
            "name": "Test Aggregator",
            "url": "https://aggregator.example.com",
            "is_default": False,
        }
        create_response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token}"},
        )
        agg_id = create_response.json()["id"]

        # Get aggregator
        response = client.get(
            f"/api/v1/users/me/aggregators/{agg_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Aggregator"
        assert data["id"] == agg_id

    def test_get_aggregator_not_found(self, client: TestClient):
        """Test 404 for non-existent aggregator."""
        token = get_auth_token(client)

        response = client.get(
            "/api/v1/users/me/aggregators/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    def test_get_aggregator_unauthorized(self, client: TestClient):
        """Test 401 when not authenticated."""
        response = client.get("/api/v1/users/me/aggregators/1")
        assert response.status_code == 401

    def test_get_aggregator_wrong_user(self, client: TestClient):
        """Test 403 when aggregator belongs to different user."""
        token1 = get_auth_token(client)

        # Create aggregator for user1
        agg_data = {
            "name": "User1 Aggregator",
            "url": "https://user1.example.com",
            "is_default": False,
        }
        create_response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token1}"},
        )
        agg_id = create_response.json()["id"]

        # Register user2
        user2_data = {
            "username": "testuser2",
            "email": "test2@example.com",
            "full_name": "Test User 2",
            "password": "testpass123",
        }
        register_response = client.post("/api/v1/auth/register", json=user2_data)
        token2 = register_response.json()["access_token"]

        # Try to access with user2
        response = client.get(
            f"/api/v1/users/me/aggregators/{agg_id}",
            headers={"Authorization": f"Bearer {token2}"},
        )

        assert response.status_code == 403


class TestUpdateUserAggregator:
    """Tests for PUT /users/me/aggregators/{id} endpoint."""

    def test_update_aggregator_success(self, client: TestClient):
        """Test updating an aggregator returns 200."""
        token = get_auth_token(client)

        # Create aggregator
        agg_data = {
            "name": "Original Name",
            "url": "https://original.example.com",
            "is_default": False,
        }
        create_response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token}"},
        )
        agg_id = create_response.json()["id"]

        # Update aggregator
        update_data = {
            "name": "Updated Name",
            "url": "https://updated.example.com",
        }
        response = client.put(
            f"/api/v1/users/me/aggregators/{agg_id}",
            json=update_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["url"] == "https://updated.example.com"

    def test_update_aggregator_not_found(self, client: TestClient):
        """Test 404 for non-existent aggregator."""
        token = get_auth_token(client)

        update_data = {"name": "Updated Name"}
        response = client.put(
            "/api/v1/users/me/aggregators/99999",
            json=update_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    def test_update_aggregator_unauthorized(self, client: TestClient):
        """Test 401 when not authenticated."""
        update_data = {"name": "Updated Name"}
        response = client.put("/api/v1/users/me/aggregators/1", json=update_data)
        assert response.status_code == 401

    def test_update_aggregator_wrong_user(self, client: TestClient):
        """Test 403 when aggregator belongs to different user."""
        token1 = get_auth_token(client)

        # Create aggregator for user1
        agg_data = {
            "name": "User1 Aggregator",
            "url": "https://user1.example.com",
            "is_default": False,
        }
        create_response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token1}"},
        )
        agg_id = create_response.json()["id"]

        # Register user2
        user2_data = {
            "username": "testuser2",
            "email": "test2@example.com",
            "full_name": "Test User 2",
            "password": "testpass123",
        }
        register_response = client.post("/api/v1/auth/register", json=user2_data)
        token2 = register_response.json()["access_token"]

        # Try to update with user2
        update_data = {"name": "Hacked Name"}
        response = client.put(
            f"/api/v1/users/me/aggregators/{agg_id}",
            json=update_data,
            headers={"Authorization": f"Bearer {token2}"},
        )

        assert response.status_code == 403

    def test_update_aggregator_invalid_url(self, client: TestClient):
        """Test 400 for invalid URL."""
        token = get_auth_token(client)

        # Create aggregator
        agg_data = {
            "name": "Test Aggregator",
            "url": "https://example.com",
            "is_default": False,
        }
        create_response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token}"},
        )
        agg_id = create_response.json()["id"]

        # Update with invalid URL
        update_data = {"url": "not-a-valid-url"}
        response = client.put(
            f"/api/v1/users/me/aggregators/{agg_id}",
            json=update_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422


class TestDeleteUserAggregator:
    """Tests for DELETE /users/me/aggregators/{id} endpoint."""

    def test_delete_aggregator_success(self, client: TestClient):
        """Test deleting an aggregator returns 204."""
        token = get_auth_token(client)

        # Create aggregator
        agg_data = {
            "name": "To Delete",
            "url": "https://delete.example.com",
            "is_default": False,
        }
        create_response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token}"},
        )
        agg_id = create_response.json()["id"]

        # Delete aggregator
        response = client.delete(
            f"/api/v1/users/me/aggregators/{agg_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 204

        # Verify deleted
        get_response = client.get(
            f"/api/v1/users/me/aggregators/{agg_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_response.status_code == 404

    def test_delete_aggregator_not_found(self, client: TestClient):
        """Test 404 for non-existent aggregator."""
        token = get_auth_token(client)

        response = client.delete(
            "/api/v1/users/me/aggregators/99999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    def test_delete_aggregator_unauthorized(self, client: TestClient):
        """Test 401 when not authenticated."""
        response = client.delete("/api/v1/users/me/aggregators/1")
        assert response.status_code == 401

    def test_delete_aggregator_wrong_user(self, client: TestClient):
        """Test 403 when aggregator belongs to different user."""
        token1 = get_auth_token(client)

        # Create aggregator for user1
        agg_data = {
            "name": "User1 Aggregator",
            "url": "https://user1.example.com",
            "is_default": False,
        }
        create_response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token1}"},
        )
        agg_id = create_response.json()["id"]

        # Register user2
        user2_data = {
            "username": "testuser2",
            "email": "test2@example.com",
            "full_name": "Test User 2",
            "password": "testpass123",
        }
        register_response = client.post("/api/v1/auth/register", json=user2_data)
        token2 = register_response.json()["access_token"]

        # Try to delete with user2
        response = client.delete(
            f"/api/v1/users/me/aggregators/{agg_id}",
            headers={"Authorization": f"Bearer {token2}"},
        )

        assert response.status_code == 403


class TestSetDefaultAggregator:
    """Tests for PATCH /users/me/aggregators/{id}/default endpoint."""

    def test_set_default_success(self, client: TestClient):
        """Test setting default returns 200."""
        token = get_auth_token(client)

        # Create two aggregators
        agg1_data = {
            "name": "First Aggregator",
            "url": "https://first.example.com",
            "is_default": False,  # Will be forced to True
        }
        create_response1 = client.post(
            "/api/v1/users/me/aggregators",
            json=agg1_data,
            headers={"Authorization": f"Bearer {token}"},
        )
        _ = create_response1.json()["id"]  # First aggregator (becomes default)

        agg2_data = {
            "name": "Second Aggregator",
            "url": "https://second.example.com",
            "is_default": False,
        }
        create_response2 = client.post(
            "/api/v1/users/me/aggregators",
            json=agg2_data,
            headers={"Authorization": f"Bearer {token}"},
        )
        agg2_id = create_response2.json()["id"]

        # Set agg2 as default
        response = client.patch(
            f"/api/v1/users/me/aggregators/{agg2_id}/default",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_default"] is True

    def test_set_default_not_found(self, client: TestClient):
        """Test 404 for non-existent aggregator."""
        token = get_auth_token(client)

        response = client.patch(
            "/api/v1/users/me/aggregators/99999/default",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    def test_set_default_unauthorized(self, client: TestClient):
        """Test 401 when not authenticated."""
        response = client.patch("/api/v1/users/me/aggregators/1/default")
        assert response.status_code == 401

    def test_set_default_wrong_user(self, client: TestClient):
        """Test 403 when aggregator belongs to different user."""
        token1 = get_auth_token(client)

        # Create aggregator for user1
        agg_data = {
            "name": "User1 Aggregator",
            "url": "https://user1.example.com",
            "is_default": False,
        }
        create_response = client.post(
            "/api/v1/users/me/aggregators",
            json=agg_data,
            headers={"Authorization": f"Bearer {token1}"},
        )
        agg_id = create_response.json()["id"]

        # Register user2
        user2_data = {
            "username": "testuser2",
            "email": "test2@example.com",
            "full_name": "Test User 2",
            "password": "testpass123",
        }
        register_response = client.post("/api/v1/auth/register", json=user2_data)
        token2 = register_response.json()["access_token"]

        # Try to set default with user2
        response = client.patch(
            f"/api/v1/users/me/aggregators/{agg_id}/default",
            headers={"Authorization": f"Bearer {token2}"},
        )

        assert response.status_code == 403
