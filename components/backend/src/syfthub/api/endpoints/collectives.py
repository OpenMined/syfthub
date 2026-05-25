"""Collective management endpoints.

A Collective is a user-owned grouping of endpoints. Endpoints join either by
requesting membership (``POST /{id}/members``) or by accepting an owner's
invitation (``POST /{id}/invitations``). See ``CollectiveService`` for the
membership state machine.
"""

from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from syfthub.auth.db_dependencies import (
    get_current_active_user,
    get_optional_current_user,
)
from syfthub.database.dependencies import get_collective_service
from syfthub.schemas.collective import (
    CollectiveCreate,
    CollectiveInvitationResponse,
    CollectiveInviteByPathRequest,
    CollectiveMemberRequest,
    CollectiveMemberResponse,
    CollectiveResponse,
    CollectiveReviewRequest,
    CollectiveSharedEndpointCreate,
    CollectiveSharedEndpointResponse,
    CollectiveSharedEndpointUpdate,
    CollectiveUpdate,
    MembershipStatus,
)
from syfthub.schemas.user import User
from syfthub.services.collective_service import CollectiveService
from syfthub.services.email_service import send_collective_invitation_email

router = APIRouter()


# ----------------------------------------------------------------------
# Collective CRUD
# ----------------------------------------------------------------------


