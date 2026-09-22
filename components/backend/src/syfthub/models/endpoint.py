"""Endpoint and EndpointStar database models."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
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
    from syfthub.models.collective import (
        CollectiveMemberModel,
        CollectiveSharedEndpointMemberModel,
    )
    from syfthub.models.satellite import SatelliteModel
    from syfthub.models.user import UserModel


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

    # Owner field - every endpoint is owned by exactly one user
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )

    # The space serving this endpoint. NULL means no satellite is known yet —
    # a pre-satellite row, or a publish by an account that has not registered
    # one. There is then no origin to build a URL from, so the sweeper skips it.
    space_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("satellites.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
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
    # NULL means no client-reported status; the health monitor treats it as unhealthy
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
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="endpoints")
    collective_memberships: Mapped[List["CollectiveMemberModel"]] = relationship(
        "CollectiveMemberModel",
        back_populates="endpoint",
        cascade="all, delete-orphan",
    )
    space: Mapped[Optional["SatelliteModel"]] = relationship(
        "SatelliteModel", back_populates="endpoints"
    )

    # The benchmark card the owner reports via POST /endpoints/quality, kept
    # in endpoint_benchmark_cards. One card or none: an endpoint nobody has
    # benchmarked has no row there at all, which is what lets the card's own
    # fields be NOT NULL instead of seven nullable columns on this table.
    #
    # Joined rather than lazy: almost every read of an endpoint is on its way
    # to a listing or a detail page that paints the badge, so a lazy load would
    # cost one extra query per endpoint on every catalogue page we serve.
    benchmark_card: Mapped[Optional["EndpointBenchmarkCardModel"]] = relationship(
        "EndpointBenchmarkCardModel",
        back_populates="endpoint",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )

    shared_endpoint_memberships: Mapped[List["CollectiveSharedEndpointMemberModel"]] = (
        relationship(
            "CollectiveSharedEndpointMemberModel",
            back_populates="endpoint",
            cascade="all, delete-orphan",
        )
    )

    # Indexes for performance - slug uniqueness is per-user
    __table_args__ = (
        Index("idx_endpoints_user_id", "user_id"),
        Index("idx_endpoints_space_id", "space_id"),
        Index("idx_endpoints_slug", "slug"),
        # Unique slug per user
        Index("idx_endpoints_user_slug", "user_id", "slug", unique=True),
        Index("idx_endpoints_type", "type"),
        Index("idx_endpoints_visibility", "visibility"),
        Index("idx_endpoints_is_active", "is_active"),
        Index("idx_endpoints_archived", "archived"),
        Index("idx_endpoints_version", "version"),
        Index("idx_endpoints_stars_count", "stars_count"),
        Index("idx_endpoints_rag_file_id", "rag_file_id"),
    )

    # --- The card, flattened.
    #
    # The card is stored in its own table, but the API has always described it
    # as flat ``quality_*`` fields of the endpoint, and the response schemas
    # validate straight off these attributes. Reading through the relationship
    # here keeps a storage decision out of the wire format. Read-only on
    # purpose: a card is written whole, through the repository, never a figure
    # at a time.
    @property
    def quality_kind(self) -> Optional[str]:
        """Which claim the score makes: 'answering' or 'retrieval'."""
        return self.benchmark_card.kind if self.benchmark_card else None

    @property
    def quality_score(self) -> Optional[float]:
        """The headline share, meaningless without quality_kind."""
        return self.benchmark_card.score if self.benchmark_card else None

    @property
    def quality_fabrication_rate(self) -> Optional[float]:
        """Share of answers the benchmark judged invented."""
        return self.benchmark_card.fabrication_rate if self.benchmark_card else None

    @property
    def quality_samples(self) -> Optional[int]:
        """How many questions the run asked."""
        return self.benchmark_card.samples if self.benchmark_card else None

    @property
    def quality_reliable(self) -> Optional[bool]:
        """Whether the benchmark vouches for its own figures."""
        return self.benchmark_card.reliable if self.benchmark_card else None

    @property
    def quality_checked_at(self) -> Optional[datetime]:
        """When the run happened; the card has no TTL, so readers judge its age."""
        return self.benchmark_card.checked_at if self.benchmark_card else None

    @property
    def quality_report(self) -> Optional[dict]:
        """The whole card, for the detail page."""
        return self.benchmark_card.report if self.benchmark_card else None

    def __repr__(self) -> str:
        """String representation of Endpoint."""
        return f"<Endpoint(id={self.id}, slug='{self.slug}', user={self.user_id})>"


class EndpointBenchmarkCardModel(Base, TimestampMixin):
    """The benchmark card an endpoint's owner publishes for it.

    Health says the endpoint answers; this says whether what comes back is any
    good. The figures come from a benchmark the owner runs against his own
    endpoint and pushes through his Space; the Hub never measures anything
    itself.

    One row per endpoint, keyed by the endpoint itself. The row *is* the card:
    an endpoint nobody has measured has no row, so the UI can say "not
    measured" rather than show a zero — "no data" and "bad" are different
    claims, and only one of them is the endpoint's fault. That is also why
    everything that makes a card a card is NOT NULL here; on the endpoints
    table each of these had to be nullable, and a score with no ``kind`` to
    read it by was a shape the schema had to allow.

    Two shapes in one row on purpose: the scalar columns are what a list of
    endpoints paints a badge from without opening a document per row, and
    ``report`` is the whole card the detail page reads. A card gaining a
    section changes the document, not the schema.
    """

    __tablename__ = "endpoint_benchmark_cards"

    endpoint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Without this the headline share is ambiguous, and a badge that reads
    # "finds 82%" as "correct 82%" misrepresents the endpoint to everyone who
    # sees it. Hence NOT NULL: there is no card without the claim it makes.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)

    # Nullable, alone among the figures. A retrieval card has no fabrication
    # rate to report, and a run cut short may vouch for nothing at all — a card
    # with a hole in it, which is still a card.
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fabrication_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    samples: Mapped[int] = mapped_column(Integer, nullable=False)

    # A gate, not a grade: the benchmark declaring whether it stands behind its
    # own numbers. A share nobody vouches for is worse than no share at all,
    # because absence is visible to a reader and a bare number is not.
    reliable: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # No TTL, unlike health. A benchmark run is deliberate and expensive, not a
    # heartbeat: the card stands until replaced or retracted, and readers judge
    # its age from here.
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    report: Mapped[dict] = mapped_column(JSONType, nullable=False)

    endpoint: Mapped["EndpointModel"] = relationship(
        "EndpointModel", back_populates="benchmark_card"
    )

    __table_args__ = (Index("idx_endpoint_benchmark_cards_score", "score"),)

    def __repr__(self) -> str:
        """String representation of EndpointBenchmarkCard."""
        return (
            f"<EndpointBenchmarkCard(endpoint_id={self.endpoint_id}, "
            f"kind='{self.kind}', score={self.score}, "
            f"reliable={self.reliable})>"
        )


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
    1800s = 30 min, matching ``health_max_ttl_seconds``).
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
