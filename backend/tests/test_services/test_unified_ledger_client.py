"""Tests for UnifiedLedgerClient and provision_ledger_user.

This module tests the Unified Global Ledger integration including:
- User provisioning flow
- Transfer operations
- Token validation
- Error handling
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from syfthub.services.unified_ledger_client import (
    LedgerAccount,
    LedgerBalance,
    LedgerResult,
    LedgerTransfer,
    ProvisionResult,
    UnifiedLedgerClient,
    generate_idempotency_key,
    provision_ledger_user,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def ledger_client():
    """Create UnifiedLedgerClient instance for testing."""
    return UnifiedLedgerClient(
        base_url="https://ledger.example.com",
        api_token="at_test_token_123",
        timeout=10.0,
    )


@pytest.fixture
def mock_provision_response():
    """Mock successful provision response."""
    return {
        "user": {"id": "user-uuid-123", "email": "test@example.com"},
        "account": {"id": "account-uuid-456", "type": "user", "status": "active"},
        "api_token": {"token": "at_new_token_789", "prefix": "at_new_"},
    }


# =============================================================================
# Tests for provision_ledger_user
# =============================================================================


class TestProvisionLedgerUser:
    """Tests for the provision_ledger_user standalone function."""

    def test_successful_provision(self, mock_provision_response):
        """Test successful user provisioning returns correct data."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = mock_provision_response
            mock_client.post.return_value = mock_response

            result = provision_ledger_user(
                base_url="https://ledger.example.com",
                email="test@example.com",
                password="secure_password_123",
            )

            assert result.success is True
            assert result.status_code == 201
            assert isinstance(result.data, ProvisionResult)
            assert result.data.user_id == "user-uuid-123"
            assert result.data.account_id == "account-uuid-456"
            assert result.data.api_token == "at_new_token_789"
            assert result.data.api_token_prefix == "at_new_"

            # Verify the request was made correctly
            mock_client.post.assert_called_once_with(
                "/auth/provision",
                json={"email": "test@example.com", "password": "secure_password_123"},
                headers={"Content-Type": "application/json"},
            )

    def test_provision_email_already_exists(self):
        """Test provisioning with existing email returns 409 conflict."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_response.json.return_value = {"detail": "Email already registered"}
            mock_client.post.return_value = mock_response

            result = provision_ledger_user(
                base_url="https://ledger.example.com",
                email="existing@example.com",
                password="password123",
            )

            assert result.success is False
            assert result.status_code == 409
            assert "already exists" in result.error.lower()

    def test_provision_invalid_request(self):
        """Test provisioning with invalid data returns 400."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"detail": "Invalid email format"}
            mock_response.text = "Invalid email format"
            mock_client.post.return_value = mock_response

            result = provision_ledger_user(
                base_url="https://ledger.example.com",
                email="invalid-email",
                password="password123",
            )

            assert result.success is False
            assert result.status_code == 400
            assert "Invalid email format" in result.error

    def test_provision_timeout_error(self):
        """Test provisioning handles timeout gracefully."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.TimeoutException(
                "Connection timed out"
            )

            result = provision_ledger_user(
                base_url="https://ledger.example.com",
                email="test@example.com",
                password="password123",
                timeout=5.0,
            )

            assert result.success is False
            assert "timed out" in result.error.lower()

    def test_provision_network_error(self):
        """Test provisioning handles network errors gracefully."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.RequestError("Connection refused")

            result = provision_ledger_user(
                base_url="https://ledger.example.com",
                email="test@example.com",
                password="password123",
            )

            assert result.success is False
            assert "connect" in result.error.lower()

    def test_provision_strips_trailing_slash(self, mock_provision_response):
        """Test that trailing slash in base URL is handled correctly."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = mock_provision_response
            mock_client.post.return_value = mock_response

            result = provision_ledger_user(
                base_url="https://ledger.example.com/",  # Trailing slash
                email="test@example.com",
                password="password123",
            )

            assert result.success is True
            # Verify the client was created with stripped URL
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs["base_url"] == "https://ledger.example.com"


# =============================================================================
# Tests for UnifiedLedgerClient
# =============================================================================


class TestUnifiedLedgerClient:
    """Tests for the UnifiedLedgerClient class."""

    def test_init(self, ledger_client):
        """Test client initialization."""
        assert ledger_client.base_url == "https://ledger.example.com"
        assert ledger_client.api_token == "at_test_token_123"
        assert ledger_client.timeout == 10.0
        assert ledger_client._client is None

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base URL."""
        client = UnifiedLedgerClient(
            base_url="https://ledger.example.com/",
            api_token="at_test",
        )
        assert client.base_url == "https://ledger.example.com"

    def test_client_property_lazy_initialization(self, ledger_client):
        """Test that HTTP client is lazily initialized."""
        assert ledger_client._client is None
        http_client = ledger_client.client
        assert http_client is not None
        assert ledger_client._client is http_client

    def test_close_client(self, ledger_client):
        """Test that close() properly closes the HTTP client."""
        # Force client creation
        _ = ledger_client.client
        assert ledger_client._client is not None

        ledger_client.close()
        assert ledger_client._client is None


