"""Datasite endpoints with authentication and visibility controls."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status

from syfthub.auth.db_dependencies import (
    get_current_active_user,
)
from syfthub.database.dependencies import (
    get_datasite_service,
)
from syfthub.repositories.datasite import DatasiteRepository
from syfthub.schemas.auth import UserRole
from syfthub.schemas.datasite import (
    RESERVED_SLUGS,
    Datasite,
    DatasiteCreate,
    DatasitePublicResponse,
    DatasiteResponse,
    DatasiteUpdate,
    DatasiteVisibility,
    generate_slug_from_name,
)
from syfthub.schemas.user import User
from syfthub.services.datasite_service import DatasiteService

router = APIRouter()

# Mock database and lookups removed - now using repository pattern


def get_datasite_by_id(
    datasite_repo: DatasiteRepository, datasite_id: int
) -> Optional[Datasite]:
    """Get datasite by ID."""
    return datasite_repo.get_by_id(datasite_id)


def get_datasite_by_slug(
    datasite_repo: DatasiteRepository, user_id: int, slug: str
) -> Optional[Datasite]:
    """Get datasite by user_id and slug."""
    return datasite_repo.get_by_user_and_slug(user_id, slug)


def is_slug_available(
    datasite_repo: DatasiteRepository,
    slug: str,
    user_id: int,
    exclude_datasite_id: Optional[int] = None,
) -> bool:
    """Check if a slug is available for a user."""
    if slug in RESERVED_SLUGS:
        return False

    # Use repository to check if slug exists for user
    exists = datasite_repo.slug_exists_for_user(user_id, slug, exclude_datasite_id)
    return not exists


def generate_unique_slug(
    datasite_repo: DatasiteRepository,
    name: str,
    owner_id: int,
    is_organization: bool = False,
) -> str:
    """Generate a unique slug for a user or organization."""
    base_slug = generate_slug_from_name(name)

    # Check if base slug is available
    if is_organization:
        slug_available = not datasite_repo.slug_exists_for_organization(
            owner_id, base_slug
        )
    else:
        slug_available = is_slug_available(datasite_repo, base_slug, owner_id)

    if slug_available:
        return base_slug

    # If base slug is taken, append numbers
    counter = 1
    while counter < 1000:  # Prevent infinite loops
        new_slug = f"{base_slug}-{counter}"
        if len(new_slug) <= 63:
            if is_organization:
                if not datasite_repo.slug_exists_for_organization(owner_id, new_slug):
                    return new_slug
            else:
                if is_slug_available(datasite_repo, new_slug, owner_id):
                    return new_slug
        counter += 1

    # Fallback: use timestamp
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-6:]
    return f"{base_slug[:50]}-{timestamp}"


def can_access_datasite(datasite: Datasite, current_user: Optional[User]) -> bool:
    """Check if user can access a datasite based on visibility."""
    if datasite.visibility == DatasiteVisibility.PUBLIC:
        return True

    if current_user is None:
        return False

    # Owner can always access
    if current_user.id == datasite.user_id:
        return True

    # Admin can access everything
    if current_user.role == UserRole.ADMIN:
        return True

    # Internal datasites are accessible to any authenticated user
    # Private datasites are only accessible to owner and admin
    return datasite.visibility == DatasiteVisibility.INTERNAL


@router.post("/", response_model=DatasiteResponse, status_code=status.HTTP_201_CREATED)
async def create_datasite(
    datasite_data: DatasiteCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
) -> DatasiteResponse:
    """Create a new datasite."""
    return datasite_service.create_datasite(
        datasite_data=datasite_data,
        owner_id=current_user.id,
        is_organization=False,
        current_user=current_user,
    )


@router.get("/", response_model=list[DatasiteResponse])
async def list_my_datasites(
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    visibility: Optional[DatasiteVisibility] = None,
    search: Optional[str] = None,
) -> list[DatasiteResponse]:
    """List current user's datasites."""
    return datasite_service.list_user_datasites(
        current_user, skip=skip, limit=limit, visibility=visibility, search=search
    )


@router.get("/public", response_model=list[DatasitePublicResponse])
async def list_public_datasites(
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
) -> list[DatasitePublicResponse]:
    """List all public datasites."""
    return datasite_service.list_public_datasites(skip=skip, limit=limit)


@router.get("/trending", response_model=list[DatasitePublicResponse])
async def list_trending_datasites(
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    min_stars: Optional[int] = Query(None, ge=0),
) -> list[DatasitePublicResponse]:
    """List trending public datasites."""
    return datasite_service.list_trending_datasites(
        skip=skip, limit=limit, min_stars=min_stars
    )


@router.get("/{datasite_id}", response_model=DatasiteResponse)
async def get_datasite(
    datasite_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
) -> DatasiteResponse:
    """Get a specific datasite by ID."""
    return datasite_service.get_datasite(datasite_id, current_user)


@router.patch("/{datasite_id}", response_model=DatasiteResponse)
async def update_datasite(
    datasite_id: int,
    datasite_data: DatasiteUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
) -> DatasiteResponse:
    """Update a datasite."""
    return datasite_service.update_datasite(datasite_id, datasite_data, current_user)


@router.delete("/{datasite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_datasite(
    datasite_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
) -> None:
    """Delete a datasite."""
    datasite_service.delete_datasite(datasite_id, current_user)
