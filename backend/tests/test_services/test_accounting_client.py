"""Tests for AccountingClient."""

import string
from unittest.mock import MagicMock

import httpx
import pytest

from syfthub.services.accounting_client import (
    AccountingClient,
    AccountingUser,
    AccountingUserResult,
    generate_accounting_password,
)


class TestGenerateAccountingPassword:
    """Tests for generate_accounting_password function."""

    def test_default_length(self):
        """Test password has default length of 32."""
        password = generate_accounting_password()
        assert len(password) == 32

    def test_custom_length(self):
        """Test password with custom length."""
        password = generate_accounting_password(length=16)
        assert len(password) == 16

    def test_contains_lowercase(self):
        """Test password contains at least one lowercase letter."""
        password = generate_accounting_password()
        assert any(c in string.ascii_lowercase for c in password)

    def test_contains_uppercase(self):
        """Test password contains at least one uppercase letter."""
        password = generate_accounting_password()
        assert any(c in string.ascii_uppercase for c in password)

    def test_contains_digit(self):
        """Test password contains at least one digit."""
        password = generate_accounting_password()
        assert any(c in string.digits for c in password)

    def test_contains_special(self):
        """Test password contains at least one special character."""
        password = generate_accounting_password()
        assert any(c in "!@#$%^&*" for c in password)

    def test_uniqueness(self):
        """Test passwords are unique."""
        passwords = [generate_accounting_password() for _ in range(10)]
        assert len(set(passwords)) == 10


