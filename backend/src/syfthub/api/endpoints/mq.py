"""Message queue endpoints for pub/consume operations."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.database.dependencies import get_mq_service
from syfthub.schemas.mq import (
    ConsumeRequest,
    ConsumeResponse,
    PeekRequest,
    PeekResponse,
    PublishRequest,
    PublishResponse,
    QueueStatusResponse,
    ReleaseQueueRequest,
    ReleaseQueueResponse,
    ReserveQueueRequest,
    ReserveQueueResponse,
)
from syfthub.schemas.user import User
from syfthub.services.mq_service import MessageQueueService

router = APIRouter()


@router.post("/pub", response_model=PublishResponse)
async def publish_message(
    request: PublishRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> PublishResponse:
    """Publish a message to another user's queue or a reserved queue.

    Sends a message to either a user's message queue or a reserved ephemeral queue.
    The target is auto-detected by prefix:
    - Regular username (e.g., "alice") - publishes to user's queue
    - Reserved queue ID (e.g., "rq_abc123") - publishes to reserved queue

    - **target_username**: The recipient (username or reserved queue ID with rq_ prefix)
    - **message**: The message payload (can be a JSON string for structured data)
    """
    return await mq_service.publish(
        sender=current_user,
        target_username=request.target_username,
        message=request.message,
    )


@router.post("/consume", response_model=ConsumeResponse)
async def consume_messages(
    request: ConsumeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> ConsumeResponse:
    """Consume messages from own queue or a reserved queue.

    Supports two modes:
    1. Own queue: Retrieves messages from authenticated user's queue
    2. Reserved queue: Retrieves from a reserved queue using queue_id + token

    Messages are returned in FIFO order (oldest first).

    - **limit**: Maximum number of messages to retrieve (1-100, default 10)
    - **queue_id**: Optional reserved queue ID (rq_*) to consume from
    - **token**: Required when consuming from a reserved queue
    """
    return await mq_service.consume(
        user=current_user,
        limit=request.limit,
        queue_id=request.queue_id,
        token=request.token,
    )


@router.get("/status", response_model=QueueStatusResponse)
async def get_queue_status(
    current_user: Annotated[User, Depends(get_current_active_user)],
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> QueueStatusResponse:
    """Get current queue status.

    Returns the number of messages waiting in the authenticated user's queue.
    """
    return await mq_service.get_status(user=current_user)


@router.post("/peek", response_model=PeekResponse)
async def peek_messages(
    request: PeekRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> PeekResponse:
    """Peek at messages without consuming them.

    Views messages in the queue without removing them.
    Useful for checking what's in the queue before deciding to consume.

    - **limit**: Maximum number of messages to peek (1-100, default 10)
    """
    return await mq_service.peek(
        user=current_user,
        limit=request.limit,
    )


@router.delete("/clear")
async def clear_queue(
    current_user: Annotated[User, Depends(get_current_active_user)],
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> dict[str, Any]:
    """Clear all messages from own queue.

    Removes all messages from the authenticated user's queue.
    This action cannot be undone.

    Returns the number of messages that were cleared.
    """
    count = await mq_service.clear_queue(user=current_user)
    return {"status": "ok", "cleared": count}


# =============================================================================
# Reserved Queue Endpoints (for tunneling support)
# =============================================================================


@router.post("/reserve", response_model=ReserveQueueResponse)
async def reserve_queue(
    request: ReserveQueueRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> ReserveQueueResponse:
    """Reserve a temporary queue for receiving messages.

    Creates a new reserved queue with a unique ID and access token.
    Reserved queues are used for receiving responses in tunneling scenarios.

    The queue will automatically expire after the TTL.

    - **ttl_seconds**: Time-to-live in seconds (60-3600, default 300)

    Returns:
    - **queue_id**: Unique queue identifier (rq_<uuid>)
    - **token**: Secret token for consuming from this queue
    - **expires_at**: When the queue will expire
    """
    return await mq_service.reserve_queue(
        user=current_user,
        ttl_seconds=request.ttl_seconds,
    )


@router.post("/release", response_model=ReleaseQueueResponse)
async def release_queue(
    request: ReleaseQueueRequest,
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> ReleaseQueueResponse:
    """Release a reserved queue and clear its messages.

    Deletes a reserved queue and all its messages.
    Requires the token that was returned when the queue was reserved.

    Note: This endpoint does not require user authentication - the token
    serves as the credential for this operation.

    - **queue_id**: The reserved queue identifier
    - **token**: The secret token for this queue
    """
    return await mq_service.release_queue(
        queue_id=request.queue_id,
        token=request.token,
    )
