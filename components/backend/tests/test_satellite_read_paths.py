"""Tests for 1d — endpoint URLs derived per satellite, not per account.

The listing join used to read ``users.domain``: one field describing one host
for the whole account. It now reads the ``base_url`` of the satellite serving
each endpoint. Nothing previously asserted what that join produced, so these
cover it directly.
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


def register(client: TestClient, username: str = "alice") -> dict:
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


def add_space(client, headers, base_url):
    """Register a space and return its public id."""
    response = client.post(
        "/api/v1/satellites",
        headers=headers,
        json={"kind": "space", "base_url": base_url},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def publish(client, headers, slug, path="v1/infer", satellite_id=None):
    """Publish an endpoint with one REST connection at ``path``."""
    url = "/api/v1/endpoints"
    if satellite_id:
        url += f"?satellite_id={satellite_id}"
    response = client.post(
        url,
        headers=headers,
        json={
            "name": slug,
            "slug": slug,
            "description": "d",
            "type": "model",
            "visibility": "public",
            "connect": [{"type": "rest_api", "config": {"url": path}, "enabled": True}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _first_url(endpoint: dict) -> str | None:
    """The first connection's URL from an endpoint response."""
    connect = endpoint.get("connect") or []
    return connect[0]["config"]["url"] if connect else None


class TestUrlsComeFromTheServingSatellite:
    """The point of 1d: the domain is per endpoint, not per account."""

    def test_url_is_built_from_the_satellite(self, client: TestClient):
        """Test that a published endpoint's URL uses its space's origin."""
        headers = register(client)
        add_space(client, headers, "https://space-a.example.com")
        publish(client, headers, "my-model")

        listed = client.get("/api/v1/endpoints", headers=headers).json()
        assert _first_url(listed[0]) == "https://space-a.example.com/v1/infer"

    def test_two_spaces_give_two_different_urls(self, client: TestClient):
        """Test the behaviour ``users.domain`` could not express.

        One account, two spaces, two endpoints — each URL must come from the
        space that actually serves it.
        """
        headers = register(client)
        a = add_space(client, headers, "https://space-a.example.com")
        b = add_space(client, headers, "https://space-b.example.com")
        publish(client, headers, "on-a", path="v1/a", satellite_id=a)
        publish(client, headers, "on-b", path="v1/b", satellite_id=b)

        listed = client.get("/api/v1/endpoints", headers=headers).json()
        urls = {e["slug"]: _first_url(e) for e in listed}
        assert urls["on-a"] == "https://space-a.example.com/v1/a"
        assert urls["on-b"] == "https://space-b.example.com/v1/b"

    def test_unattached_endpoint_still_listed_without_a_url(self, client: TestClient):
        """Test that the outer join keeps unattached endpoints visible.

        An inner join would drop them from the catalogue entirely — silently,
        and for every account that has not registered a satellite.
        """
        headers = register(client)
        publish(client, headers, "loose")

        listed = client.get("/api/v1/endpoints", headers=headers).json()
        assert [e["slug"] for e in listed] == ["loose"]
        # No origin to build from, so the path is returned unchanged.
        assert _first_url(listed[0]) == "v1/infer"

    def test_moving_a_space_moves_its_endpoint_urls(self, client: TestClient):
        """Test that a moved space is reflected immediately.

        This is the gap 1c opened and 1d closes: health stopped refreshing
        ``users.domain``, so until the read moved, a relocated space kept
        showing its old URL.
        """
        headers = register(client)
        space = add_space(client, headers, "https://old.example.com")
        publish(client, headers, "my-model")

        client.put(
            f"/api/v1/satellites/{space}",
            headers=headers,
            json={"base_url": "https://new.example.com"},
        )

        listed = client.get("/api/v1/endpoints", headers=headers).json()
        assert _first_url(listed[0]) == "https://new.example.com/v1/infer"

    def test_public_listing_uses_the_satellite_too(self, client: TestClient):
        """Test the anonymous path, which uses the same join."""
        headers = register(client)
        add_space(client, headers, "https://space-a.example.com")
        publish(client, headers, "my-model")

        listed = client.get("/api/v1/endpoints/public").json()
        mine = [e for e in listed if e["slug"] == "my-model"]
        assert mine, "endpoint missing from the public listing"
        assert _first_url(mine[0]) == "https://space-a.example.com/v1/infer"

    def test_health_report_refreshes_the_url(self, client: TestClient):
        """Test the full loop: a space reports in, listings follow."""
        headers = register(client)
        add_space(client, headers, "https://old.example.com")
        publish(client, headers, "my-model")

        response = client.post(
            "/api/v1/endpoints/health",
            headers=headers,
            json={
                "endpoints": [
                    {
                        "slug": "my-model",
                        "status": "healthy",
                        "checked_at": "2026-01-01T00:00:00Z",
                    }
                ],
                "ttl_seconds": 300,
                "url": "https://relocated.example.com",
            },
        )
        assert response.status_code == 200, response.text

        listed = client.get("/api/v1/endpoints", headers=headers).json()
        assert _first_url(listed[0]) == "https://relocated.example.com/v1/infer"


