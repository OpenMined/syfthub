"""Message queue schemas for pub/consume operations."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class PublishRequest(BaseModel):
    """Request to publish a message to a user's queue."""

    target_username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Username of the recipient",
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
    target_username: str = Field(..., description="Username of the recipient")
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
    """Request to consume messages from own queue or a reserved queue."""

    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of messages to retrieve",
    )
    queue_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Optional: Reserved queue ID (rq_*) to consume from instead of own queue",
    )
    token: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Required when consuming from a reserved queue",
    )


class ConsumeResponse(BaseModel):
    """Response with consumed messages."""

    messages: List[Message] = Field(
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

    messages: List[Message] = Field(
        default_factory=list, description="List of messages (not removed from queue)"
    )
    total: int = Field(..., ge=0, description="Total number of messages in queue")


# Reserved Queue Schemas for Tunneling Support
# Reserved queues are temporary queues that can be created by authenticated users
# and accessed using a token. They're used for receiving responses in tunneling scenarios.


class ReserveQueueRequest(BaseModel):
    """Request to reserve a temporary queue for receiving messages."""

    ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Time-to-live in seconds (60-3600, default 300)",
    )


class ReserveQueueResponse(BaseModel):
    """Response with reserved queue credentials."""

    queue_id: str = Field(..., description="Unique queue identifier (rq_<uuid>)")
    token: str = Field(..., description="Secret token for accessing this queue")
    expires_at: datetime = Field(..., description="When the queue will expire")
    owner_username: str = Field(..., description="Username of the queue owner")


class ReleaseQueueRequest(BaseModel):
    """Request to release a reserved queue."""

    queue_id: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Reserved queue identifier",
    )
    token: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Secret token for this queue",
    )


class ReleaseQueueResponse(BaseModel):
    """Response after releasing a reserved queue."""

    status: str = Field(default="ok", description="Status of the release operation")
    cleared: int = Field(..., ge=0, description="Number of messages that were cleared")
    queue_id: str = Field(..., description="The released queue identifier")
