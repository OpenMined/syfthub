"""Endpoint endpoints with authentication and visibility controls."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status

from syfthub.auth.db_dependencies import (
    get_current_active_user,
    require_admin,
)
from syfthub.database.dependencies import (
    get_endpoint_service,
)
from syfthub.schemas.endpoint import (
    EndpointAdminUpdate,
    EndpointCreate,
    EndpointPublicResponse,
    EndpointResponse,
    EndpointType,
    EndpointUpdate,
    EndpointVisibility,
)
from syfthub.schemas.user import User
from syfthub.services.endpoint_service import EndpointService

router = APIRouter()


@router.post("", response_model=EndpointResponse, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    endpoint_data: EndpointCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
    organization_id: Optional[int] = Query(
        None, description="Organization ID if creating endpoint for organization"
    ),
) -> EndpointResponse:
    """Create a new endpoint for the current user or an organization they belong to."""
    if organization_id:
        return endpoint_service.create_endpoint(
            endpoint_data=endpoint_data,
            owner_id=organization_id,
            is_organization=True,
            current_user=current_user,
        )
    else:
        return endpoint_service.create_endpoint(
            endpoint_data=endpoint_data,
            owner_id=current_user.id,
            is_organization=False,
            current_user=current_user,
        )


@router.get("", response_model=list[EndpointResponse])
async def list_my_endpoints(
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    visibility: Optional[EndpointVisibility] = None,
    search: Optional[str] = None,
) -> list[EndpointResponse]:
    """List current user's endpoints."""
    return endpoint_service.list_user_endpoints(
        current_user, skip=skip, limit=limit, visibility=visibility, search=search
    )


@router.get("/public", response_model=list[EndpointPublicResponse])
async def list_public_endpoints(
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    endpoint_type: Optional[EndpointType] = Query(
        None, description="Filter by endpoint type (model or data_source)"
    ),
) -> list[EndpointPublicResponse]:
    """List all public endpoints."""
    return endpoint_service.list_public_endpoints(
        skip=skip, limit=limit, endpoint_type=endpoint_type
    )


@router.get("/trending", response_model=list[EndpointPublicResponse])
async def list_trending_endpoints(
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    min_stars: Optional[int] = Query(None, ge=0),
    endpoint_type: Optional[EndpointType] = Query(
        None, description="Filter by endpoint type (model or data_source)"
    ),
) -> list[EndpointPublicResponse]:
    """List trending public endpoints."""
    return endpoint_service.list_trending_endpoints(
        skip=skip, limit=limit, min_stars=min_stars, endpoint_type=endpoint_type
    )


@router.get("/{endpoint_id}", response_model=EndpointResponse)
async def get_endpoint(
    endpoint_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> EndpointResponse:
    """Get a specific endpoint by ID."""
    return endpoint_service.get_endpoint(endpoint_id, current_user)


@router.patch("/{endpoint_id}", response_model=EndpointResponse)
async def update_endpoint(
    endpoint_id: int,
    endpoint_data: EndpointUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> EndpointResponse:
    """Update a endpoint."""
    return endpoint_service.update_endpoint(endpoint_id, endpoint_data, current_user)


@router.get("/{endpoint_slug}/exists", response_model=bool)
async def endpoint_exists_for_user(
    endpoint_slug: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> bool:
    """Check if endpoint exists for user."""
    return endpoint_service.endpoint_exists_for_user(endpoint_slug, current_user)


@router.patch("/{endpoint_slug}", response_model=EndpointResponse)
async def update_endpoint_by_slug(
    endpoint_slug: str,
    endpoint_data: EndpointUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> EndpointResponse:
    """Update a endpoint by slug."""
    return endpoint_service.update_endpoint_by_slug(
        endpoint_slug, endpoint_data, current_user
    )


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> None:
    """Delete a endpoint."""
    endpoint_service.delete_endpoint(endpoint_id, current_user)


# Admin-only endpoints
@router.patch("/{endpoint_id}/admin", response_model=EndpointResponse)
async def admin_update_endpoint(
    endpoint_id: int,
    admin_data: EndpointAdminUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
    _: Annotated[bool, Depends(require_admin)],
) -> EndpointResponse:
    """Admin-only endpoint updates (is_active, stars_count override)."""
    return endpoint_service.admin_update_endpoint(endpoint_id, admin_data, current_user)


# Star management endpoints
@router.post("/{endpoint_id}/star", status_code=status.HTTP_201_CREATED)
async def star_endpoint(
    endpoint_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> dict[str, bool]:
    """Star a endpoint."""
    success = endpoint_service.star_endpoint(endpoint_id, current_user)
    return {"starred": success}


@router.delete("/{endpoint_id}/star", status_code=status.HTTP_204_NO_CONTENT)
async def unstar_endpoint(
    endpoint_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> None:
    """Unstar a endpoint."""
    endpoint_service.unstar_endpoint(endpoint_id, current_user)


@router.get("/{endpoint_id}/starred")
async def check_endpoint_starred(
    endpoint_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> dict[str, bool]:
    """Check if current user has starred a endpoint."""
    starred = endpoint_service.is_endpoint_starred(endpoint_id, current_user)
    return {"starred": starred}
