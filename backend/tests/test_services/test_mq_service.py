"""Tests for MessageQueueService."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from syfthub.schemas.mq import (
    ConsumeResponse,
    PublishResponse,
    ReleaseQueueResponse,
    ReserveQueueResponse,
)
from syfthub.schemas.user import User
from syfthub.services.mq_service import MessageQueueService


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client."""
    redis = AsyncMock()
    redis.llen = AsyncMock(return_value=5)
    redis.lpush = AsyncMock()
    redis.rpop = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    redis.delete = AsyncMock()
    redis.exists = AsyncMock(return_value=True)
    redis.hget = AsyncMock(return_value="valid_token")
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()

    # Mock pipeline context manager
    pipeline = AsyncMock()
    pipeline.hset = MagicMock()
    pipeline.expire = MagicMock()
    pipeline.delete = MagicMock()
    pipeline.execute = AsyncMock()

    redis.pipeline = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=pipeline), __aexit__=AsyncMock()
        )
    )
    return redis


@pytest.fixture
def mock_user_repository():
    """Create a mock user repository."""
    repo = MagicMock()
    return repo


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.redis_mq_prefix = "mq"
    settings.redis_mq_max_queue_size = 1000
    return settings


@pytest.fixture
def mq_service(mock_redis, mock_user_repository, mock_settings):
    """Create MessageQueueService with mocks."""
    with patch("syfthub.services.mq_service.get_settings", return_value=mock_settings):
        service = MessageQueueService(mock_redis, mock_user_repository)
        return service


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        role="user",
        is_active=True,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        age=25,
        password_hash="hashed_pass",
    )


@pytest.fixture
def mock_target_user():
    """Create a mock target user for testing."""
    return User(
        id=2,
        username="targetuser",
        email="target@example.com",
        full_name="Target User",
        role="user",
        is_active=True,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        age=30,
        password_hash="hashed_pass",
    )


# =============================================================================
# Publish Tests
# =============================================================================


