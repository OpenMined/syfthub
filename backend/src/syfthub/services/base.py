"""Base service class with common functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class BaseService:
    """Base service with common functionality."""

    def __init__(self, session: Session):
        """Initialize service with database session."""
        self.session = session

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()

    def refresh(self, instance: Any) -> None:
        """Refresh an instance from the database."""
        self.session.refresh(instance)
