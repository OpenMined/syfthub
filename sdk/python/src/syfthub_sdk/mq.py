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


class MQResource:
    """Message Queue operations for pub/consume messaging.

    This resource provides access to the Redis-backed message queue system
    for asynchronous user-to-user messaging.

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
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize the MQ resource.

        Args:
            http: HTTP client for making requests.
        """
        self._http = http

    def publish(self, *, target_username: str, message: str) -> PublishResponse:
        """Publish a message to another user's queue.

        Args:
            target_username: Username of the recipient (1-50 characters).
            message: The message payload (1-65536 characters, can be JSON string).

        Returns:
            PublishResponse with status and queue information.

        Raises:
            NotFoundError: If target user doesn't exist.
            ValidationError: If target user is not active or queue is full.
            AuthenticationError: If not authenticated.
        """
        response = self._http.post(
            "/api/v1/mq/pub",
            json={"target_username": target_username, "message": message},
        )
        return PublishResponse.model_validate(response)

    def consume(self, *, limit: int = 10) -> ConsumeResponse:
        """Consume messages from your own queue.

        Messages are returned in FIFO order (oldest first) and are
        removed from the queue.

        Args:
            limit: Maximum number of messages to retrieve (1-100, default 10).

        Returns:
            ConsumeResponse with messages and remaining count.

        Raises:
            AuthenticationError: If not authenticated.
        """
        response = self._http.post(
            "/api/v1/mq/consume",
            json={"limit": limit},
        )
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
