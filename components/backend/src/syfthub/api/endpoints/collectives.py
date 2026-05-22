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
