"""query_schema: what a query against an endpoint may carry.

The publishing space declares it; the Hub stores it verbatim and relays it on
every read path a client uses to pick a source (owner listing, public listing,
single endpoint, search).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app
from syfthub.schemas.endpoint import EndpointCreate, QuerySchema

QS = {"metadata_fields": ["title", "url", "published"]}


@pytest.fixture
def client() -> TestClient:
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()
    yield TestClient(app)
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data() -> None:
    token_blacklist.clear()


@pytest.fixture
def user1_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "user1",
            "email": "user1@example.com",
            "full_name": "User One",
            "password": "testpass123",
        },
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------- schema ----------


def test_query_schema_defaults_to_none_when_not_declared() -> None:
    ep = EndpointCreate(name="ds", type="data_source")
    assert ep.query_schema is None


def test_query_schema_metadata_fields_default_empty() -> None:
    assert QuerySchema().metadata_fields == []


def test_query_schema_drops_unknown_keys_instead_of_rejecting() -> None:
    """A space may publish a newer query_schema before this Hub learns its keys."""
    ep = EndpointCreate(
        name="ds", type="data_source", query_schema={**QS, "filters": {"x": 1}}
    )
    assert ep.query_schema is not None
    assert ep.query_schema.model_dump() == QS


# ---------- create / update / read ----------


def test_create_without_query_schema_reads_back_null(
    client: TestClient, user1_token: str
) -> None:
    r = client.post(
        "/api/v1/endpoints",
        json={"name": "Plain", "type": "model"},
        headers=_auth(user1_token),
    )
    assert r.status_code == 201
    assert r.json()["query_schema"] is None


def test_create_with_query_schema_reads_back_verbatim(
    client: TestClient, user1_token: str
) -> None:
    r = client.post(
        "/api/v1/endpoints",
        json={"name": "Feed", "type": "data_source", "query_schema": QS},
        headers=_auth(user1_token),
    )
    assert r.status_code == 201
    assert r.json()["query_schema"] == QS

    r = client.get(f"/api/v1/endpoints/{r.json()['id']}", headers=_auth(user1_token))
    assert r.status_code == 200
    assert r.json()["query_schema"] == QS


def test_update_replaces_query_schema(client: TestClient, user1_token: str) -> None:
    headers = _auth(user1_token)
    created = client.post(
        "/api/v1/endpoints",
        json={"name": "Feed", "type": "data_source", "query_schema": QS},
        headers=headers,
    )
    r = client.patch(
        f"/api/v1/endpoints/{created.json()['id']}",
        json={"query_schema": {"metadata_fields": ["title"]}},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["query_schema"] == {"metadata_fields": ["title"]}


def test_update_without_query_schema_keeps_it(
    client: TestClient, user1_token: str
) -> None:
    headers = _auth(user1_token)
    created = client.post(
        "/api/v1/endpoints",
        json={"name": "Feed", "type": "data_source", "query_schema": QS},
        headers=headers,
    )
    r = client.patch(
        f"/api/v1/endpoints/{created.json()['id']}",
        json={"description": "renamed"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["query_schema"] == QS


# ---------- sync (how spaces publish) ----------


def test_sync_stores_query_schema_per_endpoint(
    client: TestClient, user1_token: str
) -> None:
    headers = _auth(user1_token)
    r = client.post(
        "/api/v1/endpoints/sync",
        json={
            "endpoints": [
                {"name": "Feed", "type": "data_source", "query_schema": QS},
                {"name": "Model", "type": "model"},
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200
    by_slug = {e["slug"]: e for e in r.json()["endpoints"]}
    assert by_slug["feed"]["query_schema"] == QS
    assert by_slug["model"]["query_schema"] is None


# ---------- public read paths ----------


def _publish(client: TestClient, token: str) -> None:
    r = client.post(
        "/api/v1/endpoints/sync",
        json={
            "endpoints": [
                {
                    "name": "Feed",
                    "type": "data_source",
                    "visibility": "public",
                    "query_schema": QS,
                }
            ]
        },
        headers=_auth(token),
    )
    assert r.status_code == 200


def test_public_listing_carries_query_schema(
    client: TestClient, user1_token: str
) -> None:
    _publish(client, user1_token)
    r = client.get("/api/v1/endpoints/public")
    assert r.status_code == 200
    assert [e["query_schema"] for e in r.json()] == [QS]


def test_owner_listing_carries_query_schema(
    client: TestClient, user1_token: str
) -> None:
    _publish(client, user1_token)
    r = client.get("/user1")
    assert r.status_code == 200
    assert [e["query_schema"] for e in r.json()] == [QS]


def test_public_single_endpoint_carries_query_schema(
    client: TestClient, user1_token: str
) -> None:
    _publish(client, user1_token)
    r = client.get("/user1/feed", headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert r.json()["query_schema"] == QS
