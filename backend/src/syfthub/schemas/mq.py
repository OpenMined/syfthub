"""Message queue schemas for pub/consume operations."""

from datetime import datetime

from pydantic import BaseModel, Field


class PublishRequest(BaseModel):
    """Request to publish a message.

    The target_username can be either:
    - A regular username (e.g., "alice") - publishes to user's queue
    - A reserved queue ID (e.g., "rq_abc123") - auto-detected and routed to reserved queue
    """

    target_username: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Target username or reserved queue ID (rq_ prefix auto-detected)",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=65536,
        description="The message payload (can be JSON string)",
    )


class PublishResponse(BaseModel):
    """Response after publishing a message."""

    status: str = Field(default="ok", description="Status of the publish operation")
    queued_at: datetime = Field(..., description="Timestamp when message was queued")
    target_username: str = Field(..., description="Target (username or queue ID)")
    queue_length: int = Field(
        ..., ge=0, description="Current queue length after publish"
    )


class Message(BaseModel):
    """A message in the queue."""

    id: str = Field(..., description="Unique message identifier (UUID)")
    from_username: str = Field(..., description="Sender's username")
    from_user_id: int = Field(..., description="Sender's user ID")
    message: str = Field(..., description="The message payload")
    queued_at: datetime = Field(..., description="Timestamp when message was queued")


class ConsumeRequest(BaseModel):
    """Request to consume messages.

    By default, consumes from the authenticated user's queue.
    If queue_id is provided with rq_ prefix, consumes from that reserved queue
    using the provided token for authentication.
    """

    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of messages to retrieve",
    )
    queue_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Reserved queue ID (must start with 'rq_'). If provided, token is required.",
    )
    token: str | None = Field(
        default=None,
        min_length=1,
        description="Secret token for reserved queue access. Required if queue_id is provided.",
    )


class ConsumeResponse(BaseModel):
    """Response with consumed messages."""

    messages: list[Message] = Field(
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


class PeekRequest(BaseModel):
    """Request to peek at messages without consuming."""

    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of messages to peek",
    )


class PeekResponse(BaseModel):
    """Response with peeked messages (not consumed)."""

    messages: list[Message] = Field(
        default_factory=list, description="List of messages (not removed from queue)"
    )
    total: int = Field(..., ge=0, description="Total number of messages in queue")


# ==============================================================================
# Reserved Queue Schemas
# ==============================================================================


class ReserveQueueRequest(BaseModel):
    """Request to reserve an ephemeral queue."""

    ttl: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Time-to-live in seconds (30-3600, default 300)",
    )


class ReserveQueueResponse(BaseModel):
    """Response after reserving an ephemeral queue."""

    queue_id: str = Field(
        ..., description="Unique queue identifier (starts with 'rq_')"
    )
    token: str = Field(..., description="Secret token for consuming from this queue")
    expires_at: datetime = Field(..., description="When the queue will expire")
    ttl: int = Field(..., description="TTL in seconds")


class ReleaseQueueRequest(BaseModel):
    """Request to release (delete) a reserved queue."""

    queue_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Queue identifier to release",
    )
    token: str = Field(
        ...,
        min_length=1,
        description="Secret token for authenticating queue access",
    )


class ReleaseQueueResponse(BaseModel):
    """Response after releasing a reserved queue."""

    queue_id: str = Field(..., description="Queue identifier that was released")
    messages_cleared: int = Field(
        ..., ge=0, description="Number of messages that were in the queue"
    )
