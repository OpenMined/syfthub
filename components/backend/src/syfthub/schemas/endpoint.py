"""Endpoint schemas."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class EndpointVisibility(str, Enum):
    """Endpoint visibility levels."""

    PUBLIC = "public"  # Anyone can view
    PRIVATE = "private"  # Only owner (and future collaborators) can view
    INTERNAL = "internal"  # Only the owner can view (behaves like private)


class EndpointType(str, Enum):
    """Endpoint type classification."""

    MODEL = "model"  # Machine learning model endpoint
    DATA_SOURCE = "data_source"  # Data source endpoint
    MODEL_DATA_SOURCE = "model_data_source"  # Both model and data source
    AGENT = "agent"  # Agent endpoint with session-based interaction


class EndpointHealthStatus(str, Enum):
    """Per-endpoint health status reported by client."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


def get_matching_types(endpoint_type: EndpointType) -> list[str]:
    """Get all type values that match a filter, including model_data_source for model/data_source."""
    if endpoint_type == EndpointType.MODEL:
        return [EndpointType.MODEL.value, EndpointType.MODEL_DATA_SOURCE.value]
    elif endpoint_type == EndpointType.DATA_SOURCE:
        return [EndpointType.DATA_SOURCE.value, EndpointType.MODEL_DATA_SOURCE.value]
    else:
        return [endpoint_type.value]


# Policy ``type`` values that bill via publisher-side prepaid credits (the
# buyer funds a wallet with the publisher and tops it up via ``payment_url``).
# ``cluster`` is a station-hosted *shared* wallet: many spaces publish the same
# ``wallet_id`` under one wallet-owner account, so one balance backs them all.
# Single source of truth — keep in lockstep with the frontend
# ``PREPAID_BALANCE_TYPES`` set in ``policy-item.tsx``.
PREPAID_POLICY_TYPES: frozenset[str] = frozenset({"xendit", "stripe", "cluster"})

# The station-hosted shared-wallet policy type. Unlike ``xendit``/``stripe``,
# its config must name the wallet-owning Hub account (``wallet_owner``) so the
# satellite-token audience can be derived; see
# ``EndpointService._process_cluster_policies``.
CLUSTER_POLICY_TYPE = "cluster"


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


def filter_visible_policies(
    policies: List[Any], viewer_email: Optional[str]
) -> List[Any]:
    """Filter policies by their `config.applied_to` audience list.

    Specific targeting overrides the wildcard: if any policy explicitly
    names the viewer's email, only those targeted policies are returned
    (the wildcard fallback is suppressed for that viewer). Otherwise
    the viewer falls back to wildcard / unset-`applied_to` policies.

    `applied_to` semantics per policy:
    - Missing/empty `applied_to` is treated as `["*"]` (wildcard fallback).
    - `"*"` in `applied_to` makes the policy a wildcard fallback.
    - Otherwise the policy is "targeted" and applies only to listed emails
      (case-insensitive).
    - An anonymous viewer (`viewer_email=None`) only ever sees wildcards.

    Accepts policies as Pydantic Policy instances or plain dicts.
    """
    normalized_viewer = viewer_email.strip().lower() if viewer_email else None

    def _applied_to(policy: Any) -> Optional[List[Any]]:
        if isinstance(policy, BaseModel):
            config = getattr(policy, "config", None) or {}
        elif isinstance(policy, dict):
            config = policy.get("config") or {}
        else:
            config = {}
        applied_to = config.get("applied_to") if isinstance(config, dict) else None
        return applied_to if applied_to else None

    wildcards: List[Any] = []
    targeted: List[Any] = []
    for policy in policies:
        applied_to = _applied_to(policy)
        if applied_to is None:
            wildcards.append(policy)
            continue
        is_wildcard = False
        is_targeted = False
        for entry in applied_to:
            if not isinstance(entry, str):
                continue
            normalized_entry = entry.strip().lower()
            if normalized_entry == "*":
                is_wildcard = True
            elif normalized_viewer and normalized_entry == normalized_viewer:
                is_targeted = True
        if is_targeted:
            targeted.append(policy)
        elif is_wildcard:
            wildcards.append(policy)

    return targeted or wildcards


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