class TestUnifiedLedgerClientGetBalance:
    """Tests for the get_balance method."""

    def test_get_balance_success(self, ledger_client):
        """Test successful balance retrieval."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "balance": {"amount": "10000", "currency": "CREDIT"},
            "available_balance": {"amount": "9500", "currency": "CREDIT"},
        }
        mock_client.get.return_value = mock_response

        result = ledger_client.get_balance("account-uuid-123")

        assert result.success is True
        assert result.data.balance == "10000"
        assert result.data.available_balance == "9500"
        assert result.data.currency == "CREDIT"

    def test_get_balance_unauthorized(self, ledger_client):
        """Test balance retrieval with invalid token."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid API token"}
        mock_response.text = "Unauthorized"
        mock_client.get.return_value = mock_response

        result = ledger_client.get_balance("account-uuid-123")

        assert result.success is False
        assert result.status_code == 401


class TestUnifiedLedgerClientCreateTransfer:
    """Tests for the create_transfer method."""

    def test_create_transfer_success(self, ledger_client):
        """Test successful transfer creation."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "transfer-uuid-789",
            "source_account_id": "account-123",
            "destination_account_id": "account-456",
            "amount": {"amount": "1000", "currency": "CREDIT"},
            "status": "completed",
            "confirmation_token": None,
            "description": "Payment",
            "created_at": "2026-02-09T12:00:00Z",
        }
        mock_client.post.return_value = mock_response

        result = ledger_client.create_transfer(
            source_account_id="account-123",
            destination_account_id="account-456",
            amount="1",  # $1 = 1000 credits
            description="Payment",
        )

        assert result.success is True
        assert result.data.id == "transfer-uuid-789"
        assert result.data.status == "completed"

    def test_create_transfer_with_confirmation(self, ledger_client):
        """Test transfer creation with confirmation token."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "transfer-uuid-789",
            "source_account_id": "account-123",
            "destination_account_id": "account-456",
            "amount": {"amount": "1000", "currency": "CREDIT"},
            "status": "pending",
            "confirmation_token": "ct1_encodedtoken",
            "description": "Payment",
            "created_at": "2026-02-09T12:00:00Z",
        }
        mock_client.post.return_value = mock_response

        result = ledger_client.create_transfer(
            source_account_id="account-123",
            destination_account_id="account-456",
            amount="1",
            require_confirmation=True,
        )

        assert result.success is True
        assert result.data.status == "pending"
        assert result.data.confirmation_token == "ct1_encodedtoken"

    def test_create_transfer_insufficient_funds(self, ledger_client):
        """Test transfer with insufficient funds."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {"detail": "Insufficient funds"}
        mock_response.text = "Insufficient funds"
        mock_client.post.return_value = mock_response

        result = ledger_client.create_transfer(
            source_account_id="account-123",
            destination_account_id="account-456",
            amount="999999999",
        )

        assert result.success is False
        assert result.status_code == 422
        assert "insufficient" in result.error.lower()


class TestUnifiedLedgerClientConfirmTransfer:
    """Tests for the confirm_transfer method."""

    def test_confirm_transfer_success(self, ledger_client):
        """Test successful transfer confirmation."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "transfer-uuid-789",
            "source_account_id": "account-123",
            "destination_account_id": "account-456",
            "amount": {"amount": "1000", "currency": "CREDIT"},
            "status": "completed",
            "confirmation_token": None,
            "description": "Payment",
            "created_at": "2026-02-09T12:00:00Z",
            "completed_at": "2026-02-09T12:01:00Z",
        }
        mock_client.post.return_value = mock_response

        result = ledger_client.confirm_transfer("ct1_confirmation_token")

        assert result.success is True
        assert result.data.id == "transfer-uuid-789"
        assert result.data.status == "completed"

    def test_confirm_transfer_invalid_token(self, ledger_client):
        """Test confirmation with invalid token."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "detail": "Transfer not found or token expired"
        }
        mock_response.text = "Not found"
        mock_client.post.return_value = mock_response

        result = ledger_client.confirm_transfer("ct1_invalid_token")

        assert result.success is False
        assert result.status_code == 404


class TestUnifiedLedgerClientCancelTransfer:
    """Tests for the cancel_transfer method."""

    def test_cancel_transfer_success(self, ledger_client):
        """Test successful transfer cancellation."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "transfer-uuid-789",
            "source_account_id": "account-123",
            "destination_account_id": "account-456",
            "amount": {"amount": "1000", "currency": "CREDIT"},
            "status": "cancelled",
            "confirmation_token": None,
            "description": "Payment",
            "created_at": "2026-02-09T12:00:00Z",
        }
        mock_client.post.return_value = mock_response

        result = ledger_client.cancel_transfer("transfer-uuid-789")

        assert result.success is True
        assert result.data.id == "transfer-uuid-789"
        assert result.data.status == "cancelled"

    def test_cancel_transfer_not_found(self, ledger_client):
        """Test cancellation of non-existent transfer."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Transfer not found"}
        mock_response.text = "Not found"
        mock_client.post.return_value = mock_response

        result = ledger_client.cancel_transfer("invalid-transfer-id")

        assert result.success is False
        assert result.status_code == 404


class TestUnifiedLedgerClientValidateToken:
    """Tests for the validate_token method."""

    def test_validate_token_success(self, ledger_client):
        """Test successful token validation."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "valid": True,
            "token_prefix": "at_test_",
            "expires_at": None,
        }
        mock_client.get.return_value = mock_response

        result = ledger_client.validate_token()

        assert result.success is True

    def test_validate_token_invalid(self, ledger_client):
        """Test validation with invalid token."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid or expired API token"}
        mock_response.text = "Unauthorized"
        mock_client.get.return_value = mock_response

        result = ledger_client.validate_token()

        assert result.success is False
        assert result.status_code == 401


class TestUnifiedLedgerClientCreateAccount:
    """Tests for the create_account method."""

    def test_create_account_success(self, ledger_client):
        """Test successful account creation."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "account-uuid-new",
            "type": "user",
            "status": "active",
            "balance": "0",
            "available_balance": "0",
            "currency": "CREDIT",
            "created_at": "2026-02-09T12:00:00Z",
        }
        mock_client.post.return_value = mock_response

        result = ledger_client.create_account(account_type="user")

        assert result.success is True
        assert result.data.id == "account-uuid-new"
        assert result.status_code == 201

    def test_create_account_with_metadata(self, ledger_client):
        """Test account creation with metadata."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "account-uuid-new",
            "type": "user",
            "status": "active",
            "balance": "0",
            "available_balance": "0",
            "currency": "CREDIT",
            "metadata": {"user_id": "123"},
            "created_at": "2026-02-09T12:00:00Z",
        }
        mock_client.post.return_value = mock_response

        result = ledger_client.create_account(
            account_type="user",
            metadata={"user_id": "123"},
        )

        assert result.success is True
        assert result.data.metadata == {"user_id": "123"}

    def test_create_account_error(self, ledger_client):
        """Test account creation failure."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid account type"}
        mock_response.text = "Bad request"
        mock_client.post.return_value = mock_response

        result = ledger_client.create_account(account_type="invalid")

        assert result.success is False
        assert result.status_code == 400

    def test_create_account_timeout(self, ledger_client):
        """Test account creation timeout."""
        import httpx

        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")

        result = ledger_client.create_account()

        assert result.success is False
        assert "timed out" in result.error.lower()


