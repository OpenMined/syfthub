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
from syfthub.services.auth_service import AuthService
from syfthub.services.datasite_service import DatasiteService
from syfthub.services.organization_service import OrganizationService
from syfthub.services.user_service import UserService


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


# Service dependencies
def get_user_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> UserService:
    """Get UserService dependency."""
    return UserService(session)


def get_auth_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> AuthService:
    """Get AuthService dependency."""
    return AuthService(session)


def get_datasite_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> DatasiteService:
    """Get DatasiteService dependency."""
    return DatasiteService(session)


def get_organization_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> OrganizationService:
    """Get OrganizationService dependency."""
    return OrganizationService(session)
