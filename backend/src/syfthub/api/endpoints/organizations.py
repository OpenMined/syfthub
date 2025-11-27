"""Organization management endpoints."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from syfthub.auth.db_dependencies import get_current_active_user, require_admin
from syfthub.database.dependencies import (
    get_organization_member_repository,
    get_organization_repository,
    get_organization_service,
)
from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.organization import (
    Organization,
    OrganizationAdminUpdate,
    OrganizationCreate,
    OrganizationMemberAdminUpdate,
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationMemberUpdate,
    OrganizationResponse,
    OrganizationRole,
    OrganizationUpdate,
)
from syfthub.schemas.user import User
from syfthub.services.organization_service import OrganizationService

router = APIRouter()

# Helper functions that work with repository pattern


def get_organization_by_id(
    org_id: int, org_repo: OrganizationRepository
) -> Optional[Organization]:
    """Get organization by ID."""
    return org_repo.get_by_id(org_id)


def get_organization_by_slug(
    slug: str, org_repo: OrganizationRepository
) -> Optional[Organization]:
    """Get organization by slug."""
    return org_repo.get_by_slug(slug)


def get_user_role_in_organization(
    org_id: int, user_id: int, member_repo: OrganizationMemberRepository
) -> Optional[OrganizationRole]:
    """Get user's role in organization."""
    return member_repo.get_member_role(org_id, user_id)


def is_organization_member(
    org_id: int, user_id: int, member_repo: OrganizationMemberRepository
) -> bool:
    """Check if user is an active member of organization."""
    return member_repo.is_member(org_id, user_id)


def is_organization_admin_or_owner(
    org_id: int, user_id: int, member_repo: OrganizationMemberRepository
) -> bool:
    """Check if user is admin or owner of organization."""
    role = member_repo.get_member_role(org_id, user_id)
    return role in (OrganizationRole.ADMIN, OrganizationRole.OWNER)


def is_organization_owner(
    org_id: int, user_id: int, member_repo: OrganizationMemberRepository
) -> bool:
    """Check if user is owner of organization."""
    role = member_repo.get_member_role(org_id, user_id)
    return role == OrganizationRole.OWNER


def require_organization_member(
    org_id: int, user_id: int, member_repo: OrganizationMemberRepository
) -> None:
    """Require user to be organization member."""
    if not is_organization_member(org_id, user_id, member_repo):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )


def require_organization_admin(
    org_id: int, user_id: int, member_repo: OrganizationMemberRepository
) -> None:
    """Require user to be organization admin or owner."""
    if not is_organization_admin_or_owner(org_id, user_id, member_repo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner privileges required",
        )


def require_organization_owner(
    org_id: int, user_id: int, member_repo: OrganizationMemberRepository
) -> None:
    """Require user to be organization owner."""
    if not is_organization_owner(org_id, user_id, member_repo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner privileges required"
        )


@router.get("/", response_model=list[OrganizationResponse])
async def list_my_organizations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    role: Optional[OrganizationRole] = None,
) -> list[OrganizationResponse]:
    """List current user's organizations."""
    # Get user's organization memberships
    user_orgs = member_repo.get_user_organizations(current_user.id)

    # Filter by role if specified
    if role is not None:
        filtered_orgs = []
        for org in user_orgs:
            user_role = member_repo.get_member_role(org.id, current_user.id)
            if user_role == role:
                filtered_orgs.append(org)
        user_orgs = filtered_orgs

    # Sort by most recent first
    user_orgs.sort(key=lambda org: org.updated_at, reverse=True)

    # Apply pagination
    user_orgs = user_orgs[skip : skip + limit]

    return user_orgs


@router.post(
    "/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    org_data: OrganizationCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    org_service: Annotated[OrganizationService, Depends(get_organization_service)],
) -> OrganizationResponse:
    """Create a new organization."""
    return org_service.create_organization(org_data, current_user)


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    org_service: Annotated[OrganizationService, Depends(get_organization_service)],
) -> OrganizationResponse:
    """Get organization details."""
    return org_service.get_organization(org_id, current_user)


@router.put("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: int,
    org_update: OrganizationUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
) -> OrganizationResponse:
    """Update organization."""
    organization = get_organization_by_id(org_id, org_repo)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (admin/owner only)
    if current_user.role != UserRole.ADMIN:
        require_organization_admin(org_id, current_user.id, member_repo)

    # Update organization
    updated_organization = org_repo.update_organization(org_id, org_update)
    if not updated_organization:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update organization",
        )

    return OrganizationResponse.model_validate(updated_organization)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
) -> None:
    """Delete organization (soft delete)."""
    organization = get_organization_by_id(org_id, org_repo)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (owner only)
    if current_user.role != UserRole.ADMIN:
        require_organization_owner(org_id, current_user.id, member_repo)

    # Soft delete organization using admin method
    admin_data = OrganizationAdminUpdate(is_active=False)
    updated_organization = org_repo.admin_update_organization(org_id, admin_data)
    if not updated_organization:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete organization",
        )


