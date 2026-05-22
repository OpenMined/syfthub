"""Collective schemas.

Pydantic models for the Collectives feature — a user-owned grouping of
endpoints. See ``syfthub.models.collective`` for the persistence layer.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from syfthub.schemas.endpoint import _validate_and_normalize_tags


class MembershipStatus(str, Enum):
    """Status of an endpoint's membership in a collective."""

    PENDING = "pending"  # endpoint owner requested to join; awaiting collective owner
    INVITED = (
        "invited"  # collective owner invited the endpoint; awaiting endpoint owner
    )
    APPROVED = "approved"  # active member
    REJECTED = "rejected"  # request/invite declined by either side


class ReviewDecision(str, Enum):
    """A collective owner's decision on a pending join request."""

    APPROVE = "approve"
    REJECT = "reject"


class InvitationDecision(str, Enum):
    """An endpoint owner's response to a collective invitation."""

    ACCEPT = "accept"
    DECLINE = "decline"


# Slugs that cannot be used for collectives (route collisions / confusables).
RESERVED_COLLECTIVE_SLUGS = {
    "api",
    "auth",
    "docs",
    "redoc",
    "openapi.json",
    "health",
    "admin",
    "www",
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
    "collective",
    "collectives",
    "members",
    "invitations",
    "by-slug",
}

