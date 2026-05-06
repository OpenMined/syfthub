"""Tests for wallet endpoints."""

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app


@pytest.fixture
def client():
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()
    client = TestClient(app)
    yield client
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data():
    token_blacklist.clear()


@pytest.fixture
def user_token(client):
    user_data = {
        "username": "walletuser",
        "email": "walletuser@example.com",
        "full_name": "Wallet User",
        "password": "testpass123",
    }
    response = client.post("/api/v1/auth/register", json=user_data)
    return response.json()["access_token"]


class TestGetWallet:
    def test_get_wallet_no_wallet_configured(self, client, user_token):
        response = client.get(
            "/api/v1/wallet/",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["address"] is None
        assert data["exists"] is False

    def test_get_wallet_requires_auth(self, client):
        response = client.get("/api/v1/wallet/")
        assert response.status_code == 401


class TestGetBalance:
    def test_get_balance_without_wallet_returns_zero(self, client, user_token):
        response = client.get(
            "/api/v1/wallet/balance",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["balance"] == 0.0
        assert data["wallet_configured"] is False
        assert data["recent_transactions"] == []

    def test_get_balance_requires_auth(self, client):
        response = client.get("/api/v1/wallet/balance")
        assert response.status_code == 401


class TestGetTransactions:
    def test_get_transactions_without_wallet_returns_empty(self, client, user_token):
        response = client.get(
            "/api/v1/wallet/transactions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_get_transactions_requires_auth(self, client):
        response = client.get("/api/v1/wallet/transactions")
        assert response.status_code == 401


class TestPayEndpoint:
    def test_pay_without_wallet_raises_400(self, client, user_token):
        response = client.post(
            "/api/v1/wallet/pay",
            json={"www_authenticate": "tempo ...", "endpoint_slug": "test"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["code"] == "WALLET_NOT_CONFIGURED"

    def test_pay_with_oversized_challenge_raises_400(self, client, user_token):
        response = client.post(
            "/api/v1/wallet/pay",
            json={
                "www_authenticate": "x" * 10001,
                "endpoint_slug": "test",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["code"] == "CHALLENGE_TOO_LARGE"

    def test_pay_requires_auth(self, client):
        response = client.post(
            "/api/v1/wallet/pay",
            json={"www_authenticate": "tempo ...", "endpoint_slug": "test"},
        )
        assert response.status_code == 401


class TestXenditSubscriptions:
    @staticmethod
    def _upsert(client, token, **overrides):
        body = {
            "credits_url": "https://alice.example.com/credits/foo",
            "payment_url": "https://alice.example.com/pay/foo",
            "endpoint_owner": "alice",
            "endpoint_slug": "foo",
            "currency": "IDR",
            "last_known_balance": 100.0,
        }
        body.update(overrides)
        return client.post(
            "/api/v1/wallet/subscriptions",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_list_empty(self, client, user_token):
        response = client.get(
            "/api/v1/wallet/subscriptions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"subscriptions": []}

    def test_list_requires_auth(self, client):
        assert client.get("/api/v1/wallet/subscriptions").status_code == 401

    def test_upsert_creates_row(self, client, user_token):
        response = self._upsert(client, user_token)
        assert response.status_code == 200
        data = response.json()
        assert data["endpoint_owner"] == "alice"
        assert data["credits_url"] == "https://alice.example.com/credits/foo"
        assert data["last_known_balance"] == 100.0

    def test_upsert_is_idempotent(self, client, user_token):
        first = self._upsert(client, user_token).json()
        second = self._upsert(client, user_token, last_known_balance=250.0).json()
        assert first["id"] == second["id"]
        assert second["last_known_balance"] == 250.0

    def test_upsert_requires_auth(self, client):
        response = client.post(
            "/api/v1/wallet/subscriptions",
            json={
                "credits_url": "https://x/credits",
                "payment_url": "https://x/pay",
                "endpoint_owner": "x",
            },
        )
        assert response.status_code == 401

    def test_list_collapses_to_one_per_owner(self, client, user_token):
        self._upsert(
            client,
            user_token,
            credits_url="https://alice.example.com/credits/foo",
            endpoint_slug="foo",
        )
        self._upsert(
            client,
            user_token,
            credits_url="https://alice.example.com/credits/bar",
            endpoint_slug="bar",
        )
        self._upsert(
            client,
            user_token,
            credits_url="https://bob.example.com/credits/baz",
            endpoint_owner="bob",
            endpoint_slug="baz",
        )
        response = client.get(
            "/api/v1/wallet/subscriptions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 200
        owners = sorted(s["endpoint_owner"] for s in response.json()["subscriptions"])
        assert owners == ["alice", "bob"]

    def test_delete_by_owner_sweeps_every_row(self, client, user_token):
        self._upsert(
            client,
            user_token,
            credits_url="https://alice.example.com/credits/foo",
            endpoint_slug="foo",
        )
        self._upsert(
            client,
            user_token,
            credits_url="https://alice.example.com/credits/bar",
            endpoint_slug="bar",
        )

        response = client.delete(
            "/api/v1/wallet/subscriptions/by-owner/alice",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 204

        listing = client.get(
            "/api/v1/wallet/subscriptions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert listing.json()["subscriptions"] == []

    def test_delete_by_owner_unknown_returns_404(self, client, user_token):
        response = client.delete(
            "/api/v1/wallet/subscriptions/by-owner/ghost",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 404

    def test_delete_by_owner_requires_auth(self, client):
        response = client.delete("/api/v1/wallet/subscriptions/by-owner/alice")
        assert response.status_code == 401

    def test_delete_by_id(self, client, user_token):
        created = self._upsert(client, user_token).json()
        response = client.delete(
            f"/api/v1/wallet/subscriptions/{created['id']}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 204

        listing = client.get(
            "/api/v1/wallet/subscriptions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert listing.json()["subscriptions"] == []

    def test_delete_by_id_unknown_returns_404(self, client, user_token):
        response = client.delete(
            "/api/v1/wallet/subscriptions/99999",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 404


class TestFeedbackEndpoint:
    def test_feedback_unconfigured_returns_error(self, client, user_token):
        from unittest.mock import patch

        with patch("syfthub.api.endpoints.feedback.settings") as mock_settings:
            mock_settings.linear_api_key = None
            mock_settings.linear_team_id = None
            response = client.post(
                "/api/v1/feedback",
                data={"description": "This is a bug report"},
                headers={"Authorization": f"Bearer {user_token}"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["ticket_id"] is None

    def test_feedback_requires_auth(self, client):
        response = client.post(
            "/api/v1/feedback",
            data={"description": "This is a bug report"},
        )
        assert response.status_code == 401
