"""Item endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from syfthub.schemas.item import Item, ItemCreate, ItemResponse, ItemUpdate

router = APIRouter()

# Mock database
fake_items_db: dict[int, Item] = {}
item_id_counter = 1


@router.get("/", response_model=list[ItemResponse])
async def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = None,
) -> list[ItemResponse]:
    """List all items with optional filtering."""
    items = list(fake_items_db.values())

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


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int) -> ItemResponse:
    """Get an item by ID."""
    if item_id not in fake_items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )
    return ItemResponse.model_validate(fake_items_db[item_id])


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(item_data: ItemCreate) -> ItemResponse:
    """Create a new item."""
    global item_id_counter

    item = Item(
        id=item_id_counter,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **item_data.model_dump(),
    )
    fake_items_db[item_id_counter] = item
    item_id_counter += 1

    return ItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(item_id: int, item_data: ItemUpdate) -> ItemResponse:
    """Partially update an item."""
    if item_id not in fake_items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    stored_item = fake_items_db[item_id]
    update_data = item_data.model_dump(exclude_unset=True)

    # Update only provided fields
    for field, value in update_data.items():
        setattr(stored_item, field, value)

    stored_item.updated_at = datetime.now(timezone.utc)

    return ItemResponse.model_validate(stored_item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int) -> None:
    """Delete an item."""
    if item_id not in fake_items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    del fake_items_db[item_id]


@router.get("/{item_id}/metadata")
async def get_item_metadata(item_id: int) -> dict[str, Any]:
    """Get item metadata."""
    if item_id not in fake_items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    item = fake_items_db[item_id]
    return {
        "id": item.id,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "name_length": len(item.name),
        "has_description": bool(item.description),
        "is_available": item.is_available,
    }
