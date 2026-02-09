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
    ProvisionResult,
    UnifiedLedgerClient,
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
        with patch.object(ledger_client, "client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "balance": "10000",
                "available_balance": "9500",
                "currency": "CREDIT",
            }
            mock_client.get.return_value = mock_response

            result = ledger_client.get_balance("account-uuid-123")

            assert result.success is True
            assert result.data.balance == "10000"
            assert result.data.available_balance == "9500"
            assert result.data.currency == "CREDIT"

    def test_get_balance_unauthorized(self, ledger_client):
        """Test balance retrieval with invalid token."""
        with patch.object(ledger_client, "client") as mock_client:
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
        with patch.object(ledger_client, "client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "id": "transfer-uuid-789",
                "source_account_id": "account-123",
                "destination_account_id": "account-456",
                "amount": "1000",
                "currency": "CREDIT",
                "status": "completed",
                "confirmation_token": None,
                "description": "Payment",
                "created_at": "2026-02-09T12:00:00Z",
            }
            mock_client.post.return_value = mock_response

            result = ledger_client.create_transfer(
                source_account_id="account-123",
                destination_account_id="account-456",
                amount="1000",
                description="Payment",
            )

            assert result.success is True
            assert result.data.id == "transfer-uuid-789"
            assert result.data.status == "completed"

    def test_create_transfer_with_confirmation(self, ledger_client):
        """Test transfer creation with confirmation token."""
        with patch.object(ledger_client, "client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "id": "transfer-uuid-789",
                "source_account_id": "account-123",
                "destination_account_id": "account-456",
                "amount": "1000",
                "currency": "CREDIT",
                "status": "pending",
                "confirmation_token": "ct1_encodedtoken",
                "description": "Payment",
                "created_at": "2026-02-09T12:00:00Z",
            }
            mock_client.post.return_value = mock_response

            result = ledger_client.create_transfer(
                source_account_id="account-123",
                destination_account_id="account-456",
                amount="1000",
                require_confirmation=True,
            )

            assert result.success is True
            assert result.data.status == "pending"
            assert result.data.confirmation_token == "ct1_encodedtoken"

    def test_create_transfer_insufficient_funds(self, ledger_client):
        """Test transfer with insufficient funds."""
        with patch.object(ledger_client, "client") as mock_client:
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


# =============================================================================
# Tests for ProvisionResult
# =============================================================================


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
