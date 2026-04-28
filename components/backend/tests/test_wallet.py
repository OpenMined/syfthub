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
