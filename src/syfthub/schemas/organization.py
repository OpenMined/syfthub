"""Organization schemas."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OrganizationRole(str, Enum):
    """Organization member roles."""

    OWNER = "owner"  # Full control including deletion
    ADMIN = "admin"  # Manage members and settings, but cannot delete org
    MEMBER = "member"  # Basic access to organization resources


# Reserved organization slugs (in addition to datasite reserved slugs)
RESERVED_ORG_SLUGS = {
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
    "organizations",
    "org",
    "orgs",
    "organization",
    "user",
    "users",
    "account",
    "accounts",
}


class OrganizationBase(BaseModel):
    """Base organization schema."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Display name of the organization",
    )
    description: str = Field(
        "", max_length=500, description="Description of the organization"
    )
    avatar_url: Optional[str] = Field(
        None, max_length=255, description="URL to organization avatar/logo"
    )
    is_active: bool = Field(
        default=True, description="Whether the organization is active"
    )


class OrganizationCreate(OrganizationBase):
    """Schema for creating a new organization."""

    slug: Optional[str] = Field(
        None,
        min_length=3,
        max_length=63,
        description="URL-safe identifier (auto-generated from name if not provided)",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        """Validate organization slug format."""
        if v is None:
            return v

        # Check for uppercase letters before converting
        if v != v.lower():
            raise ValueError("Slug must contain only lowercase letters")

        # Check reserved slugs
        if v in RESERVED_ORG_SLUGS:
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


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Display name of the organization",
    )
    description: Optional[str] = Field(
        None, max_length=500, description="Description of the organization"
    )
    avatar_url: Optional[str] = Field(
        None, max_length=255, description="URL to organization avatar/logo"
    )
    is_active: Optional[bool] = Field(
        None, description="Whether the organization is active"
    )


class Organization(OrganizationBase):
    """Organization model."""

    id: int = Field(..., description="Organization's unique identifier")
    slug: str = Field(
        ..., min_length=3, max_length=63, description="URL-safe identifier"
    )
    created_at: datetime = Field(..., description="When the organization was created")
    updated_at: datetime = Field(
        ..., description="When the organization was last updated"
    )

    model_config = {"from_attributes": True}


class OrganizationResponse(BaseModel):
    """Schema for organization response."""

    id: int = Field(..., description="Organization's unique identifier")
    name: str = Field(..., description="Display name of the organization")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Description of the organization")
    avatar_url: Optional[str] = Field(
        ..., description="URL to organization avatar/logo"
    )
    is_active: bool = Field(..., description="Whether the organization is active")
    created_at: datetime = Field(..., description="When the organization was created")
    updated_at: datetime = Field(
        ..., description="When the organization was last updated"
    )

    model_config = {"from_attributes": True}


class OrganizationMemberBase(BaseModel):
    """Base organization member schema."""

    role: OrganizationRole = Field(
        default=OrganizationRole.MEMBER, description="Member's role in the organization"
    )
    is_active: bool = Field(
        default=True, description="Whether the membership is active"
    )


class OrganizationMemberCreate(OrganizationMemberBase):
    """Schema for creating organization membership."""

    user_id: int = Field(..., description="ID of the user to add as member")


class OrganizationMemberUpdate(BaseModel):
    """Schema for updating organization membership."""

    role: Optional[OrganizationRole] = Field(
        None, description="Member's role in the organization"
    )
    is_active: Optional[bool] = Field(
        None, description="Whether the membership is active"
    )


class OrganizationMemberResponse(BaseModel):
    """Schema for organization member response."""

    id: int = Field(..., description="Membership unique identifier")
    organization_id: int = Field(..., description="Organization ID")
    user_id: int = Field(..., description="User ID")
    role: OrganizationRole = Field(..., description="Member's role in the organization")
    is_active: bool = Field(..., description="Whether the membership is active")
    joined_at: datetime = Field(
        ..., description="When the user joined the organization"
    )

    model_config = {"from_attributes": True}


def generate_slug_from_name(name: str) -> str:
    """Generate a URL-safe slug from organization name."""
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())

    # Remove leading/trailing hyphens
    slug = slug.strip("-")

    # Ensure minimum length
    if len(slug) < 3:
        slug = f"org-{slug}"

    # Truncate if too long
    if len(slug) > 63:
        slug = slug[:63].rstrip("-")

    return slug


def is_slug_available(
    slug: str,  # noqa: ARG001
    exclude_organization_id: Optional[int] = None,  # noqa: ARG001
) -> bool:
    """Check if a slug is available for an organization."""
    # This will be implemented in the endpoints module
    # Placeholder for the actual availability check logic
    return True