# alphanumeric + single hyphens, no leading/trailing hyphen
_SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def slugify_collective_name(name: str) -> str:
    """Derive a URL-safe base slug from a collective name.

    The result is not guaranteed unique — the service resolves collisions.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
    if len(slug) < 3:
        slug = f"collective-{slug}".strip("-")
    if len(slug) > 63:
        slug = slug[:63].rstrip("-")
    return slug


def _validate_slug(v: str) -> str:
    """Validate a user-provided collective slug."""
    if v != v.lower():
        raise ValueError("Slug must contain only lowercase letters")
    if v in RESERVED_COLLECTIVE_SLUGS:
        raise ValueError(f"'{v}' is a reserved slug and cannot be used")
    if "--" in v:
        raise ValueError("Slug cannot contain consecutive hyphens")
    if not _SLUG_PATTERN.match(v):
        raise ValueError(
            "Slug must contain only lowercase letters, numbers, and hyphens. "
            "Cannot start or end with a hyphen."
        )
    return v


class CollectiveBase(BaseModel):
    """Fields a user supplies when creating or updating a collective."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Display name of the collective"
    )
    description: str = Field(
        "", max_length=500, description="Short description of the collective"
    )
    about: str = Field(
        "",
        max_length=50000,
        description="Long-form markdown 'about' / README for the collective",
    )
    auto_approve: bool = Field(
        default=False,
        description="If true, join requests are accepted immediately; "
        "if false, the owner must approve each request",
    )
    icon_url: Optional[str] = Field(
        None, max_length=500, description="URL to the collective's icon/image"
    )
    tags: List[str] = Field(
        default_factory=list, description="Tags for categorizing the collective"
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Normalize and validate the tag list (max 10, lowercase, hyphenated)."""
        return _validate_and_normalize_tags(v)


class CollectiveCreate(CollectiveBase):
    """Schema for creating a new collective."""

    slug: Optional[str] = Field(
        None,
        min_length=3,
        max_length=63,
        description="URL-safe identifier (auto-generated from name if omitted)",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        """Validate the optional user-provided slug."""
        return None if v is None else _validate_slug(v)


class CollectiveUpdate(BaseModel):
    """Schema for updating a collective — all fields optional, owner-only."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    about: Optional[str] = Field(None, max_length=50000)
    auto_approve: Optional[bool] = None
    icon_url: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize and validate the tag list when provided."""
        return None if v is None else _validate_and_normalize_tags(v)


class CollectiveResponse(BaseModel):
    """Schema for a collective in API responses."""

    id: int = Field(..., description="Collective's unique identifier")
    owner_id: int = Field(..., description="ID of the user who owns this collective")
    name: str = Field(..., description="Display name of the collective")
    slug: str = Field(..., description="URL-safe identifier")
    shared_endpoint_path: str = Field(
        "",
        description=(
            "Unique shared-endpoint path for the collective, of the form "
            "'collective/<slug>'. Derived from the (unique) slug; addresses "
            "every member endpoint through a single API. Read-only."
        ),
    )
    description: str = Field(..., description="Short description of the collective")
    about: str = Field(
        "", description="Long-form markdown 'about' / README for the collective"
    )
    auto_approve: bool = Field(
        ..., description="Whether join requests are auto-accepted"
    )
    icon_url: Optional[str] = Field(None, description="URL to the collective's icon")
    tags: List[str] = Field(..., description="Tags for categorization")
    verified: bool = Field(
        False,
        description="Whether the collective has been verified by the platform",
    )
    member_count: int = Field(0, description="Number of approved endpoint members")
    owner_count: int = Field(
        0,
        description="Number of distinct users who own the approved member endpoints",
    )
    created_at: datetime = Field(..., description="When the collective was created")
    updated_at: datetime = Field(
        ..., description="When the collective was last updated"
    )

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _derive_shared_endpoint_path(self) -> CollectiveResponse:
        """Derive the shared-endpoint path from the collective's unique slug.

        Runs on every construction (including the repository's
        ``model_validate``), so the path is always consistent with ``slug``
        and never needs to be persisted or set by callers.
        """
        self.shared_endpoint_path = f"collective/{self.slug}"
        return self


class CollectiveMemberRequest(BaseModel):
    """Request body for requesting to join, or inviting an endpoint to, a collective."""

    endpoint_id: int = Field(..., description="ID of the endpoint")


class CollectiveInviteByPathRequest(BaseModel):
    """Request body for inviting an endpoint identified by ``owner/slug``.

    Used by the admin UI's invite modal, which lookups endpoints by their
    public path rather than the numeric id (the public endpoint API does not
    expose the id field).
    """

    owner_username: str = Field(..., description="Username of the endpoint owner")
    slug: str = Field(..., description="URL-safe identifier of the endpoint")


class CollectiveReviewRequest(BaseModel):
    """Request body for a collective owner reviewing a pending join request."""

    decision: ReviewDecision = Field(..., description="Approve or reject the request")


class CollectiveInvitationResponse(BaseModel):
    """Request body for an endpoint owner responding to a collective invitation."""

    decision: InvitationDecision = Field(
        ..., description="Accept or decline the invitation"
    )


class CollectiveMemberResponse(BaseModel):
    """Schema for a collective membership in API responses."""

    id: int = Field(..., description="Membership unique identifier")
    collective_id: int = Field(..., description="Collective ID")
    endpoint_id: int = Field(..., description="Endpoint ID")
    status: MembershipStatus = Field(..., description="Membership workflow status")
    requested_at: datetime = Field(
        ..., description="When the join request / invitation was created"
    )
    responded_at: Optional[datetime] = Field(
        None, description="When the membership was approved or rejected"
    )
    reviewed_by_user_id: Optional[int] = Field(
        None, description="User who approved/accepted the membership, if any"
    )
    # Endpoint identity, populated by the service layer so callers can render a
    # membership without a second round-trip. None when the endpoint has since
    # been removed.
    endpoint_name: Optional[str] = Field(
        None, description="Display name of the member endpoint"
    )
    endpoint_description: Optional[str] = Field(
        None, description="Short description of the member endpoint"
    )
    endpoint_slug: Optional[str] = Field(
        None, description="URL slug of the member endpoint"
    )
    endpoint_owner_username: Optional[str] = Field(
        None, description="Username of the member endpoint's owner"
    )
    endpoint_owner_full_name: Optional[str] = Field(
        None, description="Full name of the member endpoint's owner"
    )
    endpoint_type: Optional[str] = Field(
        None, description="Type of the member endpoint (model / data_source)"
    )

    model_config = {"from_attributes": True}


class InvitationEmailContext(BaseModel):
    """Context for the collective-invitation notification email.

    Internal service -> router payload (passed to a background email task);
    not part of the public API surface.
    """

    to_email: str = Field(..., description="Endpoint owner's email address")
    recipient_name: str = Field(..., description="Endpoint owner's display name")
    inviter_name: str = Field(..., description="Display name of the inviting user")
    collective_name: str = Field(..., description="Name of the collective")
    collective_slug: str = Field(..., description="Slug of the collective")
    endpoint_name: str = Field(..., description="Name of the invited endpoint")
    endpoint_id: int = Field(..., description="ID of the invited endpoint")
