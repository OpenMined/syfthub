"""Database dependencies for FastAPI dependency injection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from syfthub.database.connection import get_db_session
from syfthub.database.repositories import (
    DatasiteRepository,
    UserRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_user_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> UserRepository:
    """Get UserRepository dependency."""
    return UserRepository(session)


def get_datasite_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> DatasiteRepository:
    """Get DatasiteRepository dependency."""
    return DatasiteRepository(session)
