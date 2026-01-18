"""Structured logging configuration using structlog.

Provides JSON-formatted logs with correlation ID and context.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.typing import EventDict, Processor

from aggregator.observability.constants import SERVICE_NAME
from aggregator.observability.context import get_correlation_id


def add_correlation_id(
    logger: logging.Logger,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: EventDict,
) -> EventDict:
    """Structlog processor to add correlation ID to log entries.

    Args:
        logger: The logger instance (unused but required by structlog).
        method_name: The log method name (unused but required by structlog).
        event_dict: The event dictionary being processed.

    Returns:
        The event dictionary with correlation_id added.
    """
    correlation_id = get_correlation_id()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def add_service_name(
    logger: logging.Logger,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: EventDict,
) -> EventDict:
    """Structlog processor to add service name to log entries.

    Args:
        logger: The logger instance (unused but required by structlog).
        method_name: The log method name (unused but required by structlog).
        event_dict: The event dictionary being processed.

    Returns:
        The event dictionary with service name added.
    """
    event_dict["service"] = SERVICE_NAME
    return event_dict


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    development_mode: bool = False,
) -> None:
    """Configure structlog for the application.

    Args:
        log_level: The log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: Output format - "json" for production, "console" for development.
        development_mode: If True, uses colored console output.
    """
    # Common processors for all configurations
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_service_name,
        add_correlation_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "console" or development_mode:
        # Development-friendly console output with colors
        processors: list[Processor] = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Production JSON output
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure the root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
        force=True,
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: The logger name (typically __name__).

    Returns:
        A bound structlog logger.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("chat.retrieval.started", endpoint_id="123")
    """
    return structlog.get_logger(name)


def log_with_context(
    logger: structlog.stdlib.BoundLogger,
    level: str,
    event: str,
    **context: Any,
) -> None:
    """Log with additional context.

    Args:
        logger: The logger instance.
        level: Log level (debug, info, warning, error, critical).
        event: The event name (e.g., "chat.retrieval.started").
        **context: Additional context to include in the log.
    """
    log_method = getattr(logger, level.lower())
    log_method(event, **context)