def _validate_and_normalize_tags(tags: List[str]) -> List[str]:
    """Validate and normalize a list of tags.

    Args:
        tags: Raw list of tag strings.

    Returns:
        Normalized, deduplicated list of valid tags.

    Raises:
        ValueError: If any tag violates the validation rules.
    """
    # Max 10 tags
    if len(tags) > 10:
        raise ValueError("Maximum 10 tags allowed")

    normalized_tags = []
    seen: set[str] = set()

    for tag in tags:
        # Strip whitespace and convert to lowercase
        tag = tag.strip().lower()

        # Skip empty tags
        if not tag:
            continue

        # Validate length
        if len(tag) < 1 or len(tag) > 30:
            raise ValueError(f"Tag '{tag}' must be between 1 and 30 characters")

        # Validate format: alphanumeric + hyphens, no leading/trailing hyphens
        tag_pattern = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$|^[a-z0-9]$"
        if not re.match(tag_pattern, tag):
            raise ValueError(
                f"Tag '{tag}' must contain only lowercase letters, numbers, and hyphens. "
                "Cannot start or end with hyphen."
            )

        # Check for consecutive hyphens
        if "--" in tag:
            raise ValueError(f"Tag '{tag}' cannot contain consecutive hyphens")

        # Deduplicate
        if tag not in seen:
            seen.add(tag)
            normalized_tags.append(tag)

    return normalized_tags


