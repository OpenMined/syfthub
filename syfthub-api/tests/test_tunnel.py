"""Tests for tunneling functionality in SyftAPI.

This module tests the message queue tunneling mode that allows SyftAPI
to receive and process requests via MQ instead of HTTP.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syfthub_api import Document, SyftAPI
from syfthub_api.schemas import (
    EndpointType,
    TUNNEL_PROTOCOL_VERSION,
    TunnelErrorCode,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tunnel_env_vars():
    """Environment variables for tunneling mode."""
    return {
        "SYFTHUB_URL": "http://test.example.com",
        "SYFTHUB_USERNAME": "testuser",
        "SYFTHUB_PASSWORD": "testpassword",
        "SPACE_URL": "tunneling:testuser",  # Tunneling mode
        "LOG_LEVEL": "DEBUG",
    }


@pytest.fixture
def tunnel_app(tunnel_env_vars):
    """Create a SyftAPI instance configured for tunneling."""
    with patch.dict(os.environ, tunnel_env_vars):
        api = SyftAPI()
        api._skip_sync = True
        return api


@pytest.fixture
def mock_mq_client():
    """Mock MQ client for tunneling tests."""
    mock_client = MagicMock()
    mock_client.mq = MagicMock()
    mock_client.mq.consume = MagicMock()
    mock_client.mq.publish = MagicMock()
    return mock_client


# =============================================================================
# Tunneling Mode Detection Tests
# =============================================================================


class TestTunnelingModeDetection:
    """Tests for tunneling mode detection."""

    def test_tunneling_url_detected(self, tunnel_env_vars):
        """Test that tunneling: prefix is detected."""
        with patch.dict(os.environ, tunnel_env_vars):
            api = SyftAPI()
            api._skip_sync = True
            assert api._is_tunneling is True

    def test_http_url_not_tunneling(self):
        """Test that HTTP URLs don't trigger tunneling mode."""
        env_vars = {
            "SYFTHUB_URL": "http://test.example.com",
            "SYFTHUB_USERNAME": "testuser",
            "SYFTHUB_PASSWORD": "testpassword",
            "SPACE_URL": "http://localhost:8001",
            "LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, env_vars):
            api = SyftAPI()
            api._skip_sync = True
            assert api._is_tunneling is False


# =============================================================================
# Message Processing Tests
# =============================================================================


class TestProcessTunnelMessage:
    """Tests for _process_tunnel_message method."""

    @pytest.mark.asyncio
    async def test_process_valid_endpoint_request(self, tunnel_app: SyftAPI):
        """Test processing a valid endpoint request message."""
        # Register a datasource endpoint
        @tunnel_app.datasource(slug="test-ds", name="Test DS", description="Test")
        async def handler(query: str, limit: int = 5):
            return [
                Document(
                    document_id="1",
                    content="Test content",
                    metadata={},
                    similarity_score=0.9,
                )
            ]

        # Create a mock message
        mock_msg = MagicMock()
        mock_msg.id = "msg-123"
        mock_msg.from_username = "requester"
        mock_msg.message = json.dumps({
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_request",
            "correlation_id": "corr-123",
            "reply_to": "rq_response_queue",
            "endpoint": {
                "slug": "test-ds",
                "type": "data_source",
            },
            "payload": {
                "query": "test query",
                "limit": 5,
            },
        })

        # Mock the client and publish
        tunnel_app._client = MagicMock()
        tunnel_app._client.mq = MagicMock()

        published_messages = []

        async def mock_to_thread(func, *args, **kwargs):
            if "publish" in str(func):
                published_messages.append(kwargs)
            return None

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            await tunnel_app._process_tunnel_message(mock_msg)

        # Verify response was published
        assert len(published_messages) == 1
        assert published_messages[0]["target_username"] == "rq_response_queue"

        # Parse and verify response
        response = json.loads(published_messages[0]["message"])
        assert response["status"] == "success"
        assert response["correlation_id"] == "corr-123"

    @pytest.mark.asyncio
    async def test_process_non_json_message_ignored(self, tunnel_app: SyftAPI):
        """Test that non-JSON messages are ignored."""
        mock_msg = MagicMock()
        mock_msg.id = "msg-123"
        mock_msg.from_username = "requester"
        mock_msg.message = "not valid json"

        # Should not raise, just log warning
        await tunnel_app._process_tunnel_message(mock_msg)

    @pytest.mark.asyncio
    async def test_process_unknown_protocol_ignored(self, tunnel_app: SyftAPI):
        """Test that unknown protocol messages are ignored."""
        mock_msg = MagicMock()
        mock_msg.id = "msg-123"
        mock_msg.from_username = "requester"
        mock_msg.message = json.dumps({
            "protocol": "unknown-protocol/v1",
            "type": "endpoint_request",
        })

        # Should not raise, just log debug
        await tunnel_app._process_tunnel_message(mock_msg)

    @pytest.mark.asyncio
    async def test_process_unknown_message_type_logged(self, tunnel_app: SyftAPI):
        """Test that unknown message types are logged as warnings."""
        mock_msg = MagicMock()
        mock_msg.id = "msg-123"
        mock_msg.from_username = "requester"
        mock_msg.message = json.dumps({
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "unknown_type",
        })

        # Should not raise, just log warning
        await tunnel_app._process_tunnel_message(mock_msg)


# =============================================================================
# Handle Tunnel Request Tests
# =============================================================================


class TestHandleTunnelRequest:
    """Tests for _handle_tunnel_request method."""

    @pytest.mark.asyncio
    async def test_endpoint_not_found_error(self, tunnel_app: SyftAPI):
        """Test error response when endpoint not found."""
        mock_msg = MagicMock()
        mock_msg.from_username = "requester"

        data = {
            "correlation_id": "corr-123",
            "reply_to": "rq_queue",
            "endpoint": {"slug": "nonexistent", "type": "data_source"},
            "payload": {},
        }

        tunnel_app._client = MagicMock()
        published_messages = []

        async def mock_to_thread(func, *args, **kwargs):
            published_messages.append(kwargs)
            return None

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            await tunnel_app._handle_tunnel_request(
                data, mock_msg, datetime.now(timezone.utc)
            )

        assert len(published_messages) == 1
        response = json.loads(published_messages[0]["message"])
        assert response["status"] == "error"
        assert response["error"]["code"] == TunnelErrorCode.ENDPOINT_NOT_FOUND.value

    @pytest.mark.asyncio
    async def test_endpoint_type_mismatch_error(self, tunnel_app: SyftAPI):
        """Test error response when endpoint type doesn't match."""
        # Register a datasource
        @tunnel_app.datasource(slug="my-ds", name="DS", description="Test")
        async def handler(query: str):
            return []

        mock_msg = MagicMock()
        mock_msg.from_username = "requester"

        # Request it as a model
        data = {
            "correlation_id": "corr-123",
            "reply_to": "rq_queue",
            "endpoint": {"slug": "my-ds", "type": "model"},  # Wrong type
            "payload": {},
        }

        tunnel_app._client = MagicMock()
        published_messages = []

        async def mock_to_thread(func, *args, **kwargs):
            published_messages.append(kwargs)
            return None

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            await tunnel_app._handle_tunnel_request(
                data, mock_msg, datetime.now(timezone.utc)
            )

        assert len(published_messages) == 1
        response = json.loads(published_messages[0]["message"])
        assert response["status"] == "error"
        assert response["error"]["code"] == TunnelErrorCode.ENDPOINT_TYPE_MISMATCH.value

    @pytest.mark.asyncio
    async def test_missing_correlation_id_ignored(self, tunnel_app: SyftAPI):
        """Test that requests without correlation_id are ignored."""
        mock_msg = MagicMock()
        mock_msg.from_username = "requester"

        data = {
            # No correlation_id
            "reply_to": "rq_queue",
            "endpoint": {"slug": "test"},
            "payload": {},
        }

        tunnel_app._client = MagicMock()

        # Should return early without publishing
        await tunnel_app._handle_tunnel_request(
            data, mock_msg, datetime.now(timezone.utc)
        )


# =============================================================================
# Handle Tunnel Response Tests
# =============================================================================


class TestHandleTunnelResponse:
    """Tests for _handle_tunnel_response method."""

    @pytest.mark.asyncio
    async def test_response_resolves_pending_future(self, tunnel_app: SyftAPI):
        """Test that responses resolve pending futures."""
        correlation_id = "corr-123"

        # Create a pending future
        future = asyncio.Future()
        tunnel_app._pending_responses[correlation_id] = future

        mock_msg = MagicMock()
        mock_msg.from_username = "responder"

        data = {
            "correlation_id": correlation_id,
            "status": "success",
            "payload": {"response": "test data"},
        }

        await tunnel_app._handle_tunnel_response(data, mock_msg)

        # Future should be resolved
        assert future.done()
        result = future.result()
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_response_without_pending_future_logged(self, tunnel_app: SyftAPI):
        """Test that unexpected responses are logged as warnings."""
        mock_msg = MagicMock()
        mock_msg.from_username = "responder"

        data = {
            "correlation_id": "unknown-corr",
            "status": "success",
        }

        # Should not raise, just log warning
        await tunnel_app._handle_tunnel_response(data, mock_msg)

    @pytest.mark.asyncio
    async def test_response_without_correlation_id_ignored(self, tunnel_app: SyftAPI):
        """Test that responses without correlation_id are ignored."""
        mock_msg = MagicMock()
        mock_msg.from_username = "responder"

        data = {
            # No correlation_id
            "status": "success",
        }

        # Should return early
        await tunnel_app._handle_tunnel_response(data, mock_msg)


# =============================================================================
# Send Tunnel Messages Tests
# =============================================================================


class TestSendTunnelMessages:
    """Tests for _send_tunnel_success and _send_tunnel_error methods."""

    @pytest.mark.asyncio
    async def test_send_tunnel_success(self, tunnel_app: SyftAPI):
        """Test sending a success response."""
        tunnel_app._client = MagicMock()
        published_messages = []

        async def mock_to_thread(func, *args, **kwargs):
            published_messages.append(kwargs)
            return None

        start_time = datetime.now(timezone.utc)

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            await tunnel_app._send_tunnel_success(
                reply_to="rq_response_queue",
                correlation_id="corr-123",
                endpoint_slug="test-endpoint",
                payload={"response": "data"},
                start_time=start_time,
            )

        assert len(published_messages) == 1
        assert published_messages[0]["target_username"] == "rq_response_queue"

        response = json.loads(published_messages[0]["message"])
        assert response["protocol"] == TUNNEL_PROTOCOL_VERSION
        assert response["type"] == "endpoint_response"
        assert response["status"] == "success"
        assert response["correlation_id"] == "corr-123"
        assert response["payload"] == {"response": "data"}
        assert "timing" in response

    @pytest.mark.asyncio
    async def test_send_tunnel_error(self, tunnel_app: SyftAPI):
        """Test sending an error response."""
        tunnel_app._client = MagicMock()
        published_messages = []

        async def mock_to_thread(func, *args, **kwargs):
            published_messages.append(kwargs)
            return None

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            await tunnel_app._send_tunnel_error(
                reply_to="rq_response_queue",
                correlation_id="corr-123",
                endpoint_slug="test-endpoint",
                code=TunnelErrorCode.ENDPOINT_NOT_FOUND,
                message="Endpoint not found",
                details={"slug": "missing-endpoint"},
            )

        assert len(published_messages) == 1

        response = json.loads(published_messages[0]["message"])
        assert response["status"] == "error"
        assert response["error"]["code"] == "ENDPOINT_NOT_FOUND"
        assert response["error"]["message"] == "Endpoint not found"
        assert response["error"]["details"] == {"slug": "missing-endpoint"}


# =============================================================================
# Publish Tunnel Message Tests
# =============================================================================


class TestPublishTunnelMessage:
    """Tests for _publish_tunnel_message method."""

    @pytest.mark.asyncio
    async def test_publish_without_client_raises(self, tunnel_app: SyftAPI):
        """Test that publishing without client raises RuntimeError."""
        tunnel_app._client = None

        with pytest.raises(RuntimeError, match="Client not authenticated"):
            await tunnel_app._publish_tunnel_message(
                target_username="user", message={"test": "data"}
            )

    @pytest.mark.asyncio
    async def test_publish_calls_mq_publish(self, tunnel_app: SyftAPI):
        """Test that publish calls the MQ client correctly."""
        tunnel_app._client = MagicMock()
        published_calls = []

        async def mock_to_thread(func, *args, **kwargs):
            published_calls.append({"func": func, "kwargs": kwargs})
            return None

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            await tunnel_app._publish_tunnel_message(
                target_username="target_user",
                message={"test": "data"},
            )

        assert len(published_calls) == 1
        assert published_calls[0]["kwargs"]["target_username"] == "target_user"
        assert json.loads(published_calls[0]["kwargs"]["message"]) == {"test": "data"}


# =============================================================================
# Tunnel Consumer Loop Tests
# =============================================================================


class TestTunnelConsumerLoop:
    """Tests for _tunnel_consumer_loop method."""

    @pytest.mark.asyncio
    async def test_consumer_loop_processes_messages(self, tunnel_app: SyftAPI):
        """Test that consumer loop processes messages from queue."""
        tunnel_app._client = MagicMock()
        tunnel_app._tunnel_shutdown = False

        # Register endpoint
        @tunnel_app.datasource(slug="test", name="Test", description="Test")
        async def handler(query: str):
            return []

        # Create mock messages
        mock_response = MagicMock()
        mock_msg = MagicMock()
        mock_msg.id = "msg-1"
        mock_msg.from_username = "user"
        mock_msg.message = json.dumps({
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_request",
            "correlation_id": "corr-1",
            "reply_to": "rq_queue",
            "endpoint": {"slug": "test", "type": "data_source"},
            "payload": {"query": "test"},
        })
        mock_response.messages = [mock_msg]

        call_count = [0]

        async def mock_to_thread(func, *args, **kwargs):
            call_count[0] += 1
            if "consume" in str(func):
                # Return messages first time, then signal shutdown
                if call_count[0] == 1:
                    return mock_response
                tunnel_app._tunnel_shutdown = True
                mock_response.messages = []
                return mock_response
            return None

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            with patch("syfthub_api.app.asyncio.sleep", AsyncMock()):
                await tunnel_app._tunnel_consumer_loop()

        # Should have processed the message
        assert call_count[0] >= 1

    @pytest.mark.asyncio
    async def test_consumer_loop_handles_empty_queue(self, tunnel_app: SyftAPI):
        """Test that consumer loop sleeps on empty queue."""
        tunnel_app._client = MagicMock()
        tunnel_app._tunnel_shutdown = False

        call_count = [0]
        sleep_called = [False]

        async def mock_to_thread(func, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                tunnel_app._tunnel_shutdown = True
            mock_response = MagicMock()
            mock_response.messages = []
            return mock_response

        async def mock_sleep(duration):
            sleep_called[0] = True

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            with patch("syfthub_api.app.asyncio.sleep", mock_sleep):
                await tunnel_app._tunnel_consumer_loop()

        assert sleep_called[0]

    @pytest.mark.asyncio
    async def test_consumer_loop_handles_no_client(self, tunnel_app: SyftAPI):
        """Test that consumer loop handles missing client."""
        tunnel_app._client = None
        tunnel_app._tunnel_shutdown = False

        call_count = [0]

        async def mock_sleep(duration):
            nonlocal call_count
            call_count[0] += 1
            if call_count[0] >= 2:
                tunnel_app._tunnel_shutdown = True

        with patch("syfthub_api.app.asyncio.sleep", mock_sleep):
            await tunnel_app._tunnel_consumer_loop()

        # Should have slept waiting for client
        assert call_count[0] >= 1


# =============================================================================
# Tunnel Shutdown Tests
# =============================================================================


class TestTunnelShutdown:
    """Tests for tunnel shutdown handling."""

    @pytest.mark.asyncio
    async def test_initiate_shutdown_sets_flag(self, tunnel_app: SyftAPI):
        """Test that shutdown sets the flag."""
        tunnel_app._tunnel_shutdown = False

        await tunnel_app._initiate_tunnel_shutdown()

        assert tunnel_app._tunnel_shutdown is True

    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending_responses(self, tunnel_app: SyftAPI):
        """Test that shutdown cancels pending response futures."""
        # Create pending futures
        future1 = asyncio.Future()
        future2 = asyncio.Future()
        tunnel_app._pending_responses = {
            "corr-1": future1,
            "corr-2": future2,
        }

        await tunnel_app._initiate_tunnel_shutdown()

        assert future1.cancelled()
        assert future2.cancelled()


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestTunnelProtocolFormat:
    """Tests for tunnel protocol message format compliance."""

    def test_protocol_version_constant(self):
        """Test protocol version is correct."""
        assert TUNNEL_PROTOCOL_VERSION == "syfthub-tunnel/v1"

    @pytest.mark.asyncio
    async def test_success_response_format(self, tunnel_app: SyftAPI):
        """Test that success responses have correct format."""
        tunnel_app._client = MagicMock()
        published_messages = []

        async def mock_to_thread(func, *args, **kwargs):
            published_messages.append(kwargs)
            return None

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            await tunnel_app._send_tunnel_success(
                reply_to="rq_queue",
                correlation_id="corr-123",
                endpoint_slug="test",
                payload={"data": "test"},
                start_time=datetime.now(timezone.utc),
            )

        response = json.loads(published_messages[0]["message"])

        # Verify required fields
        assert "protocol" in response
        assert "type" in response
        assert response["type"] == "endpoint_response"
        assert "correlation_id" in response
        assert "status" in response
        assert response["status"] == "success"
        assert "endpoint_slug" in response
        assert "payload" in response
        assert "timing" in response

    @pytest.mark.asyncio
    async def test_error_response_format(self, tunnel_app: SyftAPI):
        """Test that error responses have correct format."""
        tunnel_app._client = MagicMock()
        published_messages = []

        async def mock_to_thread(func, *args, **kwargs):
            published_messages.append(kwargs)
            return None

        with patch("syfthub_api.app.asyncio.to_thread", mock_to_thread):
            await tunnel_app._send_tunnel_error(
                reply_to="rq_queue",
                correlation_id="corr-123",
                endpoint_slug="test",
                code=TunnelErrorCode.HANDLER_ERROR,
                message="Test error",
            )

        response = json.loads(published_messages[0]["message"])

        # Verify required fields
        assert response["type"] == "endpoint_response"
        assert response["status"] == "error"
        assert "error" in response
        assert "code" in response["error"]
        assert "message" in response["error"]
