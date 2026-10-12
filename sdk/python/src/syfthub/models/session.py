"""Session objects: ``Identity``, ``Budget`` and the client ``Options``."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, model_validator

from .base import Frozen
from .enums import AuthMethod
from .money import Money


class Identity(Frozen):
    username: str
    email: str = ""
    auth: AuthMethod = AuthMethod.TOKEN


class Budget(Frozen):
    """Per session, across searches: one cap per currency, and spend tracked per currency.

    Money is never converted. A currency with no cap in ``limits`` has no budget: its rows are
    sent and its charges are recorded in ``spent`` but never held. No caps at all means no budget.
    """

    limits: dict[str, Money] = Field(default_factory=dict)
    spent: dict[str, Money] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _keys_match_currencies(self) -> Budget:
        for name in ("limits", "spent"):
            for currency, money in getattr(self, name).items():
                if money.currency != currency:
                    raise ValueError(f"{name}[{currency!r}] holds {money.currency}")
        return self

    @property
    def capped(self) -> bool:
        return bool(self.limits)

    @property
    def currencies(self) -> tuple[str, ...]:
        """The currencies with a cap."""
        return tuple(self.limits)

    def limit(self, currency: str) -> Money | None:
        return self.limits.get(currency)

    def spent_in(self, currency: str) -> Money:
        return self.spent.get(currency) or Money.zero(currency)

    @property
    def remaining(self) -> dict[str, Money]:
        """What is left under each cap, per capped currency."""
        return {cur: limit - self.spent_in(cur) for cur, limit in self.limits.items()}

    def remaining_in(self, currency: str) -> Money | None:
        limit = self.limits.get(currency)
        return None if limit is None else limit - self.spent_in(currency)

    def counts(self, amount: Money) -> bool:
        """Whether ``amount`` is in a capped currency."""
        return amount.currency in self.limits

    def allows(self, extra: Money) -> bool:
        """True when spending ``extra`` on top of what is spent in its currency stays within that
        currency's cap. A currency without a cap always allows."""
        limit = self.limits.get(extra.currency)
        if limit is None:
            return True
        return self.spent_in(extra.currency) + extra <= limit

    def record(self, amount: Money) -> Budget:
        """A copy with ``amount`` added to the spend in its currency."""
        spent = {**self.spent, amount.currency: self.spent_in(amount.currency) + amount}
        return self.model_copy(update={"spent": spent})


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
