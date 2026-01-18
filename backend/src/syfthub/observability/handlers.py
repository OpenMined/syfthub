"""Global exception handlers for error capture and logging."""

import traceback
from typing import Any, Optional, cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from syfthub.database.connection import SessionLocal
from syfthub.observability.constants import (
    CORRELATION_ID_HEADER,
    SERVICE_NAME,
    LogEvents,
)
from syfthub.observability.context import get_correlation_id
from syfthub.observability.logger import get_logger
from syfthub.observability.repository import ErrorLogRepository
from syfthub.observability.sanitizer import sanitize, truncate_body

logger = get_logger(__name__)


def _get_user_id_from_request(request: Request) -> Optional[int]:
    """Extract user ID from request state if available.

    Args:
        request: The FastAPI request object.

    Returns:
        User ID if authenticated, None otherwise.
    """
    if hasattr(request.state, "user") and request.state.user:
        return getattr(request.state.user, "id", None)
    return None


def _get_request_body(request: Request) -> Optional[dict[str, Any]]:
    """Get request body if available.

    Args:
        request: The FastAPI request object.

    Returns:
        Request body as dict, or None.
    """
    if hasattr(request.state, "_body"):
        try:
            import json

            body = json.loads(request.state._body)
            return cast("dict[str, Any]", truncate_body(sanitize(body)))
        except Exception:
            pass
    return None


async def _persist_error(
    correlation_id: str,
    event: str,
    message: str,
    request: Request,
    error_type: Optional[str] = None,
    error_code: Optional[str] = None,
    stack_trace: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    level: str = "ERROR",
) -> None:
    """Persist error to database.

    Args:
        correlation_id: Request correlation ID.
        event: Error event name.
        message: Error message.
        request: FastAPI request object.
        error_type: Exception type name.
        error_code: Error code if available.
        stack_trace: Full stack trace.
        context: Additional context.
        level: Log level.
    """
    try:
        # Create a new session for error logging (don't use request's session)
        session = SessionLocal()
        try:
            repo = ErrorLogRepository(session)
            repo.create(
                correlation_id=correlation_id,
                service=SERVICE_NAME,
                level=level,
                event=event,
                message=message,
                user_id=_get_user_id_from_request(request),
                endpoint=str(request.url.path),
                method=request.method,
                error_type=error_type,
                error_code=error_code,
                stack_trace=stack_trace,
                context=context,
                request_data=_get_request_body(request),
            )
        finally:
            session.close()
    except Exception as e:
        # Don't let error logging failures break the response
        logger.warning("error_log.persist.failed", error=str(e))


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle HTTP exceptions with logging and correlation ID.

        Args:
            request: The incoming request.
            exc: The HTTP exception.

        Returns:
            JSON response with error details.
        """
        correlation_id = get_correlation_id()

        # Determine event based on status code
        if exc.status_code == 401:
            event = LogEvents.ERROR_UNAUTHORIZED
        elif exc.status_code == 403:
            event = LogEvents.ERROR_FORBIDDEN
        elif exc.status_code == 404:
            event = LogEvents.ERROR_NOT_FOUND
        elif exc.status_code >= 500:
            event = LogEvents.REQUEST_FAILED
        else:
            event = LogEvents.REQUEST_COMPLETED

        # Log the error
        log_method = logger.warning if exc.status_code < 500 else logger.error
        log_method(
            event,
            status_code=exc.status_code,
            detail=str(exc.detail),
            path=str(request.url.path),
            method=request.method,
        )

        # Persist 5xx errors to database
        if exc.status_code >= 500:
            await _persist_error(
                correlation_id=correlation_id,
                event=event,
                message=str(exc.detail),
                request=request,
                error_type="HTTPException",
                error_code=str(exc.status_code),
            )

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={CORRELATION_ID_HEADER: correlation_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle validation errors with logging.

        Args:
            request: The incoming request.
            exc: The validation error.

        Returns:
            JSON response with validation error details.
        """
        correlation_id = get_correlation_id()

        # Extract validation error details and make JSON-serializable
        # Remove 'ctx' field which may contain non-serializable objects (like ValueError)
        raw_errors = exc.errors()
        errors = []
        for err in raw_errors:
            clean_err = {k: v for k, v in err.items() if k != "ctx"}
            errors.append(clean_err)

        error_messages = [
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors
        ]

        logger.warning(
            LogEvents.ERROR_VALIDATION,
            path=str(request.url.path),
            method=request.method,
            errors=error_messages,
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": errors},
            headers={CORRELATION_ID_HEADER: correlation_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unhandled exceptions with full error capture.

        Args:
            request: The incoming request.
            exc: The unhandled exception.

        Returns:
            JSON response with generic error message (no details exposed).
        """
        correlation_id = get_correlation_id()
        stack_trace = traceback.format_exc()

        # Log the full error
        logger.error(
            LogEvents.ERROR_UNHANDLED,
            path=str(request.url.path),
            method=request.method,
            error_type=type(exc).__name__,
            error_message=str(exc),
            exc_info=True,
        )

        # Persist to database for analysis
        await _persist_error(
            correlation_id=correlation_id,
            event=LogEvents.ERROR_UNHANDLED,
            message=str(exc),
            request=request,
            error_type=type(exc).__name__,
            stack_trace=stack_trace,
            context={"args": [str(arg) for arg in exc.args]},
        )

        # Return generic error message (don't expose internal details)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal error occurred. Please try again later.",
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_ID_HEADER: correlation_id},
        )
