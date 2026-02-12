"""Tests for accounting API endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.database.dependencies import get_user_repository
from syfthub.main import app
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import User
from syfthub.services.accounting_client import AccountingUser


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user() -> User:
    """Create a mock user with accounting configured."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        age=30,
        role=UserRole.USER,
        password_hash="hash",
        is_active=True,
        accounting_service_url="https://accounting.example.com",
        accounting_password="test-password",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_user_no_accounting() -> User:
    """Create a mock user without accounting configured."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        age=30,
        role=UserRole.USER,
        password_hash="hash",
        is_active=True,
        accounting_service_url=None,
        accounting_password=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def reset_overrides():
    """Clear dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


class TestGetAccountingClient:
    """Tests for get_accounting_client helper function."""

    def test_accounting_not_configured(self, client, mock_user_no_accounting):
        """Test error when accounting is not configured."""
        app.dependency_overrides[get_current_active_user] = lambda: (
            mock_user_no_accounting
        )

        response = client.get("/api/v1/accounting/user")
        assert response.status_code == 400
        assert "Accounting not configured" in response.json()["detail"]


class TestGetAccountingUser:
    """Tests for GET /accounting/user endpoint."""

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_get_user_success(self, mock_client_class, client, mock_user):
        """Test successful get accounting user."""
        mock_client = MagicMock()
        mock_client.get_user.return_value = AccountingUser(
            id="user-123",
            email="test@example.com",
            balance=100.0,
            organization="test-org",
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/user")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "user-123"
        assert data["email"] == "test@example.com"
        assert data["balance"] == 100.0
        assert data["organization"] == "test-org"

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_get_user_invalid_credentials(self, mock_client_class, client, mock_user):
        """Test get user with invalid accounting credentials."""
        mock_client = MagicMock()
        mock_client.get_user.return_value = None
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/user")

        assert response.status_code == 401
        assert "Invalid accounting credentials" in response.json()["detail"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_get_user_service_error(self, mock_client_class, client, mock_user):
        """Test get user with accounting service error."""
        mock_client = MagicMock()
        mock_client.get_user.side_effect = Exception("Connection failed")
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/user")

        assert response.status_code == 502
        assert (
            "Error communicating with accounting service" in response.json()["detail"]
        )


class TestGetTransactions:
    """Tests for GET /accounting/transactions endpoint."""

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_get_transactions_success(self, mock_client_class, client, mock_user):
        """Test successful get transactions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "tx-123",
                "senderEmail": "sender@example.com",
                "recipientEmail": "recipient@example.com",
                "amount": 50.0,
                "status": "confirmed",
                "createdBy": "sender@example.com",
                "resolvedBy": "recipient@example.com",
                "createdAt": "2024-01-01T00:00:00Z",
                "resolvedAt": "2024-01-01T00:01:00Z",
                "appName": "test-app",
                "appEpPath": "/test/path",
            }
        ]

        mock_client = MagicMock()
        mock_client.client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/transactions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "tx-123"
        assert data[0]["sender_email"] == "sender@example.com"

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_get_transactions_with_pagination(
        self, mock_client_class, client, mock_user
    ):
        """Test get transactions with pagination parameters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = MagicMock()
        mock_client.client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/transactions?skip=10&limit=50")

        assert response.status_code == 200
        mock_client.client.get.assert_called_once()
        call_kwargs = mock_client.client.get.call_args
        assert call_kwargs[1]["params"]["skip"] == 10
        assert call_kwargs[1]["params"]["limit"] == 50

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_get_transactions_error(self, mock_client_class, client, mock_user):
        """Test get transactions with error response."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/transactions")

        assert response.status_code == 500
        assert "Failed to fetch transactions" in response.json()["detail"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_get_transactions_service_error(self, mock_client_class, client, mock_user):
        """Test get transactions with service error."""
        mock_client = MagicMock()
        mock_client.client.get.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/transactions")

        assert response.status_code == 502
        assert (
            "Error communicating with accounting service" in response.json()["detail"]
        )


class TestCreateTransaction:
    """Tests for POST /accounting/transactions endpoint."""

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_transaction_success(self, mock_client_class, client, mock_user):
        """Test successful transaction creation."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "tx-new",
            "senderEmail": "test@example.com",
            "recipientEmail": "recipient@example.com",
            "amount": 25.0,
            "status": "pending",
            "createdBy": "test@example.com",
            "createdAt": "2024-01-01T00:00:00Z",
        }

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transactions",
            json={
                "recipient_email": "recipient@example.com",
                "amount": 25.0,
                "app_name": "test-app",
                "app_ep_path": "/test/path",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tx-new"
        assert data["status"] == "pending"

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_transaction_without_optional_fields(
        self, mock_client_class, client, mock_user
    ):
        """Test transaction creation without optional fields."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "tx-new",
            "senderEmail": "test@example.com",
            "recipientEmail": "recipient@example.com",
            "amount": 10.0,
            "status": "pending",
            "createdBy": "test@example.com",
            "createdAt": "2024-01-01T00:00:00Z",
        }

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transactions",
            json={
                "recipient_email": "recipient@example.com",
                "amount": 10.0,
            },
        )

        assert response.status_code == 200

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_transaction_error_with_detail(
        self, mock_client_class, client, mock_user
    ):
        """Test transaction creation with error containing detail."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Insufficient balance"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transactions",
            json={
                "recipient_email": "recipient@example.com",
                "amount": 1000000.0,
            },
        )

        assert response.status_code == 400
        assert "Insufficient balance" in response.json()["detail"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_transaction_error_with_message(
        self, mock_client_class, client, mock_user
    ):
        """Test transaction creation with error containing message."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Invalid recipient"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transactions",
            json={
                "recipient_email": "invalid",
                "amount": 10.0,
            },
        )

        assert response.status_code == 400
        assert "Invalid recipient" in response.json()["detail"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_transaction_error_no_json(
        self, mock_client_class, client, mock_user
    ):
        """Test transaction creation with error that can't be parsed."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transactions",
            json={
                "recipient_email": "recipient@example.com",
                "amount": 10.0,
            },
        )

        assert response.status_code == 500


class TestConfirmTransaction:
    """Tests for POST /accounting/transactions/{id}/confirm endpoint."""

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_confirm_transaction_success(self, mock_client_class, client, mock_user):
        """Test successful transaction confirmation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "tx-123",
            "senderEmail": "sender@example.com",
            "recipientEmail": "test@example.com",
            "amount": 50.0,
            "status": "confirmed",
            "createdBy": "sender@example.com",
            "resolvedBy": "test@example.com",
            "createdAt": "2024-01-01T00:00:00Z",
            "resolvedAt": "2024-01-01T00:01:00Z",
        }

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transactions/tx-123/confirm")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tx-123"
        assert data["status"] == "confirmed"

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_confirm_transaction_not_found(self, mock_client_class, client, mock_user):
        """Test confirming non-existent transaction."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Transaction not found"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transactions/invalid-id/confirm")

        assert response.status_code == 404

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_confirm_transaction_error_no_json(
        self, mock_client_class, client, mock_user
    ):
        """Test confirm with error that can't parse JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transactions/tx-123/confirm")

        assert response.status_code == 500

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_confirm_transaction_service_error(
        self, mock_client_class, client, mock_user
    ):
        """Test confirm with service error."""
        mock_client = MagicMock()
        mock_client.client.post.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transactions/tx-123/confirm")

        assert response.status_code == 502


class TestCancelTransaction:
    """Tests for POST /accounting/transactions/{id}/cancel endpoint."""

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_cancel_transaction_success(self, mock_client_class, client, mock_user):
        """Test successful transaction cancellation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "tx-123",
            "senderEmail": "test@example.com",
            "recipientEmail": "recipient@example.com",
            "amount": 50.0,
            "status": "cancelled",
            "createdBy": "test@example.com",
            "resolvedBy": "test@example.com",
            "createdAt": "2024-01-01T00:00:00Z",
            "resolvedAt": "2024-01-01T00:01:00Z",
        }

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transactions/tx-123/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tx-123"
        assert data["status"] == "cancelled"

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_cancel_transaction_not_found(self, mock_client_class, client, mock_user):
        """Test cancelling non-existent transaction."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Transaction not found"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transactions/invalid-id/cancel")

        assert response.status_code == 404

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_cancel_transaction_error_no_json(
        self, mock_client_class, client, mock_user
    ):
        """Test cancel with error that can't parse JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transactions/tx-123/cancel")

        assert response.status_code == 400

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_cancel_transaction_service_error(
        self, mock_client_class, client, mock_user
    ):
        """Test cancel with service error."""
        mock_client = MagicMock()
        mock_client.client.post.side_effect = Exception("Timeout")
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transactions/tx-123/cancel")

        assert response.status_code == 502


