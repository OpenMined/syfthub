"""Unit tests for MQResource."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
import respx
from httpx import Response

from syfthub_sdk import SyftHubClient
from syfthub_sdk.mq import (
    ClearResponse,
    ConsumeResponse,
    MQMessage,
    PeekResponse,
    PublishResponse,
    QueueStatusResponse,
    ReleaseQueueResponse,
    ReserveQueueResponse,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def base_url() -> str:
    """Return test base URL."""
    return "https://test.syfthub.com"


@pytest.fixture
def mock_user_response() -> dict[str, Any]:
    """Return mock user response."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "is_active": True,
        "role": "user",
        "created_at": now,
    }


def _create_authenticated_client(base_url: str) -> SyftHubClient:
    """Create authenticated client for testing."""
    client = SyftHubClient(base_url=base_url)
    client._http._tokens = type(
        "Tokens",
        (),
        {
            "access_token": "test-token",
            "refresh_token": "test-refresh",
        },
    )()
    return client


# =============================================================================
# Publish Tests
# =============================================================================


class TestPublish:
    """Tests for publish method."""

    @respx.mock
    def test_publish_to_user_success(self, base_url: str):
        """Test successful publish to user queue."""
        now = datetime.now(timezone.utc)
        respx.post(f"{base_url}/api/v1/mq/pub").mock(
            return_value=Response(
                200,
                json={
                    "status": "ok",
                    "queued_at": now.isoformat(),
                    "target_username": "bob",
                    "queue_length": 5,
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.publish(
            target_username="bob",
            message='{"type": "hello"}',
        )

        assert isinstance(result, PublishResponse)
        assert result.status == "ok"
        assert result.target_username == "bob"
        assert result.queue_length == 5

    @respx.mock
    def test_publish_to_reserved_queue_autodetect(self, base_url: str):
        """Test publish auto-detects rq_ prefix."""
        now = datetime.now(timezone.utc)
        respx.post(f"{base_url}/api/v1/mq/pub").mock(
            return_value=Response(
                200,
                json={
                    "status": "ok",
                    "queued_at": now.isoformat(),
                    "target_username": "rq_abc123",
                    "queue_length": 1,
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.publish(
            target_username="rq_abc123",  # Reserved queue ID
            message='{"response": "data"}',
        )

        assert result.target_username == "rq_abc123"

    @respx.mock
    def test_publish_user_not_found(self, base_url: str):
        """Test publish to non-existent user."""
        from syfthub_sdk.exceptions import NotFoundError

        respx.post(f"{base_url}/api/v1/mq/pub").mock(
            return_value=Response(
                404,
                json={"detail": "User 'nonexistent' not found"},
            )
        )

        client = _create_authenticated_client(base_url)
        with pytest.raises(NotFoundError):
            client.mq.publish(target_username="nonexistent", message="test")


# =============================================================================
# Consume Tests
# =============================================================================


class TestConsume:
    """Tests for consume method."""

    @respx.mock
    def test_consume_from_own_queue(self, base_url: str):
        """Test consuming from own queue."""
        now = datetime.now(timezone.utc)
        respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=Response(
                200,
                json={
                    "messages": [
                        {
                            "id": "msg-123",
                            "from_username": "alice",
                            "from_user_id": 2,
                            "message": '{"type": "greeting"}',
                            "queued_at": now.isoformat(),
                        }
                    ],
                    "remaining": 0,
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.consume(limit=10)

        assert isinstance(result, ConsumeResponse)
        assert len(result.messages) == 1
        assert result.messages[0].from_username == "alice"
        assert result.remaining == 0

    @respx.mock
    def test_consume_empty_queue(self, base_url: str):
        """Test consuming from empty queue."""
        respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=Response(
                200,
                json={"messages": [], "remaining": 0},
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.consume()

        assert len(result.messages) == 0
        assert result.remaining == 0

    @respx.mock
    def test_consume_from_reserved_queue(self, base_url: str):
        """Test consuming from reserved queue with queue_id and token."""
        now = datetime.now(timezone.utc)
        respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=Response(
                200,
                json={
                    "messages": [
                        {
                            "id": "msg-456",
                            "from_username": "aggregator",
                            "from_user_id": 1,
                            "message": '{"response": "data"}',
                            "queued_at": now.isoformat(),
                        }
                    ],
                    "remaining": 0,
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.consume(
            queue_id="rq_abc123",
            token="secret_token",
            limit=10,
        )

        assert len(result.messages) == 1
        assert result.messages[0].id == "msg-456"

    @respx.mock
    def test_consume_reserved_queue_invalid_token(self, base_url: str):
        """Test consume with invalid token fails."""
        from syfthub_sdk.exceptions import AuthorizationError

        respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=Response(
                403,
                json={"detail": "Invalid queue token"},
            )
        )

        client = _create_authenticated_client(base_url)
        with pytest.raises(AuthorizationError):
            client.mq.consume(queue_id="rq_abc123", token="wrong_token")


# =============================================================================
# Reserve Queue Tests
# =============================================================================


class TestReserveQueue:
    """Tests for reserve_queue method."""

    @respx.mock
    def test_reserve_queue_success(self, base_url: str):
        """Test successful queue reservation."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=300)

        respx.post(f"{base_url}/api/v1/mq/reserve-queue").mock(
            return_value=Response(
                200,
                json={
                    "queue_id": "rq_abc123def456",
                    "token": "secret_token_value",
                    "expires_at": expires_at.isoformat(),
                    "ttl": 300,
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.reserve_queue(ttl=300)

        assert isinstance(result, ReserveQueueResponse)
        assert result.queue_id.startswith("rq_")
        assert len(result.token) > 0
        assert result.ttl == 300

    @respx.mock
    def test_reserve_queue_default_ttl(self, base_url: str):
        """Test reserve_queue with default TTL."""
        now = datetime.now(timezone.utc)

        respx.post(f"{base_url}/api/v1/mq/reserve-queue").mock(
            return_value=Response(
                200,
                json={
                    "queue_id": "rq_xyz789",
                    "token": "another_token",
                    "expires_at": now.isoformat(),
                    "ttl": 300,
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.reserve_queue()  # Default TTL

        assert result.ttl == 300


# =============================================================================
# Release Queue Tests
# =============================================================================


class TestReleaseQueue:
    """Tests for release_queue method."""

    @respx.mock
    def test_release_queue_success(self, base_url: str):
        """Test successful queue release."""
        respx.post(f"{base_url}/api/v1/mq/release-queue").mock(
            return_value=Response(
                200,
                json={
                    "queue_id": "rq_abc123",
                    "messages_cleared": 5,
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.release_queue(
            queue_id="rq_abc123",
            token="valid_token",
        )

        assert isinstance(result, ReleaseQueueResponse)
        assert result.queue_id == "rq_abc123"
        assert result.messages_cleared == 5

    @respx.mock
    def test_release_queue_not_found(self, base_url: str):
        """Test release of non-existent queue."""
        from syfthub_sdk.exceptions import NotFoundError

        respx.post(f"{base_url}/api/v1/mq/release-queue").mock(
            return_value=Response(
                404,
                json={"detail": "Reserved queue 'rq_nonexistent' not found or expired"},
            )
        )

        client = _create_authenticated_client(base_url)
        with pytest.raises(NotFoundError):
            client.mq.release_queue(queue_id="rq_nonexistent", token="token")


# =============================================================================
# Status Tests
# =============================================================================


class TestQueueStatus:
    """Tests for queue status method."""

    @respx.mock
    def test_status_success(self, base_url: str):
        """Test getting queue status."""
        respx.get(f"{base_url}/api/v1/mq/status").mock(
            return_value=Response(
                200,
                json={
                    "queue_length": 10,
                    "username": "testuser",
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.status()

        assert isinstance(result, QueueStatusResponse)
        assert result.queue_length == 10
        assert result.username == "testuser"


# =============================================================================
# Peek Tests
# =============================================================================


class TestPeek:
    """Tests for peek method."""

    @respx.mock
    def test_peek_messages(self, base_url: str):
        """Test peeking at messages."""
        now = datetime.now(timezone.utc)
        respx.post(f"{base_url}/api/v1/mq/peek").mock(
            return_value=Response(
                200,
                json={
                    "messages": [
                        {
                            "id": "msg-1",
                            "from_username": "alice",
                            "from_user_id": 2,
                            "message": "test",
                            "queued_at": now.isoformat(),
                        }
                    ],
                    "total": 5,
                },
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.peek(limit=1)

        assert isinstance(result, PeekResponse)
        assert len(result.messages) == 1
        assert result.total == 5


# =============================================================================
# Clear Tests
# =============================================================================


class TestClear:
    """Tests for clear method."""

    @respx.mock
    def test_clear_queue(self, base_url: str):
        """Test clearing queue."""
        respx.delete(f"{base_url}/api/v1/mq/clear").mock(
            return_value=Response(
                200,
                json={"status": "ok", "cleared": 15},
            )
        )

        client = _create_authenticated_client(base_url)
        result = client.mq.clear()

        assert isinstance(result, ClearResponse)
        assert result.status == "ok"
        assert result.cleared == 15


# =============================================================================
# Model Tests
# =============================================================================


class TestMQModels:
    """Tests for MQ models."""

    def test_mq_message_model(self):
        """Test MQMessage model."""
        now = datetime.now(timezone.utc)
        msg = MQMessage(
            id="msg-123",
            from_username="alice",
            from_user_id=1,
            message='{"type": "test"}',
            queued_at=now,
        )
        assert msg.id == "msg-123"
        assert msg.from_username == "alice"

    def test_reserve_queue_response_model(self):
        """Test ReserveQueueResponse model."""
        now = datetime.now(timezone.utc)
        response = ReserveQueueResponse(
            queue_id="rq_abc123",
            token="secret",
            expires_at=now,
            ttl=300,
        )
        assert response.queue_id.startswith("rq_")
        assert response.ttl == 300

    def test_release_queue_response_model(self):
        """Test ReleaseQueueResponse model."""
        response = ReleaseQueueResponse(
            queue_id="rq_abc123",
            messages_cleared=10,
        )
        assert response.messages_cleared == 10
