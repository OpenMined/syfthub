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
        request = route.calls[0].request
        import json

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
        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["queue_id"] == "rq_myqueue"
        assert body["token"] == "my_secret"


# =============================================================================
# Test: Consume with Reserved Queue
# =============================================================================


class TestConsumeReservedQueue:
    """Tests for mq.consume() with reserved queue support."""

    @respx.mock
    def test_consume_own_queue(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test consuming from own queue (default behavior)."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "messages": [
                {
                    "id": "msg-1",
                    "from_username": "alice",
                    "from_user_id": 2,
                    "message": "Hello",
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

    @respx.mock
    def test_consume_reserved_queue(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test consuming from a reserved queue."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "messages": [
                {
                    "id": "msg-2",
                    "from_username": "bob",
                    "from_user_id": 3,
                    "message": '{"response": "data"}',
                    "queued_at": now.isoformat(),
                }
            ],
            "remaining": 2,
        }

        route = respx.post(f"{base_url}/api/v1/mq/consume").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.consume(
            limit=10,
            queue_id="rq_reserved123",
            token="reserved_token",
        )

        assert isinstance(result, ConsumeResponse)
        assert len(result.messages) == 1
        assert result.remaining == 2

        # Verify queue_id and token were passed
        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["queue_id"] == "rq_reserved123"
        assert body["token"] == "reserved_token"

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

        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["limit"] == 5
        assert "queue_id" not in body
        assert "token" not in body


# =============================================================================
# Test: Publish to Reserved Queue
# =============================================================================


class TestPublishToReservedQueue:
    """Tests for mq.publish() with reserved queue target."""

    @respx.mock
    def test_publish_to_user_queue(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test publishing to a user's queue."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "status": "ok",
            "queued_at": now.isoformat(),
            "target_username": "alice",
            "queue_length": 1,
        }

        respx.post(f"{base_url}/api/v1/mq/pub").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.publish(
            target_username="alice",
            message='{"hello": "world"}',
        )

        assert isinstance(result, PublishResponse)
        assert result.target_username == "alice"
        assert result.queue_length == 1

    @respx.mock
    def test_publish_to_reserved_queue(
        self, authenticated_client: SyftHubClient, base_url: str
    ):
        """Test publishing to a reserved queue."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "status": "ok",
            "queued_at": now.isoformat(),
            "target_username": "rq_response123",
            "queue_length": 1,
        }

        route = respx.post(f"{base_url}/api/v1/mq/pub").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.publish(
            target_username="rq_response123",  # Reserved queue ID as target
            message='{"response": "data"}',
        )

        assert isinstance(result, PublishResponse)
        assert result.target_username == "rq_response123"

        # Verify the request
        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["target_username"] == "rq_response123"


# =============================================================================
# Test: Other MQ Operations
# =============================================================================


class TestOtherMQOperations:
    """Tests for other MQ operations."""

    @respx.mock
    def test_status(self, authenticated_client: SyftHubClient, base_url: str):
        """Test getting queue status."""
        mock_response = {
            "queue_length": 5,
            "username": "testuser",
        }

        respx.get(f"{base_url}/api/v1/mq/status").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.status()

        assert isinstance(result, QueueStatusResponse)
        assert result.queue_length == 5
        assert result.username == "testuser"

    @respx.mock
    def test_peek(self, authenticated_client: SyftHubClient, base_url: str):
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

    @respx.mock
    def test_clear(self, authenticated_client: SyftHubClient, base_url: str):
        """Test clearing the queue."""
        mock_response = {
            "status": "ok",
            "cleared": 10,
        }

        respx.delete(f"{base_url}/api/v1/mq/clear").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = authenticated_client.mq.clear()

        assert isinstance(result, ClearResponse)
        assert result.status == "ok"
        assert result.cleared == 10
