"""Organization management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from syfthub.auth.dependencies import get_current_active_user
from syfthub.schemas.auth import UserRole
from syfthub.schemas.organization import (
    RESERVED_ORG_SLUGS,
    Organization,
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationMemberUpdate,
    OrganizationResponse,
    OrganizationRole,
    OrganizationUpdate,
    generate_slug_from_name,
)
from syfthub.schemas.user import User  # noqa: TC001

router = APIRouter()

# Mock database - in production this would be replaced with real database operations
fake_organizations_db: dict[int, Organization] = {}
fake_org_members_db: dict[
    int, dict[int, dict[str, Any]]
] = {}  # org_id -> {user_id -> member_data}
organization_id_counter = 1
member_id_counter = 1

# Lookup tables for efficient queries
user_organizations_lookup: dict[int, set[int]] = {}  # user_id -> set of org_ids
slug_to_organization_lookup: dict[str, int] = {}  # slug -> org_id


def get_organization_by_id(org_id: int) -> Organization | None:
    """Get organization by ID."""
    return fake_organizations_db.get(org_id)


def get_organization_by_slug(slug: str) -> Organization | None:
    """Get organization by slug."""
    org_id = slug_to_organization_lookup.get(slug)
    if org_id:
        return fake_organizations_db.get(org_id)
    return None


def get_user_role_in_organization(org_id: int, user_id: int) -> OrganizationRole | None:
    """Get user's role in organization."""
    org_members = fake_org_members_db.get(org_id, {})
    member_data = org_members.get(user_id)
    if member_data and member_data.get("is_active", False):
        return OrganizationRole(member_data["role"])
    return None


def is_organization_member(org_id: int, user_id: int) -> bool:
    """Check if user is an active member of organization."""
    return get_user_role_in_organization(org_id, user_id) is not None


def is_organization_admin_or_owner(org_id: int, user_id: int) -> bool:
    """Check if user is admin or owner of organization."""
    role = get_user_role_in_organization(org_id, user_id)
    return role in (OrganizationRole.ADMIN, OrganizationRole.OWNER)


def is_organization_owner(org_id: int, user_id: int) -> bool:
    """Check if user is owner of organization."""
    role = get_user_role_in_organization(org_id, user_id)
    return role == OrganizationRole.OWNER


def require_organization_member(org_id: int, user_id: int) -> None:
    """Require user to be organization member."""
    if not is_organization_member(org_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )


def require_organization_admin(org_id: int, user_id: int) -> None:
    """Require user to be organization admin or owner."""
    if not is_organization_admin_or_owner(org_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner privileges required",
        )


def require_organization_owner(org_id: int, user_id: int) -> None:
    """Require user to be organization owner."""
    if not is_organization_owner(org_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner privileges required"
        )


@router.get("/", response_model=list[OrganizationResponse])
async def list_my_organizations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    role: OrganizationRole | None = None,
) -> list[OrganizationResponse]:
    """List current user's organizations."""
    # Get user's organization memberships
    user_org_ids = user_organizations_lookup.get(current_user.id, set())
    user_orgs = []

    for org_id in user_org_ids:
        org = fake_organizations_db.get(org_id)
        if org and org.is_active:
            # Check if user is still active member
            user_role = get_user_role_in_organization(org_id, current_user.id)
            if user_role is not None and (role is None or user_role == role):
                user_orgs.append(org)

    # Sort by most recent first
    user_orgs.sort(key=lambda org: org.updated_at, reverse=True)

    # Apply pagination
    user_orgs = user_orgs[skip : skip + limit]

    return [OrganizationResponse.model_validate(org) for org in user_orgs]


@router.post(
    "/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    org_data: OrganizationCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> OrganizationResponse:
    """Create a new organization."""
    global organization_id_counter

    # Generate slug if not provided
    slug = org_data.slug or generate_slug_from_name(org_data.name)

    # Check if slug is available
    if slug in slug_to_organization_lookup:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization with slug '{slug}' already exists",
        )

    # Check reserved slugs
    if slug in RESERVED_ORG_SLUGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{slug}' is a reserved slug and cannot be used",
        )

    # Create organization
    now = datetime.now(timezone.utc)
    organization = Organization(
        id=organization_id_counter,
        name=org_data.name,
        slug=slug,
        description=org_data.description,
        avatar_url=org_data.avatar_url,
        is_active=org_data.is_active,
        created_at=now,
        updated_at=now,
    )

    # Store organization
    fake_organizations_db[organization_id_counter] = organization
    slug_to_organization_lookup[slug] = organization_id_counter

    # Add creator as owner
    fake_org_members_db[organization_id_counter] = {
        current_user.id: {
            "id": member_id_counter,
            "organization_id": organization_id_counter,
            "user_id": current_user.id,
            "role": OrganizationRole.OWNER.value,
            "is_active": True,
            "joined_at": now,
        }
    }

    # Update lookup tables
    if current_user.id not in user_organizations_lookup:
        user_organizations_lookup[current_user.id] = set()
    user_organizations_lookup[current_user.id].add(organization_id_counter)

    organization_id_counter += 1

    return OrganizationResponse.model_validate(organization)


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> OrganizationResponse:
    """Get organization details."""
    organization = get_organization_by_id(org_id)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check if user has access (member or admin)
    if current_user.role != UserRole.ADMIN:
        require_organization_member(org_id, current_user.id)

    return OrganizationResponse.model_validate(organization)