class TestProfileDomainRedirect:
    """`PUT /users/me {domain}` is redirected, never rejected.

    Old spaces set their URL this way at setup (`marketplaces/handlers.py:123`),
    so rejecting it would break every space that has not upgraded. This is the
    compatibility guarantee the whole rollout rests on (S12).
    """

    def test_setting_a_domain_registers_a_space(self, client: TestClient):
        """Test that the legacy call creates a satellite."""
        headers = register(client)

        response = client.put(
            "/api/v1/users/me",
            headers=headers,
            json={"domain": "https://legacy.example.com"},
        )
        assert response.status_code == 200, response.text

        satellites = client.get("/api/v1/satellites", headers=headers).json()
        assert len(satellites) == 1
        assert satellites[0]["kind"] == "space"
        assert satellites[0]["base_url"] == "https://legacy.example.com"

    def test_the_response_domain_reflects_it(self, client: TestClient):
        """Test that the field still reads back, now derived from the space."""
        headers = register(client)
        client.put(
            "/api/v1/users/me",
            headers=headers,
            json={"domain": "https://legacy.example.com"},
        )

        me = client.get("/api/v1/users/me", headers=headers).json()
        assert me["domain"] == "https://legacy.example.com"

    def test_a_changed_domain_moves_the_space(self, client: TestClient):
        """Test that a relocated space is moved, not duplicated.

        Spaces call this on every marketplace setup, so a space whose public URL
        changed between deployments would otherwise leave the account owning two
        satellites — and every endpoint write after that would be ambiguous.
        """
        headers = register(client)
        client.put(
            "/api/v1/users/me",
            headers=headers,
            json={"domain": "https://old.example.com"},
        )
        client.put(
            "/api/v1/users/me",
            headers=headers,
            json={"domain": "https://new.example.com"},
        )

        satellites = client.get("/api/v1/satellites", headers=headers).json()
        assert len(satellites) == 1, "a moved space must not become a second satellite"
        assert satellites[0]["base_url"] == "https://new.example.com"

        # And publishing still works, rather than 422-ing on ambiguity.
        assert publish(client, headers, "still-works")["slug"] == "still-works"

    def test_repeating_setup_does_not_duplicate(self, client: TestClient):
        """Test that a space re-running setup is idempotent."""
        headers = register(client)
        for _ in range(3):
            client.put(
                "/api/v1/users/me",
                headers=headers,
                json={"domain": "https://legacy.example.com"},
            )

        assert len(client.get("/api/v1/satellites", headers=headers).json()) == 1

    def test_domain_is_derived_from_the_oldest_space(self, client: TestClient):
        """Test Decision D: the oldest space, not the newest, not a station."""
        headers = register(client)
        add_space(client, headers, "https://first.example.com")
        add_space(client, headers, "https://second.example.com")

        me = client.get("/api/v1/users/me", headers=headers).json()
        assert me["domain"] == "https://first.example.com"

    def test_a_station_is_never_reported_as_the_domain(self, client: TestClient):
        """Test that a station's origin does not surface as the account domain.

        A station serves no endpoints, so its origin is not where anything
        lives.
        """
        headers = register(client)
        client.post(
            "/api/v1/satellites",
            headers=headers,
            json={"kind": "station", "base_url": "https://station.example.com"},
        )

        me = client.get("/api/v1/users/me", headers=headers).json()
        assert me["domain"] is None

    def test_a_station_does_not_make_endpoint_writes_ambiguous(
        self, client: TestClient
    ):
        """Test the kind filter.

        An account running a station alongside its one space owns two
        satellites. Counting both would 422 every endpoint write, for a
        satellite that can never serve endpoints.
        """
        headers = register(client)
        add_space(client, headers, "https://space.example.com")
        client.post(
            "/api/v1/satellites",
            headers=headers,
            json={"kind": "station", "base_url": "https://station.example.com"},
        )

        response = client.post(
            "/api/v1/endpoints",
            headers=headers,
            json={
                "name": "my-model",
                "slug": "my-model",
                "description": "d",
                "type": "model",
                "visibility": "public",
                "connect": [
                    {"type": "rest_api", "config": {"url": "v1"}, "enabled": True}
                ],
            },
        )
        assert response.status_code == 201, response.text

        listed = client.get("/api/v1/endpoints", headers=headers).json()
        assert _first_url(listed[0]) == "https://space.example.com/v1"