@router.get("/{org_id}/members", response_model=list[OrganizationMemberResponse])
async def list_organization_members(
    org_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    role: Optional[OrganizationRole] = None,
) -> list[OrganizationMemberResponse]:
    """List organization members."""
    organization = get_organization_by_id(org_id, org_repo)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions
    if current_user.role != UserRole.ADMIN:
        require_organization_member(org_id, current_user.id, member_repo)

    # Get organization members
    members = member_repo.get_organization_members(org_id)

    # Filter by role if specified
    if role is not None:
        members = [
            member for member in members if OrganizationRole(member.role) == role
        ]

    # Sort by join date (most recent first)
    members.sort(key=lambda m: m.joined_at, reverse=True)

    # Apply pagination
    members = members[skip : skip + limit]

    return members


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_organization_member(
    org_id: int,
    member_data: OrganizationMemberCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
) -> OrganizationMemberResponse:
    """Add member to organization."""
    organization = get_organization_by_id(org_id, org_repo)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (admin/owner only)
    if current_user.role != UserRole.ADMIN:
        require_organization_admin(org_id, current_user.id, member_repo)

    # Check if user is already a member
    if is_organization_member(org_id, member_data.user_id, member_repo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member"
        )

    # Add member
    member = member_repo.add_member(member_data, org_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add member to organization",
        )

    return member


@router.put("/{org_id}/members/{user_id}", response_model=OrganizationMemberResponse)
async def update_organization_member(
    org_id: int,
    user_id: int,
    member_update: OrganizationMemberUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
) -> OrganizationMemberResponse:
    """Update organization member."""
    organization = get_organization_by_id(org_id, org_repo)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (admin/owner only)
    if current_user.role != UserRole.ADMIN:
        require_organization_admin(org_id, current_user.id, member_repo)

    # Get current member role
    current_member_role = member_repo.get_member_role(org_id, user_id)
    if not current_member_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Prevent removing the last owner
    if (
        member_update.role is not None
        and member_update.role != OrganizationRole.OWNER
        and current_member_role == OrganizationRole.OWNER
    ):
        owners_count = member_repo.count_owners(org_id)
        if owners_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner from organization",
            )

    # Update member
    update_data = member_update.model_dump(exclude_unset=True)
    updated_member = member_repo.update_member(org_id, user_id, update_data)
    if not updated_member:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update organization member",
        )

    return updated_member


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_organization_member(
    org_id: int,
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
) -> None:
    """Remove member from organization."""
    organization = get_organization_by_id(org_id, org_repo)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (admin/owner only, or user removing themselves)
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        require_organization_admin(org_id, current_user.id, member_repo)

    # Get current member role
    current_member_role = member_repo.get_member_role(org_id, user_id)
    if not current_member_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Prevent removing the last owner
    if current_member_role == OrganizationRole.OWNER:
        owners_count = member_repo.count_owners(org_id)
        if owners_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner from organization",
            )

    # Remove member
    success = member_repo.remove_member(org_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove member from organization",
        )


# Admin-only endpoints
@router.patch("/{org_id}/admin", response_model=OrganizationResponse)
async def admin_update_organization(
    org_id: int,
    admin_data: OrganizationAdminUpdate,
    _current_user: Annotated[User, Depends(get_current_active_user)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    _: Annotated[bool, Depends(require_admin)],
) -> OrganizationResponse:
    """Admin-only organization updates (is_active override)."""

    organization = get_organization_by_id(org_id, org_repo)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    updated_organization = org_repo.admin_update_organization(org_id, admin_data)
    if not updated_organization:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update organization",
        )

    return OrganizationResponse.model_validate(updated_organization)


@router.patch(
    "/{org_id}/members/{user_id}/admin", response_model=OrganizationMemberResponse
)
async def admin_update_organization_member(
    org_id: int,
    user_id: int,
    admin_data: OrganizationMemberAdminUpdate,
    _current_user: Annotated[User, Depends(get_current_active_user)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
    _: Annotated[bool, Depends(require_admin)],
) -> OrganizationMemberResponse:
    """Admin-only member updates (is_active override)."""

    organization = get_organization_by_id(org_id, org_repo)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check if member exists
    current_member_role = member_repo.get_member_role(org_id, user_id)
    if not current_member_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    updated_member = member_repo.admin_update_member(org_id, user_id, admin_data)
    if not updated_member:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update organization member",
        )

    return updated_member
