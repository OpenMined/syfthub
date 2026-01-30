"""Fire-and-forget error reporter that persists errors via the backend API.

Reports upstream errors (from SyftAI-Space peers) to the backend's
/api/v1/errors/service-report endpoint for centralized persistence
in the error_logs PostgreSQL table.
"""

import asyncio
from typing import Any

import httpx

from aggregator.observability import get_correlation_id, get_logger, sanitize
from aggregator.observability.constants import SERVICE_NAME

logger = get_logger(__name__)


class ErrorReporter:
    """Async HTTP client that reports errors to the backend for DB persistence.

    All reporting is fire-and-forget via asyncio.create_task() so it never
    blocks the main request flow. Failures in reporting are logged but
    silently swallowed.
    """

    def __init__(self, backend_url: str, timeout: float = 5.0):
        self.report_url = f"{backend_url.rstrip('/')}/api/v1/errors/service-report"
        self.timeout = httpx.Timeout(timeout)

    def report(
        self,
        *,
        event: str,
        message: str,
        level: str = "ERROR",
        endpoint: str | None = None,
        method: str | None = None,
        error_type: str | None = None,
        error_code: str | None = None,
        stack_trace: str | None = None,
        context: dict[str, Any] | None = None,
        request_data: dict[str, Any] | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """Schedule an error report to be sent asynchronously.

        This method returns immediately. The actual HTTP call happens
        in a background task so it never blocks the caller.
        """
        correlation_id = get_correlation_id()

        payload: dict[str, Any] = {
            "correlation_id": correlation_id or None,
            "service": SERVICE_NAME,
            "level": level,
            "event": event,
            "message": message,
        }

        if endpoint:
            payload["endpoint"] = endpoint
        if method:
            payload["method"] = method
        if error_type:
            payload["error_type"] = error_type
        if error_code:
            payload["error_code"] = error_code
        if stack_trace:
            payload["stack_trace"] = stack_trace
        if context:
            payload["context"] = sanitize(context)
        if request_data:
            payload["request_data"] = sanitize(request_data)
        if response_data:
            payload["response_data"] = sanitize(response_data)

        try:
            asyncio.get_running_loop().create_task(self._send(payload))
        except RuntimeError:
            # No running event loop (e.g. during testing); log and skip
            logger.debug("error_reporter.no_event_loop", event=event)

    async def _send(self, payload: dict[str, Any]) -> None:
        """Send the error report to the backend. Swallows all exceptions."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.report_url, json=payload)
                if response.status_code != 202:
                    logger.debug(
                        "error_reporter.unexpected_status",
                        status_code=response.status_code,
                    )
        except Exception as exc:
            # Never let error reporting break the application
            logger.debug("error_reporter.send_failed", error=str(exc))
