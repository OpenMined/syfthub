"""Datasite endpoints with authentication and visibility controls."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status

from syfthub.auth.db_dependencies import (
    get_current_active_user,
    require_admin,
)
from syfthub.database.dependencies import (
    get_datasite_service,
)
from syfthub.schemas.datasite import (
    DatasiteAdminUpdate,
    DatasiteCreate,
    DatasitePublicResponse,
    DatasiteResponse,
    DatasiteUpdate,
    DatasiteVisibility,
)
from syfthub.schemas.user import User
from syfthub.services.datasite_service import DatasiteService

router = APIRouter()


@router.post("/", response_model=DatasiteResponse, status_code=status.HTTP_201_CREATED)
async def create_datasite(
    datasite_data: DatasiteCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
    organization_id: Optional[int] = Query(
        None, description="Organization ID if creating datasite for organization"
    ),
) -> DatasiteResponse:
    """Create a new datasite for the current user or an organization they belong to."""
    if organization_id:
        return datasite_service.create_datasite(
            datasite_data=datasite_data,
            owner_id=organization_id,
            is_organization=True,
            current_user=current_user,
        )
    else:
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


# Admin-only endpoints
@router.patch("/{datasite_id}/admin", response_model=DatasiteResponse)
async def admin_update_datasite(
    datasite_id: int,
    admin_data: DatasiteAdminUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
    _: Annotated[bool, Depends(require_admin)],
) -> DatasiteResponse:
    """Admin-only datasite updates (is_active, stars_count override)."""
    return datasite_service.admin_update_datasite(datasite_id, admin_data, current_user)


# Star management endpoints
@router.post("/{datasite_id}/star", status_code=status.HTTP_201_CREATED)
async def star_datasite(
    datasite_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
) -> dict[str, bool]:
    """Star a datasite."""
    success = datasite_service.star_datasite(datasite_id, current_user)
    return {"starred": success}


@router.delete("/{datasite_id}/star", status_code=status.HTTP_204_NO_CONTENT)
async def unstar_datasite(
    datasite_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
) -> None:
    """Unstar a datasite."""
    datasite_service.unstar_datasite(datasite_id, current_user)


@router.get("/{datasite_id}/starred")
async def check_datasite_starred(
    datasite_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_service: Annotated[DatasiteService, Depends(get_datasite_service)],
) -> dict[str, bool]:
    """Check if current user has starred a datasite."""
    starred = datasite_service.is_datasite_starred(datasite_id, current_user)
    return {"starred": starred}
