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
    SyncEndpointsRequest,
    SyncEndpointsResponse,
)
from syfthub.schemas.search import EndpointSearchRequest, EndpointSearchResponse
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


@router.get(
    "/guest-accessible",
    response_model=list[EndpointPublicResponse],
    summary="List Guest-Accessible Endpoints",
    description="""
List endpoints that are accessible to guest (unauthenticated) users.

**No Authentication Required** - This endpoint is public.

**Filtering Criteria:**
Guest-accessible endpoints must meet ALL of the following criteria:
- **Public visibility**: The endpoint's visibility is set to "public"
- **Active**: The endpoint is active (not disabled or deleted)
- **No policies**: The endpoint has NO policies attached (policies array is empty)

**Use Cases:**
- Allows unauthenticated users to discover free, policy-free endpoints
- Used in conjunction with `/api/v1/token/guest` for guest access flow
- Ensures guests can only see endpoints they are actually allowed to use

**Note:**
Endpoints with any policies attached (rate limits, authentication requirements, etc.)
are NOT included in this list, even if they are public. This ensures guests only see
endpoints they can actually use without additional authorization.
""",
)
async def list_guest_accessible_endpoints(
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    endpoint_type: Optional[EndpointType] = Query(
        None, description="Filter by endpoint type (model or data_source)"
    ),
) -> list[EndpointPublicResponse]:
    """List endpoints accessible to guest (unauthenticated) users.

    Returns only public, active endpoints that have no policies attached.
    This ensures guests can only discover and use truly free endpoints.
    """
    return endpoint_service.list_guest_accessible_endpoints(
        skip=skip, limit=limit, endpoint_type=endpoint_type
    )


@router.post(
    "/search",
    response_model=EndpointSearchResponse,
    summary="Semantic Search Endpoints",
    description="""
Search for public endpoints using natural language queries.

This endpoint uses semantic search (RAG) to find the most relevant endpoints
based on their name, description, readme, and tags. Results are ordered by
relevance.

**Features:**
- Natural language queries (e.g., "machine learning model for text classification")
- Returns endpoints in order of semantic relevance
- Filters by endpoint type (model or data_source)
- Returns up to 50 results per query

**Notes:**
- Only searches public, active endpoints
- Returns the same endpoint format as `/endpoints/public`
- If RAG is not configured, returns empty results
""",
)
async def search_endpoints(
    search_request: EndpointSearchRequest,
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> EndpointSearchResponse:
    """Search endpoints using semantic search (RAG)."""
    return endpoint_service.search_endpoints(
        query=search_request.query,
        top_k=search_request.top_k,
        endpoint_type=search_request.type,
    )


@router.post(
    "/sync",
    response_model=SyncEndpointsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Sync completed successfully",
            "model": SyncEndpointsResponse,
        },
        400: {
            "description": "Validation error - batch contains invalid endpoints",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "VALIDATION_ERROR",
                            "message": "Batch validation failed with 2 error(s)",
                            "errors": [
                                {
                                    "index": 0,
                                    "field": "slug",
                                    "error": "'api' is a reserved slug",
                                },
                                {
                                    "index": 2,
                                    "field": "slug",
                                    "error": "Duplicate slug 'my-model' in batch",
                                },
                            ],
                        }
                    }
                }
            },
        },
        500: {
            "description": "Internal server error - sync failed",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "SYNC_FAILED",
                            "message": "Failed to sync endpoints. Transaction rolled back.",
                        }
                    }
                }
            },
        },
    },
    summary="Sync User Endpoints",
    description="""
Synchronize user's endpoints with the provided list.

**This is a DESTRUCTIVE operation** that:
1. Deletes ALL existing endpoints owned by the current user
2. Creates ALL endpoints from the provided list
3. Is ATOMIC: either all endpoints sync successfully, or none do

**Important Notes:**
- Organization endpoints are NOT affected
- Stars on existing endpoints will be lost (reset to 0)
- Endpoint IDs will change (new IDs assigned)
- Maximum 100 endpoints per sync request

**Validation:**
- All endpoints are validated BEFORE any database changes
- If ANY endpoint fails validation, the entire batch is rejected
- All validation errors are returned together (not just the first)

**Empty Payload:**
- Sending an empty list `{"endpoints": []}` will delete ALL user endpoints
""",
)
async def sync_user_endpoints(
    sync_request: SyncEndpointsRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> SyncEndpointsResponse:
    """Sync user's endpoints with provided list (atomic operation)."""
    return endpoint_service.sync_user_endpoints(
        endpoints_data=sync_request.endpoints,
        current_user=current_user,
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


@router.patch("/slug/{endpoint_slug}", response_model=EndpointResponse)
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


@router.delete("/slug/{endpoint_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint_by_slug(
    endpoint_slug: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    endpoint_service: Annotated[EndpointService, Depends(get_endpoint_service)],
) -> None:
    """Delete an endpoint by slug."""
    endpoint_service.delete_endpoint_by_slug(endpoint_slug, current_user)


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
