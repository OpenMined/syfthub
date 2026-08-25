"""Tests for the /satellites API endpoints.

The service tests cover the rules; these cover the HTTP contract — status
codes, auth, and that the integer primary key never reaches a response body.
"""

import pytest
from fastapi.testclient import TestClient

from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()

    client = TestClient(app)

    yield client

    drop_tables()


def register(client: TestClient, username: str = "testuser") -> dict:
    """Register a user and return an Authorization header."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "full_name": "Test User",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_satellite(
    client, headers, slug="my-space", base_url="https://s.example.com"
):
    """Register a satellite over HTTP."""
    return client.post(
        "/api/v1/satellites",
        headers=headers,
        json={"kind": "space", "slug": slug, "base_url": base_url},
    )


class TestAuth:
    """Every satellite route requires an authenticated account."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/v1/satellites"),
            ("post", "/api/v1/satellites"),
            ("get", "/api/v1/satellites/00000000-0000-0000-0000-000000000001"),
            ("put", "/api/v1/satellites/00000000-0000-0000-0000-000000000001"),
            ("delete", "/api/v1/satellites/00000000-0000-0000-0000-000000000001"),
        ],
    )
    def test_requires_authentication(self, client: TestClient, method, path):
        """Test that anonymous access is refused."""
        kwargs = {"json": {}} if method in ("post", "put") else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code in (401, 403)


class TestCreate:
    """POST /satellites."""

    def test_create_returns_201_and_a_uuid_id(self, client: TestClient):
        """Test that the response identifier is the public UUID."""
        headers = register(client)
        response = create_satellite(client, headers)

        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "space"
        assert body["base_url"] == "https://s.example.com"
        # A UUID, not an integer key.
        assert len(body["id"]) == 36 and body["id"].count("-") == 4

    def test_response_never_leaks_the_integer_key(self, client: TestClient):
        """Test that no internal identifier reaches the body.

        The whole point of public_id being separate is that it is rotatable;
        that only holds while the primary key stays unexposed.
        """
        headers = register(client)
        body = create_satellite(client, headers).json()

        assert set(body) == {"id", "kind", "base_url", "last_seen_at", "created_at"}
        assert "user_id" not in body

    def test_create_normalises_the_origin(self, client: TestClient):
        """Test that a non-canonical origin is stored canonically."""
        headers = register(client)
        response = create_satellite(
            client, headers, base_url="HTTPS://S.Example.com:443/v1/"
        )
        assert response.json()["base_url"] == "https://s.example.com"

    def test_create_a_station(self, client: TestClient):
        """Test the station case, which must be registered explicitly."""
        headers = register(client)
        response = client.post(
            "/api/v1/satellites",
            headers=headers,
            json={"kind": "station", "base_url": "https://station.example.com"},
        )
        assert response.status_code == 201
        assert response.json()["kind"] == "station"

    @pytest.mark.parametrize(
        "payload",
        [
            {"kind": "planet", "base_url": "https://h.io"},
            {"kind": "space"},
            {"kind": "space", "base_url": "not-a-url"},
            {"kind": "space", "base_url": "ftp://h.io"},
            {"kind": "space", "base_url": "https://u:p@h.io"},
            {"kind": "space", "base_url": "https://"},
            {},
        ],
    )
    def test_rejects_bad_input_with_422(self, client: TestClient, payload):
        """Test that invalid input is a field error, never a 500."""
        headers = register(client)
        response = client.post("/api/v1/satellites", headers=headers, json=payload)
        assert response.status_code == 422

    def test_duplicate_origin_is_409(self, client: TestClient):
        """Test that one host is exactly one satellite per account."""
        headers = register(client)
        create_satellite(client, headers, base_url="https://a.example.com")
        response = create_satellite(client, headers, base_url="https://a.example.com")
        assert response.status_code == 409


class TestListGetUpdateDelete:
    """The remaining routes."""

    def test_list_starts_empty(self, client: TestClient):
        """Test a fresh account owns nothing."""
        headers = register(client)
        response = client.get("/api/v1/satellites", headers=headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_returns_registered_satellites(self, client: TestClient):
        """Test that registration is reflected in the listing."""
        headers = register(client)
        a = create_satellite(client, headers, base_url="https://a.example.com").json()
        b = create_satellite(client, headers, base_url="https://b.example.com").json()

        body = client.get("/api/v1/satellites", headers=headers).json()
        assert [s["id"] for s in body] == [a["id"], b["id"]]

    def test_get_one(self, client: TestClient):
        """Test fetching a single satellite by its public id."""
        headers = register(client)
        created = create_satellite(client, headers).json()

        response = client.get(f"/api/v1/satellites/{created['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_get_unknown_is_404(self, client: TestClient):
        """Test an identifier that belongs to nobody."""
        headers = register(client)
        response = client.get(
            "/api/v1/satellites/00000000-0000-0000-0000-000000000009", headers=headers
        )
        assert response.status_code == 404

    def test_malformed_uuid_is_422(self, client: TestClient):
        """Test that a non-UUID path segment is a validation error."""
        headers = register(client)
        response = client.get("/api/v1/satellites/not-a-uuid", headers=headers)
        assert response.status_code == 422

    def test_update_keeps_identity(self, client: TestClient):
        """Test that moving a satellite does not change its id."""
        headers = register(client)
        created = create_satellite(client, headers).json()

        response = client.put(
            f"/api/v1/satellites/{created['id']}",
            headers=headers,
            json={"base_url": "https://moved.example.com"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]
        assert response.json()["base_url"] == "https://moved.example.com"

    def test_delete_returns_204_and_removes_it(self, client: TestClient):
        """Test deletion."""
        headers = register(client)
        created = create_satellite(client, headers).json()

        assert (
            client.delete(
                f"/api/v1/satellites/{created['id']}", headers=headers
            ).status_code
            == 204
        )
        assert client.get("/api/v1/satellites", headers=headers).json() == []

    def test_delete_unknown_is_404(self, client: TestClient):
        """Test deleting something that is not there."""
        headers = register(client)
        response = client.delete(
            "/api/v1/satellites/00000000-0000-0000-0000-000000000009", headers=headers
        )
        assert response.status_code == 404


class TestCrossAccountIsolation:
    """One account must not see or touch another's satellites."""

    def test_another_account_cannot_read_or_delete(self, client: TestClient):
        """Test that a foreign identifier reads as missing, not forbidden."""
        alice = register(client, "alice")
        created = create_satellite(client, alice).json()
        bob = register(client, "bob")

        assert client.get("/api/v1/satellites", headers=bob).json() == []
        assert (
            client.get(f"/api/v1/satellites/{created['id']}", headers=bob).status_code
            == 404
        )
        assert (
            client.delete(
                f"/api/v1/satellites/{created['id']}", headers=bob
            ).status_code
            == 404
        )
        # Still alice's.
        assert len(client.get("/api/v1/satellites", headers=alice).json()) == 1

    def test_two_accounts_may_use_the_same_origin(self, client: TestClient):
        """Test that uniqueness is per account, not global.

        Squatting another account's origin is harmless: resolution only ever
        looks inside the caller's own satellites.
        """
        alice = register(client, "alice")
        bob = register(client, "bob")
        assert create_satellite(client, alice).status_code == 201
        assert create_satellite(client, bob).status_code == 201
