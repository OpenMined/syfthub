"""Item schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    """Base item schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Item name")
    description: str = Field("", max_length=500, description="Item description")
    price: Decimal = Field(..., ge=0, decimal_places=2, description="Item price")
    is_available: bool = Field(True, description="Whether the item is available")


class ItemCreate(ItemBase):
    """Schema for creating a new item."""

    category: str | None = Field(None, max_length=50, description="Item category")


class ItemUpdate(BaseModel):
    """Schema for updating an item."""

    name: str | None = Field(
        None, min_length=1, max_length=100, description="Item name"
    )
    description: str | None = Field(
        None, max_length=500, description="Item description"
    )
    price: Decimal | None = Field(
        None, ge=0, decimal_places=2, description="Item price"
    )
    is_available: bool | None = Field(None, description="Whether the item is available")
    category: str | None = Field(None, max_length=50, description="Item category")


class Item(ItemBase):
    """Item model."""

    id: int = Field(..., description="Item's unique identifier")
    user_id: int = Field(..., description="ID of the user who owns this item")
    category: str | None = Field(None, max_length=50, description="Item category")
    created_at: datetime = Field(..., description="When the item was created")
    updated_at: datetime = Field(..., description="When the item was last updated")

    model_config = {"from_attributes": True}


class ItemResponse(BaseModel):
    """Schema for item response."""

    id: int = Field(..., description="Item's unique identifier")
    user_id: int = Field(..., description="ID of the user who owns this item")
    name: str = Field(..., description="Item name")
    description: str = Field(..., description="Item description")
    price: Decimal = Field(..., description="Item price")
    is_available: bool = Field(..., description="Whether the item is available")
    category: str | None = Field(None, description="Item category")
    created_at: datetime = Field(..., description="When the item was created")
    updated_at: datetime = Field(..., description="When the item was last updated")

    model_config = {"from_attributes": True}
