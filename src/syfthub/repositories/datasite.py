"""Datasite repository for database operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.datasite import DatasiteModel, DatasiteStarModel
from syfthub.repositories.base import BaseRepository
from syfthub.schemas.datasite import (
    Datasite,
    DatasiteCreate,
    DatasitePublicResponse,
    DatasiteUpdate,
    DatasiteVisibility,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class DatasiteRepository(BaseRepository[DatasiteModel]):
    """Repository for datasite database operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, DatasiteModel)

    def get_by_id(self, datasite_id: int) -> Optional[Datasite]:
        """Get datasite by ID (only active datasites)."""
        try:
            stmt = select(self.model).where(
                and_(self.model.id == datasite_id, self.model.is_active)
            )
            result = self.session.execute(stmt)
            datasite_model = result.scalar_one_or_none()
            if datasite_model:
                return Datasite.model_validate(datasite_model)
            return None
        except SQLAlchemyError:
            return None

    def get_by_user_and_slug(self, user_id: int, slug: str) -> Optional[Datasite]:
        """Get datasite by user ID and slug."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.user_id == user_id,
                    self.model.slug == slug.lower(),
                    self.model.is_active,
                )
            )
            result = self.session.execute(stmt)
            datasite_model = result.scalar_one_or_none()

            if datasite_model:
                return Datasite.model_validate(datasite_model)
            return None
        except SQLAlchemyError:
            return None

    def get_by_organization_and_slug(
        self, org_id: int, slug: str
    ) -> Optional[Datasite]:
        """Get datasite by organization ID and slug."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id,
                    self.model.slug == slug.lower(),
                    self.model.is_active,
                )
            )
            result = self.session.execute(stmt)
            datasite_model = result.scalar_one_or_none()

            if datasite_model:
                return Datasite.model_validate(datasite_model)
            return None
        except SQLAlchemyError:
            return None

    def get_user_datasites(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[DatasiteVisibility] = None,
        search: Optional[str] = None,
    ) -> List[Datasite]:
        """Get all datasites for a user with optional search."""
        try:
            stmt = select(self.model).where(
                and_(self.model.user_id == user_id, self.model.is_active)
            )

            if visibility:
                stmt = stmt.where(self.model.visibility == visibility.value)

            if search:
                search_pattern = f"%{search}%"
                stmt = stmt.where(
                    self.model.name.ilike(search_pattern)
                    | self.model.description.ilike(search_pattern)
                )

            stmt = stmt.order_by(self.model.updated_at.desc()).offset(skip).limit(limit)

            result = self.session.execute(stmt)
            datasite_models = result.scalars().all()

            return [Datasite.model_validate(datasite) for datasite in datasite_models]
        except SQLAlchemyError:
            return []

    def get_organization_datasites(
        self,
        org_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[DatasiteVisibility] = None,
    ) -> List[Datasite]:
        """Get all datasites for an organization."""
        try:
            stmt = select(self.model).where(
                and_(self.model.organization_id == org_id, self.model.is_active)
            )

            if visibility:
                stmt = stmt.where(self.model.visibility == visibility.value)

            stmt = stmt.order_by(self.model.updated_at.desc()).offset(skip).limit(limit)

            result = self.session.execute(stmt)
            datasite_models = result.scalars().all()

            return [Datasite.model_validate(datasite) for datasite in datasite_models]
        except SQLAlchemyError:
            return []

    def get_public_datasites(
        self, skip: int = 0, limit: int = 10
    ) -> List[DatasitePublicResponse]:
        """Get all public datasites."""
        try:
            stmt = (
                select(self.model)
                .where(
                    and_(
                        self.model.visibility == DatasiteVisibility.PUBLIC.value,
                        self.model.is_active,
                    )
                )
                .order_by(self.model.updated_at.desc())
                .offset(skip)
                .limit(limit)
            )

            result = self.session.execute(stmt)
            datasite_models = result.scalars().all()

            return [
                DatasitePublicResponse.model_validate(datasite)
                for datasite in datasite_models
            ]
        except SQLAlchemyError:
            return []

    def get_trending_datasites(
        self, skip: int = 0, limit: int = 10, min_stars: Optional[int] = None
    ) -> List[DatasitePublicResponse]:
        """Get trending public datasites sorted by stars count with optional min_stars filter."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.visibility == DatasiteVisibility.PUBLIC.value,
                    self.model.is_active,
                )
            )

            if min_stars is not None:
                stmt = stmt.where(self.model.stars_count >= min_stars)

            stmt = (
                stmt.order_by(self.model.stars_count.desc()).offset(skip).limit(limit)
            )

            result = self.session.execute(stmt)
            datasite_models = result.scalars().all()
            return [
                DatasitePublicResponse.model_validate(datasite)
                for datasite in datasite_models
            ]
        except SQLAlchemyError:
            return []

    def create_datasite(
        self,
        datasite_data: DatasiteCreate,
        owner_id: int,
        is_organization: bool = False,
    ) -> Optional[Datasite]:
        """Create a new datasite."""
        try:
            datasite_model = DatasiteModel(
                user_id=owner_id if not is_organization else None,
                organization_id=owner_id if is_organization else None,
                name=datasite_data.name,
                slug=datasite_data.slug.lower(),
                description=datasite_data.description,
                visibility=datasite_data.visibility.value,
                version=datasite_data.version,
                readme=datasite_data.readme,
                contributors=datasite_data.contributors,
                policies=[policy.model_dump() for policy in datasite_data.policies],
                connect=[conn.model_dump() for conn in datasite_data.connect],
                is_active=True,
            )

            self.session.add(datasite_model)
            self.session.commit()
            self.session.refresh(datasite_model)

            return Datasite.model_validate(datasite_model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def update_datasite(
        self, datasite_id: int, datasite_data: DatasiteUpdate
    ) -> Optional[Datasite]:
        """Update datasite information."""
        try:
            datasite_model = self.session.get(self.model, datasite_id)
            if not datasite_model:
                return None

            # Update fields if provided
            if datasite_data.name is not None:
                datasite_model.name = datasite_data.name
            if datasite_data.description is not None:
                datasite_model.description = datasite_data.description
            if datasite_data.visibility is not None:
                datasite_model.visibility = datasite_data.visibility.value
            if datasite_data.version is not None:
                datasite_model.version = datasite_data.version
            if datasite_data.readme is not None:
                datasite_model.readme = datasite_data.readme
            if datasite_data.contributors is not None:
                datasite_model.contributors = datasite_data.contributors
            if datasite_data.policies is not None:
                datasite_model.policies = [
                    policy.model_dump() for policy in datasite_data.policies
                ]
            if datasite_data.connect is not None:
                datasite_model.connect = [
                    conn.model_dump() for conn in datasite_data.connect
                ]
            if datasite_data.is_active is not None:
                datasite_model.is_active = datasite_data.is_active

            self.session.commit()
            self.session.refresh(datasite_model)

            return Datasite.model_validate(datasite_model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def delete_datasite(self, datasite_id: int) -> bool:
        """Delete a datasite (soft delete by setting is_active=False)."""
        try:
            datasite_model = self.session.get(self.model, datasite_id)
            if not datasite_model:
                return False

            datasite_model.is_active = False
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def slug_exists_for_user(
        self, user_id: int, slug: str, exclude_datasite_id: Optional[int] = None
    ) -> bool:
        """Check if slug exists for a specific user."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.user_id == user_id,
                    self.model.slug == slug.lower(),
                    self.model.is_active,
                )
            )

            if exclude_datasite_id:
                stmt = stmt.where(self.model.id != exclude_datasite_id)

            result = self.session.execute(stmt.limit(1))
            return result.scalar() is not None
        except SQLAlchemyError:
            return False

    def slug_exists_for_organization(
        self, org_id: int, slug: str, exclude_datasite_id: Optional[int] = None
    ) -> bool:
        """Check if slug exists for a specific organization."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id,
                    self.model.slug == slug.lower(),
                    self.model.is_active,
                )
            )

            if exclude_datasite_id:
                stmt = stmt.where(self.model.id != exclude_datasite_id)

            result = self.session.execute(stmt.limit(1))
            return result.scalar() is not None
        except SQLAlchemyError:
            return False

    def increment_stars(self, datasite_id: int) -> bool:
        """Increment the star count for a datasite."""
        try:
            datasite_model = self.session.get(self.model, datasite_id)
            if not datasite_model:
                return False

            datasite_model.stars_count += 1
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def decrement_stars(self, datasite_id: int) -> bool:
        """Decrement the star count for a datasite."""
        try:
            datasite_model = self.session.get(self.model, datasite_id)
            if not datasite_model:
                return False

            if datasite_model.stars_count > 0:
                datasite_model.stars_count -= 1
                self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def create(self, data=None, **kwargs) -> Optional[Datasite]:
        """Create a new datasite with data dict or kwargs (for test compatibility)."""
        try:
            if data is not None:
                kwargs.update(data)
            datasite_model = self.model(**kwargs)
            self.session.add(datasite_model)
            self.session.commit()
            self.session.refresh(datasite_model)
            return Datasite.model_validate(datasite_model)
        except Exception:
            self.session.rollback()
            return None

    def get_all(
        self, skip: int = 0, limit: int = 100, filters: Optional[dict] = None
    ) -> list[Datasite]:
        """Get all datasites with pagination and filtering."""
        try:
            datasite_models = super().get_all(skip=skip, limit=limit, filters=filters)
            return [
                Datasite.model_validate(datasite_model)
                for datasite_model in datasite_models
            ]
        except Exception:
            return []

    def update(self, datasite_id: int, data=None, **kwargs) -> Optional[Datasite]:
        """Update a datasite with data dict or kwargs (for test compatibility)."""
        try:
            if data is not None:
                kwargs.update(data)
            datasite_model = self.session.get(self.model, datasite_id)
            if not datasite_model:
                return None

            for field, value in kwargs.items():
                if hasattr(datasite_model, field):
                    setattr(datasite_model, field, value)

            self.session.commit()
            self.session.refresh(datasite_model)
            return Datasite.model_validate(datasite_model)
        except Exception:
            self.session.rollback()
            return None

    def delete(self, datasite_id: int) -> bool:
        """Delete a datasite by ID."""
        try:
            datasite_model = self.session.get(self.model, datasite_id)
            if not datasite_model:
                return False

            self.session.delete(datasite_model)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def count(self, filters: Optional[dict] = None) -> int:
        """Count datasites with optional filtering."""
        return super().count(filters)

    def get_by_user_id(self, user_id: int) -> list[Datasite]:
        """Get all datasites by user ID (alias for test compatibility)."""
        return self.get_user_datasites(user_id)

    def get_public_datasites_by_user_id(self, user_id: int) -> list[Datasite]:
        """Get public datasites by user ID (alias for test compatibility)."""
        # Filter user's datasites to only include public ones
        user_datasites = self.get_user_datasites(user_id)
        return [
            ds for ds in user_datasites if ds.visibility == DatasiteVisibility.PUBLIC
        ]

    def get_public_by_user_id(self, user_id: int) -> list[Datasite]:
        """Get public datasites by user ID (alias for test compatibility)."""
        # Filter user's datasites to only include public ones
        user_datasites = self.get_user_datasites(user_id)
        return [
            ds for ds in user_datasites if ds.visibility == DatasiteVisibility.PUBLIC
        ]


class DatasiteStarRepository(BaseRepository[DatasiteStarModel]):
    """Repository for datasite star operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, DatasiteStarModel)

    def star_datasite(self, user_id: int, datasite_id: int) -> bool:
        """Add a star to a datasite."""
        try:
            # Check if already starred
            if self.is_starred(user_id, datasite_id):
                return False

            star_model = DatasiteStarModel(user_id=user_id, datasite_id=datasite_id)

            self.session.add(star_model)
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def unstar_datasite(self, user_id: int, datasite_id: int) -> bool:
        """Remove a star from a datasite."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.user_id == user_id, self.model.datasite_id == datasite_id
                )
            )
            result = self.session.execute(stmt)
            star = result.scalar_one_or_none()

            if star:
                self.session.delete(star)
                self.session.commit()
                return True
            return False
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def is_starred(self, user_id: int, datasite_id: int) -> bool:
        """Check if user has starred a datasite."""
        return self.exists(user_id=user_id, datasite_id=datasite_id)

    def get_user_starred_datasites(
        self, user_id: int, skip: int = 0, limit: int = 10
    ) -> List[int]:
        """Get list of datasite IDs starred by a user."""
        try:
            stmt = (
                select(self.model.datasite_id)
                .where(self.model.user_id == user_id)
                .order_by(self.model.starred_at.desc())
                .offset(skip)
                .limit(limit)
            )

            result = self.session.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError:
            return []

    def get_datasite_stargazers(
        self, datasite_id: int, skip: int = 0, limit: int = 10
    ) -> List[int]:
        """Get list of user IDs who starred a datasite."""
        try:
            stmt = (
                select(self.model.user_id)
                .where(self.model.datasite_id == datasite_id)
                .order_by(self.model.starred_at.desc())
                .offset(skip)
                .limit(limit)
            )

            result = self.session.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError:
            return []
