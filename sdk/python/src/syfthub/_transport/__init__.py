"""Private HTTP layer: httpx client, retry, circuit breaker, logging, user agent."""

from .circuit import Breakers, host_of
from .client import ErrorDetail, Transport, TransportError, detail_of, redact

__all__ = [
    "Breakers",
    "ErrorDetail",
    "Transport",
    "TransportError",
    "detail_of",
    "host_of",
    "redact",
]
