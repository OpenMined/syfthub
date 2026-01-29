"""Unit tests for MQResource."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from syfthub_sdk import SyftHubClient
from syfthub_sdk.models import AuthTokens
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
def fake_tokens() -> AuthTokens:
    """Return fake auth tokens."""
    return AuthTokens(
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
    )


@pytest.fixture
def authenticated_client(base_url: str, fake_tokens: AuthTokens) -> SyftHubClient:
    """Return an authenticated client."""
    client = SyftHubClient(base_url=base_url)
    client._tokens = fake_tokens
    return client


# =============================================================================
# Test: Publish
# =============================================================================


class TestPublish:
    """Tests for publish method."""

    @respx.mock
    def test_publish_to_user_success(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test successful publish to user queue."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "status": "ok",
            "queued_at": now.isoformat(),
            "target_username": "bob",
            "queue_length": 5,
        }

        respx.post(f"{base_url}/api/v1/mq/pub").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.publish(
            target_username="bob",
            message='{"type": "hello"}',
        )

        assert isinstance(result, PublishResponse)
        assert result.status == "ok"
        assert result.target_username == "bob"
        assert result.queue_length == 5

    @respx.mock
    def test_publish_to_reserved_queue_autodetect(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test publish auto-detects rq_ prefix."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "status": "ok",
            "queued_at": now.isoformat(),
            "target_username": "rq_abc123",
            "queue_length": 1,
        }

        respx.post(f"{base_url}/api/v1/mq/pub").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.publish(
            target_username="rq_abc123",  # Reserved queue ID
            message='{"response": "data"}',
        )

        assert result.target_username == "rq_abc123"

    @respx.mock
    def test_publish_user_not_found(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test publish to non-existent user."""
        from syfthub_sdk.exceptions import NotFoundError

        respx.post(f"{base_url}/api/v1/mq/pub").mock(
            return_value=httpx.Response(
                404,
                json={"detail": "User 'nonexistent' not found"},
            )
        )

        with pytest.raises(NotFoundError):
            authenticated_client.mq.publish(
                target_username="nonexistent", message="test"
            )


# =============================================================================
# Test: Consume
# =============================================================================


