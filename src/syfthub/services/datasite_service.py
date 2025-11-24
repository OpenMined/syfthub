"""Datasite management business logic service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from fastapi import HTTPException, status

from syfthub.repositories.datasite import DatasiteRepository, DatasiteStarRepository
from syfthub.repositories.organization import OrganizationMemberRepository
from syfthub.schemas.datasite import (
    RESERVED_SLUGS,
    Datasite,
    DatasiteCreate,
    DatasitePublicResponse,
    DatasiteResponse,
    DatasiteUpdate,
    DatasiteVisibility,
    generate_slug_from_name,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User


class DatasiteService(BaseService):
    """Datasite service for handling datasite operations."""

    def __init__(self, session: Session):
        """Initialize datasite service."""
        super().__init__(session)
        self.datasite_repository = DatasiteRepository(session)
        self.star_repository = DatasiteStarRepository(session)
        self.org_member_repository = OrganizationMemberRepository(session)

    def _is_slug_available(
        self,
        slug: str,
        user_id: int,
        exclude_datasite_id: Optional[int] = None,
    ) -> bool:
        """Check if a slug is available for a user."""
        if slug in RESERVED_SLUGS:
            return False

        # Use repository to check if slug exists for user
        exists = self.datasite_repository.slug_exists_for_user(
            user_id, slug, exclude_datasite_id
        )
        return not exists

    def _generate_unique_slug(
        self,
        name: str,
        owner_id: int,
        is_organization: bool = False,
    ) -> str:
        """Generate a unique slug for a user or organization."""
        base_slug = generate_slug_from_name(name)

        # Check if base slug is available
        if is_organization:
            slug_available = not self.datasite_repository.slug_exists_for_organization(
                owner_id, base_slug
            )
        else:
            slug_available = self._is_slug_available(base_slug, owner_id)

        if slug_available:
            return base_slug

        # If base slug is taken, append numbers
        counter = 1
        while counter < 1000:  # Prevent infinite loops
            new_slug = f"{base_slug}-{counter}"
            if len(new_slug) <= 63:
                if is_organization:
                    if not self.datasite_repository.slug_exists_for_organization(
                        owner_id, new_slug
                    ):
                        return new_slug
                else:
                    if self._is_slug_available(new_slug, owner_id):
                        return new_slug
            counter += 1

        # Fallback: use timestamp
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-6:]
        return f"{base_slug[:50]}-{timestamp}"

    def create_datasite(
        self,
        datasite_data: DatasiteCreate,
        owner_id: int,
        is_organization: bool = False,
        current_user: Optional[User] = None,
    ) -> DatasiteResponse:
        """Create a new datasite."""
        # Validate permissions for organization datasites
        if (
            is_organization
            and current_user
            and not self.org_member_repository.is_member(owner_id, current_user.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: not a member of organization",
            )

        # Auto-generate slug if not provided
        if datasite_data.slug is None:
            datasite_data.slug = self._generate_unique_slug(
                datasite_data.name, owner_id, is_organization
            )

        if is_organization:
            if self.datasite_repository.slug_exists_for_organization(
                owner_id, datasite_data.slug
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Datasite slug already exists for this organization",
                )
        else:
            if self.datasite_repository.slug_exists_for_user(
                owner_id, datasite_data.slug
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="slug already exists - already taken",
                )

        # Auto-add owner as contributor
        if not is_organization and owner_id not in datasite_data.contributors:
            datasite_data.contributors.append(owner_id)

        # Create datasite
        datasite = self.datasite_repository.create_datasite(
            datasite_data, owner_id, is_organization
        )

        if not datasite:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create datasite",
            )

        return DatasiteResponse.model_validate(datasite)

    def get_datasite_by_user_and_slug(
        self, user_id: int, slug: str
    ) -> Optional[Datasite]:
        """Get datasite by user and slug."""
        return self.datasite_repository.get_by_user_and_slug(user_id, slug)

    def get_datasite_by_org_and_slug(
        self, org_id: int, slug: str
    ) -> Optional[Datasite]:
        """Get datasite by organization and slug."""
        return self.datasite_repository.get_by_organization_and_slug(org_id, slug)

    def get_user_datasites(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[DatasiteVisibility] = None,
        search: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> List[DatasiteResponse]:
        """Get user's datasites with proper access control and search."""
        datasites = self.datasite_repository.get_user_datasites(
            user_id, skip, limit, visibility, search
        )

        accessible_datasites = []
        for datasite in datasites:
            if self._can_access_datasite(datasite, current_user, "user"):
                if self._can_see_full_details(datasite, current_user, "user"):
                    accessible_datasites.append(
                        DatasiteResponse.model_validate(datasite)
                    )
                else:
                    accessible_datasites.append(
                        DatasiteResponse.model_validate(datasite)
                    )

        return accessible_datasites

    def get_organization_datasites(
        self,
        org_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[DatasiteVisibility] = None,
        current_user: Optional[User] = None,
    ) -> List[DatasiteResponse]:
        """Get organization's datasites with proper access control."""
        datasites = self.datasite_repository.get_organization_datasites(
            org_id, skip, limit, visibility
        )

        accessible_datasites = []
        for datasite in datasites:
            if self._can_access_datasite(datasite, current_user, "organization"):
                if self._can_see_full_details(datasite, current_user, "organization"):
                    accessible_datasites.append(
                        DatasiteResponse.model_validate(datasite)
                    )
                else:
                    accessible_datasites.append(
                        DatasiteResponse.model_validate(datasite)
                    )

        return accessible_datasites

    def get_public_datasites(
        self, skip: int = 0, limit: int = 10
    ) -> List[DatasitePublicResponse]:
        """Get public datasites."""
        return self.datasite_repository.get_public_datasites(skip, limit)

    def update_datasite(
        self, datasite_id: int, datasite_data: DatasiteUpdate, current_user: User
    ) -> DatasiteResponse:
        """Update datasite."""
        datasite = self.datasite_repository.get_by_id(datasite_id)
        if not datasite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Datasite not found",
            )

        # Check permissions
        if not self._can_modify_datasite(datasite, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        updated_datasite = self.datasite_repository.update_datasite(
            datasite_id, datasite_data
        )
        if not updated_datasite:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update datasite",
            )

        return DatasiteResponse.model_validate(updated_datasite)

    # Router-compatible methods
    def list_user_datasites(
        self,
        current_user: User,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[DatasiteVisibility] = None,
        search: Optional[str] = None,
    ) -> List[DatasiteResponse]:
        """List current user's datasites - router-compatible wrapper."""
        return self.get_user_datasites(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            visibility=visibility,
            search=search,
            current_user=current_user,
        )

    def list_public_datasites(
        self, skip: int = 0, limit: int = 10
    ) -> List[DatasitePublicResponse]:
        """List public datasites - router-compatible wrapper."""
        return self.get_public_datasites(skip=skip, limit=limit)

    def list_trending_datasites(
        self, skip: int = 0, limit: int = 10, min_stars: Optional[int] = None
    ) -> List[DatasitePublicResponse]:
        """List trending public datasites sorted by stars count with optional min_stars filter."""
        return self.datasite_repository.get_trending_datasites(skip, limit, min_stars)

    def get_datasite(self, datasite_id: int, current_user: User) -> DatasiteResponse:
        """Get datasite by ID with access control."""
        datasite = self.datasite_repository.get_by_id(datasite_id)
        if not datasite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Datasite not found",
            )

        # Check permissions
        if not self._can_access_datasite(datasite, current_user, "user"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,  # Hide existence for security
                detail="Datasite not found",
            )

        return DatasiteResponse.model_validate(datasite)

    def delete_datasite(self, datasite_id: int, current_user: User) -> bool:
        """Delete datasite."""
        datasite = self.datasite_repository.get_by_id(datasite_id)
        if not datasite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Datasite not found",
            )

        # Check permissions
        if not self._can_modify_datasite(datasite, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        success = self.datasite_repository.delete_datasite(datasite_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete datasite",
            )

        return True

    def star_datasite(self, datasite_id: int, current_user: User) -> bool:
        """Star a datasite."""
        # Check if datasite exists and is accessible
        datasite = self.datasite_repository.get_by_id(datasite_id)
        if not datasite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Datasite not found",
            )

        owner_type = "organization" if datasite.organization_id else "user"
        if not self._can_access_datasite(datasite, current_user, owner_type):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Datasite not found",
            )

        # Add star
        success = self.star_repository.star_datasite(current_user.id, datasite_id)
        if success:
            self.datasite_repository.increment_stars(datasite_id)

        return success

    def unstar_datasite(self, datasite_id: int, current_user: User) -> bool:
        """Unstar a datasite."""
        success = self.star_repository.unstar_datasite(current_user.id, datasite_id)
        if success:
            self.datasite_repository.decrement_stars(datasite_id)

        return success

    def is_datasite_starred(self, datasite_id: int, current_user: User) -> bool:
        """Check if user has starred a datasite."""
        return self.star_repository.is_starred(current_user.id, datasite_id)

    def _can_access_datasite(
        self, datasite: Datasite, current_user: Optional[User], owner_type: str
    ) -> bool:
        """Check if user can access datasite."""
        # Public datasites are always accessible
        if datasite.visibility == DatasiteVisibility.PUBLIC:
            return True

        # Unauthenticated users can only see public datasites
        if current_user is None:
            return False

        # Admin can access everything
        if current_user.role == "admin":
            return True

        # For user-owned datasites
        if owner_type == "user" and datasite.user_id:
            # Owner can always access
            if datasite.user_id == current_user.id:
                return True
            # Internal datasites are accessible to any authenticated user
            if datasite.visibility == DatasiteVisibility.INTERNAL:
                return True
            # Private datasites are only accessible to owner
            return False

        # For organization-owned datasites
        if owner_type == "organization" and datasite.organization_id:
            if datasite.visibility == DatasiteVisibility.INTERNAL:
                return self.org_member_repository.is_member(
                    datasite.organization_id, current_user.id
                )
            if datasite.visibility == DatasiteVisibility.PRIVATE:
                return self.org_member_repository.is_member(
                    datasite.organization_id, current_user.id
                )

        return False

    def _can_see_full_details(
        self, datasite: Datasite, current_user: Optional[User], owner_type: str
    ) -> bool:
        """Check if user can see full datasite details."""
        if current_user is None:
            return datasite.visibility == DatasiteVisibility.PUBLIC

        if current_user.role == "admin":
            return True

        # For user-owned datasites
        if owner_type == "user" and datasite.user_id:
            return datasite.user_id == current_user.id

        # For organization-owned datasites
        if owner_type == "organization" and datasite.organization_id:
            return self.org_member_repository.is_member(
                datasite.organization_id, current_user.id
            )

        return datasite.visibility == DatasiteVisibility.PUBLIC

    def _can_modify_datasite(self, datasite: Datasite, current_user: User) -> bool:
        """Check if user can modify datasite."""
        if current_user.role == "admin":
            return True

        # For user-owned datasites
        if datasite.user_id:
            return datasite.user_id == current_user.id

        # For organization-owned datasites
        if datasite.organization_id:
            member_role = self.org_member_repository.get_member_role(
                datasite.organization_id, current_user.id
            )
            from syfthub.schemas.organization import OrganizationRole

            return member_role in [OrganizationRole.OWNER, OrganizationRole.ADMIN]

        return False
