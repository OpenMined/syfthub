"""User aggregator service for managing user aggregator configurations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import HTTPException, status

from syfthub.models.user_aggregator import UserAggregatorModel
from syfthub.repositories.user_aggregator import UserAggregatorRepository
from syfthub.schemas.user import (
    UserAggregatorCreate,
    UserAggregatorListResponse,
    UserAggregatorResponse,
    UserAggregatorUpdate,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class UserAggregatorService(BaseService):
    """Service for managing user aggregator configurations."""

    def __init__(self, session: Session):
        """Initialize user aggregator service."""
        super().__init__(session)
        self.aggregator_repository = UserAggregatorRepository(session)

    def get_user_aggregators(self, user_id: int) -> UserAggregatorListResponse:
        """Get all aggregators for a user.

        Args:
            user_id: ID of the user

        Returns:
            List of user's aggregators with default indicator
        """
        aggregators = self.aggregator_repository.get_by_user_id(user_id)

        # Find the default aggregator ID
        default_aggregator_id = None
        for agg in aggregators:
            if agg.is_default:
                default_aggregator_id = agg.id
                break

        return UserAggregatorListResponse(
            aggregators=[
                UserAggregatorResponse.model_validate(agg) for agg in aggregators
            ],
            default_aggregator_id=default_aggregator_id,
        )

    def get_aggregator(
        self, aggregator_id: int, user_id: int
    ) -> UserAggregatorResponse:
        """Get a specific aggregator by ID.

        Args:
            aggregator_id: ID of the aggregator
            user_id: ID of the user (for ownership check)

        Returns:
            Aggregator details

        Raises:
            HTTPException: If aggregator not found or doesn't belong to user
        """
        aggregator = self.aggregator_repository.get_by_id(aggregator_id)

        if not aggregator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aggregator not found",
            )

        if aggregator.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: aggregator does not belong to user",
            )

        return UserAggregatorResponse.model_validate(aggregator)

    def create_aggregator(
        self, user_id: int, aggregator_data: UserAggregatorCreate
    ) -> UserAggregatorResponse:
        """Create a new aggregator for a user.

        If this is the first aggregator for the user, it will be set as default.

        Args:
            user_id: ID of the user
            aggregator_data: Aggregator configuration

        Returns:
            Created aggregator
        """
        # Check if user already has aggregators
        existing_aggregators = self.aggregator_repository.get_by_user_id(user_id)

        # If this is the first aggregator, force it to be default
        is_default = aggregator_data.is_default
        if not existing_aggregators:
            is_default = True

        # If setting this as default, unset any existing default first
        if is_default and existing_aggregators:
            for agg in existing_aggregators:
                if agg.is_default:
                    self.aggregator_repository.update(
                        agg.id, UserAggregatorUpdate(is_default=False)
                    )

        # Create the aggregator
        aggregator = UserAggregatorModel(
            user_id=user_id,
            name=aggregator_data.name,
            url=aggregator_data.url,
            is_default=is_default,
        )

        created = self.aggregator_repository.create(aggregator)
        return UserAggregatorResponse.model_validate(created)

    def update_aggregator(
        self,
        aggregator_id: int,
        user_id: int,
        aggregator_data: UserAggregatorUpdate,
    ) -> UserAggregatorResponse:
        """Update an existing aggregator.

        Args:
            aggregator_id: ID of the aggregator to update
            user_id: ID of the user (for ownership check)
            aggregator_data: Updated configuration

        Returns:
            Updated aggregator

        Raises:
            HTTPException: If aggregator not found or doesn't belong to user
        """
        # Verify ownership
        aggregator = self.aggregator_repository.get_by_id(aggregator_id)

        if not aggregator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aggregator not found",
            )

        if aggregator.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: aggregator does not belong to user",
            )

        # If setting this as default, unset any existing default first
        if aggregator_data.is_default:
            existing_aggregators = self.aggregator_repository.get_by_user_id(user_id)
            for agg in existing_aggregators:
                if agg.is_default and agg.id != aggregator_id:
                    self.aggregator_repository.update(
                        agg.id, UserAggregatorUpdate(is_default=False)
                    )

        # Update the aggregator
        updated = self.aggregator_repository.update(aggregator_id, aggregator_data)

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update aggregator",
            )

        return UserAggregatorResponse.model_validate(updated)

    def delete_aggregator(self, aggregator_id: int, user_id: int) -> None:
        """Delete an aggregator.

        If the deleted aggregator was the default, another aggregator will be
        set as default (if any exist).

        Args:
            aggregator_id: ID of the aggregator to delete
            user_id: ID of the user (for ownership check)

        Raises:
            HTTPException: If aggregator not found or doesn't belong to user
        """
        # Verify ownership
        aggregator = self.aggregator_repository.get_by_id(aggregator_id)

        if not aggregator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aggregator not found",
            )

        if aggregator.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: aggregator does not belong to user",
            )

        was_default = aggregator.is_default

        # Delete the aggregator
        success = self.aggregator_repository.delete(aggregator_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete aggregator",
            )

        # If we deleted the default, set another as default if any exist
        if was_default:
            remaining = self.aggregator_repository.get_by_user_id(user_id)
            if remaining:
                self.aggregator_repository.update(
                    remaining[0].id, UserAggregatorUpdate(is_default=True)
                )

    def set_default_aggregator(
        self, aggregator_id: int, user_id: int
    ) -> UserAggregatorResponse:
        """Set an aggregator as the default for a user.

        Args:
            aggregator_id: ID of the aggregator to set as default
            user_id: ID of the user (for ownership check)

        Returns:
            Updated aggregator

        Raises:
            HTTPException: If aggregator not found or doesn't belong to user
        """
        # Verify ownership
        aggregator = self.aggregator_repository.get_by_id(aggregator_id)

        if not aggregator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aggregator not found",
            )

        if aggregator.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: aggregator does not belong to user",
            )

        # Unset existing default
        existing_aggregators = self.aggregator_repository.get_by_user_id(user_id)
        for agg in existing_aggregators:
            if agg.is_default and agg.id != aggregator_id:
                self.aggregator_repository.update(
                    agg.id, UserAggregatorUpdate(is_default=False)
                )

        # Set this one as default
        updated = self.aggregator_repository.update(
            aggregator_id, UserAggregatorUpdate(is_default=True)
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update aggregator",
            )

        return UserAggregatorResponse.model_validate(updated)

    def get_default_aggregator_url(self, user_id: int) -> Optional[str]:
        """Get the default aggregator URL for a user.

        Args:
            user_id: ID of the user

        Returns:
            Default aggregator URL or None if no aggregators configured
        """
        default = self.aggregator_repository.get_default_by_user_id(user_id)
        if default:
            return default.url
        return None
