"""Context management for observability.

Provides async-safe context variables for request tracing.
"""

from contextvars import ContextVar
from typing import Optional

# Context variable for correlation ID - async-safe across concurrent requests
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the current correlation ID.

    Returns:
        The correlation ID for the current request context, or empty string if not set.
    """
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current request context.

    Args:
        correlation_id: The correlation ID to set.
    """
    correlation_id_var.set(correlation_id)


def get_optional_correlation_id() -> Optional[str]:
    """Get the correlation ID if set, otherwise None.

    Returns:
        The correlation ID or None if not set.
    """
    cid = correlation_id_var.get()
    return cid if cid else None
