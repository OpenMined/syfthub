"""Datasite schemas."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatasiteVisibility(str, Enum):
    """Datasite visibility levels."""

    PUBLIC = "public"  # Anyone can view
    PRIVATE = "private"  # Only owner (and future collaborators) can view
    INTERNAL = "internal"  # Only authenticated users can view


class Policy(BaseModel):
    """Policy configuration for datasites.

    Provides a flexible structure for declaring policies that can be applied
    to datasites without implementing the actual policy logic in this system.
    """

    type: str = Field(
        ..., min_length=1, max_length=100, description="Policy type identifier"
    )
    version: str = Field(
        default="1.0", pattern=r"^\d+\.\d+$", description="Policy version"
    )
    enabled: bool = Field(
        default=True, description="Whether this policy is currently active"
    )
    description: str = Field(
        default="", max_length=500, description="Human-readable policy description"
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible configuration object for policy-specific settings",
    )

    model_config = ConfigDict(
        extra="forbid",  # Only allow defined fields at Policy level
        str_strip_whitespace=True,
    )


class Connection(BaseModel):
    """Connection configuration for datasites.

    Provides a flexible structure for declaring connection methods that can be used
    to access datasites without implementing the actual connection logic in this system.
    """

    type: str = Field(
        ..., min_length=1, max_length=50, description="Connection type identifier"
    )
    enabled: bool = Field(
        default=True, description="Whether this connection is currently available"
    )
    description: str = Field(
        default="", max_length=500, description="Human-readable connection description"
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible configuration object for connection-specific settings",
    )

    model_config = ConfigDict(
        extra="forbid",  # Only allow defined fields at Connection level
        str_strip_whitespace=True,
    )


# Reserved slugs that cannot be used for datasites
RESERVED_SLUGS = {
    "api",
    "auth",
    "docs",
    "redoc",
    "openapi.json",
    "health",
    "admin",
    "www",
    "mail",
    "ftp",
    "blog",
    "help",
    "support",
    "about",
    "contact",
    "terms",
    "privacy",
    "login",
    "register",
    "dashboard",
    "settings",
    "profile",
    "search",
    "explore",
}


class DatasiteBase(BaseModel):
    """Base datasite schema."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Display name of the datasite"
    )
    description: str = Field(
        "", max_length=500, description="Description of the datasite"
    )
    visibility: DatasiteVisibility = Field(
        default=DatasiteVisibility.PUBLIC, description="Who can access this datasite"
    )
    is_active: bool = Field(default=True, description="Whether the datasite is active")
    contributors: List[int] = Field(
        default_factory=list, description="List of contributor user IDs"
    )
    version: str = Field(
        default="0.1.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version of the datasite",
    )
    readme: str = Field(
        default="", max_length=50000, description="Markdown content for the README"
    )
    stars_count: int = Field(
        default=0, ge=0, description="Number of stars this datasite has received"
    )
    policies: List[Policy] = Field(
        default_factory=list, description="List of policies applied to this datasite"
    )
    connect: List[Connection] = Field(
        default_factory=list,
        description="List of connection methods available for this datasite",
    )


