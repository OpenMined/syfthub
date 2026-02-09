"""Tests for accounting API endpoints (Unified Global Ledger).

These tests verify the accounting proxy endpoints that communicate with
the Unified Global Ledger service.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.database.dependencies import get_user_repository
from syfthub.main import app
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import User
from syfthub.services.unified_ledger_client import (
    LedgerBalance,
    LedgerResult,
    LedgerTransfer,
)


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user() -> User:
    """Create a mock user with accounting configured (new ledger fields)."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        age=30,
        role=UserRole.USER,
        password_hash="hash",
        is_active=True,
        accounting_service_url="https://ledger.example.com",
        accounting_api_token="at_test_token_123",
        accounting_account_id="acc_user_123",
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
        accounting_api_token=None,
        accounting_account_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_user_no_account_id() -> User:
    """Create a mock user with token but no account ID."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        age=30,
        role=UserRole.USER,
        password_hash="hash",
        is_active=True,
        accounting_service_url="https://ledger.example.com",
        accounting_api_token="at_test_token_123",
        accounting_account_id=None,  # Missing account ID
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def reset_overrides():
    """Clear dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


class TestGetLedgerClientAndAccount:
    """Tests for get_ledger_client_and_account helper function."""

    def test_accounting_not_configured(self, client, mock_user_no_accounting):
        """Test error when accounting is not configured."""
        app.dependency_overrides[get_current_active_user] = (
            lambda: mock_user_no_accounting
        )

        response = client.get("/api/v1/accounting/user")
        assert response.status_code == 400
        assert "Accounting not configured" in response.json()["detail"]

    def test_no_account_id(self, client, mock_user_no_account_id):
        """Test error when account ID is missing."""
        app.dependency_overrides[get_current_active_user] = (
            lambda: mock_user_no_account_id
        )

        response = client.get("/api/v1/accounting/user")
        assert response.status_code == 400
        assert "No accounting account linked" in response.json()["detail"]


