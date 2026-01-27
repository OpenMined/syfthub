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
    """Publish a message to another user's queue.

    Sends a message to the specified target user's message queue.
    The message will be available for the target user to consume.

    - **target_username**: The username of the recipient
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
    """Consume messages from own queue.

    Retrieves and removes messages from the authenticated user's queue.
    Messages are returned in FIFO order (oldest first).

    - **limit**: Maximum number of messages to retrieve (1-100, default 10)
    """
    return await mq_service.consume(
        user=current_user,
        limit=request.limit,
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
