"""Message Queue resource for pub/consume operations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient


class MQMessage(BaseModel):
    """A message from the queue."""

    id: str = Field(..., description="Unique message identifier (UUID)")
    from_username: str = Field(..., description="Sender's username")
    from_user_id: int = Field(..., description="Sender's user ID")
    message: str = Field(..., description="The message payload")
    queued_at: datetime = Field(..., description="Timestamp when message was queued")


class PublishResponse(BaseModel):
    """Response after publishing a message."""

    status: str = Field(default="ok", description="Status of the publish operation")
    queued_at: datetime = Field(..., description="Timestamp when message was queued")
    target_username: str = Field(..., description="Username of the recipient")
    queue_length: int = Field(
        ..., ge=0, description="Current queue length after publish"
    )


class ConsumeResponse(BaseModel):
    """Response with consumed messages."""

    messages: list[MQMessage] = Field(
        default_factory=list, description="List of consumed messages"
    )
    remaining: int = Field(
        ..., ge=0, description="Number of messages remaining in queue"
    )


class QueueStatusResponse(BaseModel):
    """Response with queue status information."""

    queue_length: int = Field(
        ..., ge=0, description="Current number of messages in queue"
    )
    username: str = Field(..., description="Username of the queue owner")


class PeekResponse(BaseModel):
    """Response with peeked messages (not consumed)."""

    messages: list[MQMessage] = Field(
        default_factory=list, description="List of messages (not removed from queue)"
    )
    total: int = Field(..., ge=0, description="Total number of messages in queue")


class ClearResponse(BaseModel):
    """Response after clearing the queue."""

    status: str = Field(default="ok", description="Status of the clear operation")
    cleared: int = Field(..., ge=0, description="Number of messages cleared")


# ==============================================================================
# Reserved Queue Models (for ephemeral queues used by aggregator/tunneling)
# ==============================================================================


class ReserveQueueResponse(BaseModel):
    """Response after reserving an ephemeral queue."""

    queue_id: str = Field(
        ..., description="Unique queue identifier (starts with 'rq_')"
    )
    token: str = Field(..., description="Secret token for consuming from this queue")
    expires_at: datetime = Field(..., description="When the queue will expire")
    ttl: int = Field(..., description="TTL in seconds")


class ReleaseQueueResponse(BaseModel):
    """Response after releasing a reserved queue."""

    queue_id: str = Field(..., description="Queue identifier that was released")
    messages_cleared: int = Field(
        ..., ge=0, description="Number of messages that were in the queue"
    )


class MQResource:
    """Message Queue operations for pub/consume messaging.

    This resource provides access to the Redis-backed message queue system
    for asynchronous user-to-user messaging and ephemeral reserved queues.

    Example:
        # Publish a message to another user
        result = client.mq.publish(
            target_username="bob",
            message='{"type": "hello", "data": "Hi Bob!"}'
        )
        print(f"Message queued at {result.queued_at}")

        # Consume messages from your queue
        response = client.mq.consume(limit=10)
        for msg in response.messages:
            print(f"From {msg.from_username}: {msg.message}")

        # Check queue status
        status = client.mq.status()
        print(f"You have {status.queue_length} messages waiting")

        # Peek without consuming
        peek = client.mq.peek(limit=5)
        print(f"Next messages: {peek.messages}")

        # Clear your queue
        cleared = client.mq.clear()
        print(f"Cleared {cleared.cleared} messages")

    Reserved Queue Example:
        # Reserve a temporary queue for receiving responses
        queue = client.mq.reserve_queue(ttl=300)
        print(f"Reserved queue: {queue.queue_id}")

        # Share queue_id with another service (it starts with 'rq_')
        # Publish to reserved queue using the queue_id as target_username
        client.mq.publish(
            target_username=queue.queue_id,  # rq_ prefix auto-detected
            message='{"type": "response", "data": "Hello!"}'
        )

        # Consume from the reserved queue
        response = client.mq.consume(
            queue_id=queue.queue_id,
            token=queue.token,
            limit=10
        )

        # Release when done
        client.mq.release_queue(
            queue_id=queue.queue_id,
            token=queue.token
        )
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize the MQ resource.

        Args:
            http: HTTP client for making requests.
        """
        self._http = http

    def publish(
        self,
        *,
        target_username: str,
        message: str,
    ) -> PublishResponse:
        """Publish a message to a user's queue or a reserved queue.

        The target type is auto-detected by prefix:
        - Regular username (e.g., "alice") - publishes to user's queue
        - Reserved queue ID (e.g., "rq_abc123") - publishes to reserved queue

        Args:
            target_username: Username of the recipient or reserved queue ID
                (reserved queues start with 'rq_' prefix).
            message: The message payload (1-65536 characters, can be JSON string).

        Returns:
            PublishResponse with status and queue information.

        Raises:
            NotFoundError: If target user or queue doesn't exist.
            ValidationError: If target user is not active or queue is full.
            AuthenticationError: If not authenticated.
        """
        response = self._http.post(
            "/api/v1/mq/pub",
            json={"target_username": target_username, "message": message},
        )
        return PublishResponse.model_validate(response)

    def consume(
        self,
        *,
        limit: int = 10,
        queue_id: str | None = None,
        token: str | None = None,
    ) -> ConsumeResponse:
        """Consume messages from your queue or a reserved queue.

        By default, consumes from the authenticated user's queue.
        If queue_id is provided (with 'rq_' prefix), consumes from that
        reserved queue using the provided token for authentication.

        Messages are returned in FIFO order (oldest first) and are
        removed from the queue.

        Args:
            limit: Maximum number of messages to retrieve (1-100, default 10).
            queue_id: Optional reserved queue ID (must start with 'rq_').
            token: Required when queue_id is provided. Authentication token
                for the reserved queue.

        Returns:
            ConsumeResponse with messages and remaining count.

        Raises:
            AuthenticationError: If not authenticated.
            NotFoundError: If reserved queue not found or expired.
            AuthorizationError: If reserved queue token is invalid.
            ValidationError: If queue_id provided without token.
        """
        payload: dict[str, str | int] = {"limit": limit}
        if queue_id is not None:
            payload["queue_id"] = queue_id
        if token is not None:
            payload["token"] = token

        response = self._http.post("/api/v1/mq/consume", json=payload)
        return ConsumeResponse.model_validate(response)

    def status(self) -> QueueStatusResponse:
        """Get the status of your queue.

        Returns:
            QueueStatusResponse with queue length.

        Raises:
            AuthenticationError: If not authenticated.
        """
        response = self._http.get("/api/v1/mq/status")
        return QueueStatusResponse.model_validate(response)

    def peek(self, *, limit: int = 10) -> PeekResponse:
        """Peek at messages without consuming them.

        Messages are returned in FIFO order (oldest first) but are
        NOT removed from the queue.

        Args:
            limit: Maximum number of messages to peek (1-100, default 10).

        Returns:
            PeekResponse with messages and total count.

        Raises:
            AuthenticationError: If not authenticated.
        """
        response = self._http.post(
            "/api/v1/mq/peek",
            json={"limit": limit},
        )
        return PeekResponse.model_validate(response)

    def clear(self) -> ClearResponse:
        """Clear all messages from your queue.

        This is a destructive operation that cannot be undone.

        Returns:
            ClearResponse with number of messages cleared.

        Raises:
            AuthenticationError: If not authenticated.
        """
        response = self._http.delete("/api/v1/mq/clear")
        return ClearResponse.model_validate(response)

    # ==========================================================================
    # Reserved Queue Operations (for ephemeral queues used by aggregator/tunneling)
    # ==========================================================================

    def reserve_queue(self, *, ttl: int = 300) -> ReserveQueueResponse:
        """Reserve an ephemeral queue for receiving messages.

        Creates a temporary queue with a unique ID and secret token.
        The queue will automatically expire after the specified TTL.

        This is used for tunneling workflows where a client needs to receive
        responses from endpoint owners via the aggregator.

        Args:
            ttl: Time-to-live in seconds (30-3600, default 300).

        Returns:
            ReserveQueueResponse with queue_id, token, and expiration.

        Raises:
            AuthenticationError: If not authenticated.
        """
        response = self._http.post(
            "/api/v1/mq/reserve-queue",
            json={"ttl": ttl},
        )
        return ReserveQueueResponse.model_validate(response)

    def release_queue(self, *, queue_id: str, token: str) -> ReleaseQueueResponse:
        """Release (delete) a reserved queue.

        Immediately deletes the reserved queue and all pending messages.

        Args:
            queue_id: The reserved queue identifier.
            token: The secret token for this queue.

        Returns:
            ReleaseQueueResponse with queue_id and messages cleared count.

        Raises:
            NotFoundError: If queue not found or expired.
            AuthorizationError: If token is invalid.
        """
        response = self._http.post(
            "/api/v1/mq/release-queue",
            json={"queue_id": queue_id, "token": token},
        )
        return ReleaseQueueResponse.model_validate(response)