class TestUnifiedLedgerClientGetAccount:
    """Tests for the get_account method."""

    def test_get_account_success(self, ledger_client):
        """Test successful account retrieval."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "account-uuid-123",
            "name": "Test Account",
            "type": "personal",
            "created_at": "2026-02-09T12:00:00Z",
        }
        mock_client.get.return_value = mock_response

        result = ledger_client.get_account("account-uuid-123")

        assert result.success is True

    def test_get_account_not_found(self, ledger_client):
        """Test account retrieval for non-existent account."""
        mock_client = MagicMock()
        ledger_client._client = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Account not found"}
        mock_response.text = "Not found"
        mock_client.get.return_value = mock_response

        result = ledger_client.get_account("invalid-account-id")

        assert result.success is False
        assert result.status_code == 404


class TestUnifiedLedgerClientNetworkErrors:
    """Tests for network error handling."""

    def test_get_balance_timeout(self, ledger_client):
        """Test balance retrieval with timeout."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

        result = ledger_client.get_balance("account-123")

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_get_balance_network_error(self, ledger_client):
        """Test balance retrieval with network error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.get.side_effect = httpx.RequestError("Connection refused")

        result = ledger_client.get_balance("account-123")

        assert result.success is False
        assert "connect" in result.error.lower()

    def test_get_balance_unexpected_error(self, ledger_client):
        """Test balance retrieval with unexpected error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.get.side_effect = RuntimeError("Unexpected failure")

        result = ledger_client.get_balance("account-123")

        assert result.success is False
        assert "unexpected" in result.error.lower()

    def test_create_transfer_timeout(self, ledger_client):
        """Test transfer creation with timeout."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")

        result = ledger_client.create_transfer(
            source_account_id="acc-123",
            destination_account_id="acc-456",
            amount="100",
        )

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_create_transfer_network_error(self, ledger_client):
        """Test transfer creation with network error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = httpx.RequestError("Connection refused")

        result = ledger_client.create_transfer(
            source_account_id="acc-123",
            destination_account_id="acc-456",
            amount="100",
        )

        assert result.success is False
        assert "connect" in result.error.lower()

    def test_create_transfer_unexpected_error(self, ledger_client):
        """Test transfer creation with unexpected error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = RuntimeError("Unexpected failure")

        result = ledger_client.create_transfer(
            source_account_id="acc-123",
            destination_account_id="acc-456",
            amount="100",
        )

        assert result.success is False
        assert "unexpected" in result.error.lower()

    def test_confirm_transfer_timeout(self, ledger_client):
        """Test transfer confirmation with timeout."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")

        result = ledger_client.confirm_transfer("ct1_token")

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_confirm_transfer_network_error(self, ledger_client):
        """Test transfer confirmation with network error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = httpx.RequestError("Connection refused")

        result = ledger_client.confirm_transfer("ct1_token")

        assert result.success is False
        assert "connect" in result.error.lower()

    def test_confirm_transfer_unexpected_error(self, ledger_client):
        """Test transfer confirmation with unexpected error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = RuntimeError("Unexpected failure")

        result = ledger_client.confirm_transfer("ct1_token")

        assert result.success is False
        assert "unexpected" in result.error.lower()

    def test_cancel_transfer_timeout(self, ledger_client):
        """Test transfer cancellation with timeout."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")

        result = ledger_client.cancel_transfer("transfer-123")

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_cancel_transfer_network_error(self, ledger_client):
        """Test transfer cancellation with network error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = httpx.RequestError("Connection refused")

        result = ledger_client.cancel_transfer("transfer-123")

        assert result.success is False
        assert "connect" in result.error.lower()

    def test_cancel_transfer_unexpected_error(self, ledger_client):
        """Test transfer cancellation with unexpected error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = RuntimeError("Unexpected failure")

        result = ledger_client.cancel_transfer("transfer-123")

        assert result.success is False
        assert "unexpected" in result.error.lower()

    def test_validate_token_timeout(self, ledger_client):
        """Test token validation with timeout."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

        result = ledger_client.validate_token()

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_validate_token_network_error(self, ledger_client):
        """Test token validation with network error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.get.side_effect = httpx.RequestError("Connection refused")

        result = ledger_client.validate_token()

        assert result.success is False
        assert "connect" in result.error.lower()

    def test_get_account_timeout(self, ledger_client):
        """Test account retrieval with timeout."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

        result = ledger_client.get_account("account-123")

        assert result.success is False
        assert "timed out" in result.error.lower()

    def test_get_account_network_error(self, ledger_client):
        """Test account retrieval with network error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.get.side_effect = httpx.RequestError("Connection refused")

        result = ledger_client.get_account("account-123")

        assert result.success is False
        assert "connect" in result.error.lower()

    def test_get_account_unexpected_error(self, ledger_client):
        """Test account retrieval with unexpected error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.get.side_effect = RuntimeError("Unexpected failure")

        result = ledger_client.get_account("account-123")

        assert result.success is False
        assert "unexpected" in result.error.lower()

    def test_create_account_network_error(self, ledger_client):
        """Test account creation with network error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = httpx.RequestError("Connection refused")

        result = ledger_client.create_account()

        assert result.success is False
        assert "connect" in result.error.lower()

    def test_create_account_unexpected_error(self, ledger_client):
        """Test account creation with unexpected error."""
        mock_client = MagicMock()
        ledger_client._client = mock_client
        mock_client.post.side_effect = RuntimeError("Unexpected failure")

        result = ledger_client.create_account()

        assert result.success is False
        assert "unexpected" in result.error.lower()


class TestErrorDetailExtraction:
    """Tests for error detail extraction from responses."""

    def test_extract_detail_field(self, ledger_client):
        """Test extraction of 'detail' field from error response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"detail": "Not found"}

        error = ledger_client._extract_error_detail(mock_response)

        assert error == "Not found"

    def test_extract_title_field(self, ledger_client):
        """Test extraction of 'title' field from error response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"title": "Bad Request"}

        error = ledger_client._extract_error_detail(mock_response)

        assert error == "Bad Request"

    def test_extract_message_field(self, ledger_client):
        """Test extraction of 'message' field from error response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": "Invalid input"}

        error = ledger_client._extract_error_detail(mock_response)

        assert error == "Invalid input"

    def test_extract_json_parse_error(self, ledger_client):
        """Test fallback when JSON parsing fails."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        error = ledger_client._extract_error_detail(mock_response)

        assert "HTTP 500" in error
        assert "Internal Server Error" in error


# =============================================================================
# Tests for Dataclasses and Helpers
# =============================================================================


class TestGenerateIdempotencyKey:
    """Tests for the generate_idempotency_key helper."""

    def test_generates_uuid_format(self):
        """Test that idempotency key is UUID format."""
        key = generate_idempotency_key()
        # UUID4 format: 8-4-4-4-12 hex chars
        parts = key.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4

    def test_generates_unique_keys(self):
        """Test that keys are unique."""
        keys = {generate_idempotency_key() for _ in range(100)}
        assert len(keys) == 100


class TestLedgerBalance:
    """Tests for the LedgerBalance dataclass."""

    def test_ledger_balance_creation(self):
        """Test LedgerBalance creation."""
        balance = LedgerBalance(
            account_id="acc-123",
            balance="10000",
            available_balance="9500",
            currency="CREDIT",
        )
        assert balance.account_id == "acc-123"
        assert balance.balance == "10000"
        assert balance.available_balance == "9500"
        assert balance.currency == "CREDIT"


class TestLedgerTransfer:
    """Tests for the LedgerTransfer dataclass."""

    def test_ledger_transfer_creation(self):
        """Test LedgerTransfer creation with all fields."""
        transfer = LedgerTransfer(
            id="tr-123",
            source_account_id="acc-1",
            destination_account_id="acc-2",
            amount="1000",
            currency="CREDIT",
            status="completed",
            confirmation_token=None,
            description="Test transfer",
            created_at="2026-02-09T12:00:00Z",
            completed_at="2026-02-09T12:01:00Z",
        )
        assert transfer.id == "tr-123"
        assert transfer.status == "completed"
        assert transfer.completed_at == "2026-02-09T12:01:00Z"

    def test_ledger_transfer_pending(self):
        """Test LedgerTransfer with pending status."""
        transfer = LedgerTransfer(
            id="tr-456",
            source_account_id="acc-1",
            destination_account_id="acc-2",
            amount="500",
            currency="CREDIT",
            status="pending",
            confirmation_token="ct1_abc",
        )
        assert transfer.status == "pending"
        assert transfer.confirmation_token == "ct1_abc"
        assert transfer.completed_at is None


class TestLedgerAccount:
    """Tests for the LedgerAccount dataclass."""

    def test_ledger_account_creation(self):
        """Test LedgerAccount creation."""
        account = LedgerAccount(
            id="acc-789",
            type="user",
            status="active",
            balance="5000",
            available_balance="4500",
            currency="CREDIT",
            metadata={"user_id": "123"},
            created_at="2026-02-09T12:00:00Z",
            updated_at="2026-02-09T12:30:00Z",
        )
        assert account.id == "acc-789"
        assert account.type == "user"
        assert account.metadata == {"user_id": "123"}


class TestLedgerResult:
    """Tests for the LedgerResult dataclass."""

    def test_ledger_result_success(self):
        """Test successful LedgerResult."""
        result = LedgerResult(
            success=True,
            data={"id": "123"},
            status_code=200,
        )
        assert result.success is True
        assert result.data == {"id": "123"}
        assert result.error is None

    def test_ledger_result_error(self):
        """Test error LedgerResult."""
        result = LedgerResult(
            success=False,
            error="Not found",
            status_code=404,
        )
        assert result.success is False
        assert result.error == "Not found"
        assert result.data is None


class TestProvisionResult:
    """Tests for the ProvisionResult dataclass."""

    def test_provision_result_frozen(self):
        """Test that ProvisionResult is immutable."""
        result = ProvisionResult(
            user_id="user-123",
            account_id="account-456",
            api_token="at_token",
            api_token_prefix="at_",
        )

        with pytest.raises(AttributeError):
            result.user_id = "new-id"

    def test_provision_result_equality(self):
        """Test ProvisionResult equality comparison."""
        result1 = ProvisionResult(
            user_id="user-123",
            account_id="account-456",
            api_token="at_token",
            api_token_prefix="at_",
        )
        result2 = ProvisionResult(
            user_id="user-123",
            account_id="account-456",
            api_token="at_token",
            api_token_prefix="at_",
        )

        assert result1 == result2
