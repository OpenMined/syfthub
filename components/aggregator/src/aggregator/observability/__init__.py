"""Observability layer for SyftHub aggregator.

This module provides structured logging, request tracing via correlation IDs,
and error capture functionality for debugging and analysis.

Usage:
    from aggregator.observability import get_logger, get_correlation_id

    logger = get_logger(__name__)
    logger.info("chat.request.started", session_id=session_id)
"""

from aggregator.observability.context import (
    correlation_id_var,
    get_correlation_id,
    set_correlation_id,
)
from aggregator.observability.logger import configure_logging, get_logger
from aggregator.observability.middleware import (
    CorrelationIDMiddleware,
    RequestLoggingMiddleware,
)
from aggregator.observability.sanitizer import sanitize

__all__ = [
    # Context
    "correlation_id_var",
    "get_correlation_id",
    "set_correlation_id",
    # Logger
    "configure_logging",
    "get_logger",
    # Middleware
    "CorrelationIDMiddleware",
    "RequestLoggingMiddleware",
    # Sanitizer
    "sanitize",
]