class EndpointBase(BaseModel):
    """Base endpoint schema."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Display name of the endpoint"
    )
    description: str = Field(
        "", max_length=500, description="Description of the endpoint"
    )
    type: EndpointType = Field(
        ..., description="Type of endpoint (model, data_source, or model_data_source)"
    )
    visibility: EndpointVisibility = Field(
        default=EndpointVisibility.PUBLIC, description="Who can access this endpoint"
    )
    archived: bool = Field(
        default=False,
        description="Whether this endpoint is archived (no new purchases, kept accessible to existing users)",
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
    tags: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="List of tags for categorization (max 10 tags)",
    )
    # REMOVED stars_count - CRITICAL: server-managed field only
    policies: List[Policy] = Field(
        default_factory=list, description="List of policies applied to this endpoint"
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Validate and normalize tags."""
        if not v:
            return []
        return _validate_and_normalize_tags(v)

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
    archived: Optional[bool] = Field(
        None, description="Archive or restore the endpoint"
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
    tags: Optional[List[str]] = Field(
        None,
        max_length=10,
        description="List of tags for categorization (max 10 tags)",
    )
    policies: Optional[List[Policy]] = Field(
        None, description="List of policies applied to this endpoint"
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate and normalize tags."""
        if v is None:
            return None
        if not v:
            return []
        return _validate_and_normalize_tags(v)

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
        ..., description="Type of endpoint (model, data_source, or model_data_source)"
    )
    visibility: EndpointVisibility = Field(
        ..., description="Who can access this endpoint"
    )
    version: str = Field(..., description="Semantic version of the endpoint")
    readme: str = Field(..., description="Markdown content for the README")
    tags: List[str] = Field(..., description="List of tags for categorization")
    policies: List[Policy] = Field(..., description="List of policies")
    connect: List[Connection] = Field(..., description="List of connection methods")

    # Server-managed fields
    id: int = Field(..., description="Endpoint's unique identifier")
    user_id: int = Field(..., description="ID of the user who owns this endpoint")
    # Internal only — Endpoint is never a response model. Carried so callers can
    # resolve each endpoint's serving origin without a per-row query.
    space_id: Optional[int] = Field(
        None, description="Internal id of the satellite serving this endpoint"
    )
    slug: str = Field(
        ..., min_length=3, max_length=63, description="URL-safe identifier"
    )
    is_active: bool = Field(..., description="Whether the endpoint is active")
    archived: bool = Field(..., description="Whether the endpoint is archived")
    contributors: List[int] = Field(..., description="List of contributor user IDs")
    stars_count: int = Field(
        ..., description="Number of stars this endpoint has received"
    )
    created_at: datetime = Field(..., description="When the endpoint was created")
    updated_at: datetime = Field(..., description="When the endpoint was last updated")

    # Per-endpoint health status (reported by client via POST /endpoints/health)
    health_status: Optional[str] = Field(
        None, description="Client-reported health status ('healthy' or 'unhealthy')"
    )
    health_checked_at: Optional[datetime] = Field(
        None, description="When the client last checked this endpoint's health"
    )
    health_ttl_seconds: Optional[int] = Field(
        None, description="TTL for the health status report in seconds"
    )

    # --- The benchmark card, reported by the owner via POST /endpoints/quality.
    # NULL throughout means nobody ever measured this endpoint, which is not a
    # score of zero and must not render as one.
    quality_kind: Optional[str] = Field(
        None,
        description=(
            "What kind of product was measured: 'answering' (it writes the "
            "answer) or 'retrieval' (it finds material and someone else's "
            "model answers). quality_score cannot be read without it"
        ),
    )
    quality_score: Optional[float] = Field(
        None,
        description=(
            "Headline share for that kind: accuracy of the answer, or share of "
            "questions where the search found the right material (0..1)"
        ),
    )
    quality_fabrication_rate: Optional[float] = Field(
        None,
        description=(
            "Share of questions with no answer in the corpus that were "
            "answered anyway (0..1). Nearly independent of how hard the corpus "
            "is, which makes it the figure that compares across endpoints"
        ),
    )
    quality_samples: Optional[int] = Field(
        None, description="How many questions the last benchmark graded"
    )
    quality_reliable: Optional[bool] = Field(
        None,
        description=(
            "Whether the benchmark vouches for these figures. False means show "
            "them greyed out or not at all; the reasons are in quality_report"
        ),
    )
    quality_checked_at: Optional[datetime] = Field(
        None, description="When the benchmark that produced this card ran"
    )
    quality_report: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "The whole card: both halves of the dataset, the spread across "
            "subject models, the breakdown by task type, what the figures rest "
            "on, and what did the measuring"
        ),
    )
    model_config = {"from_attributes": True}


class EndpointResponse(BaseModel):
    """Schema for endpoint response - includes all fields."""

    id: int = Field(..., description="Endpoint's unique identifier")
    user_id: int = Field(..., description="ID of the user who owns this endpoint")
    name: str = Field(..., description="Display name of the endpoint")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Description of the endpoint")
    type: EndpointType = Field(
        ..., description="Type of endpoint (model, data_source, or model_data_source)"
    )
    visibility: EndpointVisibility = Field(
        ..., description="Who can access this endpoint"
    )
    is_active: bool = Field(..., description="Whether the endpoint is active")
    archived: bool = Field(..., description="Whether the endpoint is archived")
    contributors: List[int] = Field(..., description="List of contributor user IDs")
    version: str = Field(..., description="Semantic version of the endpoint")
    readme: str = Field(..., description="Markdown content for the README")
    tags: List[str] = Field(..., description="List of tags for categorization")
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

    # Per-endpoint health status (reported by client via POST /endpoints/health)
    health_status: Optional[str] = Field(
        None, description="Client-reported health status ('healthy' or 'unhealthy')"
    )
    health_checked_at: Optional[datetime] = Field(
        None, description="When the client last checked this endpoint's health"
    )
    health_ttl_seconds: Optional[int] = Field(
        None, description="TTL for the health status report in seconds"
    )

    # --- The benchmark card, reported by the owner via POST /endpoints/quality.
    # NULL throughout means nobody ever measured this endpoint, which is not a
    # score of zero and must not render as one.
    quality_kind: Optional[str] = Field(
        None,
        description=(
            "What kind of product was measured: 'answering' (it writes the "
            "answer) or 'retrieval' (it finds material and someone else's "
            "model answers). quality_score cannot be read without it"
        ),
    )
    quality_score: Optional[float] = Field(
        None,
        description=(
            "Headline share for that kind: accuracy of the answer, or share of "
            "questions where the search found the right material (0..1)"
        ),
    )
    quality_fabrication_rate: Optional[float] = Field(
        None,
        description=(
            "Share of questions with no answer in the corpus that were "
            "answered anyway (0..1). Nearly independent of how hard the corpus "
            "is, which makes it the figure that compares across endpoints"
        ),
    )
    quality_samples: Optional[int] = Field(
        None, description="How many questions the last benchmark graded"
    )
    quality_reliable: Optional[bool] = Field(
        None,
        description=(
            "Whether the benchmark vouches for these figures. False means show "
            "them greyed out or not at all; the reasons are in quality_report"
        ),
    )
    quality_checked_at: Optional[datetime] = Field(
        None, description="When the benchmark that produced this card ran"
    )
    quality_report: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "The whole card: both halves of the dataset, the spread across "
            "subject models, the breakdown by task type, what the figures rest "
            "on, and what did the measuring"
        ),
    )
    model_config = {"from_attributes": True}


class EndpointPublicResponse(BaseModel):
    """Schema for public endpoint response (limited fields only)."""

    name: str = Field(..., description="Display name of the endpoint")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Description of the endpoint")
    type: EndpointType = Field(
        ..., description="Type of endpoint (model, data_source, or model_data_source)"
    )
    owner_username: str = Field(..., description="Username of the endpoint owner")
    # Show contributor count (not user IDs) for privacy - users can see collaboration level
    contributors_count: int = Field(
        ..., description="Number of contributors to this endpoint"
    )
    version: str = Field(..., description="Semantic version of the endpoint")
    readme: str = Field(..., description="Markdown content for the README")
    tags: List[str] = Field(..., description="List of tags for categorization")
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

    # Per-endpoint health status (reported by client via POST /endpoints/health)
    health_status: Optional[str] = Field(
        None, description="Client-reported health status ('healthy' or 'unhealthy')"
    )
    health_checked_at: Optional[datetime] = Field(
        None, description="When the client last checked this endpoint's health"
    )

    # --- The benchmark card, reported by the owner via POST /endpoints/quality.
    # NULL throughout means nobody ever measured this endpoint, which is not a
    # score of zero and must not render as one.
    quality_kind: Optional[str] = Field(
        None,
        description=(
            "What kind of product was measured: 'answering' (it writes the "
            "answer) or 'retrieval' (it finds material and someone else's "
            "model answers). quality_score cannot be read without it"
        ),
    )
    quality_score: Optional[float] = Field(
        None,
        description=(
            "Headline share for that kind: accuracy of the answer, or share of "
            "questions where the search found the right material (0..1)"
        ),
    )
    quality_fabrication_rate: Optional[float] = Field(
        None,
        description=(
            "Share of questions with no answer in the corpus that were "
            "answered anyway (0..1). Nearly independent of how hard the corpus "
            "is, which makes it the figure that compares across endpoints"
        ),
    )
    quality_samples: Optional[int] = Field(
        None, description="How many questions the last benchmark graded"
    )
    quality_reliable: Optional[bool] = Field(
        None,
        description=(
            "Whether the benchmark vouches for these figures. False means show "
            "them greyed out or not at all; the reasons are in quality_report"
        ),
    )
    quality_checked_at: Optional[datetime] = Field(
        None, description="When the benchmark that produced this card ran"
    )
    # The whole card rides on the public view too, and not only on the owner's.
    # There is no public route for one endpoint that returns anything else: the
    # detail page is built from this same shape, so leaving the document off
    # here would mean the card could never be shown to the people it is for.
    # The cost is proportionate — this response already carries the full README.
    quality_report: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "The whole card: both halves of the dataset, the spread across "
            "subject models, the breakdown by task type, what the figures rest "
            "on, and what did the measuring"
        ),
    )
    archived: bool = Field(
        default=False, description="Whether the endpoint is archived"
    )

    # Note: Excludes user_id, id, visibility, is_active, contributors, health_ttl_seconds for security/privacy

    model_config = {"from_attributes": True}


# ===========================================
# SYNC ENDPOINT SCHEMAS
# ===========================================


class SyncValidationError(BaseModel):
    """Validation error for a specific endpoint in sync batch."""

    index: int = Field(..., ge=0, description="Index of endpoint in batch (0-based)")
    field: str = Field(..., description="Field that failed validation")
    error: str = Field(..., description="Error message")


class SyncEndpointsRequest(BaseModel):
    """Request schema for syncing user endpoints.

    Replaces the endpoints served by ONE satellite with the provided list. It is
    atomic: either all endpoints are synced, or none are (on validation failure).
    """

    satellite_id: Optional[uuid.UUID] = Field(
        None,
        description=(
            "Which satellite this sync is for. Optional: needed only once the "
            "account owns more than one, since a sync carries no URL to "
            "identify the caller by."
        ),
    )

    endpoints: List[EndpointCreate] = Field(
        default_factory=list,
        max_length=300,
        description="List of endpoint specifications to sync (max 300)",
    )


class SyncEndpointsResponse(BaseModel):
    """Response schema for sync operation."""

    synced: int = Field(..., ge=0, description="Number of endpoints created")
    deleted: int = Field(..., ge=0, description="Number of endpoints deleted")
    endpoints: List[EndpointResponse] = Field(
        ..., description="Created endpoints with full details"
    )

    model_config = {"from_attributes": True}


# ===========================================
# GROUPED ENDPOINTS SCHEMAS
# ===========================================


class EndpointGroupItem(BaseModel):
    """A group of endpoints belonging to a single owner.

    Used in the grouped public endpoints response for the Global Directory.
    """

    owner_username: str = Field(..., description="Username of the endpoint owner")
    endpoints: List[EndpointPublicResponse] = Field(
        ..., description="Endpoints belonging to this owner (limited to max_per_owner)"
    )
    total_count: int = Field(
        ...,
        ge=0,
        description="Total number of endpoints this owner has (may be more than shown)",
    )
    has_more: bool = Field(
        ...,
        description="True if owner has more endpoints than shown (total_count > len(endpoints))",
    )


class GroupedEndpointsResponse(BaseModel):
    """Response containing endpoints grouped by owner.

    Used for the Global Directory to display a balanced view across multiple owners
    rather than having one owner dominate the listing.
    """

    groups: List[EndpointGroupItem] = Field(
        ..., description="Endpoint groups ordered by total endpoint count (descending)"
    )


# ===========================================
# OWNER SUMMARY SCHEMAS (for CLI ls command)
# ===========================================


class OwnerSummary(BaseModel):
    """Summary of an owner's endpoints for directory listing.

    Lightweight response for listing owners without fetching full endpoint data.
    Used by CLI `syft ls` command to efficiently list available users.
    """

    username: str = Field(..., description="Username")
    endpoint_count: int = Field(
        ..., ge=0, description="Total number of public endpoints"
    )
    model_count: int = Field(..., ge=0, description="Number of model endpoints")
    data_source_count: int = Field(
        ..., ge=0, description="Number of data source endpoints"
    )


class OwnersListResponse(BaseModel):
    """Response containing list of owners with endpoint summaries.

    Efficient endpoint for directory browsing - returns only owner names
    and counts, not full endpoint data.
    """

    owners: List[OwnerSummary] = Field(
        ..., description="List of owners ordered by endpoint count (descending)"
    )
    total_count: int = Field(
        ..., ge=0, description="Total number of owners with public endpoints"
    )


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


# ===========================================
# ENDPOINT HEALTH SCHEMAS
# ===========================================


class EndpointHealthItem(BaseModel):
    """Single endpoint health status report from client."""

    slug: str = Field(
        ...,
        min_length=3,
        max_length=63,
        description="Endpoint slug to report health for",
    )
    status: EndpointHealthStatus = Field(
        ..., description="Health status: 'healthy' or 'unhealthy'"
    )
    checked_at: datetime = Field(
        ..., description="When the client checked this endpoint's health"
    )


class EndpointHealthRequest(BaseModel):
    """Request schema for bulk endpoint health reporting.

    Allows clients to report per-endpoint health status. Also records the
    reporting satellite's origin (used for endpoint URL construction).
    """

    satellite_id: Optional[uuid.UUID] = Field(
        None,
        description=(
            "Which satellite is reporting. Optional: the reported url "
            "identifies it for any account owning fewer than two."
        ),
    )

    endpoints: List[EndpointHealthItem] = Field(
        ...,
        min_length=1,
        max_length=300,
        description="List of endpoint health status reports",
    )
    ttl_seconds: Optional[int] = Field(
        None,
        ge=1,
        le=3600,
        description="TTL for health status validity (capped by server max)",
    )
    url: str = Field(
        ...,
        max_length=500,
        description="Full URL of the domain sending the health report",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format (http(s):// or tunneling: prefix)."""
        from urllib.parse import urlparse

        from syfthub.domain.base_url import TUNNELING_PREFIX
        from syfthub.schemas.user import TUNNELING_USERNAME_PATTERN

        v = v.strip()

        if v.startswith(TUNNELING_PREFIX):
            username = v[len(TUNNELING_PREFIX) :]
            if not username:
                raise ValueError("Tunneling URL must include a username")
            if not TUNNELING_USERNAME_PATTERN.match(username):
                raise ValueError(
                    "Tunneling username must be 1-50 characters, "
                    "alphanumeric with underscores and hyphens only"
                )
            return v

        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"URL must start with http://, https://, or {TUNNELING_PREFIX}"
            )

        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("URL must contain a valid hostname")

        hostname = parsed.netloc.split(":")[0]
        if not hostname:
            raise ValueError("URL must contain a valid hostname, not just a port")

        return v


class EndpointHealthResponse(BaseModel):
    """Response schema for bulk endpoint health reporting."""

    updated: int = Field(
        ..., ge=0, description="Number of endpoints whose health was updated"
    )
    ignored: int = Field(
        ...,
        ge=0,
        description="Number of slugs that were not found or not accessible",
    )


# ===========================================
# ENDPOINT BENCHMARK CARD SCHEMAS
# ===========================================

# The card format this Hub reads. A card of any other version is refused rather
# than guessed at: a number understood wrongly is worse than a number not shown,
# because nobody can see that it was misread.
CARD_VERSION = 2

KIND_ANSWERING = "answering"
KIND_RETRIEVAL = "retrieval"


class CardAnswerable(BaseModel):
    """How it did on questions the corpus can answer."""

    samples: int = Field(..., ge=0)
    correct: float = Field(..., ge=0.0, le=1.0)
    abstain: float = Field(..., ge=0.0, le=1.0)
    hallucinate: float = Field(..., ge=0.0, le=1.0)
    lmi: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description=(
            "Of the times it chose to answer, the share that were wrong. The "
            "consumer's risk per answer, and it does not punish honest silence"
        ),
    )