class TestPublishToUserQueue:
    """Tests for publishing to user queues."""

    @pytest.mark.asyncio
    async def test_publish_to_user_success(
        self, mq_service: MessageQueueService, mock_user: User, mock_target_user: User
    ):
        """Test successful publish to user queue."""
        mq_service.user_repo.get_by_username = MagicMock(return_value=mock_target_user)
        mq_service.redis.llen = AsyncMock(side_effect=[5, 6])  # Before and after push

        result = await mq_service.publish(
            sender=mock_user,
            target_username="targetuser",
            message='{"type": "test"}',
        )

        assert isinstance(result, PublishResponse)
        assert result.status == "ok"
        assert result.target_username == "targetuser"
        assert result.queue_length == 6
        mq_service.redis.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_to_nonexistent_user(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test publish to non-existent user fails."""
        mq_service.user_repo.get_by_username = MagicMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.publish(
                sender=mock_user,
                target_username="nonexistent",
                message="test",
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_publish_to_inactive_user(
        self, mq_service: MessageQueueService, mock_user: User, mock_target_user: User
    ):
        """Test publish to inactive user fails."""
        mock_target_user.is_active = False
        mq_service.user_repo.get_by_username = MagicMock(return_value=mock_target_user)

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.publish(
                sender=mock_user,
                target_username="targetuser",
                message="test",
            )

        assert exc_info.value.status_code == 400
        assert "not active" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_publish_queue_full(
        self, mq_service: MessageQueueService, mock_user: User, mock_target_user: User
    ):
        """Test publish fails when queue is full."""
        mq_service.user_repo.get_by_username = MagicMock(return_value=mock_target_user)
        mq_service.redis.llen = AsyncMock(return_value=1000)  # At max capacity

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.publish(
                sender=mock_user,
                target_username="targetuser",
                message="test",
            )

        assert exc_info.value.status_code == 429
        assert "full" in exc_info.value.detail


class TestPublishToReservedQueue:
    """Tests for publishing to reserved queues."""

    @pytest.mark.asyncio
    async def test_publish_to_reserved_queue_autodetect(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test publish auto-detects rq_ prefix and routes to reserved queue."""
        mq_service.redis.exists = AsyncMock(return_value=True)
        mq_service.redis.llen = AsyncMock(side_effect=[5, 6])

        result = await mq_service.publish(
            sender=mock_user,
            target_username="rq_abc123def456",
            message='{"response": "test"}',
        )

        assert isinstance(result, PublishResponse)
        assert result.status == "ok"
        assert result.target_username == "rq_abc123def456"
        mq_service.redis.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_to_nonexistent_reserved_queue(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test publish to non-existent reserved queue fails."""
        mq_service.redis.exists = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.publish(
                sender=mock_user,
                target_username="rq_nonexistent",
                message="test",
            )

        assert exc_info.value.status_code == 404
        assert "not found or expired" in exc_info.value.detail


# =============================================================================
# Consume Tests
# =============================================================================


class TestConsumeFromUserQueue:
    """Tests for consuming from user queues."""

    @pytest.mark.asyncio
    async def test_consume_from_own_queue(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test consuming messages from own queue."""
        now = datetime.now(timezone.utc)
        message_data = {
            "id": "msg-123",
            "from_username": "sender",
            "from_user_id": 2,
            "message": '{"type": "test"}',
            "queued_at": now.isoformat(),
        }
        mq_service.redis.rpop = AsyncMock(side_effect=[json.dumps(message_data), None])
        mq_service.redis.llen = AsyncMock(return_value=0)

        result = await mq_service.consume(user=mock_user, limit=10)

        assert isinstance(result, ConsumeResponse)
        assert len(result.messages) == 1
        assert result.messages[0].id == "msg-123"
        assert result.messages[0].from_username == "sender"
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_consume_empty_queue(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test consuming from empty queue."""
        mq_service.redis.rpop = AsyncMock(return_value=None)
        mq_service.redis.llen = AsyncMock(return_value=0)

        result = await mq_service.consume(user=mock_user, limit=10)

        assert len(result.messages) == 0
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_consume_respects_limit(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test consume respects the limit parameter."""
        now = datetime.now(timezone.utc)
        messages = [
            json.dumps(
                {
                    "id": f"msg-{i}",
                    "from_username": "sender",
                    "from_user_id": 2,
                    "message": f"message {i}",
                    "queued_at": now.isoformat(),
                }
            )
            for i in range(5)
        ]
        # Return 3 messages then None
        mq_service.redis.rpop = AsyncMock(side_effect=[*messages[:3], None])
        mq_service.redis.llen = AsyncMock(return_value=2)

        result = await mq_service.consume(user=mock_user, limit=3)

        assert len(result.messages) == 3
        assert result.remaining == 2


class TestConsumeFromReservedQueue:
    """Tests for consuming from reserved queues."""

    @pytest.mark.asyncio
    async def test_consume_from_reserved_queue(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test consuming from reserved queue with queue_id and token."""
        now = datetime.now(timezone.utc)
        message_data = {
            "id": "msg-123",
            "from_username": "sender",
            "from_user_id": 2,
            "message": '{"response": "data"}',
            "queued_at": now.isoformat(),
        }
        mq_service.redis.hget = AsyncMock(return_value="valid_token")
        mq_service.redis.rpop = AsyncMock(side_effect=[json.dumps(message_data), None])
        mq_service.redis.llen = AsyncMock(return_value=0)

        result = await mq_service.consume(
            user=mock_user,
            limit=10,
            queue_id="rq_abc123",
            token="valid_token",
        )

        assert len(result.messages) == 1
        assert result.messages[0].id == "msg-123"

    @pytest.mark.asyncio
    async def test_consume_reserved_queue_invalid_prefix(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test consume fails if queue_id doesn't start with rq_."""
        with pytest.raises(HTTPException) as exc_info:
            await mq_service.consume(
                user=mock_user,
                queue_id="invalid_queue",
                token="token",
            )

        assert exc_info.value.status_code == 400
        assert "rq_" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_consume_reserved_queue_missing_token(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test consume fails if queue_id provided without token."""
        with pytest.raises(HTTPException) as exc_info:
            await mq_service.consume(
                user=mock_user,
                queue_id="rq_abc123",
                token=None,
            )

        assert exc_info.value.status_code == 400
        assert "token is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_consume_reserved_queue_invalid_token(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test consume fails with invalid token."""
        mq_service.redis.hget = AsyncMock(return_value="correct_token")

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.consume(
                user=mock_user,
                queue_id="rq_abc123",
                token="wrong_token",
            )

        assert exc_info.value.status_code == 403
        assert "Invalid queue token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_consume_reserved_queue_not_found(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test consume fails if reserved queue not found."""
        mq_service.redis.hget = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.consume(
                user=mock_user,
                queue_id="rq_nonexistent",
                token="token",
            )

        assert exc_info.value.status_code == 404
        assert "not found or expired" in exc_info.value.detail


# =============================================================================
# Reserve Queue Tests
# =============================================================================


class TestReserveQueue:
    """Tests for reserving ephemeral queues."""

    @pytest.mark.asyncio
    async def test_reserve_queue_success(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test successful queue reservation."""
        result = await mq_service.reserve_queue(user=mock_user, ttl=300)

        assert isinstance(result, ReserveQueueResponse)
        assert result.queue_id.startswith("rq_")
        assert len(result.token) > 0
        assert result.ttl == 300
        assert result.expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_reserve_queue_custom_ttl(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test queue reservation with custom TTL."""
        result = await mq_service.reserve_queue(user=mock_user, ttl=600)

        assert result.ttl == 600
        # Check expires_at is approximately TTL seconds in the future
        expected_expiry = datetime.now(timezone.utc) + timedelta(seconds=600)
        assert abs((result.expires_at - expected_expiry).total_seconds()) < 5


# =============================================================================
# Release Queue Tests
# =============================================================================


class TestReleaseQueue:
    """Tests for releasing reserved queues."""

    @pytest.mark.asyncio
    async def test_release_queue_success(self, mq_service: MessageQueueService):
        """Test successful queue release."""
        mq_service.redis.hget = AsyncMock(return_value="valid_token")
        mq_service.redis.llen = AsyncMock(return_value=5)

        result = await mq_service.release_queue(
            queue_id="rq_abc123",
            token="valid_token",
        )

        assert isinstance(result, ReleaseQueueResponse)
        assert result.queue_id == "rq_abc123"
        assert result.messages_cleared == 5

    @pytest.mark.asyncio
    async def test_release_queue_invalid_token(self, mq_service: MessageQueueService):
        """Test release fails with invalid token."""
        mq_service.redis.hget = AsyncMock(return_value="correct_token")

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.release_queue(
                queue_id="rq_abc123",
                token="wrong_token",
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_release_queue_not_found(self, mq_service: MessageQueueService):
        """Test release fails if queue not found."""
        mq_service.redis.hget = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.release_queue(
                queue_id="rq_nonexistent",
                token="token",
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Queue Status and Other Operations
# =============================================================================


class TestQueueStatus:
    """Tests for queue status operations."""

    @pytest.mark.asyncio
    async def test_get_status(self, mq_service: MessageQueueService, mock_user: User):
        """Test getting queue status."""
        mq_service.redis.llen = AsyncMock(return_value=10)

        result = await mq_service.get_status(user=mock_user)

        assert result.queue_length == 10
        assert result.username == mock_user.username


class TestPeekMessages:
    """Tests for peeking at messages."""

    @pytest.mark.asyncio
    async def test_peek_messages(
        self, mq_service: MessageQueueService, mock_user: User
    ):
        """Test peeking at messages without consuming."""
        now = datetime.now(timezone.utc)
        messages = [
            json.dumps(
                {
                    "id": f"msg-{i}",
                    "from_username": "sender",
                    "from_user_id": 2,
                    "message": f"message {i}",
                    "queued_at": now.isoformat(),
                }
            )
            for i in range(3)
        ]
        mq_service.redis.llen = AsyncMock(return_value=3)
        mq_service.redis.lrange = AsyncMock(return_value=messages)

        result = await mq_service.peek(user=mock_user, limit=10)

        assert result.total == 3
        # Messages should still be in queue (peek doesn't remove)
        mq_service.redis.rpop.assert_not_called()


class TestClearQueue:
    """Tests for clearing queue."""

    @pytest.mark.asyncio
    async def test_clear_queue(self, mq_service: MessageQueueService, mock_user: User):
        """Test clearing all messages from queue."""
        mq_service.redis.llen = AsyncMock(return_value=15)

        count = await mq_service.clear_queue(user=mock_user)

        assert count == 15
        mq_service.redis.delete.assert_called_once()
