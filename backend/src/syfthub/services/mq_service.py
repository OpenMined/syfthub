"""Message queue service for pub/consume operations."""

import json
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException, status
from redis.asyncio import Redis

from syfthub.core.config import get_settings
from syfthub.repositories.user import UserRepository
from syfthub.schemas.mq import (
    ConsumeResponse,
    Message,
    PeekResponse,
    PublishResponse,
    QueueStatusResponse,
)
from syfthub.schemas.user import User


class MessageQueueService:
    """Service for message queue operations using Redis."""

    def __init__(self, redis_client: Redis, user_repository: UserRepository):
        """Initialize the message queue service.

        Args:
            redis_client: The async Redis client.
            user_repository: Repository for user lookups.
        """
        self.redis = redis_client
        self.user_repo = user_repository
        self.settings = get_settings()

    def _get_queue_key(self, user_id: int) -> str:
        """Get the Redis key for a user's message queue.

        Args:
            user_id: The user's ID.

        Returns:
            The Redis key string.
        """
        return f"{self.settings.redis_mq_prefix}:{user_id}"

    async def publish(
        self,
        sender: User,
        target_username: str,
        message: str,
    ) -> PublishResponse:
        """Publish a message to another user's queue.

        Args:
            sender: The authenticated user sending the message.
            target_username: Username of the recipient.
            message: The message payload.

        Returns:
            PublishResponse with status and queue information.

        Raises:
            HTTPException: If target user not found or queue is full.
        """
        # Look up target user
        target_user = self.user_repo.get_by_username(target_username)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{target_username}' not found",
            )

        if not target_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User '{target_username}' is not active",
            )

        queue_key = self._get_queue_key(target_user.id)

        # Check queue size limit
        current_size = await self.redis.llen(queue_key)
        if current_size >= self.settings.redis_mq_max_queue_size:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Queue for user '{target_username}' is full",
            )

        # Create message envelope
        now = datetime.now(timezone.utc)
        message_envelope = {
            "id": str(uuid.uuid4()),
            "from_username": sender.username,
            "from_user_id": sender.id,
            "message": message,
            "queued_at": now.isoformat(),
        }

        # Push to queue (LPUSH for FIFO when consuming with RPOP)
        await self.redis.lpush(queue_key, json.dumps(message_envelope))
        queue_length = await self.redis.llen(queue_key)

        return PublishResponse(
            status="ok",
            queued_at=now,
            target_username=target_username,
            queue_length=queue_length,
        )

    async def consume(
        self,
        user: User,
        limit: int = 10,
    ) -> ConsumeResponse:
        """Consume messages from the user's own queue.

        Args:
            user: The authenticated user consuming messages.
            limit: Maximum number of messages to retrieve.

        Returns:
            ConsumeResponse with messages and remaining count.
        """
        queue_key = self._get_queue_key(user.id)
        messages: List[Message] = []

        # Pop messages from queue (RPOP for FIFO)
        for _ in range(limit):
            raw_message = await self.redis.rpop(queue_key)
            if raw_message is None:
                break

            try:
                data = json.loads(raw_message)
                messages.append(
                    Message(
                        id=data["id"],
                        from_username=data["from_username"],
                        from_user_id=data["from_user_id"],
                        message=data["message"],
                        queued_at=datetime.fromisoformat(data["queued_at"]),
                    )
                )
            except (json.JSONDecodeError, KeyError):
                # Skip malformed messages
                continue

        remaining = await self.redis.llen(queue_key)

        return ConsumeResponse(
            messages=messages,
            remaining=remaining,
        )

    async def get_status(self, user: User) -> QueueStatusResponse:
        """Get the status of the user's queue.

        Args:
            user: The authenticated user.

        Returns:
            QueueStatusResponse with queue length.
        """
        queue_key = self._get_queue_key(user.id)
        queue_length = await self.redis.llen(queue_key)

        return QueueStatusResponse(
            queue_length=queue_length,
            username=user.username,
        )

    async def peek(
        self,
        user: User,
        limit: int = 10,
    ) -> PeekResponse:
        """Peek at messages in the user's queue without consuming them.

        Args:
            user: The authenticated user.
            limit: Maximum number of messages to peek.

        Returns:
            PeekResponse with messages (not removed from queue).
        """
        queue_key = self._get_queue_key(user.id)
        messages: List[Message] = []

        # Get messages without removing (LRANGE from end for FIFO order)
        # Note: LRANGE is 0-indexed, and we want oldest first (right side of list)
        total = await self.redis.llen(queue_key)
        if total > 0:
            # Get from the right (oldest) side first
            start = max(0, total - limit)
            raw_messages = await self.redis.lrange(queue_key, start, total - 1)

            # Reverse to get oldest first
            for raw_message in reversed(raw_messages):
                try:
                    data = json.loads(raw_message)
                    messages.append(
                        Message(
                            id=data["id"],
                            from_username=data["from_username"],
                            from_user_id=data["from_user_id"],
                            message=data["message"],
                            queued_at=datetime.fromisoformat(data["queued_at"]),
                        )
                    )
                except (json.JSONDecodeError, KeyError):
                    # Skip malformed messages
                    continue

        return PeekResponse(
            messages=messages,
            total=total,
        )

    async def clear_queue(self, user: User) -> int:
        """Clear all messages from the user's queue.

        Args:
            user: The authenticated user.

        Returns:
            Number of messages cleared.
        """
        queue_key = self._get_queue_key(user.id)
        count = await self.redis.llen(queue_key)
        await self.redis.delete(queue_key)
        return int(count)
