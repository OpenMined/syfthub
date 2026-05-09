"""Tests for endpoint transaction policies persistence and exposure.

Covers:
- POST /api/v1/endpoints/sync persists `policies` (including transaction policy)
- Legacy syncs (no `policies` field) remain backward compatible
- A subsequent sync replaces the previous policy list (no merge)
- List/detail endpoint responses expose `policies` and `payment_required`
- The `EndpointModel.payment_required` property reflects policy contents
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.database.connection import (
    create_tables,
    drop_tables,
    get_db_session,
)
from syfthub.main import app
from syfthub.models.endpoint import EndpointModel
from syfthub.repositories.user import UserRepository


@pytest.fixture
def client() -> TestClient:
    """Create a test client with a clean database."""
    drop_tables()
    create_tables()
    test_client = TestClient(app)
    yield test_client
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data() -> None:
    """Reset authentication state before each test."""
    token_blacklist.clear()


@pytest.fixture
def user_token(client: TestClient) -> str:
    """Create a user and return the access token."""
    user_data = {
        "username": "tx_user",
        "email": "tx_user@example.com",
        "full_name": "Transaction User",
        "password": "testpass123",
    }
    response = client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code in (200, 201)
    return response.json()["access_token"]


def _user_id_for_username(username: str) -> int:
    """Look up a user's id directly via the repository."""
    session = next(get_db_session())
    try:
        repo = UserRepository(session)
        user = repo.get_by_username(username)
        assert user is not None, f"User {username} not found"
        return user.id
    finally:
        session.close()


def _transaction_policy() -> dict:
    """A representative on-chain transaction policy payload."""
    return {
        "name": "paid-access",
        "type": "transaction",
        "enabled": True,
        "config": {
            "recipient": "0x000000000000000000000000000000000000dead",
            "amount": "0.10",
            "currency": "0x20c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0",
            "method": "tempo",
            "intent": "charge",
            "chain_id": 42431,
            "ttl_seconds": 600,
        },
    }


# ---------------------------------------------------------------------------
# Sync persistence tests
# ---------------------------------------------------------------------------


def test_sync_with_policies_persists(client: TestClient, user_token: str) -> None:
    """A sync payload carrying a transaction policy is persisted on the row."""
    headers = {"Authorization": f"Bearer {user_token}"}
    sync_data = {
        "endpoints": [
            {
                "name": "Paid Endpoint",
                "type": "model",
                "visibility": "public",
                "description": "An endpoint with a transaction policy",
                "policies": [_transaction_policy()],
            }
        ]
    }

    response = client.post("/api/v1/endpoints/sync", json=sync_data, headers=headers)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["synced"] == 1
    assert len(body["endpoints"]) == 1
    returned = body["endpoints"][0]
    assert returned["payment_required"] is True
    assert len(returned["policies"]) == 1
    assert returned["policies"][0]["type"] == "transaction"
    assert returned["policies"][0]["name"] == "paid-access"
    assert returned["policies"][0]["config"]["method"] == "tempo"

    # Verify the row was actually persisted with the policy.
    user_id = _user_id_for_username("tx_user")
    session = next(get_db_session())
    try:
        endpoint = (
            session.query(EndpointModel)
            .filter(
                EndpointModel.user_id == user_id,
                EndpointModel.slug == "paid-endpoint",
            )
            .one()
        )
        assert endpoint.policies is not None
        assert len(endpoint.policies) == 1
        assert endpoint.policies[0]["type"] == "transaction"
        assert endpoint.payment_required is True
    finally:
        session.close()


def test_sync_without_policies_legacy_compat(
    client: TestClient, user_token: str
) -> None:
    """A legacy sync without the `policies` field still works."""
    headers = {"Authorization": f"Bearer {user_token}"}
    sync_data = {
        "endpoints": [
            {
                "name": "Legacy Endpoint",
                "type": "model",
                "visibility": "public",
                "description": "Old-style sync without policies",
            }
        ]
    }

    response = client.post("/api/v1/endpoints/sync", json=sync_data, headers=headers)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["synced"] == 1
    returned = body["endpoints"][0]
    assert returned["policies"] == []
    assert returned["payment_required"] is False

    user_id = _user_id_for_username("tx_user")
    session = next(get_db_session())
    try:
        endpoint = (
            session.query(EndpointModel)
            .filter(
                EndpointModel.user_id == user_id,
                EndpointModel.slug == "legacy-endpoint",
            )
            .one()
        )
        assert endpoint.policies == []
        assert endpoint.payment_required is False
    finally:
        session.close()


