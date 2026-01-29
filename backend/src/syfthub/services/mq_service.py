"""Message queue service for pub/consume operations."""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
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

    def _is_reserved_queue_id(self, target: str) -> bool:
        """Check if target is a reserved queue ID.

        Args:
            target: The target identifier.

        Returns:
            True if target is a reserved queue ID (starts with 'rq_').
        """
        return target.startswith("rq_")

    async def publish(
        self,
        sender: User,
        target_username: str,
        message: str,
    ) -> PublishResponse:
        """Publish a message to another user's queue or a reserved queue.

        Supports two target types:
        1. Regular username: Publishes to that user's queue
        2. Reserved queue ID (rq_*): Publishes to that reserved queue

        Args:
            sender: The authenticated user sending the message.
            target_username: Username of the recipient OR reserved queue ID.
            message: The message payload.

        Returns:
            PublishResponse with status and queue information.

        Raises:
            HTTPException: If target not found or queue is full.
        """
        # Check if target is a reserved queue
        if self._is_reserved_queue_id(target_username):
            return await self._publish_to_reserved_queue(
                sender=sender,
                queue_id=target_username,
                message=message,
            )

        # Regular user queue flow
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
        """Internal method to publish to a reserved queue.

        Args:
            sender: The authenticated user sending the message.
            queue_id: The reserved queue identifier.
            message: The message payload.

        Returns:
            PublishResponse with status and queue info.

        Raises:
            HTTPException: If queue not found or expired.
        """
        # Verify queue exists (but don't require token - anyone can publish)
        meta_key = self._get_reserved_queue_meta_key(queue_id)
        metadata = await self.redis.hgetall(meta_key)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reserved queue '{queue_id}' not found or expired",
            )

        queue_key = self._get_reserved_queue_key(queue_id)

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

        # Ensure queue inherits TTL from metadata
        ttl = await self.redis.ttl(meta_key)
        if ttl > 0:
            await self.redis.expire(queue_key, ttl)

        queue_length = await self.redis.llen(queue_key)

        return PublishResponse(
            status="ok",
            queued_at=now,
            target_username=queue_id,  # Return queue_id as target
            queue_length=queue_length,
        )

    async def consume(
        self,
        user: User,
        limit: int = 10,
        queue_id: str | None = None,
        token: str | None = None,
    ) -> ConsumeResponse:
        """Consume messages from the user's own queue or a reserved queue.

        Supports two modes:
        1. Regular mode (no queue_id): Consume from authenticated user's own queue
        2. Reserved queue mode (queue_id + token): Consume from a reserved queue

        Args:
            user: The authenticated user consuming messages.
            limit: Maximum number of messages to retrieve.
            queue_id: Optional reserved queue ID (rq_*) to consume from.
            token: Required when consuming from a reserved queue.

        Returns:
            ConsumeResponse with messages and remaining count.

        Raises:
            HTTPException: If reserved queue not found or token invalid.
        """
        # If queue_id provided, use reserved queue mode
        if queue_id and self._is_reserved_queue_id(queue_id):
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Token is required when consuming from a reserved queue",
                )
            return await self._consume_from_reserved_queue(queue_id, token, limit)

        # Regular user queue mode
        queue_key = self._get_queue_key(user.id)
        messages: List[Message] = []

        # Pop messages from queue (RPOP for FIFO)
        for _ in range(limit):
            raw_message = await self.redis.rpop(queue_key)
            if raw_message is None:
                break

            try:
                # Decode bytes if needed
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode()
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

    async def _consume_from_reserved_queue(
        self,
        queue_id: str,
        token: str,
        limit: int = 10,
    ) -> ConsumeResponse:
        """Internal method to consume from a reserved queue.

        Args:
            queue_id: The reserved queue identifier.
            token: The access token.
            limit: Maximum number of messages to retrieve.

        Returns:
            ConsumeResponse with messages and remaining count.

        Raises:
            HTTPException: If queue not found or token invalid.
        """
        # Validate access
        await self._validate_reserved_queue_token(queue_id, token)

        queue_key = self._get_reserved_queue_key(queue_id)
        messages: List[Message] = []

        # Pop messages from queue (RPOP for FIFO)
        for _ in range(limit):
            raw_message = await self.redis.rpop(queue_key)
            if raw_message is None:
                break

            try:
                # Decode bytes if needed
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode()
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

    # =========================================================================
    # Reserved Queue Methods (for tunneling support)
    # =========================================================================

    def _get_reserved_queue_key(self, queue_id: str) -> str:
        """Get the Redis key for a reserved queue's messages.

        Args:
            queue_id: The reserved queue identifier.

        Returns:
            The Redis key string.
        """
        return f"{self.settings.redis_mq_prefix}:reserved:{queue_id}"

    def _get_reserved_queue_meta_key(self, queue_id: str) -> str:
        """Get the Redis key for a reserved queue's metadata.

        Args:
            queue_id: The reserved queue identifier.

        Returns:
            The Redis key string.
        """
        return f"{self.settings.redis_mq_prefix}:reserved:{queue_id}:meta"

    def _hash_token(self, token: str) -> str:
        """Hash a token for secure storage/comparison.

        Args:
            token: The raw token.

        Returns:
            SHA-256 hash of the token.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    async def reserve_queue(
        self,
        user: User,
        ttl_seconds: int = 300,
    ) -> ReserveQueueResponse:
        """Reserve a temporary queue for receiving messages.

        Creates a new reserved queue with a unique ID and access token.
        The queue will automatically expire after the TTL.

        Args:
            user: The authenticated user reserving the queue.
            ttl_seconds: Time-to-live in seconds (default 300).

        Returns:
            ReserveQueueResponse with queue credentials.
        """
        # Generate unique queue ID and token
        queue_id = f"rq_{uuid.uuid4().hex}"
        token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(token)

        # Calculate expiration
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        # Store queue metadata
        meta_key = self._get_reserved_queue_meta_key(queue_id)
        queue_key = self._get_reserved_queue_key(queue_id)

        metadata = {
            "owner_user_id": user.id,
            "owner_username": user.username,
            "token_hash": token_hash,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        # Store metadata and set TTL on both keys
        await self.redis.hset(meta_key, mapping=metadata)
        await self.redis.expire(meta_key, ttl_seconds)
        # Also set TTL on the queue key (will be created when messages arrive)
        await self.redis.expire(queue_key, ttl_seconds)

        return ReserveQueueResponse(
            queue_id=queue_id,
            token=token,
            expires_at=expires_at,
            owner_username=user.username,
        )

    async def _validate_reserved_queue_token(
        self,
        queue_id: str,
        token: str,
    ) -> dict:
        """Validate access to a reserved queue.

        Args:
            queue_id: The reserved queue identifier.
            token: The access token.

        Returns:
            Queue metadata if valid.

        Raises:
            HTTPException: If queue not found, expired, or token invalid.
        """
        meta_key = self._get_reserved_queue_meta_key(queue_id)
        metadata = await self.redis.hgetall(meta_key)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reserved queue '{queue_id}' not found or expired",
            )

        # Decode bytes to strings if needed (Redis returns bytes)
        if isinstance(next(iter(metadata.keys()), None), bytes):
            metadata = {k.decode(): v.decode() for k, v in metadata.items()}

        # Verify token
        token_hash = self._hash_token(token)
        if token_hash != metadata.get("token_hash"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid token for this reserved queue",
            )

        return metadata

    async def release_queue(
        self,
        queue_id: str,
        token: str,
    ) -> ReleaseQueueResponse:
        """Release a reserved queue and clear its messages.

        Args:
            queue_id: The reserved queue identifier.
            token: The access token.

        Returns:
            ReleaseQueueResponse with status and cleared count.

        Raises:
            HTTPException: If queue not found or token invalid.
        """
        # Validate access
        await self._validate_reserved_queue_token(queue_id, token)

        queue_key = self._get_reserved_queue_key(queue_id)
        meta_key = self._get_reserved_queue_meta_key(queue_id)

        # Count messages before clearing
        count = await self.redis.llen(queue_key)

        # Delete both queue and metadata
        await self.redis.delete(queue_key, meta_key)

        return ReleaseQueueResponse(
            status="ok",
            cleared=int(count),
            queue_id=queue_id,
        )
