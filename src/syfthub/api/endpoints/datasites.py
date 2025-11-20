"""Datasite endpoints with authentication and visibility controls."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from syfthub.api.endpoints.organizations import (
    get_organization_by_id,
    is_organization_admin_or_owner,
)
from syfthub.auth.db_dependencies import (
    get_current_active_user,
    get_optional_current_user,
)
from syfthub.database.dependencies import (
    get_datasite_repository,
    get_organization_member_repository,
    get_organization_repository,
)
from syfthub.repositories.datasite import DatasiteRepository
from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.schemas.auth import UserRole
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
from syfthub.schemas.user import User

router = APIRouter()

# Mock database and lookups removed - now using repository pattern


def get_datasite_by_id(
    datasite_repo: DatasiteRepository, datasite_id: int
) -> Optional[Datasite]:
    """Get datasite by ID."""
    return datasite_repo.get_by_id(datasite_id)


def get_datasite_by_slug(
    datasite_repo: DatasiteRepository, user_id: int, slug: str
) -> Optional[Datasite]:
    """Get datasite by user_id and slug."""
    return datasite_repo.get_by_user_and_slug(user_id, slug)


def is_slug_available(
    datasite_repo: DatasiteRepository,
    slug: str,
    user_id: int,
    exclude_datasite_id: Optional[int] = None,
) -> bool:
    """Check if a slug is available for a user."""
    if slug in RESERVED_SLUGS:
        return False

    # Use repository to check if slug exists for user
    exists = datasite_repo.slug_exists_for_user(user_id, slug, exclude_datasite_id)
    return not exists


def generate_unique_slug(
    datasite_repo: DatasiteRepository,
    name: str,
    owner_id: int,
    is_organization: bool = False,
) -> str:
    """Generate a unique slug for a user or organization."""
    base_slug = generate_slug_from_name(name)

    # Check if base slug is available
    if is_organization:
        slug_available = not datasite_repo.slug_exists_for_organization(
            owner_id, base_slug
        )
    else:
        slug_available = is_slug_available(datasite_repo, base_slug, owner_id)

    if slug_available:
        return base_slug

    # If base slug is taken, append numbers
    counter = 1
    while counter < 1000:  # Prevent infinite loops
        new_slug = f"{base_slug}-{counter}"
        if len(new_slug) <= 63:
            if is_organization:
                if not datasite_repo.slug_exists_for_organization(owner_id, new_slug):
                    return new_slug
            else:
                if is_slug_available(datasite_repo, new_slug, owner_id):
                    return new_slug
        counter += 1

    # Fallback: use timestamp
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-6:]
    return f"{base_slug[:50]}-{timestamp}"


def can_access_datasite(datasite: Datasite, current_user: Optional[User]) -> bool:
    """Check if user can access a datasite based on visibility."""
    if datasite.visibility == DatasiteVisibility.PUBLIC:
        return True

    if current_user is None:
        return False

    # Owner can always access
    if current_user.id == datasite.user_id:
        return True

    # Admin can access everything
    if current_user.role == UserRole.ADMIN:
        return True

    # Internal datasites are accessible to any authenticated user
    # Private datasites are only accessible to owner and admin
    return datasite.visibility == DatasiteVisibility.INTERNAL


@router.get("/", response_model=list[DatasiteResponse])
async def list_my_datasites(
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    visibility: Optional[DatasiteVisibility] = None,
    search: Optional[str] = None,
) -> list[DatasiteResponse]:
    """List current user's datasites."""
    # Get user's datasites from repository
    # Note: Repository handles pagination, but we need to handle search filtering
    # Get more than needed to account for search filtering, then re-paginate
    max_results = skip + limit + 100  # Get extra to handle search filtering
    user_datasites = datasite_repo.get_user_datasites(
        current_user.id,
        skip=0,  # Get from start to handle search filtering
        limit=max_results,
        visibility=visibility,
    )

    # Apply search filter if provided
    if search:
        search_lower = search.lower()
        user_datasites = [
            ds
            for ds in user_datasites
            if search_lower in ds.name.lower()
            or search_lower in ds.description.lower()
            or search_lower in ds.slug.lower()
        ]

    # Apply pagination after search filtering
    user_datasites = user_datasites[skip : skip + limit]

    return [DatasiteResponse.model_validate(ds) for ds in user_datasites]


@router.get("/public", response_model=list[DatasitePublicResponse])
async def list_public_datasites(
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
) -> list[DatasitePublicResponse]:
    """List all public datasites."""
    # Get public datasites from repository
    # Note: Repository handles pagination and sorting, but we need search filtering
    if search:
        # Get more results to handle search filtering
        max_results = skip + limit + 100
        public_datasites = datasite_repo.get_public_datasites(skip=0, limit=max_results)

        # Apply search filter
        search_lower = search.lower()
        filtered_datasites = []
        for ds in public_datasites:
            # Convert DatasitePublicResponse back to check fields
            if (
                search_lower in ds.name.lower()
                or search_lower in ds.description.lower()
            ):
                filtered_datasites.append(ds)

        # Apply pagination after filtering
        public_datasites = filtered_datasites[skip : skip + limit]
    else:
        # No search, use repository pagination directly
        public_datasites = datasite_repo.get_public_datasites(skip=skip, limit=limit)

    return public_datasites


