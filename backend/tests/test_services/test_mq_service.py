"""Tests for MessageQueueService."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syfthub.schemas.user import User
from syfthub.services.mq_service import MessageQueueService


class TestMessageQueueService:
    """Tests for MessageQueueService class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.llen = AsyncMock(return_value=0)
        redis.lpush = AsyncMock()
        redis.rpop = AsyncMock(return_value=None)
        redis.lrange = AsyncMock(return_value=[])
        redis.delete = AsyncMock()
        redis.hset = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})
        redis.expire = AsyncMock()
        redis.ttl = AsyncMock(return_value=300)
        return redis

    @pytest.fixture
    def mock_user_repo(self):
        """Create a mock user repository."""
        repo = MagicMock()
        return repo

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = MagicMock(spec=User)
        user.id = 1
        user.username = "alice"
        user.is_active = True
        return user

    @pytest.fixture
    def target_user(self):
        """Create a mock target user."""
        user = MagicMock(spec=User)
        user.id = 2
        user.username = "bob"
        user.is_active = True
        return user

    @pytest.fixture
    def mq_service(self, mock_redis, mock_user_repo):
        """Create MessageQueueService instance with mocks."""
        with patch("syfthub.services.mq_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.redis_mq_prefix = "mq"
            settings.redis_mq_max_queue_size = 1000
            mock_settings.return_value = settings
            return MessageQueueService(mock_redis, mock_user_repo)


class TestPublish(TestMessageQueueService):
    """Tests for publish method."""

    @pytest.mark.asyncio
    async def test_publish_to_user_queue(
        self, mq_service, mock_redis, mock_user_repo, mock_user, target_user
    ):
        """Test publishing a message to a user's queue."""
        mock_user_repo.get_by_username.return_value = target_user
        mock_redis.llen.return_value = 0

        response = await mq_service.publish(
            sender=mock_user,
            target_username="bob",
            message='{"hello": "world"}',
        )

        assert response.status == "ok"
        assert response.target_username == "bob"
        mock_redis.lpush.assert_called_once()
        mock_user_repo.get_by_username.assert_called_once_with("bob")

    @pytest.mark.asyncio
    async def test_publish_to_reserved_queue(self, mq_service, mock_redis, mock_user):
        """Test publishing a message to a reserved queue."""
        # Set up reserved queue metadata
        mock_redis.hgetall.return_value = {
            "owner_user_id": "1",
            "owner_username": "alice",
            "token_hash": "some_hash",
        }
        mock_redis.llen.return_value = 0
        mock_redis.ttl.return_value = 300

        response = await mq_service.publish(
            sender=mock_user,
            target_username="rq_abc123",
            message='{"test": "message"}',
        )

        assert response.status == "ok"
        assert response.target_username == "rq_abc123"
        mock_redis.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_to_nonexistent_reserved_queue(
        self, mq_service, mock_redis, mock_user
    ):
        """Test publishing to a reserved queue that doesn't exist."""
        mock_redis.hgetall.return_value = {}

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.publish(
                sender=mock_user,
                target_username="rq_nonexistent",
                message="test",
            )

        assert exc_info.value.status_code == 404
        assert "not found or expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_publish_to_nonexistent_user(
        self, mq_service, mock_user_repo, mock_user
    ):
        """Test publishing to a user that doesn't exist."""
        mock_user_repo.get_by_username.return_value = None

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.publish(
                sender=mock_user,
                target_username="nonexistent",
                message="test",
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_publish_queue_full(
        self, mq_service, mock_redis, mock_user_repo, mock_user, target_user
    ):
        """Test publishing when queue is full."""
        mock_user_repo.get_by_username.return_value = target_user
        mock_redis.llen.return_value = 1000  # Max queue size

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.publish(
                sender=mock_user,
                target_username="bob",
                message="test",
            )

        assert exc_info.value.status_code == 429
        assert "full" in exc_info.value.detail


class TestConsume(TestMessageQueueService):
    """Tests for consume method."""

    @pytest.mark.asyncio
    async def test_consume_from_own_queue(self, mq_service, mock_redis, mock_user):
        """Test consuming messages from own queue."""
        now = datetime.now(timezone.utc)
        message_data = {
            "id": "msg-123",
            "from_username": "bob",
            "from_user_id": 2,
            "message": "hello",
            "queued_at": now.isoformat(),
        }
        mock_redis.rpop.side_effect = [json.dumps(message_data), None]
        mock_redis.llen.return_value = 0

        response = await mq_service.consume(user=mock_user, limit=10)

        assert len(response.messages) == 1
        assert response.messages[0].from_username == "bob"
        assert response.messages[0].message == "hello"
        assert response.remaining == 0

    @pytest.mark.asyncio
    async def test_consume_from_reserved_queue(self, mq_service, mock_redis, mock_user):
        """Test consuming messages from a reserved queue with token."""
        # Set up reserved queue metadata with valid token hash
        token = "test_token"
        token_hash = mq_service._hash_token(token)
        mock_redis.hgetall.return_value = {
            b"owner_user_id": b"1",
            b"owner_username": b"alice",
            b"token_hash": token_hash.encode(),
        }

        now = datetime.now(timezone.utc)
        message_data = {
            "id": "msg-456",
            "from_username": "charlie",
            "from_user_id": 3,
            "message": "response",
            "queued_at": now.isoformat(),
        }
        mock_redis.rpop.side_effect = [json.dumps(message_data), None]
        mock_redis.llen.return_value = 0

        response = await mq_service.consume(
            user=mock_user,
            limit=10,
            queue_id="rq_test123",
            token=token,
        )

        assert len(response.messages) == 1
        assert response.messages[0].from_username == "charlie"
        assert response.messages[0].message == "response"

    @pytest.mark.asyncio
    async def test_consume_reserved_queue_missing_token(self, mq_service, mock_user):
        """Test consuming from reserved queue without token."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.consume(
                user=mock_user,
                limit=10,
                queue_id="rq_test123",
                token=None,
            )

        assert exc_info.value.status_code == 400
        assert "Token is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_consume_reserved_queue_invalid_token(
        self, mq_service, mock_redis, mock_user
    ):
        """Test consuming from reserved queue with invalid token."""
        mock_redis.hgetall.return_value = {
            b"owner_user_id": b"1",
            b"owner_username": b"alice",
            b"token_hash": b"different_hash",
        }

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.consume(
                user=mock_user,
                limit=10,
                queue_id="rq_test123",
                token="wrong_token",
            )

        assert exc_info.value.status_code == 403
        assert "Invalid token" in exc_info.value.detail


class TestReserveQueue(TestMessageQueueService):
    """Tests for reserve_queue method."""

    @pytest.mark.asyncio
    async def test_reserve_queue_success(self, mq_service, mock_redis, mock_user):
        """Test reserving a queue successfully."""
        response = await mq_service.reserve_queue(user=mock_user, ttl_seconds=300)

        assert response.queue_id.startswith("rq_")
        assert response.token is not None
        assert len(response.token) > 20  # Token should be substantial
        assert response.owner_username == "alice"
        assert response.expires_at is not None

        # Verify Redis calls
        mock_redis.hset.assert_called_once()
        assert mock_redis.expire.call_count == 2  # For meta key and queue key

    @pytest.mark.asyncio
    async def test_reserve_queue_custom_ttl(self, mq_service, mock_redis, mock_user):
        """Test reserving a queue with custom TTL."""
        response = await mq_service.reserve_queue(user=mock_user, ttl_seconds=600)

        assert response.queue_id.startswith("rq_")
        # Verify TTL was set correctly
        calls = mock_redis.expire.call_args_list
        assert any(call[0][1] == 600 for call in calls)


class TestReleaseQueue(TestMessageQueueService):
    """Tests for release_queue method."""

    @pytest.mark.asyncio
    async def test_release_queue_success(self, mq_service, mock_redis):
        """Test releasing a reserved queue successfully."""
        token = "valid_token"
        token_hash = mq_service._hash_token(token)
        mock_redis.hgetall.return_value = {
            b"owner_user_id": b"1",
            b"owner_username": b"alice",
            b"token_hash": token_hash.encode(),
        }
        mock_redis.llen.return_value = 5

        response = await mq_service.release_queue(
            queue_id="rq_test123",
            token=token,
        )

        assert response.status == "ok"
        assert response.cleared == 5
        assert response.queue_id == "rq_test123"
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_queue_not_found(self, mq_service, mock_redis):
        """Test releasing a queue that doesn't exist."""
        mock_redis.hgetall.return_value = {}

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.release_queue(
                queue_id="rq_nonexistent",
                token="any_token",
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_release_queue_invalid_token(self, mq_service, mock_redis):
        """Test releasing a queue with invalid token."""
        mock_redis.hgetall.return_value = {
            b"owner_user_id": b"1",
            b"owner_username": b"alice",
            b"token_hash": b"valid_hash",
        }

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mq_service.release_queue(
                queue_id="rq_test123",
                token="invalid_token",
            )

        assert exc_info.value.status_code == 403


class TestIsReservedQueueId(TestMessageQueueService):
    """Tests for _is_reserved_queue_id helper."""

    def test_reserved_queue_id_valid(self, mq_service):
        """Test detection of valid reserved queue IDs."""
        assert mq_service._is_reserved_queue_id("rq_abc123") is True
        assert mq_service._is_reserved_queue_id("rq_") is True

    def test_reserved_queue_id_invalid(self, mq_service):
        """Test detection of invalid reserved queue IDs."""
        assert mq_service._is_reserved_queue_id("bob") is False
        assert mq_service._is_reserved_queue_id("RQ_abc") is False
        assert mq_service._is_reserved_queue_id("") is False
