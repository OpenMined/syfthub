"""Sensitive data sanitization for logging.

Recursively redacts sensitive fields from data structures before logging.
"""

from typing import Any

from aggregator.observability.constants import (
    REDACTED_VALUE,
    SENSITIVE_FIELD_PATTERNS,
    SENSITIVE_FIELDS,
)


def _is_sensitive_field(field_name: str) -> bool:
    """Check if a field name indicates sensitive data.

    Args:
        field_name: The field name to check.

    Returns:
        True if the field should be redacted.
    """
    field_lower = field_name.lower()

    # Check exact matches first (faster)
    if field_lower in SENSITIVE_FIELDS:
        return True

    # Check pattern matches
    return any(pattern in field_lower for pattern in SENSITIVE_FIELD_PATTERNS)


def sanitize(data: Any, max_depth: int = 10) -> Any:
    """Recursively sanitize sensitive data from a structure.

    Args:
        data: The data to sanitize (dict, list, or scalar).
        max_depth: Maximum recursion depth to prevent infinite loops.

    Returns:
        Sanitized copy of the data with sensitive fields redacted.
    """
    if max_depth <= 0:
        return REDACTED_VALUE

    if isinstance(data, dict):
        return {
            k: REDACTED_VALUE if _is_sensitive_field(k) else sanitize(v, max_depth - 1)
            for k, v in data.items()
        }

    if isinstance(data, list):
        return [sanitize(item, max_depth - 1) for item in data]

    if isinstance(data, tuple):
        return tuple(sanitize(item, max_depth - 1) for item in data)

    if isinstance(data, set):
        return {sanitize(item, max_depth - 1) for item in data}

    # Scalars (str, int, float, bool, None) are returned as-is
    return data


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Sanitize HTTP headers, redacting sensitive ones.

    Args:
        headers: Dictionary of HTTP headers.

    Returns:
        Sanitized copy with sensitive headers redacted.
    """
    sensitive_headers = {"authorization", "cookie", "x-api-key", "x-auth-token"}

    return {k: REDACTED_VALUE if k.lower() in sensitive_headers else v for k, v in headers.items()}


def truncate_body(body: Any, max_length: int = 1000) -> Any:
    """Truncate request/response body for logging.

    Args:
        body: The body content to truncate.
        max_length: Maximum length for string values.

    Returns:
        Truncated copy of the body.
    """
    if isinstance(body, str) and len(body) > max_length:
        return body[:max_length] + f"... [truncated, {len(body)} total bytes]"

    if isinstance(body, bytes) and len(body) > max_length:
        return f"[binary data, {len(body)} bytes]"

    if isinstance(body, dict):
        return {k: truncate_body(v, max_length) for k, v in body.items()}

    if isinstance(body, list):
        if len(body) > 100:
            return [truncate_body(item, max_length) for item in body[:100]] + [
                f"... [{len(body) - 100} more items]"
            ]
        return [truncate_body(item, max_length) for item in body]

    return body
