"""Session objects: ``Identity``, ``Budget`` and the client ``Options``."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from .base import Frozen
from .enums import AuthMethod
from .money import Money


class Identity(Frozen):
    username: str
    email: str = ""
    auth: AuthMethod = AuthMethod.TOKEN


class Budget(Frozen):
    """Per session, across searches. ``limit=None`` means no cap."""

    limit: Money | None = None
    spent: Money = Money()

    @property
    def remaining(self) -> Money | None:
        if self.limit is None:
            return None
        return self.limit - self.spent

    def allows(self, extra: Money) -> bool:
        """True when spending ``extra`` on top of ``spent`` stays within ``limit``."""
        if self.limit is None:
            return True
        return self.spent + extra <= self.limit


class Timeout(Frozen):
    connect: float = 5.0
    read: float = 30.0
    total: float = 60.0


class Retry(Frozen):
    """Network errors and 5xx only; never a 403 rate limit."""

    attempts: int = Field(default=3, ge=1)
    backoff: float = Field(default=0.5, ge=0)
    max_backoff: float = Field(default=8.0, ge=0)


class CircuitBreaker(Frozen):
    failures: int = Field(default=5, ge=1)
    cooldown: float = Field(default=30.0, ge=0)


class Options(Frozen):
    """One per ``AsyncHub``; applies to the whole client."""

    model_config = ConfigDict(
        extra="ignore", populate_by_name=True, frozen=True, arbitrary_types_allowed=True
    )

    timeout: Timeout = Timeout()
    retry: Retry = Retry()
    circuit_breaker: CircuitBreaker = CircuitBreaker()
    concurrency: int = Field(default=8, ge=1)
    max_items: int = Field(default=1000, ge=1)
    user_agent: str | None = None
    http_client: Any = Field(default=None, exclude=True)