class DatasiteCreate(DatasiteBase):
    """Schema for creating a new datasite."""

    slug: Optional[str] = Field(
        None,
        min_length=3,
        max_length=63,
        description="URL-safe identifier (auto-generated from name if not provided)",
    )
    organization_id: Optional[int] = Field(
        None,
        description="Organization ID if creating datasite for organization (optional)",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        """Validate datasite slug format."""
        if v is None:
            return v

        # Check for uppercase letters before converting
        if v != v.lower():
            raise ValueError("Slug must contain only lowercase letters")

        # Check reserved slugs
        if v in RESERVED_SLUGS:
            raise ValueError(f"'{v}' is a reserved slug and cannot be used")

        # Check for consecutive hyphens
        if "--" in v:
            raise ValueError("Slug cannot contain consecutive hyphens")

        # Validate format: alphanumeric + hyphens, no leading/trailing hyphens
        slug_pattern = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
        if not re.match(slug_pattern, v):
            raise ValueError(
                "Slug must contain only lowercase letters, numbers, and hyphens. "
                "Cannot start or end with hyphen."
            )

        return v


class DatasiteUpdate(BaseModel):
    """Schema for updating a datasite."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=100, description="Display name of the datasite"
    )
    description: Optional[str] = Field(
        None, max_length=500, description="Description of the datasite"
    )
    visibility: Optional[DatasiteVisibility] = Field(
        None, description="Who can access this datasite"
    )
    is_active: Optional[bool] = Field(
        None, description="Whether the datasite is active"
    )
    contributors: Optional[List[int]] = Field(
        None, description="List of contributor user IDs"
    )
    version: Optional[str] = Field(
        None,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version of the datasite",
    )
    readme: Optional[str] = Field(
        None, max_length=50000, description="Markdown content for the README"
    )
    policies: Optional[List[Policy]] = Field(
        None, description="List of policies applied to this datasite"
    )
    connect: Optional[List[Connection]] = Field(
        None, description="List of connection methods available for this datasite"
    )


class Datasite(DatasiteBase):
    """Datasite model."""

    id: int = Field(..., description="Datasite's unique identifier")
    user_id: Optional[int] = Field(
        None, description="ID of the user who owns this datasite"
    )
    organization_id: Optional[int] = Field(
        None, description="ID of the organization that owns this datasite"
    )
    slug: str = Field(
        ..., min_length=3, max_length=63, description="URL-safe identifier"
    )
    created_at: datetime = Field(..., description="When the datasite was created")
    updated_at: datetime = Field(..., description="When the datasite was last updated")

    model_config = {"from_attributes": True}


class DatasiteResponse(BaseModel):
    """Schema for datasite response."""

    id: int = Field(..., description="Datasite's unique identifier")
    user_id: Optional[int] = Field(
        None, description="ID of the user who owns this datasite"
    )
    organization_id: Optional[int] = Field(
        None, description="ID of the organization that owns this datasite"
    )
    name: str = Field(..., description="Display name of the datasite")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Description of the datasite")
    visibility: DatasiteVisibility = Field(
        ..., description="Who can access this datasite"
    )
    is_active: bool = Field(..., description="Whether the datasite is active")
    contributors: List[int] = Field(..., description="List of contributor user IDs")
    version: str = Field(..., description="Semantic version of the datasite")
    readme: str = Field(..., description="Markdown content for the README")
    stars_count: int = Field(
        ..., description="Number of stars this datasite has received"
    )
    policies: List[Policy] = Field(
        ..., description="List of policies applied to this datasite"
    )
    connect: List[Connection] = Field(
        ..., description="List of connection methods available for this datasite"
    )
    created_at: datetime = Field(..., description="When the datasite was created")
    updated_at: datetime = Field(..., description="When the datasite was last updated")

    model_config = {"from_attributes": True}


class DatasitePublicResponse(BaseModel):
    """Schema for public datasite response (limited fields)."""

    name: str = Field(..., description="Display name of the datasite")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Description of the datasite")
    contributors: List[int] = Field(..., description="List of contributor user IDs")
    version: str = Field(..., description="Semantic version of the datasite")
    readme: str = Field(..., description="Markdown content for the README")
    stars_count: int = Field(
        ..., description="Number of stars this datasite has received"
    )
    policies: List[Policy] = Field(
        ..., description="List of policies applied to this datasite"
    )
    connect: List[Connection] = Field(
        ..., description="List of connection methods available for this datasite"
    )
    created_at: datetime = Field(..., description="When the datasite was created")
    updated_at: datetime = Field(..., description="When the datasite was last updated")

    # Note: Excludes user_id, id, visibility, and is_active for security

    model_config = {"from_attributes": True}


def generate_slug_from_name(name: str) -> str:
    """Generate a URL-safe slug from datasite name."""
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())

    # Remove leading/trailing hyphens
    slug = slug.strip("-")

    # Ensure minimum length
    if len(slug) < 3:
        slug = f"datasite-{slug}"

    # Truncate if too long
    if len(slug) > 63:
        slug = slug[:63].rstrip("-")

    return slug


def is_slug_available(
    slug: str,  # noqa: ARG001
    user_id: int,  # noqa: ARG001
    exclude_datasite_id: Optional[int] = None,  # noqa: ARG001
) -> bool:
    """Check if a slug is available for a user."""
    # This will be implemented in the endpoints module
    # Placeholder for the actual availability check logic
    return True
