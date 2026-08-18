"""Collective repositories for database operations.

Following the codebase convention, these repositories return Pydantic
response schemas rather than ORM models; the service layer enriches them
(e.g. with member counts).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Sequence

from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.collective import (
    CollectiveMemberModel,
    CollectiveModel,
    CollectiveSharedEndpointMemberModel,
    CollectiveSharedEndpointModel,
)
from syfthub.models.endpoint import EndpointModel
from syfthub.repositories.base import BaseRepository
from syfthub.schemas.collective import (
    CollectiveMemberResponse,
    CollectiveResponse,
    CollectiveSharedEndpointResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class CollectiveRepository(BaseRepository[CollectiveModel]):
    """Repository for collective database operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, CollectiveModel)

    def get_by_id(self, collective_id: int) -> Optional[CollectiveResponse]:
        """Get a collective by ID."""
        try:
            model = self.session.get(self.model, collective_id)
            return CollectiveResponse.model_validate(model) if model else None
        except SQLAlchemyError:
            return None

    def get_by_slug(self, slug: str) -> Optional[CollectiveResponse]:
        """Get a collective by its slug."""
        try:
            stmt = select(self.model).where(self.model.slug == slug.lower())
            model = self.session.execute(stmt).scalar_one_or_none()
            return CollectiveResponse.model_validate(model) if model else None
        except SQLAlchemyError:
            return None

    def slug_exists(self, slug: str, exclude_id: Optional[int] = None) -> bool:
        """Check whether a slug is already taken."""
        try:
            stmt = select(self.model.id).where(self.model.slug == slug.lower())
            if exclude_id is not None:
                stmt = stmt.where(self.model.id != exclude_id)
            return self.session.execute(stmt.limit(1)).scalar() is not None
        except SQLAlchemyError:
            return False

    def list_collectives(
        self,
        skip: int = 0,
        limit: int = 50,
        owner_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> List[CollectiveResponse]:
        """List collectives, newest first.

        Optionally filtered by ``owner_id`` and/or a ``search`` string matched
        against name, description and tags (mirrors ``EndpointRepository``).
        """
        try:
            stmt = select(self.model)
            if owner_id is not None:
                stmt = stmt.where(self.model.owner_id == owner_id)
            if search:
                search_pattern = f"%{search}%"
                stmt = stmt.where(
                    or_(
                        self.model.name.ilike(search_pattern),
                        self.model.description.ilike(search_pattern),
                        # Search within the tags JSON array by casting to text.
                        cast(self.model.tags, Text).ilike(search_pattern),
                    )
                )
            stmt = stmt.order_by(self.model.created_at.desc()).offset(skip).limit(limit)
            models = self.session.execute(stmt).scalars().all()
            return [CollectiveResponse.model_validate(m) for m in models]
        except SQLAlchemyError:
            return []

    def create_collective(
        self,
        *,
        owner_id: int,
        name: str,
        slug: str,
        description: str,
        about: str,
        auto_approve: bool,
        icon_url: Optional[str],
        tags: List[str],
    ) -> Optional[CollectiveResponse]:
        """Create a new collective."""
        try:
            model = CollectiveModel(
                owner_id=owner_id,
                name=name,
                slug=slug,
                description=description,
                about=about,
                auto_approve=auto_approve,
                icon_url=icon_url,
                tags=tags,
            )
            self.session.add(model)
            self.session.commit()
            self.session.refresh(model)
            return CollectiveResponse.model_validate(model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def update_collective(
        self, collective_id: int, fields: dict[str, Any]
    ) -> Optional[CollectiveResponse]:
        """Update a collective's user-controlled fields."""
        try:
            model = self.session.get(self.model, collective_id)
            if model is None:
                return None
            for key, value in fields.items():
                if hasattr(model, key):
                    setattr(model, key, value)
            self.session.commit()
            self.session.refresh(model)
            return CollectiveResponse.model_validate(model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def delete(self, collective_id: int) -> bool:
        """Delete a collective by ID.

        Overrides BaseRepository.delete: this repository's get_by_id returns a
        schema, so the inherited delete (which expects an ORM model) cannot be
        reused.
        """
        try:
            model = self.session.get(self.model, collective_id)
            if model is None:
                return False
            self.session.delete(model)
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False


class CollectiveMemberRepository(BaseRepository[CollectiveMemberModel]):
    """Repository for collective membership operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, CollectiveMemberModel)

    def get_membership(
        self, collective_id: int, endpoint_id: int
    ) -> Optional[CollectiveMemberResponse]:
        """Get the membership row for a (collective, endpoint) pair, if any."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.collective_id == collective_id,
                    self.model.endpoint_id == endpoint_id,
                )
            )
            model = self.session.execute(stmt).scalar_one_or_none()
            return CollectiveMemberResponse.model_validate(model) if model else None
        except SQLAlchemyError:
            return None

    def list_members(
        self,
        collective_id: int,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[CollectiveMemberResponse]:
        """List a collective's memberships, optionally filtered by status."""
        try:
            stmt = select(self.model).where(self.model.collective_id == collective_id)
            if statuses:
                stmt = stmt.where(self.model.status.in_(list(statuses)))
            stmt = stmt.order_by(self.model.requested_at.desc())
            models = self.session.execute(stmt).scalars().all()
            return [CollectiveMemberResponse.model_validate(m) for m in models]
        except SQLAlchemyError:
            return []

    def list_collectives_for_endpoint(
        self,
        endpoint_id: int,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[CollectiveResponse]:
        """List the collectives an endpoint participates in.

        Joins ``collective_members`` to ``collectives`` so the caller gets full
        collective rows without a second round-trip. Ordered by the membership's
        ``requested_at`` descending — most recently joined first.
        """
        try:
            stmt = (
                select(CollectiveModel)
                .join(self.model, self.model.collective_id == CollectiveModel.id)
                .where(self.model.endpoint_id == endpoint_id)
            )
            if statuses:
                stmt = stmt.where(self.model.status.in_(list(statuses)))
            stmt = stmt.order_by(self.model.requested_at.desc())
            models = self.session.execute(stmt).scalars().all()
            return [CollectiveResponse.model_validate(m) for m in models]
        except SQLAlchemyError:
            return []

    def list_collectives_for_user(
        self,
        user_id: int,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[CollectiveResponse]:
        """List distinct collectives where any endpoint owned by user_id is a member.

        Joins collective_members → endpoints to filter by endpoint owner, then
        deduplicates via GROUP BY so a user with multiple endpoints in the same
        collective only appears once. Ordered newest-first by collective creation.
        """
        try:
            stmt = (
                select(CollectiveModel)
                .join(self.model, self.model.collective_id == CollectiveModel.id)
                .join(EndpointModel, EndpointModel.id == self.model.endpoint_id)
                .where(EndpointModel.user_id == user_id)
            )
            if statuses:
                stmt = stmt.where(self.model.status.in_(list(statuses)))
            stmt = stmt.group_by(CollectiveModel.id).order_by(
                CollectiveModel.created_at.desc()
            )
            models = self.session.execute(stmt).scalars().all()
            return [CollectiveResponse.model_validate(m) for m in models]
        except SQLAlchemyError:
            return []

    def count_members(self, collective_id: int, status: str) -> int:
        """Count a single collective's memberships with the given status."""
        try:
            stmt = select(func.count()).where(
                and_(
                    self.model.collective_id == collective_id,
                    self.model.status == status,
                )
            )
            return self.session.execute(stmt).scalar_one()
        except SQLAlchemyError:
            return 0

    def count_members_bulk(
        self, collective_ids: Sequence[int], status: str
    ) -> dict[int, int]:
        """Count memberships per collective in a single query (avoids N+1).

        Returns a mapping of collective_id -> count; collectives with zero
        matching members are omitted.
        """
        if not collective_ids:
            return {}
        try:
            stmt = (
                select(self.model.collective_id, func.count())
                .where(
                    and_(
                        self.model.collective_id.in_(list(collective_ids)),
                        self.model.status == status,
                    )
                )
                .group_by(self.model.collective_id)
            )
            return {row[0]: row[1] for row in self.session.execute(stmt).all()}
        except SQLAlchemyError:
            return {}

    def count_owners(self, collective_id: int, status: str) -> int:
        """Count the distinct owners of a collective's member endpoints."""
        try:
            stmt = (
                select(func.count(func.distinct(EndpointModel.user_id)))
                .select_from(self.model)
                .join(EndpointModel, EndpointModel.id == self.model.endpoint_id)
                .where(
                    and_(
                        self.model.collective_id == collective_id,
                        self.model.status == status,
                    )
                )
            )
            return self.session.execute(stmt).scalar_one()
        except SQLAlchemyError:
            return 0

    def count_owners_bulk(
        self, collective_ids: Sequence[int], status: str
    ) -> dict[int, int]:
        """Count distinct member-endpoint owners per collective in one query.

        Returns a mapping of collective_id -> distinct owner count; collectives
        with zero matching members are omitted.
        """
        if not collective_ids:
            return {}
        try:
            stmt = (
                select(
                    self.model.collective_id,
                    func.count(func.distinct(EndpointModel.user_id)),
                )
                .select_from(self.model)
                .join(EndpointModel, EndpointModel.id == self.model.endpoint_id)
                .where(
                    and_(
                        self.model.collective_id.in_(list(collective_ids)),
                        self.model.status == status,
                    )
                )
                .group_by(self.model.collective_id)
            )
            return {row[0]: row[1] for row in self.session.execute(stmt).all()}
        except SQLAlchemyError:
            return {}

    def create_membership(
        self,
        *,
        collective_id: int,
        endpoint_id: int,
        status: str,
        responded_at: Any = None,
        reviewed_by_user_id: Optional[int] = None,
    ) -> Optional[CollectiveMemberResponse]:
        """Insert a new membership row."""
        try:
            model = CollectiveMemberModel(
                collective_id=collective_id,
                endpoint_id=endpoint_id,
                status=status,
                responded_at=responded_at,
                reviewed_by_user_id=reviewed_by_user_id,
            )
            self.session.add(model)
            self.session.commit()
            self.session.refresh(model)
            return CollectiveMemberResponse.model_validate(model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def update_membership(
        self, membership_id: int, **fields: Any
    ) -> Optional[CollectiveMemberResponse]:
        """Update a membership row's fields by ID."""
        try:
            model = self.session.get(self.model, membership_id)
            if model is None:
                return None
            for key, value in fields.items():
                if hasattr(model, key):
                    setattr(model, key, value)
            self.session.commit()
            self.session.refresh(model)
            return CollectiveMemberResponse.model_validate(model)
        except SQLAlchemyError:
            self.session.rollback()
            return None


class CollectiveSharedEndpointRepository(BaseRepository[CollectiveSharedEndpointModel]):
    """Repository for collective shared-endpoint operations.

    Returns Pydantic responses pre-populated with the parent collective's slug
    so callers can render the public ``collective/<collective_slug>/<slug>``
    path without a second round-trip. Configured-member ids and active/inactive
    state are computed in the service layer (intersection with the parent
    collective's approved members).
    """

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, CollectiveSharedEndpointModel)

    @staticmethod
    def _to_response(
        model: CollectiveSharedEndpointModel,
        collective_slug: str,
    ) -> CollectiveSharedEndpointResponse:
        """Build a response payload carrying the parent collective's slug.

        The ``shared_endpoint_path`` is derived here so every callsite gets a
        consistent ``collective/<collective_slug>/<slug>`` without having to
        rebuild the path manually.
        """
        return CollectiveSharedEndpointResponse(
            id=model.id,
            collective_id=model.collective_id,
            collective_slug=collective_slug,
            name=model.name,
            slug=model.slug,
            shared_endpoint_path=f"collective/{collective_slug}/{model.slug}",
            description=model.description,
            members=[],
            member_count=0,
            active_member_count=0,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def get_by_id_with_collective_slug(
        self, shared_endpoint_id: int
    ) -> Optional[tuple[CollectiveSharedEndpointResponse, int]]:
        """Get a shared endpoint and its parent collective id by id.

        Returns ``(response, collective_id)`` or ``None``. The collective id
        lets the service layer validate ``collective_id`` parameters from the
        URL against the actual parent without an extra query.
        """
        try:
            stmt = (
                select(self.model, CollectiveModel.slug)
                .join(CollectiveModel, CollectiveModel.id == self.model.collective_id)
                .where(self.model.id == shared_endpoint_id)
            )
            row = self.session.execute(stmt).first()
            if row is None:
                return None
            model, collective_slug = row
            return self._to_response(model, collective_slug), model.collective_id
        except SQLAlchemyError:
            return None

    def get_by_collective_and_slug(
        self, collective_id: int, slug: str
    ) -> Optional[CollectiveSharedEndpointResponse]:
        """Get a shared endpoint by its parent collective id and own slug."""
        try:
            stmt = (
                select(self.model, CollectiveModel.slug)
                .join(CollectiveModel, CollectiveModel.id == self.model.collective_id)
                .where(
                    and_(
                        self.model.collective_id == collective_id,
                        self.model.slug == slug.lower(),
                    )
                )
            )
            row = self.session.execute(stmt).first()
            if row is None:
                return None
            model, collective_slug = row
            return self._to_response(model, collective_slug)
        except SQLAlchemyError:
            return None

    def get_by_collective_slugs(
        self, collective_slug: str, shared_slug: str
    ) -> Optional[CollectiveSharedEndpointResponse]:
        """Get a shared endpoint by collective slug + shared slug.

        Used by the public ``/by-slug/{slug}/shared-endpoints/{shared_slug}``
        route so the resolver doesn't need to look up the collective id first.
        """
        try:
            stmt = (
                select(self.model, CollectiveModel.slug)
                .join(CollectiveModel, CollectiveModel.id == self.model.collective_id)
                .where(
                    and_(
                        CollectiveModel.slug == collective_slug.lower(),
                        self.model.slug == shared_slug.lower(),
                    )
                )
            )
            row = self.session.execute(stmt).first()
            if row is None:
                return None
            model, fetched_slug = row
            return self._to_response(model, fetched_slug)
        except SQLAlchemyError:
            return None

    def slug_exists(self, collective_id: int, slug: str) -> bool:
        """Check whether a slug is already taken within the collective."""
        try:
            stmt = select(self.model.id).where(
                and_(
                    self.model.collective_id == collective_id,
                    self.model.slug == slug.lower(),
                )
            )
            return self.session.execute(stmt.limit(1)).scalar() is not None
        except SQLAlchemyError:
            return False

    def list_for_collective(
        self, collective_id: int
    ) -> List[CollectiveSharedEndpointResponse]:
        """List a collective's shared endpoints, newest first."""
        try:
            stmt = (
                select(self.model, CollectiveModel.slug)
                .join(CollectiveModel, CollectiveModel.id == self.model.collective_id)
                .where(self.model.collective_id == collective_id)
                .order_by(self.model.created_at.desc())
            )
            rows = self.session.execute(stmt).all()
            return [self._to_response(model, slug) for model, slug in rows]
        except SQLAlchemyError:
            return []

    def list_for_collectives(
        self, collective_ids: Sequence[int]
    ) -> List[CollectiveSharedEndpointResponse]:
        """Bulk-list shared endpoints across multiple collectives.

        Powers the chat-view modal's single-shot fetch (replaces the
        per-collective fan-out). Rows are returned newest-first overall —
        callers that need them grouped by parent should bucket by
        ``collective_id`` themselves.
        """
        if not collective_ids:
            return []
        try:
            stmt = (
                select(self.model, CollectiveModel.slug)
                .join(CollectiveModel, CollectiveModel.id == self.model.collective_id)
                .where(self.model.collective_id.in_(list(collective_ids)))
                .order_by(self.model.created_at.desc())
            )
            rows = self.session.execute(stmt).all()
            return [self._to_response(model, slug) for model, slug in rows]
        except SQLAlchemyError:
            return []

    def list_for_collective_slug(
        self, collective_slug: str
    ) -> List[CollectiveSharedEndpointResponse]:
        """List shared endpoints by parent collective slug."""
        try:
            stmt = (
                select(self.model, CollectiveModel.slug)
                .join(CollectiveModel, CollectiveModel.id == self.model.collective_id)
                .where(CollectiveModel.slug == collective_slug.lower())
                .order_by(self.model.created_at.desc())
            )
            rows = self.session.execute(stmt).all()
            return [self._to_response(model, slug) for model, slug in rows]
        except SQLAlchemyError:
            return []

    def create_shared_endpoint(
        self,
        *,
        collective_id: int,
        name: str,
        slug: str,
        description: str,
        endpoint_ids: Sequence[int],
        collective_slug: str,
    ) -> Optional[CollectiveSharedEndpointResponse]:
        """Insert a new shared endpoint with its configured member rows.

        Both rows commit in a single transaction so a created shared endpoint
        never exists without its initial members. The caller must have already
        validated that every ``endpoint_id`` is an approved collective member.
        """
        try:
            model = CollectiveSharedEndpointModel(
                collective_id=collective_id,
                name=name,
                slug=slug,
                description=description,
            )
            self.session.add(model)
            self.session.flush()
            for endpoint_id in endpoint_ids:
                self.session.add(
                    CollectiveSharedEndpointMemberModel(
                        shared_endpoint_id=model.id,
                        endpoint_id=endpoint_id,
                    )
                )
            self.session.commit()
            self.session.refresh(model)
            return self._to_response(model, collective_slug)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def update_shared_endpoint(
        self,
        shared_endpoint_id: int,
        *,
        fields: dict[str, Any],
        endpoint_ids: Optional[Sequence[int]],
        collective_slug: str,
    ) -> Optional[CollectiveSharedEndpointResponse]:
        """Update a shared endpoint's fields and (optionally) its member set.

        When ``endpoint_ids`` is ``None`` the member rows are untouched;
        otherwise the membership is fully replaced with the provided set.

        The parent row is locked with ``FOR UPDATE`` so two concurrent owner
        PATCHes can't interleave the DELETE+INSERT replacement step — the
        second waiter sees the first writer's committed state before
        applying its own change.
        """
        try:
            model = self.session.get(
                self.model, shared_endpoint_id, with_for_update=True
            )
            if model is None:
                return None
            for key, value in fields.items():
                if key == "slug":
                    # Slug is immutable — see the schema docstring.
                    continue
                if hasattr(model, key):
                    setattr(model, key, value)

            if endpoint_ids is not None:
                self.session.execute(
                    CollectiveSharedEndpointMemberModel.__table__.delete().where(
                        CollectiveSharedEndpointMemberModel.shared_endpoint_id
                        == shared_endpoint_id
                    )
                )
                for endpoint_id in endpoint_ids:
                    self.session.add(
                        CollectiveSharedEndpointMemberModel(
                            shared_endpoint_id=shared_endpoint_id,
                            endpoint_id=endpoint_id,
                        )
                    )

            self.session.commit()
            self.session.refresh(model)
            return self._to_response(model, collective_slug)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def delete_shared_endpoint(self, shared_endpoint_id: int) -> bool:
        """Delete a shared endpoint by id (cascades to member rows)."""
        try:
            model = self.session.get(self.model, shared_endpoint_id)
            if model is None:
                return False
            self.session.delete(model)
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False


class CollectiveSharedEndpointMemberRepository(
    BaseRepository[CollectiveSharedEndpointMemberModel]
):
    """Repository for shared-endpoint member rows.

    Most mutations go through ``CollectiveSharedEndpointRepository`` so that a
    shared endpoint and its members commit atomically; this repository is for
    read paths (resolution, reverse lookups) and bulk lookups.
    """

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, CollectiveSharedEndpointMemberModel)

    def list_endpoint_ids(self, shared_endpoint_id: int) -> List[int]:
        """List the endpoint ids configured into a shared endpoint.

        Returned in insertion order (id ASC) so the fan-out order matches the
        order surfaced by ``list_endpoint_ids_bulk`` (which the admin UI uses).
        """
        try:
            stmt = (
                select(self.model.endpoint_id)
                .where(self.model.shared_endpoint_id == shared_endpoint_id)
                .order_by(self.model.id.asc())
            )
            return [row[0] for row in self.session.execute(stmt).all()]
        except SQLAlchemyError:
            return []

    def list_endpoint_ids_bulk(
        self, shared_endpoint_ids: Sequence[int]
    ) -> dict[int, List[int]]:
        """Bulk-load configured endpoint ids per shared endpoint.

        Returns ``{shared_endpoint_id: [endpoint_id, ...]}``. Shared endpoints
        with zero configured members are omitted; callers should default to
        ``[]`` when looking up.
        """
        if not shared_endpoint_ids:
            return {}
        try:
            stmt = (
                select(self.model.shared_endpoint_id, self.model.endpoint_id)
                .where(self.model.shared_endpoint_id.in_(list(shared_endpoint_ids)))
                .order_by(self.model.id.asc())
            )
            result: dict[int, List[int]] = {}
            for shared_id, endpoint_id in self.session.execute(stmt).all():
                result.setdefault(shared_id, []).append(endpoint_id)
            return result
        except SQLAlchemyError:
            return {}
