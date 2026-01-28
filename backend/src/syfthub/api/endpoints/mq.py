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

    By default, retrieves and removes messages from the authenticated user's queue.
    If queue_id is provided with rq_ prefix, consumes from that reserved queue
    using the provided token for authentication.
    Messages are returned in FIFO order (oldest first).

    - **limit**: Maximum number of messages to retrieve (1-100, default 10)
    - **queue_id**: Optional reserved queue ID (must start with 'rq_')
    - **token**: Required when queue_id is provided
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


# ==============================================================================
# Reserved Queue Endpoints (for ephemeral queues used by aggregator/tunneling)
# ==============================================================================


@router.post("/reserve-queue", response_model=ReserveQueueResponse)
async def reserve_queue(
    request: ReserveQueueRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> ReserveQueueResponse:
    """Reserve an ephemeral queue for receiving messages.

    Creates a temporary queue with a unique ID and secret token.
    The queue will automatically expire after the specified TTL.

    This is used for tunneling workflows where a client needs to receive
    responses from endpoint owners via the aggregator.

    - **ttl**: Time-to-live in seconds (30-3600, default 300)

    Returns the queue_id and token needed to consume from the queue.
    """
    return await mq_service.reserve_queue(
        user=current_user,
        ttl=request.ttl,
    )


@router.post("/release-queue", response_model=ReleaseQueueResponse)
async def release_queue(
    request: ReleaseQueueRequest,
    mq_service: Annotated[MessageQueueService, Depends(get_mq_service)],
) -> ReleaseQueueResponse:
    """Release (delete) a reserved queue.

    Immediately deletes the reserved queue and all pending messages.
    Authentication is via the token provided in the request body.

    - **queue_id**: The reserved queue identifier
    - **token**: The secret token for this queue

    Returns the number of messages that were in the queue.
    """
    return await mq_service.release_queue(
        queue_id=request.queue_id,
        token=request.token,
    )
