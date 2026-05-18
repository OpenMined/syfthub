"""Collective management business logic.

Owns the membership state machine: a join request lands as ``pending`` (or
``approved`` when the collective has ``auto_approve`` set), an invitation lands
as ``invited``, and an owner review / endpoint-owner response moves it to
``approved`` or ``rejected``. See ``syfthub.schemas.collective.MembershipStatus``.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional

from fastapi import HTTPException, status

from syfthub.repositories.collective import (
    CollectiveMemberRepository,
    CollectiveRepository,
)
from syfthub.repositories.endpoint import EndpointRepository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import UserRole
from syfthub.schemas.collective import (
    CollectiveCreate,
    CollectiveMemberResponse,
    CollectiveResponse,
    CollectiveUpdate,
    InvitationDecision,
    InvitationEmailContext,
    MembershipStatus,
    ReviewDecision,
    slugify_collective_name,
)
from syfthub.schemas.endpoint import Endpoint, EndpointVisibility
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User


class CollectiveService(BaseService):
    """Service for collective and membership operations."""

    def __init__(self, session: Session):
        """Initialize the service with its repositories."""
        super().__init__(session)
        self.collective_repo = CollectiveRepository(session)
        self.member_repo = CollectiveMemberRepository(session)
        self.endpoint_repo = EndpointRepository(session)
        self.user_repo = UserRepository(session)

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
            auto_approve=data.auto_approve,
            icon_url=data.icon_url,
            tags=data.tags,
        )
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create collective",
            )
        return self._with_member_count(collective)

    def get_collective(self, collective_id: int) -> CollectiveResponse:
        """Get a collective by ID. Collectives are publicly viewable."""
        return self._with_member_count(self._get_collective_or_404(collective_id))

    def get_collective_by_slug(self, slug: str) -> CollectiveResponse:
        """Get a collective by slug. Collectives are publicly viewable."""
        collective = self.collective_repo.get_by_slug(slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        return self._with_member_count(collective)

    def list_collectives(
        self,
        skip: int = 0,
        limit: int = 50,
        owner_id: Optional[int] = None,
    ) -> List[CollectiveResponse]:
        """List collectives, newest first, optionally filtered by owner."""
        collectives = self.collective_repo.list_collectives(skip, limit, owner_id)
        # One grouped query for all member counts instead of N per-row queries.
        counts = self.member_repo.count_members_bulk(
            [c.id for c in collectives], MembershipStatus.APPROVED.value
        )
        for collective in collectives:
            collective.member_count = counts.get(collective.id, 0)
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
        return self._with_member_count(collective)

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
        """
        collective = self._get_collective_or_404(collective_id)
        endpoint = self._get_endpoint_or_404(endpoint_id)
        self._require_endpoint_owner(endpoint, current_user)
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
        """
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        # The owner need not own the endpoint to invite it — just confirm it exists.
        endpoint = self._get_endpoint_or_404(endpoint_id)

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
        # NOTE: one endpoint lookup per member — acceptable at current scale;
        # revisit with a join if collectives grow large.
        viewer_id = current_user.id if current_user is not None else None
        visible: List[CollectiveMemberResponse] = []
        for membership in memberships:
            endpoint = self.endpoint_repo.get_by_id(membership.endpoint_id)
            if endpoint is None:
                continue  # endpoint deactivated or removed
            if (
                endpoint.visibility == EndpointVisibility.PUBLIC
                or endpoint.user_id == viewer_id
            ):
                visible.append(membership)
        return self._enrich_many(visible)

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

    def _with_member_count(self, collective: CollectiveResponse) -> CollectiveResponse:
        """Populate a collective's approved-member count."""
        collective.member_count = self.member_repo.count_members(
            collective.id, MembershipStatus.APPROVED.value
        )
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
        self, members: List[CollectiveMemberResponse]
    ) -> List[CollectiveMemberResponse]:
        """Populate memberships with endpoint name/slug/owner/type in bulk.

        Endpoint lookups are still one-per-member (no batch fetch on the
        endpoint repository); owner usernames are resolved in a single query.
        Acceptable at current scale — revisit with a join if collectives grow.
        """
        if not members:
            return members
        endpoints = {}
        for endpoint_id in {m.endpoint_id for m in members}:
            endpoint = self.endpoint_repo.get_by_id(endpoint_id)
            if endpoint is not None:
                endpoints[endpoint_id] = endpoint
        owners = {
            owner.id: owner
            for owner in self.user_repo.get_by_ids(
                list({ep.user_id for ep in endpoints.values()})
            )
        }
        for member in members:
            endpoint = endpoints.get(member.endpoint_id)
            if endpoint is None:
                continue  # endpoint removed since the membership was created
            member.endpoint_name = endpoint.name
            member.endpoint_slug = endpoint.slug
            member.endpoint_type = endpoint.type.value
            owner = owners.get(endpoint.user_id)
            if owner is not None:
                member.endpoint_owner_username = owner.username
        return members

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