@router.post("", response_model=CollectiveResponse, status_code=status.HTTP_201_CREATED)
async def create_collective(
    data: CollectiveCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveResponse:
    """Create a new collective owned by the current user."""
    return service.create_collective(data, current_user)


@router.get("", response_model=List[CollectiveResponse])
async def list_collectives(
    service: Annotated[CollectiveService, Depends(get_collective_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    owner_id: Optional[int] = Query(None, description="Filter by owning user ID"),
    search: Optional[str] = Query(
        None,
        min_length=1,
        max_length=200,
        description="Search by name, description, or tags",
    ),
) -> List[CollectiveResponse]:
    """List collectives, newest first. Collectives are publicly viewable."""
    return service.list_collectives(
        skip=skip, limit=limit, owner_id=owner_id, search=search
    )


@router.get("/by-slug/{slug}", response_model=CollectiveResponse)
async def get_collective_by_slug(
    slug: str,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveResponse:
    """Get a collective by its slug."""
    return service.get_collective_by_slug(slug)


@router.get(
    "/by-endpoint/{owner_username}/{slug}", response_model=List[CollectiveResponse]
)
async def list_collectives_for_endpoint(
    owner_username: str,
    slug: str,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> List[CollectiveResponse]:
    """List approved collectives an ``owner/slug`` endpoint participates in.

    Public-readable. Backs the Collectives card on the endpoint detail page;
    returns an empty list when the endpoint exists but isn't an approved
    member of any collective, or when the endpoint can't be resolved.
    """
    return service.list_collectives_for_endpoint(owner_username, slug)


@router.get("/by-slug/{slug}/endpoint-paths", response_model=List[str])
async def get_collective_endpoint_paths(
    slug: str,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> List[str]:
    """Return the owner/slug paths of all approved member endpoints.

    Used by the TypeScript SDK to resolve a collective path (``collective/<slug>``)
    into the constituent endpoint paths before building the aggregator request.
    Returns an empty list when the collective exists but has no approved members.
    """
    return service.get_collective_endpoint_paths(slug)


# ----------------------------------------------------------------------
# Shared endpoints — named, curated subsets of approved members
# ----------------------------------------------------------------------
#
# Public read routes are nested under ``/by-slug/{slug}/shared-endpoints``
# (no auth) and MUST be declared before the catch-all ``/{collective_id}``
# routes so FastAPI's path resolver picks the more-specific match.
# Management routes (auth required) are mounted under
# ``/{collective_id}/shared-endpoints``.


@router.get(
    "/shared-endpoints/bulk",
    response_model=List[CollectiveSharedEndpointResponse],
)
async def list_shared_endpoints_bulk(
    service: Annotated[CollectiveService, Depends(get_collective_service)],
    collective_ids: Annotated[
        Optional[List[int]],
        Query(
            alias="collective_id",
            description=(
                "Repeat the parameter to request multiple collectives in one "
                "shot, e.g. ``?collective_id=1&collective_id=2``."
            ),
        ),
    ] = None,
) -> List[CollectiveSharedEndpointResponse]:
    """Bulk list of shared endpoints for a set of collectives (public).

    Powers the chat-view's add-sources modal — collapses N per-collective
    fetches into one round trip. Unknown ids are silently skipped so a
    stale id doesn't 404 the whole batch.
    """
    return service.list_shared_endpoints_bulk(collective_ids or [])


@router.get(
    "/by-slug/{slug}/shared-endpoints",
    response_model=List[CollectiveSharedEndpointResponse],
)
async def list_shared_endpoints_by_slug(
    slug: str,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> List[CollectiveSharedEndpointResponse]:
    """List a collective's shared endpoints by parent slug (public-readable)."""
    return service.list_shared_endpoints_by_slug(slug)


@router.get(
    "/by-slug/{slug}/shared-endpoints/{shared_slug}",
    response_model=CollectiveSharedEndpointResponse,
)
async def get_shared_endpoint_by_slug(
    slug: str,
    shared_slug: str,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveSharedEndpointResponse:
    """Get one shared endpoint by collective slug + shared slug (public)."""
    return service.get_shared_endpoint_by_slugs(slug, shared_slug)


@router.get(
    "/by-slug/{slug}/shared-endpoints/{shared_slug}/endpoint-paths",
    response_model=List[str],
)
async def get_shared_endpoint_endpoint_paths(
    slug: str,
    shared_slug: str,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> List[str]:
    """Return owner/slug paths of a shared endpoint's active member endpoints.

    Used by the TypeScript SDK to resolve ``collective/<X>/<Y>`` paths. The
    result is the intersection of the configured endpoint set with the
    collective's currently approved members; configured endpoints that have
    since left the collective are silently filtered out. The ``all`` shared
    slug short-circuits to "every approved member" (same payload as
    ``/by-slug/{slug}/endpoint-paths``).
    """
    return service.get_shared_endpoint_paths(slug, shared_slug)


@router.get("/{collective_id}", response_model=CollectiveResponse)
async def get_collective(
    collective_id: int,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveResponse:
    """Get a collective by ID."""
    return service.get_collective(collective_id)


@router.patch("/{collective_id}", response_model=CollectiveResponse)
async def update_collective(
    collective_id: int,
    data: CollectiveUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveResponse:
    """Update a collective. Owner only."""
    return service.update_collective(collective_id, data, current_user)


@router.delete("/{collective_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collective(
    collective_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> None:
    """Delete a collective and all its memberships. Owner only."""
    service.delete_collective(collective_id, current_user)


# ----------------------------------------------------------------------
# Membership
# ----------------------------------------------------------------------


@router.get("/{collective_id}/members", response_model=List[CollectiveMemberResponse])
async def list_members(
    collective_id: int,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
    member_status: Annotated[
        Optional[MembershipStatus],
        Query(alias="status", description="Filter by membership status"),
    ] = None,
) -> List[CollectiveMemberResponse]:
    """List a collective's memberships.

    Non-owners see only approved members; the owner sees every status.
    """
    return service.list_members(collective_id, current_user, member_status)


@router.post(
    "/{collective_id}/members",
    response_model=CollectiveMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_join(
    collective_id: int,
    data: CollectiveMemberRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveMemberResponse:
    """Request that one of your endpoints join a collective."""
    return service.request_join(collective_id, data.endpoint_id, current_user)


@router.post(
    "/{collective_id}/members/{endpoint_id}/review",
    response_model=CollectiveMemberResponse,
)
async def review_request(
    collective_id: int,
    endpoint_id: int,
    data: CollectiveReviewRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveMemberResponse:
    """Approve or reject a pending join request. Collective owner only."""
    return service.review_request(
        collective_id, endpoint_id, data.decision, current_user
    )


@router.delete(
    "/{collective_id}/members/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    collective_id: int,
    endpoint_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> None:
    """Remove an endpoint from a collective (collective owner or endpoint owner)."""
    service.remove_member(collective_id, endpoint_id, current_user)


@router.post(
    "/{collective_id}/invitations",
    response_model=CollectiveMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_endpoint(
    collective_id: int,
    data: CollectiveMemberRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
    background_tasks: BackgroundTasks,
) -> CollectiveMemberResponse:
    """Invite an endpoint into a collective. Collective owner only.

    When an invitation is (re)issued, the endpoint owner is emailed a link to
    the accept/decline page.
    """
    membership, email_context = service.invite_endpoint(
        collective_id, data.endpoint_id, current_user
    )
    if email_context is not None:
        background_tasks.add_task(send_collective_invitation_email, email_context)
    return membership


@router.post(
    "/{collective_id}/invitations/by-path",
    response_model=CollectiveMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_endpoint_by_path(
    collective_id: int,
    data: CollectiveInviteByPathRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
    background_tasks: BackgroundTasks,
) -> CollectiveMemberResponse:
    """Invite an endpoint into a collective by its ``owner/slug`` path.

    Same semantics as ``POST /invitations`` — the body identifies the endpoint
    by its public path instead of by numeric id. Used by the admin invite UI
    since the public endpoint API does not expose ids.
    """
    membership, email_context = service.invite_endpoint_by_path(
        collective_id, data.owner_username, data.slug, current_user
    )
    if email_context is not None:
        background_tasks.add_task(send_collective_invitation_email, email_context)
    return membership


@router.get(
    "/{collective_id}/invitations/{endpoint_id}",
    response_model=CollectiveMemberResponse,
)
async def get_invitation(
    collective_id: int,
    endpoint_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveMemberResponse:
    """Get the membership row for an invitation.

    Readable by the endpoint owner, collective owner, or an admin — used by
    the invitation landing page that the email links to.
    """
    return service.get_invitation(collective_id, endpoint_id, current_user)


@router.post(
    "/{collective_id}/invitations/{endpoint_id}/respond",
    response_model=CollectiveMemberResponse,
)
async def respond_to_invitation(
    collective_id: int,
    endpoint_id: int,
    data: CollectiveInvitationResponse,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveMemberResponse:
    """Accept or decline a collective invitation. Endpoint owner only."""
    return service.respond_to_invitation(
        collective_id, endpoint_id, data.decision, current_user
    )


# ----------------------------------------------------------------------
# Shared endpoints — management routes (auth required for mutations)
# ----------------------------------------------------------------------


@router.get(
    "/{collective_id}/shared-endpoints",
    response_model=List[CollectiveSharedEndpointResponse],
)
async def list_shared_endpoints(
    collective_id: int,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> List[CollectiveSharedEndpointResponse]:
    """List a collective's shared endpoints. Public-readable."""
    return service.list_shared_endpoints(collective_id)


@router.post(
    "/{collective_id}/shared-endpoints",
    response_model=CollectiveSharedEndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shared_endpoint(
    collective_id: int,
    data: CollectiveSharedEndpointCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveSharedEndpointResponse:
    """Create a shared endpoint under a collective. Collective owner only.

    Every ``endpoint_ids`` entry must be an approved member of the parent
    collective. The slug is auto-derived from the name when omitted.
    """
    return service.create_shared_endpoint(collective_id, data, current_user)


@router.get(
    "/{collective_id}/shared-endpoints/{shared_slug}",
    response_model=CollectiveSharedEndpointResponse,
)
async def get_shared_endpoint(
    collective_id: int,
    shared_slug: str,
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveSharedEndpointResponse:
    """Get one shared endpoint by parent id + own slug. Public-readable."""
    return service.get_shared_endpoint(collective_id, shared_slug)


@router.patch(
    "/{collective_id}/shared-endpoints/{shared_slug}",
    response_model=CollectiveSharedEndpointResponse,
)
async def update_shared_endpoint(
    collective_id: int,
    shared_slug: str,
    data: CollectiveSharedEndpointUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> CollectiveSharedEndpointResponse:
    """Update a shared endpoint. Collective owner only.

    ``endpoint_ids`` is a full replacement when present; omit it to leave the
    membership untouched. Slug is immutable.
    """
    return service.update_shared_endpoint(
        collective_id, shared_slug, data, current_user
    )


@router.delete(
    "/{collective_id}/shared-endpoints/{shared_slug}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_shared_endpoint(
    collective_id: int,
    shared_slug: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CollectiveService, Depends(get_collective_service)],
) -> None:
    """Delete a shared endpoint and its member rows. Collective owner only."""
    service.delete_shared_endpoint(collective_id, shared_slug, current_user)
