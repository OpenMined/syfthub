"""Private HTTP layer: httpx client, retry, circuit breaker, logging, user agent."""

from .circuit import Breakers, host_of
from .client import Transport, TransportError, detail_of, redact

__all__ = ["Breakers", "Transport", "TransportError", "detail_of", "host_of", "redact"]
