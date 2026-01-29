"""Tests for the TunnelClient."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aggregator.clients.tunnel import (
    TUNNEL_PROTOCOL_VERSION,
    TUNNELING_PREFIX,
    TunnelClient,
    TunnelClientError,
    extract_tunnel_username,
    is_tunneled_url,
)


class TestTunnelingHelpers:
    """Tests for tunneling URL helper functions."""

    def test_is_tunneled_url_valid(self):
        """Test detection of valid tunneling URLs."""
        assert is_tunneled_url("tunneling:alice") is True
        assert is_tunneled_url("tunneling:bob") is True
        assert is_tunneled_url("tunneling:user-123") is True

    def test_is_tunneled_url_invalid(self):
        """Test detection of non-tunneling URLs."""
        assert is_tunneled_url("http://localhost:8080") is False
        assert is_tunneled_url("https://example.com") is False
        assert is_tunneled_url("") is False
        assert is_tunneled_url("tunnel:alice") is False  # Wrong prefix

    def test_extract_tunnel_username_valid(self):
        """Test extracting username from tunneling URL."""
        assert extract_tunnel_username("tunneling:alice") == "alice"
        assert extract_tunnel_username("tunneling:bob") == "bob"
        assert extract_tunnel_username("tunneling:user-123") == "user-123"

    def test_extract_tunnel_username_invalid(self):
        """Test extracting username from non-tunneling URL raises error."""
        with pytest.raises(ValueError):
            extract_tunnel_username("http://localhost:8080")

        with pytest.raises(ValueError):
            extract_tunnel_username("not-a-tunnel-url")


class TestTunnelClientInit:
    """Tests for TunnelClient initialization."""

    def test_init_default_values(self):
        """Test TunnelClient initialization with defaults."""
        client = TunnelClient(syfthub_url="http://localhost:8000")

        assert client.syfthub_url == "http://localhost:8000"
        assert client.timeout == 30.0
        assert client.poll_interval == 0.5

    def test_init_custom_values(self):
        """Test TunnelClient initialization with custom values."""
        client = TunnelClient(
            syfthub_url="https://hub.syft.com/",
            timeout=60.0,
            poll_interval=1.0,
        )

        assert client.syfthub_url == "https://hub.syft.com"  # Trailing slash stripped
        assert client.timeout == 60.0
        assert client.poll_interval == 1.0


class TestTunnelClientQueryDataSource:
    """Tests for TunnelClient.query_data_source."""

    @pytest.fixture
    def tunnel_client(self):
        """Create a TunnelClient instance."""
        return TunnelClient(syfthub_url="http://localhost:8000", timeout=5.0)

    @pytest.mark.asyncio
    async def test_query_data_source_success(self, tunnel_client):
        """Test successful data source query via tunnel."""
        # Mock the internal methods
        mock_response = {
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_response",
            "correlation_id": "test-123",
            "status": "success",
            "payload": {
                "references": {
                    "documents": [
                        {
                            "content": "Test document content",
                            "similarity_score": 0.95,
                            "metadata": {"title": "Test Doc"},
                        }
                    ]
                }
            },
        }

        with patch.object(
            tunnel_client, "_send_tunnel_request", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = mock_response

            result = await tunnel_client.query_data_source(
                target_username="alice",
                endpoint_slug="my-dataset",
                query="test query",
                top_k=5,
                similarity_threshold=0.5,
                satellite_token="sat_token_123",
                response_queue_id="rq_test",
                response_queue_token="token_123",
                endpoint_path="alice/my-dataset",
            )

            assert result.status == "success"
            assert len(result.documents) == 1
            assert result.documents[0].content == "Test document content"
            assert result.documents[0].score == 0.95

    @pytest.mark.asyncio
    async def test_query_data_source_error_response(self, tunnel_client):
        """Test data source query with error response."""
        mock_response = {
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_response",
            "status": "error",
            "error": {"message": "Endpoint not found"},
        }

        with patch.object(
            tunnel_client, "_send_tunnel_request", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = mock_response

            result = await tunnel_client.query_data_source(
                target_username="alice",
                endpoint_slug="missing",
                query="test",
                top_k=5,
                similarity_threshold=0.5,
                satellite_token="token",
                response_queue_id="rq_test",
                response_queue_token="token",
                endpoint_path="alice/missing",
            )

            assert result.status == "error"
            assert "Endpoint not found" in result.error_message
            assert result.documents == []

    @pytest.mark.asyncio
    async def test_query_data_source_timeout(self, tunnel_client):
        """Test data source query timeout."""
        import asyncio

        with patch.object(
            tunnel_client, "_send_tunnel_request", new_callable=AsyncMock
        ) as mock_send:
            mock_send.side_effect = asyncio.TimeoutError()

            result = await tunnel_client.query_data_source(
                target_username="alice",
                endpoint_slug="slow",
                query="test",
                top_k=5,
                similarity_threshold=0.5,
                satellite_token="token",
                response_queue_id="rq_test",
                response_queue_token="token",
                endpoint_path="alice/slow",
            )

            assert result.status == "timeout"
            assert "timed out" in result.error_message.lower()


class TestTunnelClientQueryModel:
    """Tests for TunnelClient.query_model."""

    @pytest.fixture
    def tunnel_client(self):
        """Create a TunnelClient instance."""
        return TunnelClient(syfthub_url="http://localhost:8000", timeout=5.0)

    @pytest.mark.asyncio
    async def test_query_model_success(self, tunnel_client):
        """Test successful model query via tunnel."""
        mock_response = {
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_response",
            "correlation_id": "test-456",
            "status": "success",
            "payload": {
                "summary": {
                    "message": {"content": "Generated response text"}
                }
            },
        }

        with patch.object(
            tunnel_client, "_send_tunnel_request", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = mock_response

            result = await tunnel_client.query_model(
                target_username="bob",
                endpoint_slug="gpt-model",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=100,
                temperature=0.7,
                satellite_token="sat_token_456",
                response_queue_id="rq_model",
                response_queue_token="model_token",
                endpoint_path="bob/gpt-model",
            )

            assert result.response == "Generated response text"
            assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_query_model_error_raises(self, tunnel_client):
        """Test model query error raises TunnelClientError."""
        mock_response = {
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_response",
            "status": "error",
            "error": {"message": "Model unavailable"},
        }

        with patch.object(
            tunnel_client, "_send_tunnel_request", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = mock_response

            with pytest.raises(TunnelClientError) as exc_info:
                await tunnel_client.query_model(
                    target_username="bob",
                    endpoint_slug="broken",
                    messages=[{"role": "user", "content": "Test"}],
                    max_tokens=100,
                    temperature=0.7,
                    satellite_token="token",
                    response_queue_id="rq_test",
                    response_queue_token="token",
                    endpoint_path="bob/broken",
                )

            assert "Model unavailable" in str(exc_info.value)


class TestTunnelClientPublishAndPoll:
    """Tests for TunnelClient internal publish and poll methods."""

    @pytest.fixture
    def tunnel_client(self):
        """Create a TunnelClient instance."""
        return TunnelClient(syfthub_url="http://localhost:8000", timeout=5.0)

    @pytest.mark.asyncio
    async def test_publish_to_queue_success(self, tunnel_client):
        """Test publishing to MQ queue."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "queue_length": 1}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Should not raise
            await tunnel_client._publish_to_queue(
                target_username="alice",
                message='{"test": "message"}',
                satellite_token="sat_token",
            )

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/api/v1/mq/pub" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_publish_to_queue_failure(self, tunnel_client):
        """Test publishing to MQ queue failure."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_response.json.return_value = {"detail": "User not found"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(TunnelClientError) as exc_info:
                await tunnel_client._publish_to_queue(
                    target_username="nonexistent",
                    message='{"test": "message"}',
                    satellite_token="sat_token",
                )

            assert "404" in str(exc_info.value)


class TestTunnelProtocol:
    """Tests for tunnel protocol message format."""

    @pytest.fixture
    def tunnel_client(self):
        """Create a TunnelClient instance."""
        return TunnelClient(syfthub_url="http://localhost:8000")

    def test_protocol_version_constant(self):
        """Test protocol version constant."""
        assert TUNNEL_PROTOCOL_VERSION == "syfthub-tunnel/v1"

    def test_tunneling_prefix_constant(self):
        """Test tunneling prefix constant."""
        assert TUNNELING_PREFIX == "tunneling:"

    @pytest.mark.asyncio
    async def test_request_message_format(self, tunnel_client):
        """Test that tunnel request has correct format."""
        captured_message = None

        async def capture_publish(target_username, message, satellite_token):
            nonlocal captured_message
            captured_message = json.loads(message)

        async def mock_poll(queue_id, token, correlation_id):
            return {
                "protocol": TUNNEL_PROTOCOL_VERSION,
                "type": "endpoint_response",
                "correlation_id": correlation_id,
                "status": "success",
                "payload": {"references": {"documents": []}},
            }

        with patch.object(tunnel_client, "_publish_to_queue", capture_publish):
            with patch.object(tunnel_client, "_poll_for_response", mock_poll):
                await tunnel_client.query_data_source(
                    target_username="alice",
                    endpoint_slug="test-ds",
                    query="test query",
                    top_k=5,
                    similarity_threshold=0.7,
                    satellite_token="token",
                    response_queue_id="rq_test",
                    response_queue_token="token",
                    endpoint_path="alice/test-ds",
                )

        assert captured_message is not None
        assert captured_message["protocol"] == TUNNEL_PROTOCOL_VERSION
        assert captured_message["type"] == "endpoint_request"
        assert captured_message["reply_to"] == "rq_test"
        assert captured_message["endpoint"]["slug"] == "test-ds"
        assert captured_message["endpoint"]["type"] == "data_source"
        assert captured_message["payload"]["messages"] == "test query"
        assert captured_message["payload"]["limit"] == 5
