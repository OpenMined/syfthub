"""Endpoint repository for database operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.core.url_builder import transform_connection_urls
from syfthub.models.endpoint import EndpointModel, EndpointStarModel
from syfthub.models.user import UserModel
from syfthub.repositories.base import BaseRepository
from syfthub.schemas.endpoint import (
    Endpoint,
    EndpointAdminUpdate,
    EndpointCreate,
    EndpointPublicResponse,
    EndpointType,
    EndpointUpdate,
    EndpointVisibility,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class EndpointRepository(BaseRepository[EndpointModel]):
    """Repository for endpoint database operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, EndpointModel)

    def get_by_id(self, endpoint_id: int) -> Optional[Endpoint]:
        """Get endpoint by ID (only active endpoints)."""
        try:
            stmt = select(self.model).where(
                and_(self.model.id == endpoint_id, self.model.is_active)
            )
            result = self.session.execute(stmt)
            endpoint_model = result.scalar_one_or_none()
            if endpoint_model:
                return Endpoint.model_validate(endpoint_model)
            return None
        except SQLAlchemyError:
            return None

    def get_by_user_and_slug(self, user_id: int, slug: str) -> Optional[Endpoint]:
        """Get endpoint by user ID and slug."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.user_id == user_id,
                    self.model.slug == slug.lower(),
                    self.model.is_active,
                )
            )
            result = self.session.execute(stmt)
            endpoint_model = result.scalar_one_or_none()

            if endpoint_model:
                return Endpoint.model_validate(endpoint_model)
            return None
        except SQLAlchemyError:
            return None

    def get_by_organization_and_slug(
        self, org_id: int, slug: str
    ) -> Optional[Endpoint]:
        """Get endpoint by organization ID and slug."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id,
                    self.model.slug == slug.lower(),
                    self.model.is_active,
                )
            )
            result = self.session.execute(stmt)
            endpoint_model = result.scalar_one_or_none()

            if endpoint_model:
                return Endpoint.model_validate(endpoint_model)
            return None
        except SQLAlchemyError:
            return None

    def get_user_endpoints(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[EndpointVisibility] = None,
        search: Optional[str] = None,
    ) -> List[Endpoint]:
        """Get all endpoints for a user with optional search.

        Note: This returns ALL user endpoints including inactive ones,
        so owners can always see and manage their own endpoints regardless
        of health status or soft-delete state.
        """
        try:
            stmt = select(self.model).where(self.model.user_id == user_id)

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
            endpoint_models = result.scalars().all()

            return [Endpoint.model_validate(endpoint) for endpoint in endpoint_models]
        except SQLAlchemyError:
            return []

    def get_organization_endpoints(
        self,
        org_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[EndpointVisibility] = None,
    ) -> List[Endpoint]:
        """Get all endpoints for an organization.

        Note: This returns ALL organization endpoints including inactive ones,
        so members can always see and manage their org's endpoints regardless
        of health status or soft-delete state.
        """
        try:
            stmt = select(self.model).where(self.model.organization_id == org_id)

            if visibility:
                stmt = stmt.where(self.model.visibility == visibility.value)

            stmt = stmt.order_by(self.model.updated_at.desc()).offset(skip).limit(limit)

            result = self.session.execute(stmt)
            endpoint_models = result.scalars().all()

            return [Endpoint.model_validate(endpoint) for endpoint in endpoint_models]
        except SQLAlchemyError:
            return []

    def get_public_endpoints(
        self,
        skip: int = 0,
        limit: int = 10,
        endpoint_type: Optional[EndpointType] = None,
    ) -> List[EndpointPublicResponse]:
        """Get all public endpoints with owner usernames and transformed URLs."""
        try:
            stmt = (
                select(self.model, UserModel.username, UserModel.domain)
                .join(UserModel, self.model.user_id == UserModel.id)
                .where(
                    and_(
                        self.model.visibility == EndpointVisibility.PUBLIC.value,
                        self.model.is_active,
                    )
                )
            )

            if endpoint_type:
                stmt = stmt.where(self.model.type == endpoint_type.value)

            stmt = stmt.order_by(self.model.updated_at.desc()).offset(skip).limit(limit)

            result = self.session.execute(stmt)
            rows = result.all()

            endpoints = []
            for endpoint_model, username, domain in rows:
                # Transform connection URLs using owner's domain
                transformed_connect = transform_connection_urls(
                    domain, endpoint_model.connect or []
                )

                endpoint_dict = {
                    "name": endpoint_model.name,
                    "slug": endpoint_model.slug,
                    "description": endpoint_model.description,
                    "type": endpoint_model.type,
                    "owner_username": username,
                    "contributors_count": len(endpoint_model.contributors or []),
                    "version": endpoint_model.version,
                    "readme": endpoint_model.readme,
                    "tags": endpoint_model.tags or [],
                    "stars_count": endpoint_model.stars_count,
                    "policies": endpoint_model.policies,
                    "connect": transformed_connect,
                    "created_at": endpoint_model.created_at,
                    "updated_at": endpoint_model.updated_at,
                }
                endpoints.append(EndpointPublicResponse(**endpoint_dict))

            return endpoints
        except SQLAlchemyError:
            return []

    def get_trending_endpoints(
        self,
        skip: int = 0,
        limit: int = 10,
        min_stars: Optional[int] = None,
        endpoint_type: Optional[EndpointType] = None,
    ) -> List[EndpointPublicResponse]:
        """Get trending public endpoints with owner usernames and transformed URLs, sorted by stars count."""
        try:
            stmt = (
                select(self.model, UserModel.username, UserModel.domain)
                .join(UserModel, self.model.user_id == UserModel.id)
                .where(
                    and_(
                        self.model.visibility == EndpointVisibility.PUBLIC.value,
                        self.model.is_active,
                    )
                )
            )

            if min_stars is not None:
                stmt = stmt.where(self.model.stars_count >= min_stars)

            if endpoint_type:
                stmt = stmt.where(self.model.type == endpoint_type.value)

            stmt = (
                stmt.order_by(self.model.stars_count.desc()).offset(skip).limit(limit)
            )

            result = self.session.execute(stmt)
            rows = result.all()

            endpoints = []
            for endpoint_model, username, domain in rows:
                # Transform connection URLs using owner's domain
                transformed_connect = transform_connection_urls(
                    domain, endpoint_model.connect or []
                )

                endpoint_dict = {
                    "name": endpoint_model.name,
                    "slug": endpoint_model.slug,
                    "description": endpoint_model.description,
                    "type": endpoint_model.type,
                    "owner_username": username,
                    "contributors_count": len(endpoint_model.contributors or []),
                    "version": endpoint_model.version,
                    "readme": endpoint_model.readme,
                    "tags": endpoint_model.tags or [],
                    "stars_count": endpoint_model.stars_count,
                    "policies": endpoint_model.policies,
                    "connect": transformed_connect,
                    "created_at": endpoint_model.created_at,
                    "updated_at": endpoint_model.updated_at,
                }
                endpoints.append(EndpointPublicResponse(**endpoint_dict))

            return endpoints
        except SQLAlchemyError:
            return []

    def create_endpoint(
        self,
        endpoint_data: EndpointCreate,
        owner_id: int,
        is_organization: bool = False,
    ) -> Optional[Endpoint]:
        """Create a new endpoint."""
        import logging

        logger = logging.getLogger(__name__)
        try:
            endpoint_model = EndpointModel(
                user_id=owner_id if not is_organization else None,
                organization_id=owner_id if is_organization else None,
                name=endpoint_data.name,
                slug=endpoint_data.slug.lower(),
                description=endpoint_data.description,
                type=endpoint_data.type.value,
                visibility=endpoint_data.visibility.value,
                version=endpoint_data.version,
                readme=endpoint_data.readme,
                contributors=endpoint_data.contributors,
                policies=[policy.model_dump() for policy in endpoint_data.policies],
                connect=[conn.model_dump() for conn in endpoint_data.connect],
                is_active=True,
            )

            self.session.add(endpoint_model)
            self.session.commit()
            self.session.refresh(endpoint_model)

            return Endpoint.model_validate(endpoint_model)
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy error creating endpoint: {e}")
            self.session.rollback()
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating endpoint: {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_endpoint(
        self, endpoint_id: int, endpoint_data: EndpointUpdate
    ) -> Optional[Endpoint]:
        """Update endpoint information."""
        try:
            endpoint_model = self.session.get(self.model, endpoint_id)
            if not endpoint_model:
                return None

            # Update fields if provided
            if endpoint_data.name is not None:
                endpoint_model.name = endpoint_data.name
            if endpoint_data.description is not None:
                endpoint_model.description = endpoint_data.description
            if endpoint_data.visibility is not None:
                endpoint_model.visibility = endpoint_data.visibility.value
            if endpoint_data.version is not None:
                endpoint_model.version = endpoint_data.version
            if endpoint_data.readme is not None:
                endpoint_model.readme = endpoint_data.readme
            if endpoint_data.contributors is not None:
                endpoint_model.contributors = endpoint_data.contributors
            if endpoint_data.policies is not None:
                endpoint_model.policies = [
                    policy.model_dump() for policy in endpoint_data.policies
                ]
            if endpoint_data.connect is not None:
                endpoint_model.connect = [
                    conn.model_dump() for conn in endpoint_data.connect
                ]
            # REMOVED is_active update - this should only be done by admin_update_endpoint

            self.session.commit()
            self.session.refresh(endpoint_model)

            return Endpoint.model_validate(endpoint_model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def admin_update_endpoint(
        self, endpoint_id: int, admin_data: EndpointAdminUpdate
    ) -> Optional[Endpoint]:
        """Admin-only update for server-managed fields like is_active and stars_count."""
        try:
            endpoint_model = self.session.get(self.model, endpoint_id)
            if not endpoint_model:
                return None

            # Admin can update server-managed fields
            if admin_data.is_active is not None:
                endpoint_model.is_active = admin_data.is_active
            if admin_data.stars_count is not None:
                endpoint_model.stars_count = admin_data.stars_count

            self.session.commit()
            self.session.refresh(endpoint_model)

            return Endpoint.model_validate(endpoint_model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def delete_endpoint(self, endpoint_id: int) -> bool:
        """Delete a endpoint (soft delete by setting is_active=False)."""
        try:
            endpoint_model = self.session.get(self.model, endpoint_id)
            if not endpoint_model:
                return False

            endpoint_model.is_active = False
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def slug_exists_for_user(
        self, user_id: int, slug: str, exclude_endpoint_id: Optional[int] = None
    ) -> bool:
        """Check if slug exists for a specific user.

        Note: This checks ALL endpoints (active and inactive) because the unique
        index on (user_id, slug) applies regardless of is_active status.
        """
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.user_id == user_id,
                    self.model.slug == slug.lower(),
                )
            )

            if exclude_endpoint_id:
                stmt = stmt.where(self.model.id != exclude_endpoint_id)

            result = self.session.execute(stmt.limit(1))
            return result.scalar() is not None
        except SQLAlchemyError:
            return False

    def slug_exists_for_organization(
        self, org_id: int, slug: str, exclude_endpoint_id: Optional[int] = None
    ) -> bool:
        """Check if slug exists for a specific organization.

        Note: This checks ALL endpoints (active and inactive) because the unique
        index on (organization_id, slug) applies regardless of is_active status.
        """
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id,
                    self.model.slug == slug.lower(),
                )
            )

            if exclude_endpoint_id:
                stmt = stmt.where(self.model.id != exclude_endpoint_id)

            result = self.session.execute(stmt.limit(1))
            return result.scalar() is not None
        except SQLAlchemyError:
            return False

    def increment_stars(self, endpoint_id: int) -> bool:
        """Increment the star count for a endpoint."""
        try:
            endpoint_model = self.session.get(self.model, endpoint_id)
            if not endpoint_model:
                return False

            endpoint_model.stars_count += 1
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def decrement_stars(self, endpoint_id: int) -> bool:
        """Decrement the star count for a endpoint."""
        try:
            endpoint_model = self.session.get(self.model, endpoint_id)
            if not endpoint_model:
                return False

            if endpoint_model.stars_count > 0:
                endpoint_model.stars_count -= 1
                self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def create(self, data=None, **kwargs) -> Optional[Endpoint]:
        """Create a new endpoint with data dict or kwargs (for test compatibility)."""
        try:
            if data is not None:
                kwargs.update(data)
            endpoint_model = self.model(**kwargs)
            self.session.add(endpoint_model)
            self.session.commit()
            self.session.refresh(endpoint_model)
            return Endpoint.model_validate(endpoint_model)
        except Exception:
            self.session.rollback()
            return None

    def get_all(
        self, skip: int = 0, limit: int = 100, filters: Optional[dict] = None
    ) -> list[Endpoint]:
        """Get all endpoints with pagination and filtering."""
        try:
            endpoint_models = super().get_all(skip=skip, limit=limit, filters=filters)
            return [
                Endpoint.model_validate(endpoint_model)
                for endpoint_model in endpoint_models
            ]
        except Exception:
            return []

    def update(self, endpoint_id: int, data=None, **kwargs) -> Optional[Endpoint]:
        """Update a endpoint with data dict or kwargs (for test compatibility)."""
        try:
            if data is not None:
                kwargs.update(data)
            endpoint_model = self.session.get(self.model, endpoint_id)
            if not endpoint_model:
                return None

            for field, value in kwargs.items():
                if hasattr(endpoint_model, field):
                    setattr(endpoint_model, field, value)

            self.session.commit()
            self.session.refresh(endpoint_model)
            return Endpoint.model_validate(endpoint_model)
        except Exception:
            self.session.rollback()
            return None

    def delete(self, endpoint_id: int) -> bool:
        """Delete a endpoint by ID."""
        try:
            endpoint_model = self.session.get(self.model, endpoint_id)
            if not endpoint_model:
                return False

            self.session.delete(endpoint_model)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def count(self, filters: Optional[dict] = None) -> int:
        """Count endpoints with optional filtering."""
        return super().count(filters)

    def get_by_user_id(self, user_id: int) -> list[Endpoint]:
        """Get all endpoints by user ID (alias for test compatibility)."""
        return self.get_user_endpoints(user_id)

    def get_public_endpoints_by_user_id(self, user_id: int) -> list[Endpoint]:
        """Get public endpoints by user ID (alias for test compatibility).

        Note: This is for PUBLIC browsing, so it filters to only active + public endpoints.
        For owner management view, use get_user_endpoints() instead.
        """
        user_endpoints = self.get_user_endpoints(user_id)
        return [
            ds
            for ds in user_endpoints
            if ds.visibility == EndpointVisibility.PUBLIC and ds.is_active
        ]

    def get_public_by_user_id(self, user_id: int) -> list[Endpoint]:
        """Get public endpoints by user ID (alias for test compatibility).

        Note: This is for PUBLIC browsing, so it filters to only active + public endpoints.
        For owner management view, use get_user_endpoints() instead.
        """
        user_endpoints = self.get_user_endpoints(user_id)
        return [
            ds
            for ds in user_endpoints
            if ds.visibility == EndpointVisibility.PUBLIC and ds.is_active
        ]


