"""User aggregator management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.database.dependencies import get_db_session
from syfthub.schemas.user import (
    User,
    UserAggregatorCreate,
    UserAggregatorListResponse,
    UserAggregatorResponse,
    UserAggregatorUpdate,
)
from syfthub.services.user_aggregator_service import UserAggregatorService

router = APIRouter()


def get_user_aggregator_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> UserAggregatorService:
    """Dependency to get user aggregator service."""
    return UserAggregatorService(session)


@router.get("/me/aggregators", response_model=UserAggregatorListResponse)
async def list_user_aggregators(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[UserAggregatorService, Depends(get_user_aggregator_service)],
) -> UserAggregatorListResponse:
    """Get all aggregators for the current user.

    Returns a list of all aggregator configurations with the default marked.
    """
    return service.get_user_aggregators(current_user.id)


@router.post(
    "/me/aggregators",
    response_model=UserAggregatorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_aggregator(
    aggregator_data: UserAggregatorCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[UserAggregatorService, Depends(get_user_aggregator_service)],
) -> UserAggregatorResponse:
    """Create a new aggregator for the current user.

    If this is the first aggregator for the user, it will automatically
    be set as the default.
    """
    return service.create_aggregator(current_user.id, aggregator_data)


@router.get("/me/aggregators/{aggregator_id}", response_model=UserAggregatorResponse)
async def get_user_aggregator(
    aggregator_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[UserAggregatorService, Depends(get_user_aggregator_service)],
) -> UserAggregatorResponse:
    """Get a specific aggregator by ID."""
    return service.get_aggregator(aggregator_id, current_user.id)


@router.put("/me/aggregators/{aggregator_id}", response_model=UserAggregatorResponse)
async def update_user_aggregator(
    aggregator_id: int,
    aggregator_data: UserAggregatorUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[UserAggregatorService, Depends(get_user_aggregator_service)],
) -> UserAggregatorResponse:
    """Update an existing aggregator.

    Users can only update their own aggregators.
    """
    return service.update_aggregator(aggregator_id, current_user.id, aggregator_data)


@router.delete(
    "/me/aggregators/{aggregator_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_user_aggregator(
    aggregator_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[UserAggregatorService, Depends(get_user_aggregator_service)],
) -> None:
    """Delete an aggregator.

    If the deleted aggregator was the default, another aggregator
    will be automatically set as default (if any exist).

    Users can only delete their own aggregators.
    """
    service.delete_aggregator(aggregator_id, current_user.id)


@router.patch(
    "/me/aggregators/{aggregator_id}/default", response_model=UserAggregatorResponse
)
async def set_default_aggregator(
    aggregator_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[UserAggregatorService, Depends(get_user_aggregator_service)],
) -> UserAggregatorResponse:
    """Set an aggregator as the default for the current user.

    This will unset any existing default aggregator.
    """
    return service.set_default_aggregator(aggregator_id, current_user.id)