class CardUnanswerable(BaseModel):
    """How it did on questions the corpus cannot answer.

    There is no right answer to these, so there is no accuracy: any reply at
    all is an invention. This is the half a consumer cannot check for himself
    and cannot recover from.
    """

    samples: int = Field(..., ge=0)
    fabricated: float = Field(..., ge=0.0, le=1.0)


class CardModel(BaseModel):
    """What one subject model got out of this endpoint's material.

    One row per model, never averaged: a mean over them would move when the
    benchmark changes its own list of models while nothing happened here.
    """

    model: str = Field(..., max_length=120)
    samples: int = Field(..., ge=0)
    accuracy: float = Field(..., ge=0.0, le=1.0)
    fabrication: Optional[float] = Field(None, ge=0.0, le=1.0)
    lmi: Optional[float] = Field(None, ge=0.0, le=1.0)
    context_gain: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description=(
            "What this endpoint's material did to the model's honesty. "
            "Positive means the context made it bolder, not better"
        ),
    )


class CardSkill(BaseModel):
    """How it does on one type of task."""

    generator: str = Field(..., max_length=64)
    samples: int = Field(..., ge=0)
    accuracy: float = Field(..., ge=0.0, le=1.0)


class CardTrust(BaseModel):
    """What the figures rest on.

    ``flags`` are codes, not sentences: the wording belongs to whoever renders
    them, in the reader's own language.
    """

    judges: int = Field(default=0, ge=0)
    agreement: Optional[float] = Field(None, ge=0.0, le=1.0)
    consistency: Optional[float] = Field(None, ge=0.0, le=1.0)
    even_coverage: bool = Field(default=True)
    failed: int = Field(default=0, ge=0)
    pending: int = Field(default=0, ge=0)
    flags: List[str] = Field(default_factory=list, max_length=16)