@router.put("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: int,
    org_update: OrganizationUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> OrganizationResponse:
    """Update organization."""
    organization = get_organization_by_id(org_id)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (admin/owner only)
    if current_user.role != UserRole.ADMIN:
        require_organization_admin(org_id, current_user.id)

    # Update organization fields
    update_data = org_update.model_dump(exclude_unset=True)
    if update_data:
        for field, value in update_data.items():
            setattr(organization, field, value)
        organization.updated_at = datetime.now(timezone.utc)

    return OrganizationResponse.model_validate(organization)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Delete organization (soft delete)."""
    organization = get_organization_by_id(org_id)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (owner only)
    if current_user.role != UserRole.ADMIN:
        require_organization_owner(org_id, current_user.id)

    # Soft delete organization
    organization.is_active = False
    organization.updated_at = datetime.now(timezone.utc)


@router.get("/{org_id}/members", response_model=list[OrganizationMemberResponse])
async def list_organization_members(
    org_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    role: OrganizationRole | None = None,
) -> list[OrganizationMemberResponse]:
    """List organization members."""
    organization = get_organization_by_id(org_id)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions
    if current_user.role != UserRole.ADMIN:
        require_organization_member(org_id, current_user.id)

    # Get organization members
    org_members = fake_org_members_db.get(org_id, {})
    members = []

    for member_data in org_members.values():
        if member_data.get("is_active", False) and (
            role is None or OrganizationRole(member_data["role"]) == role
        ):
            members.append(member_data)

    # Sort by join date (most recent first)
    members.sort(key=lambda m: m["joined_at"], reverse=True)

    # Apply pagination
    members = members[skip : skip + limit]

    return [OrganizationMemberResponse.model_validate(member) for member in members]


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_organization_member(
    org_id: int,
    member_data: OrganizationMemberCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> OrganizationMemberResponse:
    """Add member to organization."""
    global member_id_counter

    organization = get_organization_by_id(org_id)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (admin/owner only)
    if current_user.role != UserRole.ADMIN:
        require_organization_admin(org_id, current_user.id)

    # Check if user is already a member
    if is_organization_member(org_id, member_data.user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member"
        )

    # Add member
    now = datetime.now(timezone.utc)
    member = {
        "id": member_id_counter,
        "organization_id": org_id,
        "user_id": member_data.user_id,
        "role": member_data.role.value,
        "is_active": member_data.is_active,
        "joined_at": now,
    }

    if org_id not in fake_org_members_db:
        fake_org_members_db[org_id] = {}
    fake_org_members_db[org_id][member_data.user_id] = member

    # Update lookup tables
    if member_data.user_id not in user_organizations_lookup:
        user_organizations_lookup[member_data.user_id] = set()
    user_organizations_lookup[member_data.user_id].add(org_id)

    member_id_counter += 1

    return OrganizationMemberResponse.model_validate(member)


@router.put("/{org_id}/members/{user_id}", response_model=OrganizationMemberResponse)
async def update_organization_member(
    org_id: int,
    user_id: int,
    member_update: OrganizationMemberUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> OrganizationMemberResponse:
    """Update organization member."""
    organization = get_organization_by_id(org_id)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (admin/owner only)
    if current_user.role != UserRole.ADMIN:
        require_organization_admin(org_id, current_user.id)

    # Get member
    org_members = fake_org_members_db.get(org_id, {})
    member_data = org_members.get(user_id)
    if not member_data or not member_data.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Prevent removing the last owner
    if (
        member_update.role != OrganizationRole.OWNER
        and OrganizationRole(member_data["role"]) == OrganizationRole.OWNER
    ):
        owners_count = sum(
            1
            for m in org_members.values()
            if m.get("is_active") and m.get("role") == OrganizationRole.OWNER.value
        )
        if owners_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner from organization",
            )

    # Update member
    update_data = member_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "role":
            member_data[field] = value.value if hasattr(value, "value") else value
        else:
            member_data[field] = value

    return OrganizationMemberResponse.model_validate(member_data)


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_organization_member(
    org_id: int,
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Remove member from organization."""
    organization = get_organization_by_id(org_id)
    if not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    # Check permissions (admin/owner only, or user removing themselves)
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        require_organization_admin(org_id, current_user.id)

    # Get member
    org_members = fake_org_members_db.get(org_id, {})
    member_data = org_members.get(user_id)
    if not member_data or not member_data.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Prevent removing the last owner
    if OrganizationRole(member_data["role"]) == OrganizationRole.OWNER:
        owners_count = sum(
            1
            for m in org_members.values()
            if m.get("is_active") and m.get("role") == OrganizationRole.OWNER.value
        )
        if owners_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner from organization",
            )

    # Remove member (soft delete)
    member_data["is_active"] = False

    # Update lookup tables
    if user_id in user_organizations_lookup:
        user_organizations_lookup[user_id].discard(org_id)