class TestGetAccountingUser:
    """Tests for GET /accounting/user endpoint."""

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_get_user_success(self, mock_client_class, client, mock_user):
        """Test successful get accounting user (balance)."""
        mock_client = MagicMock()
        mock_client.get_balance.return_value = LedgerResult(
            success=True,
            data=LedgerBalance(
                account_id="acc_user_123",
                balance="10000",
                available_balance="9500",
                currency="CREDIT",
            ),
            status_code=200,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/user")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "acc_user_123"
        assert data["email"] == "test@example.com"
        assert data["balance"] == 9500.0  # available_balance
        assert data["currency"] == "CREDIT"

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_get_user_invalid_credentials(self, mock_client_class, client, mock_user):
        """Test get user with invalid accounting credentials."""
        mock_client = MagicMock()
        mock_client.get_balance.return_value = LedgerResult(
            success=False,
            error="Invalid API token",
            status_code=401,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/user")

        assert response.status_code == 401
        assert "Invalid accounting credentials" in response.json()["detail"]

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_get_user_service_error(self, mock_client_class, client, mock_user):
        """Test get user with accounting service error."""
        mock_client = MagicMock()
        mock_client.get_balance.side_effect = Exception("Connection failed")
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/accounting/user")

        assert response.status_code == 502
        assert "Error communicating with ledger service" in response.json()["detail"]


class TestCreateTransfer:
    """Tests for POST /accounting/transfers endpoint."""

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_transfer_success(self, mock_client_class, client, mock_user):
        """Test successful transfer creation."""
        mock_client = MagicMock()
        mock_client.create_transfer.return_value = LedgerResult(
            success=True,
            data=LedgerTransfer(
                id="tr_new_123",
                source_account_id="acc_user_123",
                destination_account_id="acc_recipient_456",
                amount="1000",
                currency="CREDIT",
                status="completed",
                confirmation_token=None,
                description="Test payment",
                created_at="2026-02-09T12:00:00Z",
            ),
            status_code=201,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transfers",
            json={
                "destination_account_id": "acc_recipient_456",
                "amount": "1.00",
                "description": "Test payment",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tr_new_123"
        assert data["status"] == "completed"

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_transfer_with_confirmation(
        self, mock_client_class, client, mock_user
    ):
        """Test transfer creation with confirmation token."""
        mock_client = MagicMock()
        mock_client.create_transfer.return_value = LedgerResult(
            success=True,
            data=LedgerTransfer(
                id="tr_pending_123",
                source_account_id="acc_user_123",
                destination_account_id="acc_recipient_456",
                amount="1000",
                currency="CREDIT",
                status="pending",
                confirmation_token="ct1_abc123",
                description="Test payment",
                created_at="2026-02-09T12:00:00Z",
            ),
            status_code=201,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transfers",
            json={
                "destination_account_id": "acc_recipient_456",
                "amount": "1.00",
                "require_confirmation": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["confirmation_token"] == "ct1_abc123"

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_transfer_insufficient_funds(
        self, mock_client_class, client, mock_user
    ):
        """Test transfer with insufficient funds."""
        mock_client = MagicMock()
        mock_client.create_transfer.return_value = LedgerResult(
            success=False,
            error="Insufficient funds",
            status_code=422,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transfers",
            json={
                "destination_account_id": "acc_recipient_456",
                "amount": "999999.00",
            },
        )

        assert response.status_code == 422
        assert "Insufficient funds" in response.json()["detail"]

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_transfer_service_error(self, mock_client_class, client, mock_user):
        """Test transfer with service error."""
        mock_client = MagicMock()
        mock_client.create_transfer.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transfers",
            json={
                "destination_account_id": "acc_recipient_456",
                "amount": "1.00",
            },
        )

        assert response.status_code == 502


class TestConfirmTransfer:
    """Tests for POST /accounting/transfers/confirm endpoint."""

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_confirm_transfer_success(self, mock_client_class, client, mock_user):
        """Test successful transfer confirmation."""
        mock_client = MagicMock()
        mock_client.confirm_transfer.return_value = LedgerResult(
            success=True,
            data=LedgerTransfer(
                id="tr_123",
                source_account_id="acc_sender_123",
                destination_account_id="acc_user_123",
                amount="1000",
                currency="CREDIT",
                status="completed",
                confirmation_token=None,
                description="Payment",
                created_at="2026-02-09T12:00:00Z",
                completed_at="2026-02-09T12:01:00Z",
            ),
            status_code=200,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transfers/confirm",
            json={"confirmation_token": "ct1_abc123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tr_123"
        assert data["status"] == "completed"

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_confirm_transfer_not_found(self, mock_client_class, client, mock_user):
        """Test confirming with invalid token."""
        mock_client = MagicMock()
        mock_client.confirm_transfer.return_value = LedgerResult(
            success=False,
            error="Transfer not found or token expired",
            status_code=404,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transfers/confirm",
            json={"confirmation_token": "ct1_invalid"},
        )

        assert response.status_code == 404

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_confirm_transfer_service_error(self, mock_client_class, client, mock_user):
        """Test confirm with service error."""
        mock_client = MagicMock()
        mock_client.confirm_transfer.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post(
            "/api/v1/accounting/transfers/confirm",
            json={"confirmation_token": "ct1_abc123"},
        )

        assert response.status_code == 502


class TestCancelTransfer:
    """Tests for POST /accounting/transfers/{id}/cancel endpoint."""

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_cancel_transfer_success(self, mock_client_class, client, mock_user):
        """Test successful transfer cancellation."""
        mock_client = MagicMock()
        mock_client.cancel_transfer.return_value = LedgerResult(
            success=True,
            data=LedgerTransfer(
                id="tr_123",
                source_account_id="acc_user_123",
                destination_account_id="acc_recipient_456",
                amount="1000",
                currency="CREDIT",
                status="cancelled",
                confirmation_token=None,
                description="Cancelled payment",
                created_at="2026-02-09T12:00:00Z",
            ),
            status_code=200,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transfers/tr_123/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tr_123"
        assert data["status"] == "cancelled"

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_cancel_transfer_not_found(self, mock_client_class, client, mock_user):
        """Test cancelling non-existent transfer."""
        mock_client = MagicMock()
        mock_client.cancel_transfer.return_value = LedgerResult(
            success=False,
            error="Transfer not found",
            status_code=404,
        )
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transfers/invalid-id/cancel")

        assert response.status_code == 404

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_cancel_transfer_service_error(self, mock_client_class, client, mock_user):
        """Test cancel with service error."""
        mock_client = MagicMock()
        mock_client.cancel_transfer.side_effect = Exception("Timeout")
        mock_client_class.return_value = mock_client

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.post("/api/v1/accounting/transfers/tr_123/cancel")

        assert response.status_code == 502


class TestCreateTransactionTokens:
    """Tests for POST /accounting/transaction-tokens endpoint."""

    @pytest.fixture
    def mock_owner_user(self) -> User:
        """Create a mock owner user with ledger account."""
        return User(
            id=2,
            username="owner",
            email="owner@example.com",
            full_name="Owner User",
            age=35,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            accounting_service_url="https://ledger.example.com",
            accounting_api_token="at_owner_token",
            accounting_account_id="acc_owner_456",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_tokens_success(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test successful token creation for single owner."""
        mock_client = MagicMock()
        mock_client.create_transfer.return_value = LedgerResult(
            success=True,
            data=LedgerTransfer(
                id="tr_pending_123",
                source_account_id="acc_user_123",
                destination_account_id="acc_owner_456",
                amount="500",
                currency="CREDIT",
                status="pending",
                confirmation_token="ct1_token_for_owner",
                description="Payment to owner",
                created_at="2026-02-09T12:00:00Z",
            ),
            status_code=201,
        )
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"requests": [{"owner_username": "owner", "amount": "0.50"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "owner" in data["tokens"]
        assert data["tokens"]["owner"]["token"] == "ct1_token_for_owner"
        assert data["tokens"]["owner"]["amount"] == "0.50"
        assert data["tokens"]["owner"]["transfer_id"] == "tr_pending_123"
        assert data["errors"] == {}

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_tokens_multiple_owners(self, mock_client_class, client, mock_user):
        """Test token creation for multiple owners with different amounts."""
        call_count = [0]

        def mock_create_transfer(*args, **kwargs):
            call_count[0] += 1
            return LedgerResult(
                success=True,
                data=LedgerTransfer(
                    id=f"tr_pending_{call_count[0]}",
                    source_account_id="acc_user_123",
                    destination_account_id=kwargs.get("destination_account_id"),
                    amount=kwargs.get("amount"),
                    currency="CREDIT",
                    status="pending",
                    confirmation_token=f"ct1_token_{call_count[0]}",
                    description=kwargs.get("description"),
                    created_at="2026-02-09T12:00:00Z",
                ),
                status_code=201,
            )

        mock_client = MagicMock()
        mock_client.create_transfer.side_effect = mock_create_transfer
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
            accounting_account_id="acc_owner1_456",
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
            accounting_account_id="acc_owner2_789",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_repo = MagicMock()
        mock_repo.get_by_username.side_effect = (
            lambda u: owner1 if u == "owner1" else owner2
        )

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={
                "requests": [
                    {"owner_username": "owner1", "amount": "0.50"},
                    {"owner_username": "owner2", "amount": "1.00"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "owner1" in data["tokens"]
        assert "owner2" in data["tokens"]
        assert data["tokens"]["owner1"]["amount"] == "0.50"
        assert data["tokens"]["owner2"]["amount"] == "1.00"

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
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
            json={"requests": [{"owner_username": "nonexistent", "amount": "1.00"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "nonexistent" in data["errors"]
        assert "not found" in data["errors"]["nonexistent"]

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_tokens_owner_no_account(self, mock_client_class, client, mock_user):
        """Test token creation when owner has no linked ledger account."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Owner without accounting_account_id
        owner_no_account = User(
            id=2,
            username="noaccount",
            email="noaccount@example.com",
            full_name="No Account User",
            age=30,
            role=UserRole.USER,
            password_hash="hash",
            is_active=True,
            accounting_account_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = owner_no_account

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"requests": [{"owner_username": "noaccount", "amount": "1.00"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "noaccount" in data["errors"]
        assert "no linked accounting account" in data["errors"]["noaccount"]

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_tokens_ledger_error(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation with ledger service error."""
        mock_client = MagicMock()
        mock_client.create_transfer.return_value = LedgerResult(
            success=False,
            error="Internal ledger error",
            status_code=500,
        )
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"requests": [{"owner_username": "owner", "amount": "1.00"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "owner" in data["errors"]
        assert "Internal ledger error" in data["errors"]["owner"]

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_tokens_no_confirmation_token(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation when response has no confirmation token."""
        mock_client = MagicMock()
        mock_client.create_transfer.return_value = LedgerResult(
            success=True,
            data=LedgerTransfer(
                id="tr_123",
                source_account_id="acc_user_123",
                destination_account_id="acc_owner_456",
                amount="500",
                currency="CREDIT",
                status="completed",  # Not pending, so no token
                confirmation_token=None,
                description="Payment",
                created_at="2026-02-09T12:00:00Z",
            ),
            status_code=201,
        )
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"requests": [{"owner_username": "owner", "amount": "0.50"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "owner" in data["errors"]
        assert "No confirmation token" in data["errors"]["owner"]

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_tokens_request_exception(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation with request exception."""
        mock_client = MagicMock()
        mock_client.create_transfer.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"requests": [{"owner_username": "owner", "amount": "1.00"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"] == {}
        assert "owner" in data["errors"]
        assert "Request failed" in data["errors"]["owner"]

    @patch("syfthub.api.endpoints.accounting.UnifiedLedgerClient")
    def test_create_tokens_duplicate_owners(
        self, mock_client_class, client, mock_user, mock_owner_user
    ):
        """Test token creation with duplicate owners in request."""
        mock_client = MagicMock()
        mock_client.create_transfer.return_value = LedgerResult(
            success=True,
            data=LedgerTransfer(
                id="tr_pending_123",
                source_account_id="acc_user_123",
                destination_account_id="acc_owner_456",
                amount="500",
                currency="CREDIT",
                status="pending",
                confirmation_token="ct1_token",
                description="Payment",
                created_at="2026-02-09T12:00:00Z",
            ),
            status_code=201,
        )
        mock_client_class.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.get_by_username.return_value = mock_owner_user

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={
                "requests": [
                    {"owner_username": "owner", "amount": "0.50"},
                    {"owner_username": "owner", "amount": "1.00"},
                    {"owner_username": "owner", "amount": "0.25"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Should only have one entry despite duplicates (first one wins)
        assert len(data["tokens"]) == 1
        assert "owner" in data["tokens"]
        # First amount should be used
        assert data["tokens"]["owner"]["amount"] == "0.50"

    def test_create_tokens_accounting_not_configured(
        self, client, mock_user_no_accounting
    ):
        """Test token creation when accounting not configured."""
        app.dependency_overrides[get_current_active_user] = (
            lambda: mock_user_no_accounting
        )

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"requests": [{"owner_username": "owner", "amount": "1.00"}]},
        )

        assert response.status_code == 400
        assert "Accounting not configured" in response.json()["detail"]

    def test_create_tokens_no_account_id(self, client, mock_user_no_account_id):
        """Test token creation when user has no account ID."""
        app.dependency_overrides[get_current_active_user] = (
            lambda: mock_user_no_account_id
        )

        response = client.post(
            "/api/v1/accounting/transaction-tokens",
            json={"requests": [{"owner_username": "owner", "amount": "1.00"}]},
        )

        assert response.status_code == 400
        assert "No accounting account linked" in response.json()["detail"]