def test_sync_replaces_policies(client: TestClient, user_token: str) -> None:
    """Re-syncing with an empty `policies` list clears the prior value."""
    headers = {"Authorization": f"Bearer {user_token}"}

    initial = {
        "endpoints": [
            {
                "name": "Replaceable Endpoint",
                "type": "model",
                "visibility": "public",
                "policies": [_transaction_policy()],
            }
        ]
    }
    first = client.post("/api/v1/endpoints/sync", json=initial, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["endpoints"][0]["payment_required"] is True

    # Second sync with the same endpoint but no policies must clear them.
    cleared = {
        "endpoints": [
            {
                "name": "Replaceable Endpoint",
                "type": "model",
                "visibility": "public",
                "policies": [],
            }
        ]
    }
    second = client.post("/api/v1/endpoints/sync", json=cleared, headers=headers)
    assert second.status_code == 200, second.text
    returned = second.json()["endpoints"][0]
    assert returned["policies"] == []
    assert returned["payment_required"] is False


# ---------------------------------------------------------------------------
# Response serializer tests
# ---------------------------------------------------------------------------


def test_list_endpoints_includes_policies(client: TestClient, user_token: str) -> None:
    """GET /api/v1/endpoints includes `policies` and `payment_required`."""
    headers = {"Authorization": f"Bearer {user_token}"}

    sync_data = {
        "endpoints": [
            {
                "name": "Listable Paid",
                "type": "model",
                "visibility": "public",
                "policies": [_transaction_policy()],
            },
            {
                "name": "Listable Free",
                "type": "model",
                "visibility": "public",
            },
        ]
    }
    response = client.post("/api/v1/endpoints/sync", json=sync_data, headers=headers)
    assert response.status_code == 200, response.text

    listing = client.get("/api/v1/endpoints", headers=headers)
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 2
    by_slug = {item["slug"]: item for item in items}
    paid = by_slug["listable-paid"]
    free = by_slug["listable-free"]

    assert "policies" in paid
    assert "payment_required" in paid
    assert paid["payment_required"] is True
    assert paid["policies"][0]["type"] == "transaction"

    assert free["policies"] == []
    assert free["payment_required"] is False


def test_detail_endpoint_includes_policies(client: TestClient, user_token: str) -> None:
    """GET /api/v1/endpoints/{owner}/{slug}-style detail includes the fields."""
    headers = {"Authorization": f"Bearer {user_token}"}

    sync_data = {
        "endpoints": [
            {
                "name": "Detail Paid",
                "type": "model",
                "visibility": "public",
                "policies": [_transaction_policy()],
            }
        ]
    }
    response = client.post("/api/v1/endpoints/sync", json=sync_data, headers=headers)
    assert response.status_code == 200, response.text
    endpoint_id = response.json()["endpoints"][0]["id"]

    detail = client.get(f"/api/v1/endpoints/{endpoint_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["payment_required"] is True
    assert len(body["policies"]) == 1
    assert body["policies"][0]["type"] == "transaction"

    # Anonymous public detail (mounted at "/{owner_slug}/{endpoint_slug}")
    public_detail = client.get("/tx_user/detail-paid")
    assert public_detail.status_code == 200
    public_body = public_detail.json()
    assert public_body["payment_required"] is True
    assert any(p["type"] == "transaction" for p in public_body["policies"])


# ---------------------------------------------------------------------------
# payment_required property unit tests
# ---------------------------------------------------------------------------


def test_payment_required_property_when_no_policies() -> None:
    """`payment_required` is False when `policies` is None or empty."""
    endpoint = EndpointModel()
    endpoint.policies = None  # type: ignore[assignment]
    assert endpoint.payment_required is False

    endpoint.policies = []
    assert endpoint.payment_required is False


def test_payment_required_property_when_only_rate_limit() -> None:
    """A non-payment policy keeps `payment_required` False."""
    endpoint = EndpointModel()
    endpoint.policies = [
        {"type": "rate_limit", "config": {"per_minute": 10}},
    ]
    assert endpoint.payment_required is False


def test_payment_required_property_when_transaction_present() -> None:
    """A transaction policy flips `payment_required` to True."""
    endpoint = EndpointModel()
    endpoint.policies = [
        {"type": "rate_limit", "config": {"per_minute": 10}},
        {
            "type": "transaction",
            "config": {"amount": "0.10", "method": "tempo"},
        },
    ]
    assert endpoint.payment_required is True


def test_payment_required_property_when_xendit_present() -> None:
    """An existing xendit policy also marks the endpoint as paid."""
    endpoint = EndpointModel()
    endpoint.policies = [{"type": "xendit", "config": {}}]
    assert endpoint.payment_required is True


def test_payment_required_property_handles_non_dict_entries() -> None:
    """Malformed policy entries are ignored, not raised."""
    endpoint = EndpointModel()
    endpoint.policies = ["not a dict", {"type": None}, {"no_type": True}]  # type: ignore[list-item]
    assert endpoint.payment_required is False