class CardDataset(BaseModel):
    """Which set of questions this was measured on.

    "71% over yesterday's documents" and "71% over the whole corpus" are
    different claims, and the difference is invisible in the share itself.
    """

    mode: str = Field(default="", max_length=32)
    window_days: int = Field(default=0, ge=0)
    cohort: str = Field(default="", max_length=64)
    questions: int = Field(default=0, ge=0)


class CardInstrument(BaseModel):
    """What did the measuring.

    Endpoints measured by one benchmark installation share a grader, a panel
    and a list of subject models, and so compare with each other. Between two
    installations nothing is guaranteed — and this marketplace puts both in the
    same list, so it has to be able to tell.
    """

    profile: str = Field(default="", max_length=64)
    judge: str = Field(default="", max_length=120)
    judges: int = Field(default=0, ge=0)
    subjects: int = Field(default=0, ge=0)


class EndpointQualityItem(BaseModel):
    """A benchmark card for one endpoint, reported by its owner."""

    slug: str = Field(
        ...,
        min_length=3,
        max_length=63,
        description="Endpoint slug this card is about",
    )
    version: int = Field(..., description="Card format version")
    kind: str = Field(..., description="'answering' or 'retrieval'")
    arm: str = Field(default="", max_length=32)
    checked_at: datetime = Field(..., description="When the benchmark ran")

    score: Optional[float] = Field(None, ge=0.0, le=1.0)
    fabrication_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    reliable: bool = Field(default=False)
    samples: int = Field(..., ge=0)

    answerable: Optional[CardAnswerable] = None
    unanswerable: Optional[CardUnanswerable] = None
    discrimination: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description=(
            "Refusals on unanswerable questions minus refusals on answerable "
            "ones. Says whether this endpoint's silence is a signal at all"
        ),
    )
    retrieval: Optional[float] = Field(None, ge=0.0, le=1.0)
    models: List[CardModel] = Field(default_factory=list, max_length=64)
    skills: List[CardSkill] = Field(default_factory=list, max_length=32)
    trust: Optional[CardTrust] = None
    dataset: Optional[CardDataset] = None
    instrument: Optional[CardInstrument] = None

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        """Refuse a card this Hub was not written to read."""
        if v != CARD_VERSION:
            raise ValueError(
                f"unsupported card version {v}; this hub reads {CARD_VERSION}"
            )
        return v

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        """Refuse a kind nothing can render.

        Without a kind the headline share is ambiguous, and a badge that reads
        "finds 82%" as "correct 82%" misrepresents the endpoint to everyone who
        sees it.
        """
        if v not in (KIND_ANSWERING, KIND_RETRIEVAL):
            raise ValueError(
                f"unknown kind '{v}'; expected '{KIND_ANSWERING}' or '{KIND_RETRIEVAL}'"
            )
        return v

    @model_validator(mode="after")
    def validate_no_prose(self) -> EndpointQualityItem:
        """Refuse anything that looks like text rather than an identifier.

        A benchmark builds its questions from a private corpus, and promises
        that nothing but shares, counts and identifiers leaves that perimeter.
        This is the last place that promise can be checked before the figures
        become a public document, and it is checked by form rather than by a
        list of forbidden words: every string here is one token, and a fragment
        of somebody's private corpus always has spaces in it.
        """
        for name in ("kind", "arm"):
            value = getattr(self, name)
            if value and " " in value:
                raise ValueError(f"{name} must be an identifier, not text")
        for row in self.models:
            if " " in row.model:
                raise ValueError("models[].model must be an identifier, not text")
        for skill in self.skills:
            if " " in skill.generator:
                raise ValueError("skills[].generator must be an identifier, not text")
        if self.trust:
            for flag in self.trust.flags:
                if " " in flag or len(flag) > 64:
                    raise ValueError("trust.flags must be codes, not sentences")
        if self.instrument:
            for name in ("profile", "judge"):
                value = getattr(self.instrument, name)
                if value and " " in value:
                    raise ValueError(
                        f"instrument.{name} must be an identifier, not text"
                    )
        if self.dataset and " " in self.dataset.cohort:
            raise ValueError("dataset.cohort must be an identifier, not text")
        return self


