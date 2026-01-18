"""Observability layer for SyftHub backend.

This module provides structured logging, request tracing via correlation IDs,
and error capture functionality for debugging and analysis.

Usage:
    from syfthub.observability import get_logger, get_correlation_id

    logger = get_logger(__name__)
    logger.info("user.login.success", user_id=user.id)

Note:
    Some items are not exported here to avoid circular imports:
    - register_exception_handlers: import from syfthub.observability.handlers
    - ErrorLogRepository: import from syfthub.observability.repository
    - ErrorLogModel: import from syfthub.observability.models
"""

from syfthub.observability.constants import CORRELATION_ID_HEADER
from syfthub.observability.context import (
    correlation_id_var,
    get_correlation_id,
    set_correlation_id,
)
from syfthub.observability.logger import configure_logging, get_logger
from syfthub.observability.middleware import (
    CorrelationIDMiddleware,
    RequestLoggingMiddleware,
)
from syfthub.observability.sanitizer import sanitize

__all__ = [
    "CORRELATION_ID_HEADER",
    "CorrelationIDMiddleware",
    "RequestLoggingMiddleware",
    "configure_logging",
    "correlation_id_var",
    "get_correlation_id",
    "get_logger",
    "sanitize",
    "set_correlation_id",
]
