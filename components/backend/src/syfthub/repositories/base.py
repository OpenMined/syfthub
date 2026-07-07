"""Base repository with common CRUD operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.base import BaseModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""

    def __init__(self, session: Session, model: Type[T]):
        """Initialize repository with database session and model class."""
        self.session = session
        self.model = model

    def get_by_id(self, id: int) -> Optional[T]:
        """Get a record by ID."""
        try:
            return self.session.get(self.model, id)
        except SQLAlchemyError as e:
            logger.error(f"Failed to get {self.model.__name__} by id {id}: {e}")
            return None

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> List[T]:
        """Get all records with pagination and optional filtering."""
        try:
            query = select(self.model)

            # Apply filters if provided
            if filters:
                conditions = []
                for field, value in filters.items():
                    if hasattr(self.model, field):
                        conditions.append(getattr(self.model, field) == value)
                if conditions:
                    query = query.where(and_(*conditions))

            query = query.offset(skip).limit(limit)
            result = self.session.execute(query)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Failed to get all {self.model.__name__}: {e}")
            return []

    def create(self, **kwargs) -> Optional[T]:
        """Create a new record."""
        try:
            obj = self.model(**kwargs)
            self.session.add(obj)
            self.session.commit()
            self.session.refresh(obj)
            return obj
        except SQLAlchemyError as e:
            logger.error(f"Failed to create {self.model.__name__}: {e}")
            self.session.rollback()
            return None

    def update(self, id: int, **kwargs) -> Optional[T]:
        """Update a record by ID."""
        try:
            obj = self.get_by_id(id)
            if not obj:
                return None

            for field, value in kwargs.items():
                if hasattr(obj, field):
                    setattr(obj, field, value)

            self.session.commit()
            self.session.refresh(obj)
            return obj
        except SQLAlchemyError as e:
            logger.error(f"Failed to update {self.model.__name__} with id {id}: {e}")
            self.session.rollback()
            return None

    def delete(self, id: int) -> bool:
        """Delete a record by ID."""
        try:
            obj = self.get_by_id(id)
            if not obj:
                return False

            self.session.delete(obj)
            self.session.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Failed to delete {self.model.__name__} with id {id}: {e}")
            self.session.rollback()
            return False

    def exists(self, **filters) -> bool:
        """Check if a record exists with the given filters."""
        try:
            query = select(self.model)
            conditions = []
            for field, value in filters.items():
                if hasattr(self.model, field):
                    conditions.append(getattr(self.model, field) == value)

            if conditions:
                query = query.where(and_(*conditions))

            result = self.session.execute(query.limit(1))
            return result.scalar() is not None
        except SQLAlchemyError as e:
            logger.error(f"Failed to check existence of {self.model.__name__}: {e}")
            return False

    def count(self, filters: Optional[dict[str, Any]] = None) -> int:
        """Count records with optional filtering."""
        try:
            subquery = select(self.model)

            if filters:
                conditions = []
                for field, value in filters.items():
                    if hasattr(self.model, field):
                        conditions.append(getattr(self.model, field) == value)
                if conditions:
                    subquery = subquery.where(and_(*conditions))

            query = select(func.count()).select_from(subquery.subquery())
            result = self.session.execute(query)
            return result.scalar_one()
        except SQLAlchemyError as e:
            logger.error(f"Failed to count {self.model.__name__}: {e}")
            return 0
