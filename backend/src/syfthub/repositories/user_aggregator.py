"""User aggregator repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.user_aggregator import UserAggregatorModel
from syfthub.repositories.base import BaseRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class UserAggregatorRepository(BaseRepository[UserAggregatorModel]):
    """Repository for user aggregator operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, UserAggregatorModel)

    def get_by_user_id(self, user_id: int) -> List[UserAggregatorModel]:
        """Get all aggregators for a user.

        Args:
            user_id: ID of the user

        Returns:
            List of aggregator models, ordered by created_at
        """
        try:
            query = (
                select(UserAggregatorModel)
                .where(UserAggregatorModel.user_id == user_id)
                .order_by(UserAggregatorModel.created_at.desc())
            )
            result = self.session.execute(query)
            return result.scalars().all()
        except SQLAlchemyError:
            return []

    def get_default_by_user_id(self, user_id: int) -> Optional[UserAggregatorModel]:
        """Get the default aggregator for a user.

        Args:
            user_id: ID of the user

        Returns:
            Default aggregator model or None if not found
        """
        try:
            query = select(UserAggregatorModel).where(
                UserAggregatorModel.user_id == user_id,
                UserAggregatorModel.is_default.is_(True),
            )
            result = self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError:
            return None

    def create(self, aggregator: UserAggregatorModel) -> Optional[UserAggregatorModel]:
        """Create a new aggregator record.

        Args:
            aggregator: Aggregator model to create

        Returns:
            Created aggregator model or None if failed
        """
        try:
            self.session.add(aggregator)
            self.session.commit()
            self.session.refresh(aggregator)
            return aggregator
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def update(self, aggregator_id: int, update_data) -> Optional[UserAggregatorModel]:
        """Update an aggregator by ID.

        Args:
            aggregator_id: ID of the aggregator to update
            update_data: Update data (can be UserAggregatorUpdate or dict)

        Returns:
            Updated aggregator model or None if failed
        """
        try:
            obj = self.get_by_id(aggregator_id)
            if not obj:
                return None

            # Handle both Pydantic model and dict
            if hasattr(update_data, "model_dump"):
                # Pydantic v2
                data = update_data.model_dump(exclude_unset=True)
            elif hasattr(update_data, "dict"):
                # Pydantic v1
                data = update_data.dict(exclude_unset=True)
            else:
                # Assume it's already a dict
                data = update_data

            for field, value in data.items():
                if hasattr(obj, field) and value is not None:
                    setattr(obj, field, value)

            self.session.commit()
            self.session.refresh(obj)
            return obj
        except SQLAlchemyError:
            self.session.rollback()
            return None
