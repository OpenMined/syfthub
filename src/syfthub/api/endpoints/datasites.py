"""Datasite endpoints with authentication and visibility controls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from syfthub.auth.dependencies import (
    get_current_active_user,
    get_optional_current_user,
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
from syfthub.schemas.user import User  # noqa: TC001

router = APIRouter()

# Mock database - in production this would be a real database
fake_datasites_db: dict[int, Datasite] = {}
datasite_id_counter = 1

# User slug lookups for efficient queries
user_datasites_lookup: dict[int, set[int]] = {}  # user_id -> set of datasite_ids
slug_to_datasite_lookup: dict[
    tuple[int, str], int
] = {}  # (user_id, slug) -> datasite_id


def get_datasite_by_id(datasite_id: int) -> Datasite | None:
    """Get datasite by ID."""
    return fake_datasites_db.get(datasite_id)


def get_datasite_by_slug(user_id: int, slug: str) -> Datasite | None:
    """Get datasite by user_id and slug."""
    datasite_id = slug_to_datasite_lookup.get((user_id, slug))
    if datasite_id:
        return fake_datasites_db.get(datasite_id)
    return None


def is_slug_available(
    slug: str, user_id: int, exclude_datasite_id: int | None = None
) -> bool:
    """Check if a slug is available for a user."""
    if slug in RESERVED_SLUGS:
        return False

    existing_datasite_id = slug_to_datasite_lookup.get((user_id, slug))
    if existing_datasite_id is None:
        return True

    # If we're excluding a specific datasite (for updates), check if it's the same one
    return (
        exclude_datasite_id is not None and existing_datasite_id == exclude_datasite_id
    )


def generate_unique_slug(name: str, user_id: int) -> str:
    """Generate a unique slug for a user."""
    base_slug = generate_slug_from_name(name)

    if is_slug_available(base_slug, user_id):
        return base_slug

    # If base slug is taken, append numbers
    counter = 1
    while counter < 1000:  # Prevent infinite loops
        new_slug = f"{base_slug}-{counter}"
        if len(new_slug) <= 63 and is_slug_available(new_slug, user_id):
            return new_slug
        counter += 1

    # Fallback: use timestamp
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-6:]
    return f"{base_slug[:50]}-{timestamp}"


def can_access_datasite(datasite: Datasite, current_user: User | None) -> bool:
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
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    visibility: DatasiteVisibility | None = None,
    search: str | None = None,
) -> list[DatasiteResponse]:
    """List current user's datasites."""
    # Get user's datasites
    user_datasite_ids = user_datasites_lookup.get(current_user.id, set())
    user_datasites = [
        fake_datasites_db[ds_id]
        for ds_id in user_datasite_ids
        if ds_id in fake_datasites_db
    ]

    # Apply filters
    if visibility is not None:
        user_datasites = [ds for ds in user_datasites if ds.visibility == visibility]

    if search:
        search_lower = search.lower()
        user_datasites = [
            ds
            for ds in user_datasites
            if search_lower in ds.name.lower()
            or search_lower in ds.description.lower()
            or search_lower in ds.slug.lower()
        ]

    # Sort by most recent first
    user_datasites.sort(key=lambda ds: ds.updated_at, reverse=True)

    # Apply pagination
    user_datasites = user_datasites[skip : skip + limit]

    return [DatasiteResponse.model_validate(ds) for ds in user_datasites]


@router.get("/public", response_model=list[DatasitePublicResponse])
async def list_public_datasites(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = None,
) -> list[DatasitePublicResponse]:
    """List all public datasites."""
    # Get all public datasites
    public_datasites = [
        ds
        for ds in fake_datasites_db.values()
        if ds.visibility == DatasiteVisibility.PUBLIC and ds.is_active
    ]

    # Apply search filter
    if search:
        search_lower = search.lower()
        public_datasites = [
            ds
            for ds in public_datasites
            if search_lower in ds.name.lower() or search_lower in ds.description.lower()
        ]

    # Sort by most recent first
    public_datasites.sort(key=lambda ds: ds.updated_at, reverse=True)

    # Apply pagination
    public_datasites = public_datasites[skip : skip + limit]

    return [DatasitePublicResponse.model_validate(ds) for ds in public_datasites]


@router.get("/{datasite_id}", response_model=DatasiteResponse)
async def get_datasite(
    datasite_id: int,
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> DatasiteResponse:
    """Get a datasite by ID (respects visibility rules)."""
    datasite = get_datasite_by_id(datasite_id)
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
) -> DatasiteResponse:
    """Create a new datasite."""
    global datasite_id_counter

    # Generate slug if not provided
    if datasite_data.slug is None:
        slug = generate_unique_slug(datasite_data.name, current_user.id)
    else:
        slug = datasite_data.slug.lower()

        # Check if slug is available
        if not is_slug_available(slug, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Slug '{slug}' is already taken. Please choose a different slug.",
            )

    # Create datasite
    datasite = Datasite(
        id=datasite_id_counter,
        user_id=current_user.id,
        slug=slug,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **datasite_data.model_dump(exclude={"slug"}),
    )

    # Store in database
    fake_datasites_db[datasite_id_counter] = datasite

    # Update lookups
    if current_user.id not in user_datasites_lookup:
        user_datasites_lookup[current_user.id] = set()
    user_datasites_lookup[current_user.id].add(datasite_id_counter)
    slug_to_datasite_lookup[(current_user.id, slug)] = datasite_id_counter

    datasite_id_counter += 1

    return DatasiteResponse.model_validate(datasite)


@router.patch("/{datasite_id}", response_model=DatasiteResponse)
async def update_datasite(
    datasite_id: int,
    datasite_data: DatasiteUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> DatasiteResponse:
    """Update a datasite (owner or admin only)."""
    datasite = get_datasite_by_id(datasite_id)
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

    # Update only provided fields
    update_data = datasite_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(datasite, field, value)

    datasite.updated_at = datetime.now(timezone.utc)

    return DatasiteResponse.model_validate(datasite)


@router.delete("/{datasite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_datasite(
    datasite_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Delete a datasite (owner or admin only)."""
    datasite = get_datasite_by_id(datasite_id)
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

    # Remove from database
    del fake_datasites_db[datasite_id]

    # Clean up lookups
    if datasite.user_id in user_datasites_lookup:
        user_datasites_lookup[datasite.user_id].discard(datasite_id)

    lookup_key = (datasite.user_id, datasite.slug)
    slug_to_datasite_lookup.pop(lookup_key, None)
