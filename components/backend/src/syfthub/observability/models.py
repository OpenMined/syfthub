"""Error log models for persistence."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column  # type: ignore[attr-defined]

from syfthub.models.base import Base

# Use JSONB for PostgreSQL, JSON for other databases (e.g., SQLite in tests)
JSONType = JSON().with_variant(JSONB(), "postgresql")  # type: ignore[no-untyped-call]


class ErrorLogModel(Base):
    """SQLAlchemy model for error logs.

    Stores errors with full context for debugging and analysis.
    Includes correlation ID for request tracing across services.
    """

    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Correlation and timing
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Service identification
    service: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    event: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Error message
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # User context (optional - may not be logged in)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Request context
    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Error details
    error_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Additional context (JSONB for PostgreSQL, JSON for SQLite)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    request_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONType, nullable=True
    )
    response_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONType, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("idx_error_logs_timestamp", timestamp.desc()),
        Index("idx_error_logs_correlation_event", correlation_id, event),
    )

    def __repr__(self) -> str:
        return (
            f"<ErrorLog(id={self.id}, correlation_id={self.correlation_id}, "
            f"event={self.event}, level={self.level})>"
        )
