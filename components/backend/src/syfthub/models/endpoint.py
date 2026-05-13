"""Endpoint and EndpointStar database models."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import Base, BaseModel, TimestampMixin

# Use JSONB for PostgreSQL, JSON for other databases (e.g., SQLite in tests)
JSONType = JSON().with_variant(JSONB(), "postgresql")  # type: ignore[no-untyped-call]

if TYPE_CHECKING:
    from syfthub.models.organization import OrganizationModel
    from syfthub.models.user import UserModel


# Policy types that mark an endpoint as requiring payment for invocation.
# Includes "transaction" (on-chain MPP-over-NATS, emitted by the Go SDK) and
# "xendit" (existing prepaid wallet flow). Compared case-insensitively.
PAYMENT_POLICY_TYPES = frozenset({"transaction", "xendit"})


def policies_require_payment(policies: object) -> bool:
    """Return True iff any policy entry has a payment-bearing type."""
    if not policies:
        return False
    if not isinstance(policies, list):
        return False
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        policy_type = policy.get("type")
        if isinstance(policy_type, str) and policy_type.lower() in PAYMENT_POLICY_TYPES:
            return True
    return False


class EndpointModel(BaseModel, TimestampMixin):
    """Endpoint database model."""

    __tablename__ = "endpoints"

    # Override updated_at from TimestampMixin without onupdate hook.
    # Endpoints should only update this timestamp for user-initiated changes,
    # not for health check status updates (which would cause endpoints to
    # dominate listings due to frequent automated checks).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Owner fields (exactly one of user_id or organization_id must be set)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    organization_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=True
    )

    # Endpoint fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="public"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Health check failure tracking - used by health monitor to track consecutive failures
    # before marking endpoint as inactive (multi-worker safe, persisted in DB)
    consecutive_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Per-endpoint health status reported by client (via POST /endpoints/health)
    # NULL means no client-reported status; fallback to existing heartbeat-based health
    health_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default=None
    )
    health_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    health_ttl_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )

    version: Mapped[str] = mapped_column(String(20), nullable=False, default="0.1.0")
    readme: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stars_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags: Mapped[List[str]] = mapped_column(
        JSONType, nullable=False, default=lambda: []
    )

    # JSON fields for complex data
    contributors: Mapped[List[int]] = mapped_column(
        JSONType, nullable=False, default=lambda: []
    )
    policies: Mapped[List[dict]] = mapped_column(
        JSONType, nullable=False, default=lambda: []
    )
    connect: Mapped[List[dict]] = mapped_column(
        JSONType, nullable=False, default=lambda: []
    )

    # RAG integration - vector store file ID
    rag_file_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )

    # Relationships
    user: Mapped[Optional["UserModel"]] = relationship(
        "UserModel", back_populates="endpoints"
    )
    organization: Mapped[Optional["OrganizationModel"]] = relationship(
        "OrganizationModel", back_populates="endpoints"
    )

    # Indexes for performance - slug uniqueness is per-owner (user or organization)
    __table_args__ = (
        # Ensure exactly one owner (user_id XOR organization_id)
        CheckConstraint(
            "(user_id IS NULL) != (organization_id IS NULL)",
            name="ck_endpoints_single_owner",
        ),
        Index("idx_endpoints_user_id", "user_id"),
        Index("idx_endpoints_organization_id", "organization_id"),
        Index("idx_endpoints_slug", "slug"),
        # Unique slug per user (nulls ignored in unique constraints)
        Index("idx_endpoints_user_slug", "user_id", "slug", unique=True),
        # Unique slug per organization (nulls ignored in unique constraints)
        Index("idx_endpoints_org_slug", "organization_id", "slug", unique=True),
        Index("idx_endpoints_type", "type"),
        Index("idx_endpoints_visibility", "visibility"),
        Index("idx_endpoints_is_active", "is_active"),
        Index("idx_endpoints_archived", "archived"),
        Index("idx_endpoints_version", "version"),
        Index("idx_endpoints_stars_count", "stars_count"),
        Index("idx_endpoints_rag_file_id", "rag_file_id"),
    )

    @property
    def payment_required(self) -> bool:
        """True iff any registered policy requires payment.

        UI surfaces this flag to render paid-endpoint badges without
        inspecting the full policy list. See ``PAYMENT_POLICY_TYPES`` for
        the set of policy types that flip this on.
        """
        return policies_require_payment(self.policies)

    def __repr__(self) -> str:
        """String representation of Endpoint."""
        owner = (
            f"user={self.user_id}" if self.user_id else f"org={self.organization_id}"
        )
        return f"<Endpoint(id={self.id}, slug='{self.slug}', {owner})>"


class EndpointStarModel(BaseModel):
    """Endpoint star relationship model for tracking user stars."""

    __tablename__ = "endpoint_stars"

    # Star relationship fields
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    endpoint_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False
    )
    starred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Indexes for performance and uniqueness
    __table_args__ = (
        Index("idx_endpoint_stars_user_id", "user_id"),
        Index("idx_endpoint_stars_endpoint_id", "endpoint_id"),
        Index(
            "idx_endpoint_stars_unique", "user_id", "endpoint_id", unique=True
        ),  # Prevent duplicate stars
        Index("idx_endpoint_stars_starred_at", "starred_at"),
    )

    def __repr__(self) -> str:
        """String representation of EndpointStar."""
        return f"<EndpointStar(id={self.id}, user_id={self.user_id}, endpoint_id={self.endpoint_id})>"


class EndpointUptimeSampleModel(Base):
    """Bucketed uptime + latency aggregates for an endpoint.

    One row per (endpoint_id, bucket_start). The health monitor upserts a row
    every cycle (default every 30s), accumulating totals so the bucket can be
    rendered as a single uptime + latency data point.

    Bucket size is controlled by ``settings.uptime_bucket_seconds`` (default
    1800s = 30 min, matching ``heartbeat_max_ttl_seconds``).
    """

    __tablename__ = "endpoint_uptime_samples"

    endpoint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    bucket_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    total_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    healthy_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        PrimaryKeyConstraint("endpoint_id", "bucket_start"),
        Index(
            "idx_endpoint_uptime_endpoint_bucket",
            "endpoint_id",
            "bucket_start",
        ),
        Index("idx_endpoint_uptime_bucket_start", "bucket_start"),
    )

    def __repr__(self) -> str:
        return (
            f"<EndpointUptimeSample(endpoint_id={self.endpoint_id}, "
            f"bucket_start={self.bucket_start}, "
            f"healthy={self.healthy_checks}/{self.total_checks})>"
        )