class TestConsume:
    """Tests for consume method."""

    @respx.mock
    def test_consume_from_own_queue(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test consuming from own queue."""
        now = datetime.now(timezone.utc)
        mock_response = {
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
        }

        respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.consume(limit=10)

        assert isinstance(result, ConsumeResponse)
        assert len(result.messages) == 1
        assert result.messages[0].from_username == "alice"
        assert result.remaining == 0

    @respx.mock
    def test_consume_empty_queue(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test consuming from empty queue."""
        respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=httpx.Response(
                200,
                json={"messages": [], "remaining": 0},
            )
        )

        result = authenticated_client.mq.consume()

        assert len(result.messages) == 0
        assert result.remaining == 0

    @respx.mock
    def test_consume_from_reserved_queue(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test consuming from reserved queue with queue_id and token."""
        now = datetime.now(timezone.utc)
        mock_response = {
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
        }

        route = respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.consume(
            queue_id="rq_abc123",
            token="secret_token",
            limit=10,
        )

        assert len(result.messages) == 1
        assert result.messages[0].id == "msg-456"

        # Verify queue_id and token were passed
        import json

        request = route.calls[0].request
        body = json.loads(request.content)
        assert body["queue_id"] == "rq_abc123"
        assert body["token"] == "secret_token"

    @respx.mock
    def test_consume_reserved_queue_invalid_token(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test consume with invalid token fails."""
        from syfthub_sdk.exceptions import AuthorizationError

        respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=httpx.Response(
                403,
                json={"detail": "Invalid token for this reserved queue"},
            )
        )

        with pytest.raises(AuthorizationError):
            authenticated_client.mq.consume(queue_id="rq_abc123", token="wrong_token")

    @respx.mock
    def test_consume_without_reserved_queue_params(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test that consume without queue_id/token doesn't include them."""
        mock_response = {
            "messages": [],
            "remaining": 0,
        }

        route = respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        authenticated_client.mq.consume(limit=5)

        import json

        request = route.calls[0].request
        body = json.loads(request.content)
        assert body["limit"] == 5
        assert "queue_id" not in body
        assert "token" not in body


# =============================================================================
# Test: Reserve Queue
# =============================================================================


class TestReserveQueue:
    """Tests for mq.reserve_queue()."""

    @respx.mock
    def test_reserve_queue_success(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test reserving a queue successfully."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "queue_id": "rq_abc123def456",
            "token": "secret_token_xyz",
            "expires_at": now.isoformat(),
            "owner_username": "testuser",
        }

        respx.post(f"{base_url}/api/v1/mq/reserve").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.reserve_queue(ttl_seconds=300)

        assert isinstance(result, ReserveQueueResponse)
        assert result.queue_id == "rq_abc123def456"
        assert result.token == "secret_token_xyz"
        assert result.owner_username == "testuser"
        assert result.expires_at is not None

    @respx.mock
    def test_reserve_queue_custom_ttl(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test reserving a queue with custom TTL."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "queue_id": "rq_custom",
            "token": "token",
            "expires_at": now.isoformat(),
            "owner_username": "testuser",
        }

        route = respx.post(f"{base_url}/api/v1/mq/reserve").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        authenticated_client.mq.reserve_queue(ttl_seconds=600)

        # Verify the TTL was passed in the request
        assert route.called
        import json

        request = route.calls[0].request
        body = json.loads(request.content)
        assert body["ttl_seconds"] == 600


# =============================================================================
# Test: Release Queue
# =============================================================================


class TestReleaseQueue:
    """Tests for mq.release_queue()."""

    @respx.mock
    def test_release_queue_success(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test releasing a queue successfully."""
        mock_response = {
            "status": "ok",
            "cleared": 5,
            "queue_id": "rq_test123",
        }

        respx.post(f"{base_url}/api/v1/mq/release").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.release_queue(
            queue_id="rq_test123",
            token="secret_token",
        )

        assert isinstance(result, ReleaseQueueResponse)
        assert result.status == "ok"
        assert result.cleared == 5
        assert result.queue_id == "rq_test123"

    @respx.mock
    def test_release_queue_passes_credentials(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test that release passes queue_id and token."""
        mock_response = {
            "status": "ok",
            "cleared": 0,
            "queue_id": "rq_test",
        }

        route = respx.post(f"{base_url}/api/v1/mq/release").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        authenticated_client.mq.release_queue(
            queue_id="rq_myqueue",
            token="my_secret",
        )

        assert route.called
        import json

        request = route.calls[0].request
        body = json.loads(request.content)
        assert body["queue_id"] == "rq_myqueue"
        assert body["token"] == "my_secret"

    @respx.mock
    def test_release_queue_not_found(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test release of non-existent queue."""
        from syfthub_sdk.exceptions import NotFoundError

        respx.post(f"{base_url}/api/v1/mq/release").mock(
            return_value=httpx.Response(
                404,
                json={"detail": "Reserved queue 'rq_nonexistent' not found or expired"},
            )
        )

        with pytest.raises(NotFoundError):
            authenticated_client.mq.release_queue(
                queue_id="rq_nonexistent", token="token"
            )


# =============================================================================
# Test: Other MQ Operations
# =============================================================================


class TestQueueStatus:
    """Tests for queue status method."""

    @respx.mock
    def test_status_success(self, authenticated_client: SyftHubClient, base_url: str):
        """Test getting queue status."""
        mock_response = {
            "queue_length": 10,
            "username": "testuser",
        }

        respx.get(f"{base_url}/api/v1/mq/status").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.status()

        assert isinstance(result, QueueStatusResponse)
        assert result.queue_length == 10
        assert result.username == "testuser"


class TestPeek:
    """Tests for peek method."""

    @respx.mock
    def test_peek_messages(self, authenticated_client: SyftHubClient, base_url: str):
        """Test peeking at messages."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "messages": [
                {
                    "id": "msg-peek",
                    "from_username": "charlie",
                    "from_user_id": 4,
                    "message": "Peeked message",
                    "queued_at": now.isoformat(),
                }
            ],
            "total": 3,
        }

        respx.post(f"{base_url}/api/v1/mq/peek").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.peek(limit=5)

        assert isinstance(result, PeekResponse)
        assert len(result.messages) == 1
        assert result.total == 3


class TestClear:
    """Tests for clear method."""

    @respx.mock
    def test_clear_queue(self, authenticated_client: SyftHubClient, base_url: str):
        """Test clearing queue."""
        mock_response = {
            "status": "ok",
            "cleared": 15,
        }

        respx.delete(f"{base_url}/api/v1/mq/clear").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.clear()

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
            owner_username="testuser",
        )
        assert response.queue_id.startswith("rq_")
        assert response.owner_username == "testuser"

    def test_release_queue_response_model(self):
        """Test ReleaseQueueResponse model."""
        response = ReleaseQueueResponse(
            status="ok",
            cleared=10,
            queue_id="rq_abc123",
        )
        assert response.cleared == 10
        assert response.status == "ok"