class EndpointQualityRequest(BaseModel):
    """Request schema for bulk benchmark-card reporting."""

    endpoints: List[EndpointQualityItem] = Field(
        ...,
        min_length=1,
        max_length=300,
        description="One card per endpoint",
    )


class EndpointQualityResponse(BaseModel):
    """Response schema for bulk benchmark-card reporting."""

    updated: int = Field(
        ..., ge=0, description="Number of endpoints whose card was stored"
    )
    ignored: int = Field(
        ...,
        ge=0,
        description="Number of slugs that were not found or not accessible",
    )


class EndpointQualityClearResponse(BaseModel):
    """Response schema for withdrawing a published benchmark card."""

    cleared: bool = Field(
        ...,
        description=(
            "Whether a card was removed; False means there was none, which is "
            "not an error"
        ),
    )


# ===========================================
# ENDPOINT UPTIME / TELEMETRY SCHEMAS
# ===========================================


class UptimeBucket(BaseModel):
    """One bucketed uptime data point for an endpoint."""

    bucket_start: datetime = Field(..., description="UTC start of the bucket interval")
    samples: int = Field(
        ..., ge=0, description="Number of health monitor cycles in this bucket"
    )
    healthy_samples: int = Field(
        ..., ge=0, description="Number of those cycles that observed a healthy state"
    )
    uptime_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of cycles in which the endpoint was healthy",
    )


class EndpointUptimeResponse(BaseModel):
    """Bucketed uptime series for a single endpoint."""

    endpoint_id: int = Field(..., description="Endpoint ID the series belongs to")
    owner_username: str = Field(..., description="Owner's username")
    slug: str = Field(..., description="Endpoint slug")
    bucket_seconds: int = Field(..., ge=1, description="Size of each bucket in seconds")
    window_hours: int = Field(
        ..., ge=1, description="Time window covered by the response in hours"
    )
    buckets: List[UptimeBucket] = Field(
        default_factory=list,
        description="Ordered list of buckets (oldest first)",
    )
