"""Retry policy: exponential backoff with full jitter on network errors and 5xx only."""

from __future__ import annotations

import random
from collections.abc import Iterator

from ..models.session import Retry

RETRYABLE_STATUSES: frozenset[int] = frozenset({500, 502, 503, 504})


def delays(retry: Retry) -> Iterator[float]:
    """One delay per retry after the first attempt: ``attempts - 1`` values."""
    for n in range(max(0, retry.attempts - 1)):
        cap = min(retry.max_backoff, retry.backoff * (2**n))
        yield random.uniform(0, cap)  # noqa: S311 - jitter, not security


def retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUSES
