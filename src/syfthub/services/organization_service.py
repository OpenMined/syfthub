"""Organization management business logic service."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from fastapi import HTTPException, status

from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationResponse,
    OrganizationRole,
    OrganizationUpdate,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User


class OrganizationService(BaseService):
    """Organization service for handling organization operations."""

    def __init__(self, session: Session):
        """Initialize organization service."""
        super().__init__(session)
        self.org_repository = OrganizationRepository(session)
        self.member_repository = OrganizationMemberRepository(session)

    def create_organization(
        self, org_data: OrganizationCreate, current_user: User
    ) -> OrganizationResponse:
        """Create a new organization with current user as owner."""
        # Create organization
        organization = self.org_repository.create_organization(org_data)
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create organization",
            )

        # Add creator as owner
        member_data = OrganizationMemberCreate(
            user_id=current_user.id,
            role=OrganizationRole.OWNER,
            is_active=True,
        )

        self.member_repository.add_member(member_data, organization.id)

        return OrganizationResponse.model_validate(organization)

    def get_organization(self, slug: str) -> Optional[OrganizationResponse]:
        """Get organization by slug."""
        organization = self.org_repository.get_by_slug(slug)
        if organization:
            return OrganizationResponse.model_validate(organization)
        return None

    def update_organization(
        self, org_id: int, org_data: OrganizationUpdate, current_user: User
    ) -> OrganizationResponse:
        """Update organization (only owners/admins)."""
        # Check if user is owner or admin of organization
        if not self._can_manage_organization(org_id, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        updated_org = self.org_repository.update_organization(org_id, org_data)
        if not updated_org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        return OrganizationResponse.model_validate(updated_org)

    def add_member(
        self, org_id: int, member_data: OrganizationMemberCreate, current_user: User
    ) -> OrganizationMemberResponse:
        """Add member to organization."""
        if not self._can_manage_organization(org_id, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        member = self.member_repository.add_member(member_data, org_id)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to add member (already exists or invalid data)",
            )

        return member

    def remove_member(self, org_id: int, user_id: int, current_user: User) -> bool:
        """Remove member from organization."""
        if not self._can_manage_organization(org_id, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        success = self.member_repository.remove_member(org_id, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found",
            )

        return success

    def is_member(self, org_id: int, user_id: int) -> bool:
        """Check if user is member of organization."""
        return self.member_repository.is_member(org_id, user_id)

    def get_member_role(self, org_id: int, user_id: int) -> Optional[OrganizationRole]:
        """Get user's role in organization."""
        return self.member_repository.get_member_role(org_id, user_id)

    def get_organization_members(
        self, org_id: int, current_user: User
    ) -> List[OrganizationMemberResponse]:
        """Get organization members."""
        # Check if user has access to view members
        if not self._can_view_organization(org_id, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        return self.member_repository.get_organization_members(org_id)

    def get_user_organizations(self, user_id: int) -> List[OrganizationResponse]:
        """Get organizations user is member of."""
        return self.member_repository.get_user_organizations(user_id)

    def _can_manage_organization(self, org_id: int, user: User) -> bool:
        """Check if user can manage organization (owner/admin role)."""
        if user.role == "admin":
            return True

        member_role = self.member_repository.get_member_role(org_id, user.id)
        return member_role in [OrganizationRole.OWNER, OrganizationRole.ADMIN]

    def _can_view_organization(self, org_id: int, user: User) -> bool:
        """Check if user can view organization details."""
        if user.role == "admin":
            return True

        return self.member_repository.is_member(org_id, user.id)
