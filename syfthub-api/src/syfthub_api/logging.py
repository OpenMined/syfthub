"""
Logging configuration for the SyftHub API framework.

This module provides logging utilities for consistent log output
across the SyftAPI framework.

Example:
    from syfthub_api.logging import setup_logging, get_logger

    # Setup logging for the application
    setup_logging(level="INFO")

    # Get a logger for a specific module
    logger = get_logger(__name__)
    logger.info("Starting application")
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

# Package-level logger name
LOGGER_NAME = "syfthub_api"

# Default format
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    format_string: str | None = None,
    date_format: str | None = None,
    stream: TextIO | None = None,
) -> logging.Logger:
    """
    Configure logging for the SyftHub API framework.

    This function sets up the root logger for the syfthub_api package
    with the specified configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            Defaults to INFO.
        format_string: Custom format string for log messages.
            Defaults to "%(asctime)s - %(name)s - %(levelname)s - %(message)s".
        date_format: Custom date format for timestamps.
            Defaults to "%Y-%m-%d %H:%M:%S".
        stream: Output stream for log messages. Defaults to sys.stdout.

    Returns:
        Configured logger instance for the syfthub_api package.

    Example:
        # Basic setup
        logger = setup_logging()
        logger.info("Application started")

        # Debug logging
        logger = setup_logging(level="DEBUG")

        # Custom format
        logger = setup_logging(
            level="INFO",
            format_string="%(levelname)s: %(message)s"
        )
    """
    # Get or create the package logger
    logger = logging.getLogger(LOGGER_NAME)

    # Clear existing handlers to avoid duplicates on re-configuration
    logger.handlers.clear()

    # Set the log level
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Create stream handler
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter(
        fmt=format_string or DEFAULT_FORMAT,
        datefmt=date_format or DEFAULT_DATE_FORMAT,
    )
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger instance for the SyftHub API framework.

    If a name is provided, returns a child logger under the syfthub_api
    namespace. Otherwise, returns the root syfthub_api logger.

    Args:
        name: Optional name for the child logger. If provided, the logger
            will be named "syfthub_api.{name}".

    Returns:
        Logger instance.

    Example:
        # Get the root package logger
        logger = get_logger()

        # Get a module-specific logger
        logger = get_logger("app")  # Returns "syfthub_api.app" logger

        # Get logger for current module
        logger = get_logger(__name__)
    """
    if name is None:
        return logging.getLogger(LOGGER_NAME)

    # If the name already starts with the package name, use it directly
    if name.startswith(LOGGER_NAME):
        return logging.getLogger(name)

    # Otherwise, create a child logger
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
