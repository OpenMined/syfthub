"""Organization management business logic service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List, Optional
from urllib.parse import urlparse

from fastapi import HTTPException, status

from syfthub.core.config import settings
from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.schemas.organization import (
    Organization,
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationResponse,
    OrganizationRole,
    OrganizationUpdate,
)
from syfthub.schemas.user import HeartbeatResponse
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
        # Check for duplicate slug if provided
        if org_data.slug and self.org_repository.slug_exists(org_data.slug):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization slug already exists",
            )

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
        )

        self.member_repository.add_member(member_data, organization.id)

        return OrganizationResponse.model_validate(organization)

    def get_organization(self, org_id: int, current_user: User) -> OrganizationResponse:
        """Get organization by ID with access control."""
        organization = self.org_repository.get_by_id(org_id)
        if not organization or not organization.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        # Check if user has access to view organization
        if not self._can_view_organization(org_id, current_user):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        return OrganizationResponse.model_validate(organization)

    def get_organization_by_slug(self, slug: str) -> Optional[OrganizationResponse]:
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

    def is_organization_admin_or_owner(self, org_id: int, user_id: int) -> bool:
        """Check if user is admin or owner of organization."""
        role = self.member_repository.get_member_role(org_id, user_id)
        return role in (OrganizationRole.ADMIN, OrganizationRole.OWNER)

    def is_organization_member(self, org_id: int, user_id: int) -> bool:
        """Check if user is member of organization."""
        return self.member_repository.is_member(org_id, user_id)

    def get_organization_by_id(self, org_id: int) -> Optional[Organization]:
        """Get organization by ID."""
        return self.org_repository.get_by_id(org_id)

    def send_heartbeat(
        self,
        org_id: int,
        url: str,
        current_user: User,
        ttl_seconds: Optional[int] = None,
    ) -> HeartbeatResponse:
        """Send heartbeat to indicate organization's domain is online.

        This method:
        - Verifies user has permission to send heartbeats for the organization
        - Extracts domain (host + port) from the provided URL
        - Calculates effective TTL (capped at server max, defaults if not specified)
        - Updates organization's heartbeat information in the database

        Args:
            org_id: ID of the organization
            url: Full URL of the domain (e.g., 'https://api.example.com')
            current_user: The user making the request (for permission check)
            ttl_seconds: Requested TTL in seconds (optional, will use default if not provided)

        Returns:
            HeartbeatResponse with status, timestamps, domain, and effective TTL

        Raises:
            HTTPException: If organization not found, permission denied, URL is invalid,
                          or heartbeat update fails
        """
        # Check organization exists and is active
        organization = self.org_repository.get_by_id(org_id)
        if not organization or not organization.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        # Check permissions (admin/owner only, unless system admin)
        if not self._can_manage_organization(org_id, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or owner privileges required",
            )

        now = datetime.now(timezone.utc)

        # Calculate effective TTL (cap at max, use default if not specified)
        requested_ttl = ttl_seconds or settings.heartbeat_default_ttl_seconds
        effective_ttl = min(requested_ttl, settings.heartbeat_max_ttl_seconds)

        # Extract domain with protocol (scheme + host + port) from URL
        parsed = urlparse(url)
        if not parsed.netloc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid URL: could not extract domain",
            )
        domain = f"{parsed.scheme}://{parsed.netloc}"

        expires_at = now + timedelta(seconds=effective_ttl)

        # Update organization record
        success = self.org_repository.update_heartbeat(
            org_id=org_id,
            domain=domain,
            last_heartbeat_at=now,
            heartbeat_expires_at=expires_at,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update heartbeat",
            )

        return HeartbeatResponse(
            status="ok",
            received_at=now,
            expires_at=expires_at,
            domain=domain,
            ttl_seconds=effective_ttl,
        )
