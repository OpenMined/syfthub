"""Collective management business logic.

Owns the membership state machine: a join request lands as ``pending`` (or
``approved`` when the collective has ``auto_approve`` set), an invitation lands
as ``invited``, and an owner review / endpoint-owner response moves it to
``approved`` or ``rejected``. See ``syfthub.schemas.collective.MembershipStatus``.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional, Sequence

from fastapi import HTTPException, status

from syfthub.repositories.collective import (
    CollectiveMemberRepository,
    CollectiveRepository,
    CollectiveSharedEndpointMemberRepository,
    CollectiveSharedEndpointRepository,
)
from syfthub.repositories.endpoint import EndpointRepository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import UserRole
from syfthub.schemas.collective import (
    CollectiveCreate,
    CollectiveMemberResponse,
    CollectiveResponse,
    CollectiveSharedEndpointCreate,
    CollectiveSharedEndpointMemberSummary,
    CollectiveSharedEndpointResponse,
    CollectiveSharedEndpointUpdate,
    CollectiveUpdate,
    InvitationDecision,
    InvitationEmailContext,
    MembershipStatus,
    ReviewDecision,
    slugify_collective_name,
    slugify_shared_endpoint_name,
)
from syfthub.schemas.endpoint import (
    Endpoint,
    EndpointType,
    EndpointVisibility,
    get_matching_types,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User


# Endpoint types eligible for collective membership. A collective groups data
# sources, so model-only and agent endpoints cannot join; ``model_data_source``
# qualifies because it also exposes a data source.
_JOINABLE_ENDPOINT_TYPES: frozenset[str] = frozenset(
    get_matching_types(EndpointType.DATA_SOURCE)
)


class CollectiveService(BaseService):
    """Service for collective and membership operations."""

    def __init__(self, session: Session):
        """Initialize the service with its repositories."""
        super().__init__(session)
        self.collective_repo = CollectiveRepository(session)
        self.member_repo = CollectiveMemberRepository(session)
        self.endpoint_repo = EndpointRepository(session)
        self.user_repo = UserRepository(session)
        self.shared_endpoint_repo = CollectiveSharedEndpointRepository(session)
        self.shared_endpoint_member_repo = CollectiveSharedEndpointMemberRepository(
            session
        )

    # ------------------------------------------------------------------
    # Collective CRUD
    # ------------------------------------------------------------------

    def create_collective(
        self, data: CollectiveCreate, current_user: User
    ) -> CollectiveResponse:
        """Create a new collective owned by the current user."""
        slug = self._resolve_slug(data)
        collective = self.collective_repo.create_collective(
            owner_id=current_user.id,
            name=data.name,
            slug=slug,
            description=data.description,
            about=data.about,
            auto_approve=data.auto_approve,
            icon_url=data.icon_url,
            tags=data.tags,
        )
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create collective",
            )
        return self._with_counts(collective)

    def get_collective(self, collective_id: int) -> CollectiveResponse:
        """Get a collective by ID. Collectives are publicly viewable."""
        return self._with_counts(self._get_collective_or_404(collective_id))

    def get_collective_by_slug(self, slug: str) -> CollectiveResponse:
        """Get a collective by slug. Collectives are publicly viewable."""
        collective = self.collective_repo.get_by_slug(slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        return self._with_counts(collective)

    def get_collective_endpoint_paths(self, slug: str) -> List[str]:
        """Return owner/slug paths of all approved member endpoints.

        Called by the SDK's collective-resolution step to expand a
        ``collective/<slug>`` (or the equivalent ``collective/<slug>/all``)
        path into the individual endpoint paths that participate in the
        aggregator request.
        """
        collective = self.collective_repo.get_by_slug(slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        return self._collective_approved_paths(collective.id)

    def get_shared_endpoint_paths(
        self, collective_slug: str, shared_slug: str
    ) -> List[str]:
        """Resolve a ``collective/<X>/<Y>`` path to owner/slug endpoint paths.

        The result is the intersection of the configured endpoint set with the
        parent collective's currently approved members — endpoints that have
        since left the collective are silently filtered out. The ``all`` slug
        short-circuits to "every approved member".
        """
        collective = self.collective_repo.get_by_slug(collective_slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        if shared_slug == "all":
            return self._collective_approved_paths(collective.id)

        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective.id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )
        configured_ids = self.shared_endpoint_member_repo.list_endpoint_ids(shared.id)
        approved_ids = self._approved_endpoint_ids(collective.id)
        active_ids = [eid for eid in configured_ids if eid in approved_ids]
        return self._resolve_endpoint_paths(active_ids)

    def list_collectives(
        self,
        skip: int = 0,
        limit: int = 50,
        owner_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> List[CollectiveResponse]:
        """List collectives, newest first.

        Optionally filtered by ``owner_id`` and/or a ``search`` string.
        """
        collectives = self.collective_repo.list_collectives(
            skip, limit, owner_id, search
        )
        # Grouped queries for all counts instead of N per-row queries.
        ids = [c.id for c in collectives]
        approved = MembershipStatus.APPROVED.value
        member_counts = self.member_repo.count_members_bulk(ids, approved)
        owner_counts = self.member_repo.count_owners_bulk(ids, approved)
        for collective in collectives:
            collective.member_count = member_counts.get(collective.id, 0)
            collective.owner_count = owner_counts.get(collective.id, 0)
        return collectives

    def list_collectives_for_endpoint(
        self, owner_username: str, slug: str
    ) -> List[CollectiveResponse]:
        """List approved collectives an ``owner/slug`` endpoint belongs to.

        Public-readable. Returns only ``APPROVED`` memberships so pending /
        invited / rejected state never leaks to non-owners — mirrors the
        non-owner view of ``list_members``.
        """
        owner = self.user_repo.get_by_username(owner_username)
        if owner is None:
            return []
        endpoint = self.endpoint_repo.get_by_user_and_slug(owner.id, slug)
        if endpoint is None:
            return []
        collectives = self.member_repo.list_collectives_for_endpoint(
            endpoint.id, [MembershipStatus.APPROVED.value]
        )
        ids = [c.id for c in collectives]
        approved = MembershipStatus.APPROVED.value
        member_counts = self.member_repo.count_members_bulk(ids, approved)
        owner_counts = self.member_repo.count_owners_bulk(ids, approved)
        for collective in collectives:
            collective.member_count = member_counts.get(collective.id, 0)
            collective.owner_count = owner_counts.get(collective.id, 0)
        return collectives

    def update_collective(
        self, collective_id: int, data: CollectiveUpdate, current_user: User
    ) -> CollectiveResponse:
        """Update a collective. Owner (or admin) only."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)

        fields = data.model_dump(exclude_unset=True)
        if fields:
            updated = self.collective_repo.update_collective(collective_id, fields)
            if updated is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update collective",
                )
            collective = updated
        return self._with_counts(collective)

    def delete_collective(self, collective_id: int, current_user: User) -> None:
        """Delete a collective and all its memberships. Owner (or admin) only."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        if not self.collective_repo.delete(collective_id):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete collective",
            )

    # ------------------------------------------------------------------
    # Membership — joining
    # ------------------------------------------------------------------

    def request_join(
        self, collective_id: int, endpoint_id: int, current_user: User
    ) -> CollectiveMemberResponse:
        """Request that an endpoint join a collective (endpoint owner action).

        With ``auto_approve`` the membership is approved immediately; otherwise
        it lands as ``pending`` for the collective owner to review.

        Only data-source endpoints (``data_source`` / ``model_data_source``)
        are eligible; a model-only or agent endpoint is rejected with 400.
        """
        collective = self._get_collective_or_404(collective_id)
        endpoint = self._get_endpoint_or_404(endpoint_id)
        self._require_endpoint_owner(endpoint, current_user)
        self._require_joinable_endpoint(endpoint)
        if endpoint.archived:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived endpoints cannot join collectives",
            )

        existing = self.member_repo.get_membership(collective_id, endpoint_id)
        now = datetime.now(timezone.utc)

        if existing is not None:
            if existing.status == MembershipStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Endpoint is already a member of this collective",
                )
            if existing.status == MembershipStatus.PENDING:
                # Idempotent — a request is already awaiting review.
                return self._enrich(existing)
            if existing.status == MembershipStatus.INVITED:
                # The owner already invited this endpoint; requesting to join
                # accepts that standing invitation.
                return self._apply(
                    existing.id,
                    MembershipStatus.APPROVED,
                    responded_at=now,
                    reviewed_by_user_id=current_user.id,
                )
            # rejected -> a fresh request reopens the membership below.

        join_status, responded_at = self._join_outcome(collective, now)
        if existing is not None:
            return self._apply(
                existing.id,
                join_status,
                requested_at=now,
                responded_at=responded_at,
                reviewed_by_user_id=None,
            )
        member = self.member_repo.create_membership(
            collective_id=collective_id,
            endpoint_id=endpoint_id,
            status=join_status.value,
            responded_at=responded_at,
        )
        return self._member_response(member)

    def invite_endpoint(
        self, collective_id: int, endpoint_id: int, current_user: User
    ) -> tuple[CollectiveMemberResponse, Optional[InvitationEmailContext]]:
        """Invite an endpoint into a collective (collective owner action).

        The invited endpoint's owner must accept before the membership becomes
        active. If the endpoint had already requested to join, the invitation
        is treated as an approval.

        Returns the membership plus, when an invitation is (re)issued, the
        context for the notification email the caller should send. The email
        context is ``None`` when no invitation email is warranted — e.g. the
        invite approved a standing join request, or the endpoint has no
        individual owner to notify.

        Only data-source endpoints (``data_source`` / ``model_data_source``)
        are eligible; inviting a model-only or agent endpoint is rejected
        with 400.
        """
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        # The owner need not own the endpoint to invite it — just confirm it exists.
        endpoint = self._get_endpoint_or_404(endpoint_id)
        self._require_joinable_endpoint(endpoint)

        existing = self.member_repo.get_membership(collective_id, endpoint_id)
        now = datetime.now(timezone.utc)
        email_context = self._build_invitation_context(
            collective, endpoint, current_user
        )

        if existing is not None:
            if existing.status == MembershipStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Endpoint is already a member of this collective",
                )
            if existing.status == MembershipStatus.INVITED:
                # Idempotent — re-notify so the owner gets a fresh link.
                return self._enrich(existing), email_context
            if existing.status == MembershipStatus.PENDING:
                # The endpoint already asked to join — inviting it approves it,
                # so no invitation email is warranted.
                approved = self._apply(
                    existing.id,
                    MembershipStatus.APPROVED,
                    responded_at=now,
                    reviewed_by_user_id=current_user.id,
                )
                return approved, None
            # rejected -> reissue the invitation.
            reissued = self._apply(
                existing.id,
                MembershipStatus.INVITED,
                requested_at=now,
                responded_at=None,
                reviewed_by_user_id=None,
            )
            return reissued, email_context

        member = self.member_repo.create_membership(
            collective_id=collective_id,
            endpoint_id=endpoint_id,
            status=MembershipStatus.INVITED.value,
        )
        return self._member_response(member), email_context

    # ------------------------------------------------------------------
    # Membership — review / response / removal
    # ------------------------------------------------------------------

    def review_request(
        self,
        collective_id: int,
        endpoint_id: int,
        decision: ReviewDecision,
        current_user: User,
    ) -> CollectiveMemberResponse:
        """Approve or reject a pending join request (collective owner action)."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)

        membership = self.member_repo.get_membership(collective_id, endpoint_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found",
            )
        if membership.status != MembershipStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This membership has no pending join request to review",
            )

        new_status = (
            MembershipStatus.APPROVED
            if decision == ReviewDecision.APPROVE
            else MembershipStatus.REJECTED
        )
        return self._apply(
            membership.id,
            new_status,
            responded_at=datetime.now(timezone.utc),
            reviewed_by_user_id=current_user.id,
        )

    def respond_to_invitation(
        self,
        collective_id: int,
        endpoint_id: int,
        decision: InvitationDecision,
        current_user: User,
    ) -> CollectiveMemberResponse:
        """Accept or decline a collective invitation (endpoint owner action)."""
        self._get_collective_or_404(collective_id)
        endpoint = self._get_endpoint_or_404(endpoint_id)
        self._require_endpoint_owner(endpoint, current_user)

        membership = self.member_repo.get_membership(collective_id, endpoint_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )
        if membership.status != MembershipStatus.INVITED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="There is no pending invitation for this endpoint",
            )

        new_status = (
            MembershipStatus.APPROVED
            if decision == InvitationDecision.ACCEPT
            else MembershipStatus.REJECTED
        )
        return self._apply(
            membership.id,
            new_status,
            responded_at=datetime.now(timezone.utc),
            reviewed_by_user_id=current_user.id,
        )

    def invite_endpoint_by_path(
        self,
        collective_id: int,
        owner_username: str,
        slug: str,
        current_user: User,
    ) -> tuple[CollectiveMemberResponse, Optional[InvitationEmailContext]]:
        """Invite an endpoint identified by ``owner/slug``.

        Resolves the path to an endpoint id and delegates to ``invite_endpoint``.
        Only public endpoints are resolvable here (this is how the admin UI
        finds them); 404 otherwise.
        """
        owner = self.user_repo.get_by_username(owner_username)
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{owner_username}' not found",
            )
        endpoint = self.endpoint_repo.get_by_owner_and_slug_any_state(owner.id, slug)
        if endpoint is None or endpoint.visibility != EndpointVisibility.PUBLIC:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint '{owner_username}/{slug}' not found",
            )
        return self.invite_endpoint(collective_id, endpoint.id, current_user)

    def get_invitation(
        self, collective_id: int, endpoint_id: int, current_user: User
    ) -> CollectiveMemberResponse:
        """Return the membership row for an invitation.

        Used by the invitation-response landing page so the recipient can see
        the invite even before they accept. Readable by the endpoint owner,
        the collective owner, and admins; everyone else gets 403. A row that
        does not exist (or has been removed) yields 404. The status is not
        constrained — the caller may want to render an "already accepted" or
        "declined" state.
        """
        collective = self._get_collective_or_404(collective_id)
        endpoint = self._get_endpoint_or_404(endpoint_id)

        allowed = (
            self._is_admin(current_user)
            or collective.owner_id == current_user.id
            or endpoint.user_id == current_user.id
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the collective owner or the endpoint owner "
                "can view this invitation",
            )

        membership = self.member_repo.get_membership(collective_id, endpoint_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )
        return self._enrich(membership)

    def remove_member(
        self, collective_id: int, endpoint_id: int, current_user: User
    ) -> None:
        """Remove an endpoint from a collective.

        Allowed for the collective owner (remove) or the endpoint owner (leave).
        """
        collective = self._get_collective_or_404(collective_id)
        membership = self.member_repo.get_membership(collective_id, endpoint_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found",
            )

        allowed = self._is_admin(current_user) or collective.owner_id == current_user.id
        if not allowed:
            endpoint = self.endpoint_repo.get_by_id(endpoint_id)
            allowed = endpoint is not None and endpoint.user_id == current_user.id
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the collective owner or the endpoint owner "
                "can remove this membership",
            )

        if not self.member_repo.delete(membership.id):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove membership",
            )

    def list_members(
        self,
        collective_id: int,
        current_user: Optional[User],
        status_filter: Optional[MembershipStatus] = None,
    ) -> List[CollectiveMemberResponse]:
        """List a collective's memberships.

        Anonymous and non-owner viewers see only ``approved`` members, and only
        those whose endpoint is visible to them. The collective owner (and
        admins) see every membership in every status.
        """
        collective = self._get_collective_or_404(collective_id)
        is_manager = current_user is not None and (
            self._is_admin(current_user) or collective.owner_id == current_user.id
        )

        if status_filter is not None:
            if not is_manager and status_filter != MembershipStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the collective owner can view "
                    "non-approved memberships",
                )
            statuses: Optional[List[str]] = [status_filter.value]
        elif is_manager:
            statuses = None  # all statuses
        else:
            statuses = [MembershipStatus.APPROVED.value]

        memberships = self.member_repo.list_members(collective_id, statuses)
        if is_manager:
            return self._enrich_many(memberships)

        # Non-managers must not learn that a private/internal endpoint exists.
        # Batch-fetch all endpoints once — used for both visibility filtering
        # and enrichment so each endpoint is fetched at most once.
        viewer_id = current_user.id if current_user is not None else None
        endpoint_map = {
            ep.id: ep
            for ep in self.endpoint_repo.get_by_ids(
                list({m.endpoint_id for m in memberships})
            )
        }
        visible: List[CollectiveMemberResponse] = []
        for membership in memberships:
            endpoint = endpoint_map.get(membership.endpoint_id)
            if endpoint is None:
                continue  # endpoint deactivated or removed
            if (
                endpoint.visibility == EndpointVisibility.PUBLIC
                or endpoint.user_id == viewer_id
            ):
                visible.append(membership)
        return self._enrich_many(visible, endpoints=endpoint_map)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_admin(user: User) -> bool:
        """Whether the user is a platform admin."""
        return user.role == UserRole.ADMIN

    def _get_collective_or_404(self, collective_id: int) -> CollectiveResponse:
        """Load a collective or raise 404."""
        collective = self.collective_repo.get_by_id(collective_id)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        return collective

    def _get_endpoint_or_404(self, endpoint_id: int) -> Endpoint:
        """Load an active endpoint or raise 404."""
        endpoint = self.endpoint_repo.get_by_id(endpoint_id)
        if endpoint is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )
        return endpoint

    def _require_owner(self, collective: CollectiveResponse, user: User) -> None:
        """Raise 403 unless the user owns the collective (or is an admin)."""
        if not self._is_admin(user) and collective.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the collective owner can perform this action",
            )

    def _require_endpoint_owner(self, endpoint: Endpoint, user: User) -> None:
        """Raise 403 unless the user owns the endpoint (or is an admin)."""
        if not self._is_admin(user) and endpoint.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only manage memberships for your own endpoints",
            )

    @staticmethod
    def _require_joinable_endpoint(endpoint: Endpoint) -> None:
        """Raise 400 unless the endpoint type is eligible for a collective.

        Collectives group data sources, so model-only and agent endpoints
        cannot join. ``model_data_source`` qualifies because it also exposes a
        data source. This is the single guard for both membership entry points
        (``request_join`` and ``invite_endpoint``) — together they are the only
        paths that create a membership row, so an ineligible endpoint can never
        become (or be invited to become) a member.
        """
        if endpoint.type.value not in _JOINABLE_ENDPOINT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only data source endpoints can join a collective; "
                "model and agent endpoints are not eligible",
            )

    @staticmethod
    def _join_outcome(
        collective: CollectiveResponse, now: datetime
    ) -> tuple[MembershipStatus, Optional[datetime]]:
        """Resolve the status of a fresh join request from ``auto_approve``."""
        if collective.auto_approve:
            return MembershipStatus.APPROVED, now
        return MembershipStatus.PENDING, None

    def _apply(
        self,
        membership_id: int,
        new_status: MembershipStatus,
        *,
        requested_at: Optional[datetime] = None,
        responded_at: Optional[datetime] = None,
        reviewed_by_user_id: Optional[int] = None,
    ) -> CollectiveMemberResponse:
        """Update a membership row's status fields and return the response."""
        fields: dict[str, Any] = {
            "status": new_status.value,
            "responded_at": responded_at,
            "reviewed_by_user_id": reviewed_by_user_id,
        }
        if requested_at is not None:
            fields["requested_at"] = requested_at
        return self._member_response(
            self.member_repo.update_membership(membership_id, **fields)
        )

    def _with_counts(self, collective: CollectiveResponse) -> CollectiveResponse:
        """Populate a collective's approved-member and distinct-owner counts."""
        approved = MembershipStatus.APPROVED.value
        collective.member_count = self.member_repo.count_members(
            collective.id, approved
        )
        collective.owner_count = self.member_repo.count_owners(collective.id, approved)
        return collective

    def _member_response(
        self,
        member: Optional[CollectiveMemberResponse],
    ) -> CollectiveMemberResponse:
        """Return the enriched membership response, or raise 500 if the write failed."""
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update membership",
            )
        return self._enrich(member)

    def _enrich(self, member: CollectiveMemberResponse) -> CollectiveMemberResponse:
        """Populate a single membership with its endpoint's identity."""
        return self._enrich_many([member])[0]

    def _enrich_many(
        self,
        members: List[CollectiveMemberResponse],
        endpoints: Optional[dict[int, Endpoint]] = None,
    ) -> List[CollectiveMemberResponse]:
        """Populate memberships with endpoint name/slug/owner/type in bulk."""
        if not members:
            return members
        if endpoints is None:
            endpoint_list = self.endpoint_repo.get_by_ids(
                list({m.endpoint_id for m in members})
            )
            endpoints = {ep.id: ep for ep in endpoint_list}
        owners = {
            owner.id: owner
            for owner in self.user_repo.get_by_ids(
                list({ep.user_id for ep in endpoints.values()})
            )
        }
        result: List[CollectiveMemberResponse] = []
        for member in members:
            endpoint = endpoints.get(member.endpoint_id)
            if endpoint is None:
                result.append(member)
                continue  # endpoint removed since the membership was created
            update: dict[str, str | None] = {
                "endpoint_name": endpoint.name,
                "endpoint_description": endpoint.description,
                "endpoint_slug": endpoint.slug,
                "endpoint_type": endpoint.type.value,
            }
            owner = owners.get(endpoint.user_id)
            if owner is not None:
                update["endpoint_owner_username"] = owner.username
                update["endpoint_owner_full_name"] = owner.full_name
            result.append(member.model_copy(update=update))
        return result

    def _build_invitation_context(
        self,
        collective: CollectiveResponse,
        endpoint: Endpoint,
        inviter: User,
    ) -> Optional[InvitationEmailContext]:
        """Build the notification-email context for an invited endpoint.

        Returns ``None`` when there is nobody to notify: an inviter who owns
        the endpoint themselves, or an owner with no email on file.
        """
        if endpoint.user_id == inviter.id:
            return None
        owner = self.user_repo.get_by_id(endpoint.user_id)
        if owner is None or not owner.email:
            return None
        return InvitationEmailContext(
            to_email=owner.email,
            recipient_name=owner.full_name or owner.username,
            inviter_name=inviter.full_name or inviter.username,
            collective_name=collective.name,
            collective_slug=collective.slug,
            endpoint_name=endpoint.name,
            endpoint_id=endpoint.id,
        )

    def _resolve_slug(self, data: CollectiveCreate) -> str:
        """Determine a unique slug for a new collective."""
        if data.slug:
            if self.collective_repo.slug_exists(data.slug):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Collective slug already taken",
                )
            return data.slug

        base = slugify_collective_name(data.name)
        if not self.collective_repo.slug_exists(base):
            return base
        # Collision on the derived slug — append a short random suffix.
        for _ in range(5):
            candidate = f"{base[:56]}-{secrets.token_hex(3)}"
            if not self.collective_repo.slug_exists(candidate):
                return candidate
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not generate a unique slug; please supply one explicitly",
        )

    # ------------------------------------------------------------------
    # Shared endpoints — curated subsets of approved members
    # ------------------------------------------------------------------

    def list_shared_endpoints(
        self, collective_id: int
    ) -> List[CollectiveSharedEndpointResponse]:
        """List a collective's shared endpoints with active/inactive enrichment."""
        self._get_collective_or_404(collective_id)
        rows = self.shared_endpoint_repo.list_for_collective(collective_id)
        return self._enrich_shared_endpoints(collective_id, rows)

    def list_shared_endpoints_by_slug(
        self, collective_slug: str
    ) -> List[CollectiveSharedEndpointResponse]:
        """List shared endpoints by parent collective slug (public)."""
        collective = self.collective_repo.get_by_slug(collective_slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        rows = self.shared_endpoint_repo.list_for_collective(collective.id)
        return self._enrich_shared_endpoints(collective.id, rows)

    def get_shared_endpoint(
        self, collective_id: int, shared_slug: str
    ) -> CollectiveSharedEndpointResponse:
        """Get one shared endpoint by collective id + slug."""
        self._get_collective_or_404(collective_id)
        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective_id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )
        return self._enrich_shared_endpoint(collective_id, shared)

    def get_shared_endpoint_by_slugs(
        self, collective_slug: str, shared_slug: str
    ) -> CollectiveSharedEndpointResponse:
        """Get one shared endpoint by collective slug + own slug (public)."""
        collective = self.collective_repo.get_by_slug(collective_slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective.id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )
        return self._enrich_shared_endpoint(collective.id, shared)

    def create_shared_endpoint(
        self,
        collective_id: int,
        data: CollectiveSharedEndpointCreate,
        current_user: User,
    ) -> CollectiveSharedEndpointResponse:
        """Create a shared endpoint under a collective.

        Validates that every ``endpoint_ids`` entry is currently an approved
        member of the collective — owners can't smuggle in pending, rejected,
        or unrelated endpoints. Slug is auto-derived from the name when
        omitted, with collision resolution mirroring the collective slug
        helper.
        """
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)

        approved_ids = self._approved_endpoint_ids(collective_id)
        unknown = [eid for eid in data.endpoint_ids if eid not in approved_ids]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Every endpoint must be an approved member of this "
                    "collective. Not approved: "
                    f"{', '.join(str(eid) for eid in unknown)}"
                ),
            )

        slug = self._resolve_shared_endpoint_slug(collective_id, data)
        created = self.shared_endpoint_repo.create_shared_endpoint(
            collective_id=collective_id,
            name=data.name,
            slug=slug,
            description=data.description,
            endpoint_ids=data.endpoint_ids,
            collective_slug=collective.slug,
        )
        if created is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create shared endpoint",
            )
        return self._enrich_shared_endpoint(collective_id, created)

    def update_shared_endpoint(
        self,
        collective_id: int,
        shared_slug: str,
        data: CollectiveSharedEndpointUpdate,
        current_user: User,
    ) -> CollectiveSharedEndpointResponse:
        """Update a shared endpoint's name/description and (optionally) members."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective_id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )

        endpoint_ids: Optional[List[int]] = None
        if data.endpoint_ids is not None:
            approved_ids = self._approved_endpoint_ids(collective_id)
            unknown = [eid for eid in data.endpoint_ids if eid not in approved_ids]
            if unknown:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Every endpoint must be an approved member of this "
                        "collective. Not approved: "
                        f"{', '.join(str(eid) for eid in unknown)}"
                    ),
                )
            endpoint_ids = list(data.endpoint_ids)

        fields = data.model_dump(exclude_unset=True, exclude={"endpoint_ids"})
        if not fields and endpoint_ids is None:
            return self._enrich_shared_endpoint(collective_id, shared)

        updated = self.shared_endpoint_repo.update_shared_endpoint(
            shared.id,
            fields=fields,
            endpoint_ids=endpoint_ids,
            collective_slug=collective.slug,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update shared endpoint",
            )
        return self._enrich_shared_endpoint(collective_id, updated)

    def delete_shared_endpoint(
        self,
        collective_id: int,
        shared_slug: str,
        current_user: User,
    ) -> None:
        """Delete a shared endpoint (cascades to its member rows)."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective_id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )
        if not self.shared_endpoint_repo.delete_shared_endpoint(shared.id):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete shared endpoint",
            )

    # ------------------------------------------------------------------
    # Shared-endpoint helpers
    # ------------------------------------------------------------------

    def _resolve_shared_endpoint_slug(
        self, collective_id: int, data: CollectiveSharedEndpointCreate
    ) -> str:
        """Determine a unique slug for a new shared endpoint within a collective."""
        if data.slug:
            if self.shared_endpoint_repo.slug_exists(collective_id, data.slug):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Shared endpoint slug already taken in this collective",
                )
            return data.slug

        base = slugify_shared_endpoint_name(data.name)
        if not self.shared_endpoint_repo.slug_exists(collective_id, base):
            return base
        for _ in range(5):
            candidate = f"{base[:56]}-{secrets.token_hex(3)}"
            if not self.shared_endpoint_repo.slug_exists(collective_id, candidate):
                return candidate
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not generate a unique slug; please supply one explicitly",
        )

    def _approved_endpoint_ids(self, collective_id: int) -> set[int]:
        """Set of endpoint ids currently approved in the collective."""
        memberships = self.member_repo.list_members(
            collective_id, [MembershipStatus.APPROVED.value]
        )
        return {m.endpoint_id for m in memberships}

    def _collective_approved_paths(self, collective_id: int) -> List[str]:
        """Owner/slug paths of every approved member endpoint."""
        memberships = self.member_repo.list_members(
            collective_id, [MembershipStatus.APPROVED.value]
        )
        enriched = self._enrich_many(memberships)
        return [
            f"{m.endpoint_owner_username}/{m.endpoint_slug}"
            for m in enriched
            if m.endpoint_owner_username and m.endpoint_slug
        ]

    def _resolve_endpoint_paths(self, endpoint_ids: Sequence[int]) -> List[str]:
        """Resolve endpoint ids to ``owner/slug`` strings, preserving input order."""
        if not endpoint_ids:
            return []
        endpoints = {
            ep.id: ep for ep in self.endpoint_repo.get_by_ids(list(endpoint_ids))
        }
        owners = {
            owner.id: owner
            for owner in self.user_repo.get_by_ids(
                list({ep.user_id for ep in endpoints.values()})
            )
        }
        paths: List[str] = []
        for endpoint_id in endpoint_ids:
            endpoint = endpoints.get(endpoint_id)
            if endpoint is None:
                continue
            owner = owners.get(endpoint.user_id)
            if owner is None:
                continue
            paths.append(f"{owner.username}/{endpoint.slug}")
        return paths

    def _enrich_shared_endpoint(
        self,
        collective_id: int,
        shared: CollectiveSharedEndpointResponse,
    ) -> CollectiveSharedEndpointResponse:
        """Populate ``members``, ``member_count`` and ``active_member_count``."""
        return self._enrich_shared_endpoints(collective_id, [shared])[0]

    def _enrich_shared_endpoints(
        self,
        collective_id: int,
        rows: List[CollectiveSharedEndpointResponse],
    ) -> List[CollectiveSharedEndpointResponse]:
        """Bulk-enrich shared endpoints with member summaries + counts."""
        if not rows:
            return rows
        approved_ids = self._approved_endpoint_ids(collective_id)
        configured = self.shared_endpoint_member_repo.list_endpoint_ids_bulk(
            [row.id for row in rows]
        )
        endpoint_ids_all: set[int] = set()
        for ids in configured.values():
            endpoint_ids_all.update(ids)
        endpoint_map = {
            ep.id: ep for ep in self.endpoint_repo.get_by_ids(list(endpoint_ids_all))
        }
        owners = {
            owner.id: owner
            for owner in self.user_repo.get_by_ids(
                list({ep.user_id for ep in endpoint_map.values()})
            )
        }

        enriched: List[CollectiveSharedEndpointResponse] = []
        for row in rows:
            ids = configured.get(row.id, [])
            members: List[CollectiveSharedEndpointMemberSummary] = []
            active = 0
            for endpoint_id in ids:
                endpoint = endpoint_map.get(endpoint_id)
                if endpoint is None:
                    # Endpoint was hard-deleted (CASCADE removed the join row)
                    # so this should never fire in practice, but be defensive.
                    continue
                is_active = endpoint_id in approved_ids
                if is_active:
                    active += 1
                owner = owners.get(endpoint.user_id)
                members.append(
                    CollectiveSharedEndpointMemberSummary(
                        endpoint_id=endpoint.id,
                        endpoint_name=endpoint.name,
                        endpoint_slug=endpoint.slug,
                        endpoint_owner_username=(
                            owner.username if owner is not None else None
                        ),
                        endpoint_type=endpoint.type.value,
                        is_active=is_active,
                    )
                )
            enriched.append(
                row.model_copy(
                    update={
                        "members": members,
                        "member_count": len(members),
                        "active_member_count": active,
                    }
                )
            )
        return enriched
