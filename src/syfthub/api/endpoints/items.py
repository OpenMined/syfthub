"""Item endpoints with authentication."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from syfthub.auth.dependencies import (
    OwnershipChecker,
    get_current_active_user,
    get_optional_current_user,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.item import Item, ItemCreate, ItemResponse, ItemUpdate
from syfthub.schemas.user import User  # noqa: TC001

router = APIRouter()

# Mock database
fake_items_db: dict[int, Item] = {}
item_id_counter = 1

# Ownership checker for item resources
check_item_ownership = OwnershipChecker()


@router.get("/", response_model=list[ItemResponse])
async def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = None,
    current_user: User | None = Depends(get_optional_current_user),
) -> list[ItemResponse]:
    """List items with optional filtering (public endpoint)."""
    items = list(fake_items_db.values())

    # If not authenticated, only show available items
    if current_user is None:
        items = [item for item in items if item.is_available]

    # Apply search filter if provided
    if search:
        items = [
            item
            for item in items
            if search.lower() in item.name.lower()
            or search.lower() in item.description.lower()
        ]

    # Apply pagination
    items = items[skip : skip + limit]

    return [ItemResponse.model_validate(item) for item in items]


@router.get("/my", response_model=list[ItemResponse])
async def list_my_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = None,
) -> list[ItemResponse]:
    """List current user's items."""
    # Get only user's items
    user_items = [
        item for item in fake_items_db.values() if item.user_id == current_user.id
    ]

    # Apply search filter if provided
    if search:
        user_items = [
            item
            for item in user_items
            if search.lower() in item.name.lower()
            or search.lower() in item.description.lower()
        ]

    # Apply pagination
    user_items = user_items[skip : skip + limit]

    return [ItemResponse.model_validate(item) for item in user_items]


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int, current_user: User | None = Depends(get_optional_current_user)
) -> ItemResponse:
    """Get an item by ID (public for available items, auth required for unavailable)."""
    if item_id not in fake_items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    item = fake_items_db[item_id]

    # If item is not available, require authentication and ownership/admin
    if not item.is_available:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to view unavailable items",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user owns the item or is admin
        if current_user.role != UserRole.ADMIN and item.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

    return ItemResponse.model_validate(item)


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_data: ItemCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ItemResponse:
    """Create a new item (requires authentication)."""
    global item_id_counter

    item = Item(
        id=item_id_counter,
        user_id=current_user.id,  # Set owner to current user
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **item_data.model_dump(),
    )
    fake_items_db[item_id_counter] = item
    item_id_counter += 1

    return ItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    item_data: ItemUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ItemResponse:
    """Update an item (owner or admin only)."""
    if item_id not in fake_items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    stored_item = fake_items_db[item_id]

    # Check ownership or admin permissions
    if current_user.role != UserRole.ADMIN and stored_item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you can only update your own items",
        )

    # Update only provided fields
    update_data = item_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(stored_item, field, value)

    stored_item.updated_at = datetime.now(timezone.utc)

    return ItemResponse.model_validate(stored_item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int, current_user: Annotated[User, Depends(get_current_active_user)]
) -> None:
    """Delete an item (owner or admin only)."""
    if item_id not in fake_items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    item = fake_items_db[item_id]

    # Check ownership or admin permissions
    if current_user.role != UserRole.ADMIN and item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you can only delete your own items",
        )

    del fake_items_db[item_id]


@router.get("/{item_id}/metadata")
async def get_item_metadata(
    item_id: int, current_user: User | None = Depends(get_optional_current_user)
) -> dict[str, Any]:
    """Get item metadata (public for available items, auth required for unavailable)."""
    if item_id not in fake_items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    item = fake_items_db[item_id]

    # If item is not available, require authentication and ownership/admin
    if not item.is_available:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to view unavailable items",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user owns the item or is admin
        if current_user.role != UserRole.ADMIN and item.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

    return {
        "id": item.id,
        "user_id": item.user_id,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "name_length": len(item.name),
        "has_description": bool(item.description),
        "is_available": item.is_available,
        "category": item.category,
    }