class TestCreateTransactionTokens:
    """Tests for POST /accounting/transaction-tokens endpoint."""

    @pytest.fixture
    def mock_owner_user(self) -> User:
        """Create a mock owner user."""
        return User(
            id=2,
            username="owner",
            email="owner@example.com",
            full_name="Owner User",
            age=35,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_success(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test successful token creation for single owner."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "jwt-token-123"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "owner" in data["tokens"]
        assert data["tokens"]["owner"] == "jwt-token-123"
        assert data["errors"] == {}

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_multiple_owners(self, mock_client_class, client, mock_user):
        """Test token creation for multiple owners."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "jwt-token"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        owner1 = User(
            id=2,
            username="owner1",
            email="owner1@example.com",
            full_name="Owner 1",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        owner2 = User(
            id=3,
            username="owner2",
            email="owner2@example.com",
            full_name="Owner 2",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_repo = MagicMock()
        mock_repo.get_by_username.side_effect = lambda u: (
            owner1 if u == "owner1" else owner2
        )

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner1", "owner2"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "owner1" in data["tokens"]
        assert "owner2" in data["tokens"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_owner_not_found(self, mock_client_class, client, mock_user):
        """Test token creation when owner not found."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = None

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["nonexistent"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "nonexistent" in data["errors"]
        assert "not found" in data["errors"]["nonexistent"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_owner_no_email(self, mock_client_class, client, mock_user):
        """Test token creation when owner has no email."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Use a MagicMock to simulate a user with no email attribute
        owner_no_email = MagicMock()
        owner_no_email.email = None

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = owner_no_email

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["noemail"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "noemail" in data["errors"]
        assert "no email" in data["errors"]["noemail"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_accounting_error(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation with accounting service error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal error"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "owner" in data["errors"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_no_token_in_response(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation when response has no token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # No token field

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "owner" in data["errors"]
        assert "not returned" in data["errors"]["owner"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_request_exception(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation with request exception."""
        mock_client = MagicMock()
        mock_client.client.post.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "owner" in data["errors"]
        assert "Request failed" in data["errors"]["owner"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_duplicate_owners(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation with duplicate owners in request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "jwt-token"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner", "owner", "owner"]},
        )

        assert response.status_code == 200
        data = response.json()
        # Should only have one entry despite duplicates
        assert len(data["tokens"]) == 1
        assert "owner" in data["tokens"]

    def test_create_tokens_accounting_not_configured(
        self, client, mock_user_no_accounting
    ):
        """Test token creation when accounting not configured."""
        app.dependency_overrides[get_current_active_user] = lambda: (
            mock_user_no_accounting
        )

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner"]},
        )

        assert response.status_code == 400
        assert "Accounting not configured" in response.json()["detail"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_error_with_message(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation with error containing message field."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"message": "Forbidden"}

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "Forbidden" in data["errors"]["owner"]

    @patch("syfthub.api.endpoints.accounting.AccountingClient")
    def test_create_tokens_error_no_json(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation with error that can't parse JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = MagicMock()
        mock_client.client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"owner_usernames": ["owner"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "HTTP 500" in data["errors"]["owner"]