class EndpointStarRepository(BaseRepository[EndpointStarModel]):
    """Repository for endpoint star operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, EndpointStarModel)

    def star_endpoint(self, user_id: int, endpoint_id: int) -> bool:
        """Add a star to a endpoint."""
        try:
            # Check if already starred
            if self.is_starred(user_id, endpoint_id):
                return False

            star_model = EndpointStarModel(user_id=user_id, endpoint_id=endpoint_id)

            self.session.add(star_model)
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def unstar_endpoint(self, user_id: int, endpoint_id: int) -> bool:
        """Remove a star from a endpoint."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.user_id == user_id, self.model.endpoint_id == endpoint_id
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

    def is_starred(self, user_id: int, endpoint_id: int) -> bool:
        """Check if user has starred a endpoint."""
        return self.exists(user_id=user_id, endpoint_id=endpoint_id)

    def get_user_starred_endpoints(
        self, user_id: int, skip: int = 0, limit: int = 10
    ) -> List[int]:
        """Get list of endpoint IDs starred by a user."""
        try:
            stmt = (
                select(self.model.endpoint_id)
                .where(self.model.user_id == user_id)
                .order_by(self.model.starred_at.desc())
                .offset(skip)
                .limit(limit)
            )

            result = self.session.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError:
            return []

    def get_endpoint_stargazers(
        self, endpoint_id: int, skip: int = 0, limit: int = 10
    ) -> List[int]:
        """Get list of user IDs who starred a endpoint."""
        try:
            stmt = (
                select(self.model.user_id)
                .where(self.model.endpoint_id == endpoint_id)
                .order_by(self.model.starred_at.desc())
                .offset(skip)
                .limit(limit)
            )

            result = self.session.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError:
            return []
