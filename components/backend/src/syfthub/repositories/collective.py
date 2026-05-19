"""Collective repositories for database operations.

Following the codebase convention, these repositories return Pydantic
response schemas rather than ORM models; the service layer enriches them
(e.g. with member counts).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Sequence

from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.collective import CollectiveMemberModel, CollectiveModel
from syfthub.models.endpoint import EndpointModel
from syfthub.repositories.base import BaseRepository
from syfthub.schemas.collective import CollectiveMemberResponse, CollectiveResponse

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