class TestAccountingClient:
    """Tests for AccountingClient class."""

    @pytest.fixture
    def client(self):
        """Create AccountingClient instance for testing."""
        return AccountingClient("https://accounting.example.com", timeout=10.0)

    def test_init(self, client):
        """Test client initialization."""
        assert client.base_url == "https://accounting.example.com"
        assert client.timeout == 10.0
        assert client._client is None

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base URL."""
        client = AccountingClient("https://accounting.example.com/")
        assert client.base_url == "https://accounting.example.com"

    def test_client_property_lazy_initialization(self, client):
        """Test that HTTP client is lazily initialized."""
        assert client._client is None
        http_client = client.client
        assert http_client is not None
        assert client._client is http_client

    def test_client_property_returns_same_instance(self, client):
        """Test that client property returns same instance."""
        http_client1 = client.client
        http_client2 = client.client
        assert http_client1 is http_client2
        client.close()

    def test_close(self, client):
        """Test client close releases resources."""
        _ = client.client  # Initialize
        client.close()
        assert client._client is None

    def test_close_when_not_initialized(self, client):
        """Test close when client was never initialized."""
        client.close()  # Should not raise
        assert client._client is None

    def test_context_manager(self):
        """Test context manager protocol."""
        with AccountingClient("https://accounting.example.com") as client:
            assert client is not None
        # Client should be closed after context exit
        assert client._client is None


class TestAccountingClientCreateUser:
    """Tests for AccountingClient.create_user method."""

    @pytest.fixture
    def client(self):
        """Create AccountingClient instance for testing."""
        return AccountingClient("https://accounting.example.com")

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client."""
        return MagicMock(spec=httpx.Client)

    def test_create_user_success(self, client, mock_http_client):
        """Test successful user creation."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "user": {
                "id": "user-123",
                "email": "test@example.com",
                "balance": 100.0,
                "organization": "test-org",
            }
        }
        mock_http_client.post.return_value = mock_response
        client._client = mock_http_client

        result = client.create_user("test@example.com", "password123", "test-org")

        assert result.success is True
        assert result.conflict is False
        assert result.error is None
        assert result.user is not None
        assert result.user.id == "user-123"
        assert result.user.email == "test@example.com"
        assert result.user.balance == 100.0
        assert result.user.organization == "test-org"

        mock_http_client.post.assert_called_once_with(
            "/user/create",
            json={
                "email": "test@example.com",
                "password": "password123",
                "organization": "test-org",
            },
        )

    def test_create_user_success_without_organization(self, client, mock_http_client):
        """Test successful user creation without organization."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "user-456",
            "email": "test@example.com",
            "balance": 0.0,
        }
        mock_http_client.post.return_value = mock_response
        client._client = mock_http_client

        result = client.create_user("test@example.com", "password123")

        assert result.success is True
        assert result.user is not None
        assert result.user.id == "user-456"
        assert result.user.organization is None

        mock_http_client.post.assert_called_once_with(
            "/user/create",
            json={"email": "test@example.com", "password": "password123"},
        )

    def test_create_user_conflict(self, client, mock_http_client):
        """Test user creation with existing email (409 conflict)."""
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_http_client.post.return_value = mock_response
        client._client = mock_http_client

        result = client.create_user("existing@example.com", "password123")

        assert result.success is False
        assert result.conflict is True
        assert "already exists" in result.error

    def test_create_user_other_error(self, client, mock_http_client):
        """Test user creation with other HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid email format"}
        mock_http_client.post.return_value = mock_response
        client._client = mock_http_client

        result = client.create_user("invalid", "password123")

        assert result.success is False
        assert result.conflict is False
        assert "Invalid email format" in result.error

    def test_create_user_timeout(self, client, mock_http_client):
        """Test user creation with timeout."""
        mock_http_client.post.side_effect = httpx.TimeoutException(
            "Connection timed out"
        )
        client._client = mock_http_client

        result = client.create_user("test@example.com", "password123")

        assert result.success is False
        assert "timed out" in result.error

    def test_create_user_network_error(self, client, mock_http_client):
        """Test user creation with network error."""
        mock_http_client.post.side_effect = httpx.RequestError("Connection refused")
        client._client = mock_http_client

        result = client.create_user("test@example.com", "password123")

        assert result.success is False
        assert "Failed to connect" in result.error

    def test_create_user_unexpected_error(self, client, mock_http_client):
        """Test user creation with unexpected error."""
        mock_http_client.post.side_effect = ValueError("Unexpected error")
        client._client = mock_http_client

        result = client.create_user("test@example.com", "password123")

        assert result.success is False
        assert "Unexpected error" in result.error


class TestAccountingClientValidateCredentials:
    """Tests for AccountingClient.validate_credentials method."""

    @pytest.fixture
    def client(self):
        """Create AccountingClient instance for testing."""
        return AccountingClient("https://accounting.example.com")

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client."""
        return MagicMock(spec=httpx.Client)

    def test_validate_credentials_success(self, client, mock_http_client):
        """Test successful credential validation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_client.get.return_value = mock_response
        client._client = mock_http_client

        result = client.validate_credentials("test@example.com", "password123")

        assert result is True
        mock_http_client.get.assert_called_once_with(
            "/user/my-info",
            auth=("test@example.com", "password123"),
        )

    def test_validate_credentials_invalid(self, client, mock_http_client):
        """Test invalid credential validation."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_http_client.get.return_value = mock_response
        client._client = mock_http_client

        result = client.validate_credentials("test@example.com", "wrong-password")

        assert result is False

    def test_validate_credentials_timeout(self, client, mock_http_client):
        """Test credential validation with timeout."""
        mock_http_client.get.side_effect = httpx.TimeoutException(
            "Connection timed out"
        )
        client._client = mock_http_client

        result = client.validate_credentials("test@example.com", "password123")

        assert result is False

    def test_validate_credentials_network_error(self, client, mock_http_client):
        """Test credential validation with network error."""
        mock_http_client.get.side_effect = httpx.RequestError("Connection refused")
        client._client = mock_http_client

        result = client.validate_credentials("test@example.com", "password123")

        assert result is False

    def test_validate_credentials_unexpected_error(self, client, mock_http_client):
        """Test credential validation with unexpected error."""
        mock_http_client.get.side_effect = ValueError("Unexpected error")
        client._client = mock_http_client

        result = client.validate_credentials("test@example.com", "password123")

        assert result is False


