"""Database dependencies for FastAPI dependency injection."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from syfthub.database.connection import get_db_session
from syfthub.repositories import (
    DatasiteRepository,
    OrganizationRepository,
    UserRepository,
)
from syfthub.repositories.datasite import DatasiteStarRepository
from syfthub.repositories.organization import OrganizationMemberRepository


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


def get_organization_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> OrganizationRepository:
    """Get OrganizationRepository dependency."""
    return OrganizationRepository(session)


def get_organization_member_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> OrganizationMemberRepository:
    """Get OrganizationMemberRepository dependency."""
    return OrganizationMemberRepository(session)


def get_datasite_star_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> DatasiteStarRepository:
    """Get DatasiteStarRepository dependency."""
    return DatasiteStarRepository(session)
