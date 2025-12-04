"""Endpoint schemas."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EndpointVisibility(str, Enum):
    """Endpoint visibility levels."""

    PUBLIC = "public"  # Anyone can view
    PRIVATE = "private"  # Only owner (and future collaborators) can view
    INTERNAL = "internal"  # Only authenticated users can view


class EndpointType(str, Enum):
    """Endpoint type classification."""

    MODEL = "model"  # Machine learning model endpoint
    DATA_SOURCE = "data_source"  # Data source endpoint


class Policy(BaseModel):
    """Policy configuration for endpoints.

    Provides a flexible structure for declaring policies that can be applied
    to endpoints without implementing the actual policy logic in this system.
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
    """Connection configuration for endpoints.

    Provides a flexible structure for declaring connection methods that can be used
    to access endpoints without implementing the actual connection logic in this system.
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


# Reserved slugs that cannot be used for endpoints
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


class EndpointBase(BaseModel):
    """Base endpoint schema."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Display name of the endpoint"
    )
    description: str = Field(
        "", max_length=500, description="Description of the endpoint"
    )
    type: EndpointType = Field(
        ..., description="Type of endpoint (model or data_source)"
    )
    visibility: EndpointVisibility = Field(
        default=EndpointVisibility.PUBLIC, description="Who can access this endpoint"
    )
    # REMOVED is_active - server-managed field
    # REMOVED contributors - will be validated separately
    version: str = Field(
        default="0.1.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version of the endpoint",
    )
    readme: str = Field(
        default="", max_length=50000, description="Markdown content for the README"
    )
    # REMOVED stars_count - CRITICAL: server-managed field only
    policies: List[Policy] = Field(
        default_factory=list, description="List of policies applied to this endpoint"
    )
    connect: List[Connection] = Field(
        default_factory=list,
        description="List of connection methods available for this endpoint",
    )


class EndpointCreate(EndpointBase):
    """Schema for creating a new endpoint - user input only."""

    slug: Optional[str] = Field(
        None,
        min_length=3,
        max_length=63,
        description="URL-safe identifier (auto-generated from name if not provided)",
    )
    # Optional contributors list - will be validated by server
    contributors: List[int] = Field(
        default_factory=list,
        description="List of contributor user IDs (will be validated)",
    )
    # organization_id removed - should be passed separately to the service method

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        """Validate endpoint slug format."""
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


