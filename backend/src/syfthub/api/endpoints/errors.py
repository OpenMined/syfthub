"""Error reporting endpoint for frontend errors."""

from datetime import datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from syfthub.auth.db_dependencies import get_optional_current_user
from syfthub.database.connection import get_db_session
from syfthub.observability import get_logger
from syfthub.observability.context import get_correlation_id
from syfthub.observability.repository import ErrorLogRepository
from syfthub.schemas.user import User

router = APIRouter()
logger = get_logger(__name__)


class ErrorDetail(BaseModel):
    """Error details from frontend."""

    type: str = Field(..., description="Error type name (e.g., TypeError)")
    message: Optional[str] = Field(None, description="Error message")
    stack_trace: Optional[str] = Field(None, description="JavaScript stack trace")
    component_stack: Optional[str] = Field(
        None, description="React component stack trace"
    )


class ErrorContext(BaseModel):
    """Context information about where the error occurred."""

    url: Optional[str] = Field(None, description="Current page URL")
    user_agent: Optional[str] = Field(None, description="Browser user agent")
    app_state: Optional[dict[str, Any]] = Field(
        None, description="Relevant app state at time of error"
    )


class FrontendErrorReport(BaseModel):
    """Frontend error report schema."""

    correlation_id: Optional[str] = Field(None, description="Correlation ID if known")
    timestamp: Optional[datetime] = Field(
        None, description="When the error occurred (ISO8601)"
    )
    event: str = Field(
        default="frontend.error.unhandled",
        description="Event name (e.g., frontend.error.unhandled)",
    )
    message: str = Field(..., description="Human-readable error description")
    error: ErrorDetail = Field(..., description="Error details")
    context: Optional[ErrorContext] = Field(None, description="Error context")


class ErrorReportResponse(BaseModel):
    """Response after accepting an error report."""

    received: bool = True
    correlation_id: str = Field(..., description="Correlation ID for tracking")


@router.post(
    "/errors/report",
    response_model=ErrorReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Report frontend error",
    description="""
    Accept error reports from the frontend application.

    This endpoint allows the frontend to report JavaScript errors, React component
    errors, and other client-side issues for centralized logging and analysis.

    Authentication is optional - anonymous errors can be reported.
    """,
)
async def report_frontend_error(
    error_report: FrontendErrorReport,
    session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
) -> ErrorReportResponse:
    """Report a frontend error for logging and analysis.

    Args:
        error_report: The error report from the frontend.
        session: Database session.
        current_user: Current user if authenticated.

    Returns:
        Confirmation with correlation ID.
    """
    # Use provided correlation ID or generate from current context
    correlation_id = error_report.correlation_id or get_correlation_id()

    # Log the frontend error
    logger.warning(
        error_report.event,
        error_type=error_report.error.type,
        error_message=error_report.error.message,
        url=error_report.context.url if error_report.context else None,
        user_id=current_user.id if current_user else None,
    )

    # Persist to database
    try:
        repo = ErrorLogRepository(session)
        repo.create(
            correlation_id=correlation_id,
            service="frontend",
            level="ERROR",
            event=error_report.event,
            message=error_report.message,
            user_id=current_user.id if current_user else None,
            endpoint=error_report.context.url if error_report.context else None,
            method="CLIENT",
            error_type=error_report.error.type,
            stack_trace=error_report.error.stack_trace,
            context={
                "component_stack": error_report.error.component_stack,
                "user_agent": (
                    error_report.context.user_agent if error_report.context else None
                ),
                "app_state": (
                    error_report.context.app_state if error_report.context else None
                ),
                "client_timestamp": (
                    error_report.timestamp.isoformat()
                    if error_report.timestamp
                    else None
                ),
            },
        )
    except Exception as e:
        logger.warning("frontend_error.persist.failed", error=str(e))

    return ErrorReportResponse(correlation_id=correlation_id)