@router.get("/trending", response_model=list[DatasitePublicResponse])
async def list_trending_datasites(
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    min_stars: int = Query(0, ge=0),
) -> list[DatasitePublicResponse]:
    """List datasites by popularity (stars count)."""
    # Get all public datasites (need to get more than needed for filtering and sorting)
    # Since we need to filter by min_stars and sort by stars_count, get a large set
    max_results = 1000  # Get a large set to ensure we have enough after filtering
    public_datasites = datasite_repo.get_public_datasites(skip=0, limit=max_results)

    # Filter by minimum stars
    trending_datasites = [ds for ds in public_datasites if ds.stars_count >= min_stars]

    # Sort by stars count (desc) then by created_at (desc) for ties
    trending_datasites.sort(
        key=lambda ds: (ds.stars_count, ds.created_at), reverse=True
    )

    # Apply pagination
    trending_datasites = trending_datasites[skip : skip + limit]

    return trending_datasites


@router.get("/{datasite_id}", response_model=DatasiteResponse)
async def get_datasite(
    datasite_id: int,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
) -> DatasiteResponse:
    """Get a datasite by ID (respects visibility rules)."""
    datasite = get_datasite_by_id(datasite_repo, datasite_id)
    if not datasite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Datasite not found"
        )

    # Check access permissions
    if not can_access_datasite(datasite, current_user):
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this datasite",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            # Return 404 for private datasites to hide existence (like GitHub)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Datasite not found"
            )

    return DatasiteResponse.model_validate(datasite)


@router.post("/", response_model=DatasiteResponse, status_code=status.HTTP_201_CREATED)
async def create_datasite(
    datasite_data: DatasiteCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
) -> DatasiteResponse:
    """Create a new datasite for user or organization."""
    # Determine ownership type and validate permissions
    organization_id = datasite_data.organization_id

    if organization_id:
        # Creating for organization - check if user can create org datasites
        organization = get_organization_by_id(organization_id, org_repo)
        if not organization or not organization.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
            )

        # Check if user is admin/owner of organization
        if current_user.role != "admin" and not is_organization_admin_or_owner(
            organization_id, current_user.id, member_repo
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or owner privileges required to create organization datasites",
            )

    # Generate slug if not provided
    if datasite_data.slug is None:
        # Use organization_id or user_id for slug generation
        owner_id = organization_id or current_user.id
        is_org_slug_gen = organization_id is not None
        slug = generate_unique_slug(
            datasite_repo, datasite_data.name, owner_id, is_org_slug_gen
        )
    else:
        slug = datasite_data.slug.lower()

        # Check if slug is available for the owner
        if organization_id:
            # Check org datasite slug availability using repository
            if datasite_repo.slug_exists_for_organization(organization_id, slug):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Slug '{slug}' is already taken in this organization.",
                )
        else:
            # Check user datasite slug availability using repository
            if not is_slug_available(datasite_repo, slug, current_user.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Slug '{slug}' is already taken. Please choose a different slug.",
                )

    # Prepare datasite data
    datasite_create = DatasiteCreate(
        name=datasite_data.name,
        slug=slug,
        description=datasite_data.description,
        visibility=datasite_data.visibility,
        version=datasite_data.version,
        readme=datasite_data.readme,
        contributors=datasite_data.contributors or [current_user.id],
        policies=datasite_data.policies,
        connect=datasite_data.connect,
        organization_id=organization_id,
    )

    # Ensure creator is in contributors list
    if current_user.id not in datasite_create.contributors:
        datasite_create.contributors.append(current_user.id)

    # Create datasite using repository
    owner_id = organization_id or current_user.id
    is_organization = organization_id is not None

    datasite = datasite_repo.create_datasite(datasite_create, owner_id, is_organization)
    if not datasite:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create datasite",
        )

    return DatasiteResponse.model_validate(datasite)


@router.patch("/{datasite_id}", response_model=DatasiteResponse)
async def update_datasite(
    datasite_id: int,
    datasite_data: DatasiteUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
) -> DatasiteResponse:
    """Update a datasite (owner or admin only)."""
    datasite = get_datasite_by_id(datasite_repo, datasite_id)
    if not datasite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Datasite not found"
        )

    # Check ownership or admin permissions
    if current_user.role != UserRole.ADMIN and datasite.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you can only update your own datasites",
        )

    # Update datasite using repository
    updated_datasite = datasite_repo.update_datasite(datasite_id, datasite_data)
    if not updated_datasite:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update datasite",
        )

    return DatasiteResponse.model_validate(updated_datasite)


@router.delete("/{datasite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_datasite(
    datasite_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
) -> None:
    """Delete a datasite (owner or admin only)."""
    datasite = get_datasite_by_id(datasite_repo, datasite_id)
    if not datasite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Datasite not found"
        )

    # Check ownership or admin permissions
    if current_user.role != UserRole.ADMIN and datasite.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you can only delete your own datasites",
        )

    # Delete datasite using repository (soft delete)
    success = datasite_repo.delete_datasite(datasite_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete datasite",
        )