class EndpointUpdate(BaseModel):
    """Schema for updating a endpoint - user-modifiable fields only."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=100, description="Display name of the endpoint"
    )
    description: Optional[str] = Field(
        None, max_length=500, description="Description of the endpoint"
    )
    visibility: Optional[EndpointVisibility] = Field(
        None, description="Who can access this endpoint"
    )
    # REMOVED is_active - only admin can change this
    contributors: Optional[List[int]] = Field(
        None, description="List of contributor user IDs (will be validated)"
    )
    version: Optional[str] = Field(
        None,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version of the endpoint",
    )
    readme: Optional[str] = Field(
        None, max_length=50000, description="Markdown content for the README"
    )
    policies: Optional[List[Policy]] = Field(
        None, description="List of policies applied to this endpoint"
    )
    connect: Optional[List[Connection]] = Field(
        None, description="List of connection methods available for this endpoint"
    )


class EndpointAdminUpdate(BaseModel):
    """Schema for admin-only endpoint updates."""

    is_active: Optional[bool] = Field(
        None, description="Whether the endpoint is active (admin only)"
    )
    stars_count: Optional[int] = Field(
        None, ge=0, description="Override star count (admin only, use with caution)"
    )


class Endpoint(BaseModel):
    """Complete endpoint model with all fields."""

    # User-provided fields
    name: str = Field(..., description="Display name of the endpoint")
    description: str = Field(..., description="Description of the endpoint")
    type: EndpointType = Field(
        ..., description="Type of endpoint (model or data_source)"
    )
    visibility: EndpointVisibility = Field(
        ..., description="Who can access this endpoint"
    )
    version: str = Field(..., description="Semantic version of the endpoint")
    readme: str = Field(..., description="Markdown content for the README")
    policies: List[Policy] = Field(..., description="List of policies")
    connect: List[Connection] = Field(..., description="List of connection methods")

    # Server-managed fields
    id: int = Field(..., description="Endpoint's unique identifier")
    user_id: Optional[int] = Field(
        None, description="ID of the user who owns this endpoint"
    )
    organization_id: Optional[int] = Field(
        None, description="ID of the organization that owns this endpoint"
    )
    slug: str = Field(
        ..., min_length=3, max_length=63, description="URL-safe identifier"
    )
    is_active: bool = Field(..., description="Whether the endpoint is active")
    contributors: List[int] = Field(..., description="List of contributor user IDs")
    stars_count: int = Field(
        ..., description="Number of stars this endpoint has received"
    )
    created_at: datetime = Field(..., description="When the endpoint was created")
    updated_at: datetime = Field(..., description="When the endpoint was last updated")

    model_config = {"from_attributes": True}


class EndpointResponse(BaseModel):
    """Schema for endpoint response - includes all fields."""

    id: int = Field(..., description="Endpoint's unique identifier")
    user_id: Optional[int] = Field(
        None, description="ID of the user who owns this endpoint"
    )
    organization_id: Optional[int] = Field(
        None, description="ID of the organization that owns this endpoint"
    )
    name: str = Field(..., description="Display name of the endpoint")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Description of the endpoint")
    type: EndpointType = Field(
        ..., description="Type of endpoint (model or data_source)"
    )
    visibility: EndpointVisibility = Field(
        ..., description="Who can access this endpoint"
    )
    is_active: bool = Field(..., description="Whether the endpoint is active")
    contributors: List[int] = Field(..., description="List of contributor user IDs")
    version: str = Field(..., description="Semantic version of the endpoint")
    readme: str = Field(..., description="Markdown content for the README")
    stars_count: int = Field(
        ..., description="Number of stars this endpoint has received"
    )
    policies: List[Policy] = Field(
        ..., description="List of policies applied to this endpoint"
    )
    connect: List[Connection] = Field(
        ..., description="List of connection methods available for this endpoint"
    )
    created_at: datetime = Field(..., description="When the endpoint was created")
    updated_at: datetime = Field(..., description="When the endpoint was last updated")

    model_config = {"from_attributes": True}


class EndpointPublicResponse(BaseModel):
    """Schema for public endpoint response (limited fields only)."""

    name: str = Field(..., description="Display name of the endpoint")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Description of the endpoint")
    type: EndpointType = Field(
        ..., description="Type of endpoint (model or data_source)"
    )
    owner_username: str = Field(..., description="Username of the endpoint owner")
    # REMOVED contributors - privacy issue, only owner should see this
    version: str = Field(..., description="Semantic version of the endpoint")
    readme: str = Field(..., description="Markdown content for the README")
    stars_count: int = Field(
        ..., description="Number of stars this endpoint has received"
    )
    policies: List[Policy] = Field(
        ..., description="List of policies applied to this endpoint"
    )
    connect: List[Connection] = Field(
        ..., description="List of connection methods available for this endpoint"
    )
    created_at: datetime = Field(..., description="When the endpoint was created")
    updated_at: datetime = Field(..., description="When the endpoint was last updated")

    # Note: Excludes user_id, id, visibility, is_active, contributors for security/privacy

    model_config = {"from_attributes": True}


def generate_slug_from_name(name: str) -> str:
    """Generate a URL-safe slug from endpoint name."""
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())

    # Remove leading/trailing hyphens
    slug = slug.strip("-")

    # Ensure minimum length
    if len(slug) < 3:
        slug = f"endpoint-{slug}"

    # Truncate if too long
    if len(slug) > 63:
        slug = slug[:63].rstrip("-")

    return slug


def is_slug_available(
    slug: str,  # noqa: ARG001
    user_id: int,  # noqa: ARG001
    exclude_endpoint_id: Optional[int] = None,  # noqa: ARG001
) -> bool:
    """Check if a slug is available for a user."""
    # This will be implemented in the endpoints module
    # Placeholder for the actual availability check logic
    return True
