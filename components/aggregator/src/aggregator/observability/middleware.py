"""FastAPI middleware for observability.

Provides correlation ID injection and request/response logging.
"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from aggregator.observability.constants import (
    CORRELATION_ID_HEADER,
    LogEvents,
)
from aggregator.observability.context import set_correlation_id

logger = structlog.get_logger(__name__)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware to extract or generate correlation IDs for request tracing.

    The correlation ID is:
    1. Extracted from the X-Correlation-ID header if present
    2. Generated as a new UUID v4 if not present
    3. Stored in a ContextVar for async-safe access
    4. Added to structlog context for all log entries
    5. Returned in the response X-Correlation-ID header
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request and inject correlation ID.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware/handler in the chain.

        Returns:
            The response with correlation ID header.
        """
        # Extract or generate correlation ID
        correlation_id = request.headers.get(CORRELATION_ID_HEADER)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in context for async-safe access
        set_correlation_id(correlation_id)

        # Bind to structlog context for all subsequent log entries
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        # Process the request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request/response details.

    Logs request start, completion, and timing information
    with sanitized headers and request metadata.
    """

    def __init__(
        self,
        app: ASGIApp,
        log_request_body: bool = False,
        log_response_body: bool = False,
        exclude_paths: set[str] | None = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application.
            log_request_body: Whether to log request bodies (performance impact).
            log_response_body: Whether to log response bodies (on error only recommended).
            exclude_paths: Paths to exclude from logging (e.g., health checks).
        """
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.exclude_paths = exclude_paths or {"/health", "/ready", "/metrics"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request and log details.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware/handler in the chain.

        Returns:
            The response.
        """
        # Skip logging for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Record start time
        start_time = time.perf_counter()

        # Build request context
        request_context = {
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params) if request.query_params else None,
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
        }

        # Log request started
        logger.info(
            LogEvents.REQUEST_STARTED,
            **{k: v for k, v in request_context.items() if v is not None},
        )

        # Process the request
        try:
            response = await call_next(request)
        except Exception as exc:
            # Calculate duration even on error
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Log the unhandled error
            logger.error(
                LogEvents.REQUEST_FAILED,
                **request_context,
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        # Calculate request duration
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Build response context
        response_context = {
            **request_context,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }

        # Log based on status code
        if response.status_code >= 500:
            logger.error(LogEvents.REQUEST_FAILED, **response_context)
        elif response.status_code >= 400:
            logger.warning(LogEvents.REQUEST_COMPLETED, **response_context)
        else:
            logger.info(LogEvents.REQUEST_COMPLETED, **response_context)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, considering proxies.

        Args:
            request: The incoming HTTP request.

        Returns:
            The client IP address.
        """
        # Check X-Forwarded-For header (set by reverse proxies)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP (original client)
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header (nginx convention)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fallback to direct client
        if request.client:
            return request.client.host

        return "unknown"
