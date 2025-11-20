"""Datasite management business logic service."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from fastapi import HTTPException, status

from syfthub.repositories.datasite import DatasiteRepository, DatasiteStarRepository
from syfthub.repositories.organization import OrganizationMemberRepository
from syfthub.schemas.datasite import (
    Datasite,
    DatasiteCreate,
    DatasitePublicResponse,
    DatasiteResponse,
    DatasiteUpdate,
    DatasiteVisibility,
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

        # Check slug uniqueness
        if datasite_data.slug is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slug is required for datasite creation",
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
                    detail="Datasite slug already exists for this user",
                )

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
        current_user: Optional[User] = None,
    ) -> List[DatasiteResponse]:
        """Get user's datasites with proper access control."""
        datasites = self.datasite_repository.get_user_datasites(
            user_id, skip, limit, visibility
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

        return success

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
            return datasite.user_id == current_user.id

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
