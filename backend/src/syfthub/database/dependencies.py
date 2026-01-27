"""Database dependencies for FastAPI dependency injection."""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from syfthub.core.redis_client import get_redis_client
from syfthub.database.connection import get_db_session
from syfthub.repositories import (
    EndpointRepository,
    OrganizationRepository,
    UserRepository,
)
from syfthub.repositories.endpoint import EndpointStarRepository
from syfthub.repositories.organization import OrganizationMemberRepository
from syfthub.services.auth_service import AuthService
from syfthub.services.endpoint_service import EndpointService
from syfthub.services.mq_service import MessageQueueService
from syfthub.services.organization_service import OrganizationService
from syfthub.services.user_service import UserService


def get_user_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> UserRepository:
    """Get UserRepository dependency."""
    return UserRepository(session)


def get_endpoint_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> EndpointRepository:
    """Get EndpointRepository dependency."""
    return EndpointRepository(session)


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


def get_endpoint_star_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> EndpointStarRepository:
    """Get EndpointStarRepository dependency."""
    return EndpointStarRepository(session)


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


def get_endpoint_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> EndpointService:
    """Get EndpointService dependency."""
    return EndpointService(session)


def get_organization_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> OrganizationService:
    """Get OrganizationService dependency."""
    return OrganizationService(session)


async def get_mq_service(
    session: Annotated[Session, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> MessageQueueService:
    """Get MessageQueueService dependency."""
    user_repository = UserRepository(session)
    return MessageQueueService(redis, user_repository)