class TestAccountingClientGetUser:
    """Tests for AccountingClient.get_user method."""

    @pytest.fixture
    def client(self):
        """Create AccountingClient instance for testing."""
        return AccountingClient("https://accounting.example.com")

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client."""
        return MagicMock(spec=httpx.Client)

    def test_get_user_success(self, client, mock_http_client):
        """Test successful get user."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "user-123",
            "email": "test@example.com",
            "balance": 50.0,
            "organization": "my-org",
        }
        mock_http_client.get.return_value = mock_response
        client._client = mock_http_client

        result = client.get_user("test@example.com", "password123")

        assert result is not None
        assert result.id == "user-123"
        assert result.email == "test@example.com"
        assert result.balance == 50.0
        assert result.organization == "my-org"

    def test_get_user_invalid_credentials(self, client, mock_http_client):
        """Test get user with invalid credentials."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_http_client.get.return_value = mock_response
        client._client = mock_http_client

        result = client.get_user("test@example.com", "wrong-password")

        assert result is None

    def test_get_user_error(self, client, mock_http_client):
        """Test get user with error."""
        mock_http_client.get.side_effect = Exception("Some error")
        client._client = mock_http_client

        result = client.get_user("test@example.com", "password123")

        assert result is None


class TestAccountingClientParseUserResponse:
    """Tests for AccountingClient._parse_user_response method."""

    @pytest.fixture
    def client(self):
        """Create AccountingClient instance for testing."""
        return AccountingClient("https://accounting.example.com")

    def test_parse_nested_user_response(self, client):
        """Test parsing response with nested user object."""
        data = {
            "user": {
                "id": "user-123",
                "email": "test@example.com",
                "balance": 100.0,
                "organization": "my-org",
            }
        }

        result = client._parse_user_response(data)

        assert result.id == "user-123"
        assert result.email == "test@example.com"
        assert result.balance == 100.0
        assert result.organization == "my-org"

    def test_parse_flat_user_response(self, client):
        """Test parsing response with flat structure."""
        data = {
            "id": "user-456",
            "email": "flat@example.com",
            "balance": 50.0,
        }

        result = client._parse_user_response(data)

        assert result.id == "user-456"
        assert result.email == "flat@example.com"
        assert result.balance == 50.0
        assert result.organization is None

    def test_parse_missing_fields(self, client):
        """Test parsing response with missing optional fields."""
        data = {}

        result = client._parse_user_response(data)

        assert result.id == ""
        assert result.email == ""
        assert result.balance == 0.0
        assert result.organization is None


class TestAccountingClientExtractErrorDetail:
    """Tests for AccountingClient._extract_error_detail method."""

    @pytest.fixture
    def client(self):
        """Create AccountingClient instance for testing."""
        return AccountingClient("https://accounting.example.com")

    def test_extract_detail_field(self, client):
        """Test extracting 'detail' field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"detail": "Validation error"}

        result = client._extract_error_detail(mock_response)

        assert result == "Validation error"

    def test_extract_message_field(self, client):
        """Test extracting 'message' field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": "Something went wrong"}

        result = client._extract_error_detail(mock_response)

        assert result == "Something went wrong"

    def test_extract_error_field(self, client):
        """Test extracting 'error' field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "Bad request"}

        result = client._extract_error_detail(mock_response)

        assert result == "Bad request"

    def test_extract_fallback_to_str(self, client):
        """Test fallback to string conversion."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"unknown_field": "value"}

        result = client._extract_error_detail(mock_response)

        assert "unknown_field" in result

    def test_extract_non_dict_response(self, client):
        """Test with non-dict JSON response."""
        mock_response = MagicMock()
        mock_response.json.return_value = "Error string"

        result = client._extract_error_detail(mock_response)

        assert result == "Error string"

    def test_extract_json_decode_error(self, client):
        """Test when JSON decoding fails."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("JSON decode error")
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        result = client._extract_error_detail(mock_response)

        assert "HTTP 500" in result
        assert "Internal Server Error" in result


class TestAccountingUserDataclasses:
    """Tests for AccountingUser and AccountingUserResult dataclasses."""

    def test_accounting_user_creation(self):
        """Test AccountingUser dataclass creation."""
        user = AccountingUser(
            id="123",
            email="test@example.com",
            balance=100.0,
            organization="test-org",
        )

        assert user.id == "123"
        assert user.email == "test@example.com"
        assert user.balance == 100.0
        assert user.organization == "test-org"

    def test_accounting_user_without_organization(self):
        """Test AccountingUser without organization."""
        user = AccountingUser(
            id="123",
            email="test@example.com",
            balance=0.0,
        )

        assert user.organization is None

    def test_accounting_user_frozen(self):
        """Test AccountingUser is immutable (frozen)."""
        user = AccountingUser(id="123", email="test@example.com", balance=0.0)

        with pytest.raises(AttributeError):
            user.email = "new@example.com"  # type: ignore[misc]

    def test_accounting_user_result_success(self):
        """Test AccountingUserResult for successful operation."""
        user = AccountingUser(id="123", email="test@example.com", balance=0.0)
        result = AccountingUserResult(success=True, user=user)

        assert result.success is True
        assert result.user is user
        assert result.conflict is False
        assert result.error is None

    def test_accounting_user_result_conflict(self):
        """Test AccountingUserResult for conflict."""
        result = AccountingUserResult(
            success=False,
            conflict=True,
            error="User already exists",
        )

        assert result.success is False
        assert result.user is None
        assert result.conflict is True
        assert result.error == "User already exists"

    def test_accounting_user_result_error(self):
        """Test AccountingUserResult for other errors."""
        result = AccountingUserResult(
            success=False,
            error="Network error",
        )

        assert result.success is False
        assert result.user is None
        assert result.conflict is False
        assert result.error == "Network error"
