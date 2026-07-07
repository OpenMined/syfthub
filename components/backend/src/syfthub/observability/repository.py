"""Repository for error log persistence."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from syfthub.observability.logger import get_logger
from syfthub.observability.models import ErrorLogModel
from syfthub.observability.sanitizer import sanitize

logger = get_logger(__name__)


class ErrorLogRepository:
    """Repository for managing error log persistence."""

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy database session.
        """
        self.session = session

    def create(
        self,
        correlation_id: str,
        service: str,
        level: str,
        event: str,
        message: Optional[str] = None,
        user_id: Optional[int] = None,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        error_type: Optional[str] = None,
        error_code: Optional[str] = None,
        stack_trace: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        request_data: Optional[dict[str, Any]] = None,
        response_data: Optional[dict[str, Any]] = None,
    ) -> Optional[ErrorLogModel]:
        """Create a new error log entry.

        Args:
            correlation_id: Request correlation ID.
            service: Service name (backend, aggregator, etc.).
            level: Log level (ERROR, WARNING, etc.).
            event: Event name (e.g., "request.failed").
            message: Error message.
            user_id: User ID if authenticated.
            endpoint: Request endpoint path.
            method: HTTP method.
            error_type: Exception type name.
            error_code: Error code if available.
            stack_trace: Full stack trace.
            context: Additional context (sanitized).
            request_data: Request data (sanitized).
            response_data: Response data (sanitized).

        Returns:
            Created ErrorLogModel or None if failed.
        """
        try:
            # Sanitize sensitive data before storing
            sanitized_context = sanitize(context) if context else None
            sanitized_request = sanitize(request_data) if request_data else None
            sanitized_response = sanitize(response_data) if response_data else None

            error_log = ErrorLogModel(
                correlation_id=correlation_id,
                service=service,
                level=level,
                event=event,
                message=message,
                user_id=user_id,
                endpoint=endpoint,
                method=method,
                error_type=error_type,
                error_code=error_code,
                stack_trace=stack_trace,
                context=sanitized_context,
                request_data=sanitized_request,
                response_data=sanitized_response,
            )

            self.session.add(error_log)
            self.session.commit()
            self.session.refresh(error_log)

            return error_log

        except SQLAlchemyError as e:
            logger.warning(
                "error_log.create.failed",
                correlation_id=correlation_id,
                error=str(e),
            )
            self.session.rollback()
            return None

    def get_by_correlation_id(self, correlation_id: str) -> list[ErrorLogModel]:
        """Get all error logs for a correlation ID.

        Args:
            correlation_id: The correlation ID to search for.

        Returns:
            List of error logs matching the correlation ID.
        """
        try:
            query = (
                select(ErrorLogModel)
                .where(ErrorLogModel.correlation_id == correlation_id)
                .order_by(desc(ErrorLogModel.timestamp))
            )
            result = self.session.execute(query)
            return list(result.scalars().all())  # type: ignore[no-untyped-call]
        except SQLAlchemyError:
            return []

    def get_recent(
        self,
        limit: int = 100,
        service: Optional[str] = None,
        level: Optional[str] = None,
        event: Optional[str] = None,
        user_id: Optional[int] = None,
        hours: int = 24,
    ) -> list[ErrorLogModel]:
        """Get recent error logs with optional filtering.

        Args:
            limit: Maximum number of logs to return.
            service: Filter by service name.
            level: Filter by log level.
            event: Filter by event name.
            user_id: Filter by user ID.
            hours: Only return logs from the last N hours.

        Returns:
            List of error logs matching the filters.
        """
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)

            query = select(ErrorLogModel).where(
                ErrorLogModel.timestamp >= since  # type: ignore[operator]
            )

            if service:
                query = query.where(ErrorLogModel.service == service)
            if level:
                query = query.where(ErrorLogModel.level == level)
            if event:
                query = query.where(ErrorLogModel.event == event)
            if user_id:
                query = query.where(ErrorLogModel.user_id == user_id)

            query = query.order_by(desc(ErrorLogModel.timestamp)).limit(limit)

            result = self.session.execute(query)
            return list(result.scalars().all())  # type: ignore[no-untyped-call]
        except SQLAlchemyError:
            return []

    def delete_old_logs(self, retention_days: int = 30) -> int:
        """Delete error logs older than the retention period.

        Args:
            retention_days: Number of days to retain logs.

        Returns:
            Number of deleted logs.
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

            query = select(ErrorLogModel).where(
                ErrorLogModel.timestamp < cutoff  # type: ignore[operator]
            )
            result = self.session.execute(query)
            logs_to_delete = result.scalars().all()  # type: ignore[no-untyped-call]
            count = len(logs_to_delete)

            for log in logs_to_delete:
                self.session.delete(log)

            self.session.commit()

            logger.info(
                "error_log.cleanup.completed",
                deleted_count=count,
                retention_days=retention_days,
            )

            return count
        except SQLAlchemyError as e:
            logger.error("error_log.cleanup.failed", error=str(e))
            self.session.rollback()
            return 0

    def count_by_event(
        self,
        hours: int = 24,
        service: Optional[str] = None,
    ) -> dict[str, int]:
        """Count error logs grouped by event.

        Args:
            hours: Only count logs from the last N hours.
            service: Filter by service name.

        Returns:
            Dictionary mapping event names to counts.
        """
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)

            conditions = [ErrorLogModel.timestamp >= since]  # type: ignore[operator]
            if service:
                conditions.append(ErrorLogModel.service == service)

            query = select(ErrorLogModel).where(and_(*conditions))

            result = self.session.execute(query)
            logs = result.scalars().all()  # type: ignore[no-untyped-call]

            # Count by event
            counts: dict[str, int] = {}
            for log in logs:
                counts[log.event] = counts.get(log.event, 0) + 1

            return counts
        except SQLAlchemyError:
            return {}
