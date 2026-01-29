"""Tests for TunnelClient and tunnel utilities."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from aggregator.clients.tunnel import (
    TUNNELING_PREFIX,
    TunnelClient,
    extract_tunnel_username,
    is_tunneled_url,
)
from aggregator.schemas.internal import RetrievalResult
from aggregator.schemas.responses import Document


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestIsTunneledUrl:
    """Tests for is_tunneled_url utility."""

    def test_tunneled_url_returns_true(self):
        """Test that tunneling: prefix is detected."""
        assert is_tunneled_url("tunneling:alice") is True
        assert is_tunneled_url("tunneling:bob123") is True

    def test_non_tunneled_url_returns_false(self):
        """Test that regular URLs return False."""
        assert is_tunneled_url("http://localhost:8080") is False
        assert is_tunneled_url("https://api.example.com") is False
        assert is_tunneled_url("") is False

    def test_partial_prefix_returns_false(self):
        """Test that partial prefix doesn't match."""
        assert is_tunneled_url("tunnel:alice") is False
        assert is_tunneled_url("tunnelingalice") is False


class TestExtractTunnelUsername:
    """Tests for extract_tunnel_username utility."""

    def test_extract_valid_username(self):
        """Test extracting username from tunneling URL."""
        assert extract_tunnel_username("tunneling:alice") == "alice"
        assert extract_tunnel_username("tunneling:bob_123") == "bob_123"

    def test_extract_from_non_tunneled_raises(self):
        """Test that non-tunneled URL raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            extract_tunnel_username("http://localhost:8080")
        assert "Not a tunneling URL" in str(exc_info.value)


# =============================================================================
# TunnelClient Tests
# =============================================================================


@pytest.fixture
def mock_syfthub_client():
    """Create a mock SyftHubClient."""
    client = MagicMock()
    client.mq = MagicMock()
    client.mq.publish = MagicMock()
    client.mq.consume = MagicMock()
    return client


@pytest.fixture
def tunnel_client(mock_syfthub_client):
    """Create a TunnelClient with mocked SyftHubClient."""
    return TunnelClient(
        syfthub_client=mock_syfthub_client,
        response_queue_id="rq_test123",
        response_queue_token="test_token",
        timeout=5.0,
    )


class TestTunnelClientInit:
    """Tests for TunnelClient initialization."""

    def test_init_with_defaults(self, mock_syfthub_client):
        """Test initialization with default timeout."""
        client = TunnelClient(
            syfthub_client=mock_syfthub_client,
            response_queue_id="rq_abc",
            response_queue_token="token",
        )
        assert client.timeout == TunnelClient.DEFAULT_TIMEOUT
        assert client.response_queue_id == "rq_abc"

    def test_init_with_custom_timeout(self, mock_syfthub_client):
        """Test initialization with custom timeout."""
        client = TunnelClient(
            syfthub_client=mock_syfthub_client,
            response_queue_id="rq_abc",
            response_queue_token="token",
            timeout=60.0,
        )
        assert client.timeout == 60.0


class TestQueryDataSource:
    """Tests for query_data_source method."""

    @pytest.mark.asyncio
    async def test_query_data_source_success(self, tunnel_client: TunnelClient):
        """Test successful data source query via tunnel."""
        # Patch _wait_for_response to return a valid response
        async def mock_wait(correlation_id):
            return {
                "protocol": "syfthub-tunnel/v1",
                "type": "endpoint_response",
                "correlation_id": correlation_id,
                "status": "success",
                "payload": {
                    "references": {
                        "documents": [
                            {
                                "content": "Test document content",
                                "similarity_score": 0.95,
                                "metadata": {"source": "test.txt"},
                            }
                        ]
                    }
                },
            }

        async def mock_to_thread(func, *args, **kwargs):
            # For publish, just return None
            return None

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            with patch.object(tunnel_client, "_wait_for_response", mock_wait):
                result = await tunnel_client.query_data_source(
                    target_username="alice",
                    slug="my-datasource",
                    endpoint_path="alice/my-datasource",
                    query="What is the answer?",
                    top_k=5,
                    similarity_threshold=0.5,
                )

        assert isinstance(result, RetrievalResult)
        assert result.status == "success"
        assert len(result.documents) == 1
        assert result.documents[0].content == "Test document content"
        assert result.documents[0].score == 0.95

    @pytest.mark.asyncio
    async def test_query_data_source_timeout(self, tunnel_client: TunnelClient):
        """Test data source query timeout."""
        async def mock_wait(correlation_id):
            return None  # Timeout

        async def mock_to_thread(func, *args, **kwargs):
            return None

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            with patch.object(tunnel_client, "_wait_for_response", mock_wait):
                result = await tunnel_client.query_data_source(
                    target_username="alice",
                    slug="slow-datasource",
                    endpoint_path="alice/slow-datasource",
                    query="test",
                )

        assert result.status == "timeout"
        assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_query_data_source_error_response(self, tunnel_client: TunnelClient):
        """Test handling of error response from endpoint."""
        async def mock_wait(correlation_id):
            return {
                "protocol": "syfthub-tunnel/v1",
                "type": "endpoint_response",
                "correlation_id": correlation_id,
                "status": "error",
                "error": {"message": "Database connection failed"},
            }

        async def mock_to_thread(func, *args, **kwargs):
            return None

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            with patch.object(tunnel_client, "_wait_for_response", mock_wait):
                result = await tunnel_client.query_data_source(
                    target_username="alice",
                    slug="broken-datasource",
                    endpoint_path="alice/broken-datasource",
                    query="test",
                )

        assert result.status == "error"
        assert "Database connection failed" in result.error_message

    @pytest.mark.asyncio
    async def test_query_data_source_exception(self, tunnel_client: TunnelClient):
        """Test handling of exception during query."""
        async def mock_to_thread(func, *args, **kwargs):
            raise Exception("Network error")

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            result = await tunnel_client.query_data_source(
                target_username="alice",
                slug="datasource",
                endpoint_path="alice/datasource",
                query="test",
            )

        assert result.status == "error"
        assert "Tunnel error" in result.error_message


class TestChatModel:
    """Tests for chat_model method."""

    @pytest.mark.asyncio
    async def test_chat_model_success(self, tunnel_client: TunnelClient):
        """Test successful model chat via tunnel."""
        async def mock_wait(correlation_id):
            return {
                "protocol": "syfthub-tunnel/v1",
                "type": "endpoint_response",
                "correlation_id": correlation_id,
                "status": "success",
                "payload": {
                    "response": "The answer is 42.",
                },
            }

        async def mock_to_thread(func, *args, **kwargs):
            return None

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            with patch.object(tunnel_client, "_wait_for_response", mock_wait):
                result = await tunnel_client.chat_model(
                    target_username="bob",
                    slug="gpt-model",
                    endpoint_path="bob/gpt-model",
                    messages=[{"role": "user", "content": "What is the answer?"}],
                    max_tokens=100,
                    temperature=0.7,
                )

        assert result["status"] == "success"
        assert result["response"] == "The answer is 42."
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_chat_model_timeout(self, tunnel_client: TunnelClient):
        """Test model chat timeout."""
        async def mock_wait(correlation_id):
            return None  # Timeout

        async def mock_to_thread(func, *args, **kwargs):
            return None

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            with patch.object(tunnel_client, "_wait_for_response", mock_wait):
                with pytest.raises(TimeoutError) as exc_info:
                    await tunnel_client.chat_model(
                        target_username="bob",
                        slug="slow-model",
                        endpoint_path="bob/slow-model",
                        messages=[{"role": "user", "content": "test"}],
                    )

        assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_chat_model_error_response(self, tunnel_client: TunnelClient):
        """Test handling of error response from model."""
        async def mock_wait(correlation_id):
            return {
                "protocol": "syfthub-tunnel/v1",
                "type": "endpoint_response",
                "correlation_id": correlation_id,
                "status": "error",
                "error": {"message": "Model overloaded"},
            }

        async def mock_to_thread(func, *args, **kwargs):
            return None

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            with patch.object(tunnel_client, "_wait_for_response", mock_wait):
                with pytest.raises(Exception) as exc_info:
                    await tunnel_client.chat_model(
                        target_username="bob",
                        slug="busy-model",
                        endpoint_path="bob/busy-model",
                        messages=[{"role": "user", "content": "test"}],
                    )

        assert "Model overloaded" in str(exc_info.value)


class TestWaitForResponse:
    """Tests for _wait_for_response method."""

    @pytest.mark.asyncio
    async def test_wait_for_response_finds_match(self, tunnel_client: TunnelClient):
        """Test finding matching response by correlation ID."""
        correlation_id = "test-correlation-123"

        mock_response = MagicMock()
        mock_response.messages = [
            MagicMock(
                message=json.dumps({
                    "correlation_id": correlation_id,
                    "status": "success",
                    "payload": {"data": "test"},
                })
            )
        ]
        mock_response.remaining = 0

        async def mock_to_thread(func, *args, **kwargs):
            return mock_response

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            result = await tunnel_client._wait_for_response(correlation_id)

        assert result is not None
        assert result["correlation_id"] == correlation_id

    @pytest.mark.asyncio
    async def test_wait_for_response_skips_non_matching(self, tunnel_client: TunnelClient):
        """Test that non-matching messages are skipped."""
        target_id = "target-123"
        call_count = [0]

        # First response has wrong correlation ID, second has correct one
        wrong_response = MagicMock()
        wrong_response.messages = [
            MagicMock(
                message=json.dumps({
                    "correlation_id": "wrong-id",
                    "status": "success",
                })
            )
        ]
        wrong_response.remaining = 1

        correct_response = MagicMock()
        correct_response.messages = [
            MagicMock(
                message=json.dumps({
                    "correlation_id": target_id,
                    "status": "success",
                })
            )
        ]
        correct_response.remaining = 0

        async def mock_to_thread(func, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return wrong_response
            return correct_response

        async def mock_sleep(duration):
            pass

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread):
            with patch("aggregator.clients.tunnel.asyncio.sleep", mock_sleep):
                result = await tunnel_client._wait_for_response(target_id)

        assert result is not None
        assert result["correlation_id"] == target_id


class TestParseDocuments:
    """Tests for _parse_documents method."""

    def test_parse_documents_success(self, tunnel_client: TunnelClient):
        """Test parsing documents from response payload."""
        payload = {
            "references": {
                "documents": [
                    {
                        "content": "First document",
                        "similarity_score": 0.95,
                        "metadata": {"page": 1},
                    },
                    {
                        "content": "Second document",
                        "similarity_score": 0.85,
                        "metadata": {"page": 2},
                    },
                ]
            }
        }

        result = tunnel_client._parse_documents(payload)

        assert len(result) == 2
        assert isinstance(result[0], Document)
        assert result[0].content == "First document"
        assert result[0].score == 0.95
        assert result[1].content == "Second document"

    def test_parse_documents_empty_references(self, tunnel_client: TunnelClient):
        """Test parsing with no references."""
        payload = {}
        result = tunnel_client._parse_documents(payload)
        assert result == []

    def test_parse_documents_empty_documents(self, tunnel_client: TunnelClient):
        """Test parsing with empty documents list."""
        payload = {"references": {"documents": []}}
        result = tunnel_client._parse_documents(payload)
        assert result == []

    def test_parse_documents_missing_fields(self, tunnel_client: TunnelClient):
        """Test parsing documents with missing optional fields."""
        payload = {
            "references": {
                "documents": [
                    {"content": "Document without score"},
                ]
            }
        }

        result = tunnel_client._parse_documents(payload)

        assert len(result) == 1
        assert result[0].content == "Document without score"
        assert result[0].score == 0.0  # Default


# =============================================================================
# Integration-style Tests (Message Format)
# =============================================================================


class TestTunnelProtocol:
    """Tests for tunnel protocol message format."""

    def test_protocol_version(self):
        """Test protocol version constant."""
        assert TunnelClient.PROTOCOL_VERSION == "syfthub-tunnel/v1"

    @pytest.mark.asyncio
    async def test_request_message_format(self, tunnel_client: TunnelClient):
        """Test that request messages have correct format."""
        captured_message = [None]

        async def mock_to_thread(func, *args, **kwargs):
            # Capture the message from publish call
            if args and len(args) >= 2:
                # args are (target_username=X, message=Y)
                pass
            if "message" in kwargs:
                captured_message[0] = json.loads(kwargs["message"])
            elif len(args) >= 1:
                # First positional arg after func is target_username, but message might be kwarg
                # Check the func signature - mq.publish(target_username, message)
                pass
            return None

        async def mock_wait(correlation_id):
            return {
                "status": "success",
                "payload": {"references": {"documents": []}},
            }

        # Capture the publish call by mocking the client.mq.publish method
        original_publish = tunnel_client.client.mq.publish

        def capture_publish(target_username, message):
            captured_message[0] = json.loads(message)
            return MagicMock()

        tunnel_client.client.mq.publish = capture_publish

        async def mock_to_thread_simple(func, *args, **kwargs):
            # Actually call the function to capture the message
            return func(*args, **kwargs)

        with patch("aggregator.clients.tunnel.asyncio.to_thread", mock_to_thread_simple):
            with patch.object(tunnel_client, "_wait_for_response", mock_wait):
                await tunnel_client.query_data_source(
                    target_username="alice",
                    slug="test-ds",
                    endpoint_path="alice/test-ds",
                    query="test query",
                    top_k=10,
                    similarity_threshold=0.7,
                    transaction_token="tx_123",
                )

        # Restore original
        tunnel_client.client.mq.publish = original_publish

        # Verify message format
        assert captured_message[0] is not None
        assert captured_message[0]["protocol"] == "syfthub-tunnel/v1"
        assert captured_message[0]["type"] == "endpoint_request"
        assert "correlation_id" in captured_message[0]
        assert captured_message[0]["reply_to"] == "rq_test123"
        assert captured_message[0]["endpoint"]["slug"] == "test-ds"
        assert captured_message[0]["endpoint"]["type"] == "data_source"
        assert captured_message[0]["payload"]["query"] == "test query"
        assert captured_message[0]["payload"]["limit"] == 10
        assert captured_message[0]["payload"]["similarity_threshold"] == 0.7
        assert captured_message[0]["payload"]["transaction_token"] == "tx_123"
