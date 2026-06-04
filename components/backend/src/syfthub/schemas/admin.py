"""Admin dashboard schemas.

Response models for the admin user-overview dashboard. See the pinned API
contract in the implementation plan; these schemas are the authoritative
serialization shapes for ``GET /api/v1/admin/overview`` and
``GET /api/v1/admin/users``.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Imported at runtime: Pydantic resolves these enum field types when building
# the models below, so they cannot live in a type-checking-only block.
from syfthub.schemas.auth import AuthProvider, UserRole  # noqa: TC001


class HeadlineCounts(BaseModel):
    """Top-level headline counts for the overview dashboard."""

    total_users: int = Field(..., description="Total number of users")
    active_users: int = Field(..., description="Number of active users")
    inactive_users: int = Field(..., description="Number of inactive users")
    email_verified: int = Field(..., description="Number of email-verified users")
    email_unverified: int = Field(..., description="Number of email-unverified users")
    admins: int = Field(..., description="Number of admin users")


class RoleCount(BaseModel):
    """Count of users for a single role."""

    role: UserRole = Field(..., description="User role")
    count: int = Field(..., description="Number of users with this role")


class AuthProviderCount(BaseModel):
    """Count of users for a single auth provider."""

    provider: AuthProvider = Field(..., description="Authentication provider")
    count: int = Field(..., description="Number of users with this provider")


class SignupBucket(BaseModel):
    """A single daily signup bucket."""

    date: date_type = Field(..., description="Calendar date (UTC) of the bucket")
    signups: int = Field(..., description="Number of signups on this date")


class SignupTrend(BaseModel):
    """Daily signup trend over a rolling window."""

    days: int = Field(..., description="Number of daily buckets (echoes trend_days)")
    buckets: list[SignupBucket] = Field(
        ..., description="Ascending, gap-filled daily buckets"
    )


class LastLoginBucket(BaseModel):
    """A single last-login recency bucket."""

    bucket: str = Field(..., description="Bucket key (24h, 7d, 30d, 90d, never)")
    label: str = Field(..., description="Human-readable bucket label")
    count: int = Field(..., description="Number of users in this bucket")


class LastLoginStats(BaseModel):
    """Last-login recency distribution and derived convenience counts."""

    buckets: list[LastLoginBucket] = Field(
        ..., description="Mutually-exclusive recency buckets summing to total_users"
    )
    active_24h: int = Field(
        ..., description="Users active in the last 24 hours (duplicate of 24h bucket)"
    )
    dormant_30d: int = Field(
        ...,
        description="Users with null last_login_at OR older than 30 days",
    )


class UserOverviewStats(BaseModel):
    """Aggregated overview statistics for the admin dashboard."""

    headline: HeadlineCounts
    by_role: list[RoleCount]
    by_auth_provider: list[AuthProviderCount]
    signup_trend: SignupTrend
    last_login: LastLoginStats


class AdminUserRow(BaseModel):
    """A single row in the admin users table."""

    id: int = Field(..., description="User's unique identifier")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="User's email address")
    full_name: str = Field(..., description="User's full name")
    avatar_url: Optional[str] = Field(None, description="URL to user's avatar image")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether the user is active")
    is_email_verified: bool = Field(
        ..., description="Whether the user has verified their email"
    )
    auth_provider: AuthProvider = Field(..., description="Authentication provider")
    created_at: datetime = Field(..., description="When the user was created")
    last_login_at: Optional[datetime] = Field(
        None, description="Timestamp of the user's last successful login"
    )

    model_config = {"from_attributes": True}


class AdminUserPage(BaseModel):
    """A paginated page of admin user rows."""

    items: list[AdminUserRow] = Field(..., description="User rows for this page")
    page: int = Field(..., description="Current page number (1-based)")
    page_size: int = Field(..., description="Number of items per page")
    total: int = Field(..., description="Total users matching the filters")
    total_pages: int = Field(..., description="Total number of pages")
