"""Message queue service for pub/consume operations."""

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

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
    ReleaseQueueResponse,
    ReserveQueueResponse,
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
        """Publish a message to another user's queue or a reserved queue.

        Args:
            sender: The authenticated user sending the message.
            target_username: Username of the recipient. If it starts with "rq_",
                it's automatically treated as a reserved queue ID.
            message: The message payload.

        Returns:
            PublishResponse with status and queue information.

        Raises:
            HTTPException: If target not found or queue is full.
        """
        # Auto-detect reserved queue by "rq_" prefix
        if target_username.startswith("rq_"):
            return await self._publish_to_reserved_queue(
                sender, target_username, message
            )
        return await self._publish_to_user_queue(sender, target_username, message)

    async def _publish_to_user_queue(
        self,
        sender: User,
        target_username: str,
        message: str,
    ) -> PublishResponse:
        """Publish a message to a user's queue.

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

    async def _publish_to_reserved_queue(
        self,
        sender: User,
        queue_id: str,
        message: str,
    ) -> PublishResponse:
        """Publish a message to a reserved queue.

        Args:
            sender: The authenticated user sending the message.
            queue_id: The reserved queue identifier.
            message: The message payload.

        Returns:
            PublishResponse with status and queue information.

        Raises:
            HTTPException: If queue not found or queue is full.
        """
        queue_key = self._get_reserved_queue_key(queue_id)
        meta_key = self._get_reserved_queue_meta_key(queue_id)

        # Check if queue exists
        exists = await self.redis.exists(meta_key)
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reserved queue '{queue_id}' not found or expired",
            )

        # Check queue size limit
        current_size = await self.redis.llen(queue_key)
        if current_size >= self.settings.redis_mq_max_queue_size:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Reserved queue '{queue_id}' is full",
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
            target_username=queue_id,  # Using queue_id as "username" for reserved queues
            queue_length=queue_length,
        )

    async def consume(
        self,
        user: User,
        limit: int = 10,
        queue_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> ConsumeResponse:
        """Consume messages from the user's queue or a reserved queue.

        Args:
            user: The authenticated user consuming messages.
            limit: Maximum number of messages to retrieve.
            queue_id: Optional reserved queue ID (must start with 'rq_').
                If provided, consumes from reserved queue instead of user's queue.
            token: Required when queue_id is provided. Authentication token for
                the reserved queue.

        Returns:
            ConsumeResponse with messages and remaining count.

        Raises:
            HTTPException: If queue_id is provided without token, or if
                queue not found / token invalid.
        """
        # Determine which queue to consume from
        if queue_id is not None:
            # Reserved queue - validate and consume
            if not queue_id.startswith("rq_"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="queue_id must start with 'rq_' prefix",
                )
            if token is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="token is required when consuming from reserved queue",
                )
            await self._validate_queue_token(queue_id, token)
            queue_key = self._get_reserved_queue_key(queue_id)
        else:
            # User's own queue
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

    # ==========================================================================
    # Reserved Queue Operations (for ephemeral queues used by aggregator/tunneling)
    # ==========================================================================

    def _get_reserved_queue_key(self, queue_id: str) -> str:
        """Get the Redis key for a reserved queue's data.

        Args:
            queue_id: The queue identifier.

        Returns:
            The Redis key string.
        """
        return f"{self.settings.redis_mq_prefix}:reserved:{queue_id}"

    def _get_reserved_queue_meta_key(self, queue_id: str) -> str:
        """Get the Redis key for a reserved queue's metadata.

        Args:
            queue_id: The queue identifier.

        Returns:
            The Redis key string.
        """
        return f"{self.settings.redis_mq_prefix}:reserved:{queue_id}:meta"

    async def _validate_queue_token(self, queue_id: str, token: str) -> None:
        """Validate that the token matches the queue's stored token.

        Args:
            queue_id: The queue identifier.
            token: The token to validate.

        Raises:
            HTTPException: If queue not found or token invalid.
        """
        meta_key = self._get_reserved_queue_meta_key(queue_id)
        stored_token = await self.redis.hget(meta_key, "token")

        if stored_token is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reserved queue '{queue_id}' not found or expired",
            )

        if stored_token != token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid queue token",
            )

    async def reserve_queue(self, user: User, ttl: int = 300) -> ReserveQueueResponse:
        """Reserve a new ephemeral queue.

        Args:
            user: The authenticated user reserving the queue.
            ttl: Time-to-live in seconds (default 300).

        Returns:
            ReserveQueueResponse with queue_id, token, and expiration.
        """
        # Generate unique queue ID and token
        queue_id = f"rq_{uuid.uuid4().hex[:16]}"
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)

        # Store metadata
        meta_key = self._get_reserved_queue_meta_key(queue_id)
        queue_key = self._get_reserved_queue_key(queue_id)

        # Use pipeline for atomic operation
        async with self.redis.pipeline() as pipe:
            # Store metadata as hash
            pipe.hset(
                meta_key,
                mapping={
                    "token": token,
                    "user_id": str(user.id),
                    "username": user.username,
                    "created_at": now.isoformat(),
                    "expires_at": expires_at.isoformat(),
                },
            )
            # Set TTL on metadata
            pipe.expire(meta_key, ttl)
            # Initialize empty list (will be created on first push, but set TTL now)
            # We use a sentinel value that will be removed on first real push
            # Actually, let's just set TTL when messages are pushed
            # For now, create an empty key with TTL
            pipe.delete(queue_key)  # Ensure clean state
            await pipe.execute()

        return ReserveQueueResponse(
            queue_id=queue_id,
            token=token,
            expires_at=expires_at,
            ttl=ttl,
        )

    async def release_queue(
        self,
        queue_id: str,
        token: str,
    ) -> ReleaseQueueResponse:
        """Release (delete) a reserved queue.

        Args:
            queue_id: The queue identifier.
            token: The authentication token.

        Returns:
            ReleaseQueueResponse with queue_id and messages cleared count.

        Raises:
            HTTPException: If queue not found or token invalid.
        """
        # Validate token
        await self._validate_queue_token(queue_id, token)

        meta_key = self._get_reserved_queue_meta_key(queue_id)
        queue_key = self._get_reserved_queue_key(queue_id)

        # Get message count before deletion
        count = await self.redis.llen(queue_key)

        # Delete both keys
        async with self.redis.pipeline() as pipe:
            pipe.delete(meta_key)
            pipe.delete(queue_key)
            await pipe.execute()

        return ReleaseQueueResponse(
            queue_id=queue_id,
            messages_cleared=int(count),
        )
