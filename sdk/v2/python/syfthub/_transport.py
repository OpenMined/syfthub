"""Transport configuration and the seam the SDK talks through.

``Options`` is the one object a user tunes; it applies to the whole client: the Hub, every Space, the
Aggregator. ``Transport`` is what the hand-written layer calls. The real SDK implements it over
``httpx`` with the generated low-level clients; ``syfthub.testing.MockTransport`` implements it over
in-memory fakes. Retry, circuit-breaker and token-cache logic live here and are shared by both."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger("syfthub")


@dataclass(frozen=True)
class Timeout:
    """Seconds allowed for each phase of a request.

    Attributes:
        connect: Opening the connection.
        read: Waiting for the response.
        write: Sending the body.
        pool: Waiting for a free pooled connection."""
    connect: float = 5.0
    read: float = 30.0
    write: float = 10.0
    pool: float = 5.0


@dataclass(frozen=True)
class Retry:
    """Exponential backoff with full jitter. Applies to network errors and the listed 5xx.

    Never applied to 4xx, with one exception: a Space's rate limit (403 with ``reset_seconds``) is
    waited out and retried once when the wait is at most ``rate_limit_wait`` seconds.

    Attributes:
        max_attempts: Requests in all, the first one included.
        initial: Seconds before the first retry.
        multiplier: Growth factor between retries.
        jitter: Fraction of the delay randomised away, from 0 to 1.
        max_elapsed: Give up once this many seconds have been spent retrying.
        on_status: Response statuses that are retried.
        on_network: Whether connection errors and timeouts are retried.
        rate_limit_wait: Longest rate-limit reset the SDK waits out inside a call."""
    max_attempts: int = 3
    initial: float = 0.5
    multiplier: float = 1.5
    jitter: float = 0.5
    max_elapsed: float = 30.0
    on_status: tuple[int, ...] = (500, 502, 503, 504)
    on_network: bool = True
    rate_limit_wait: float = 10.0

    def delay(self, attempt: int) -> float:
        """Seconds to wait before retry number ``attempt`` (1 for the first retry)."""
        base = self.initial * (self.multiplier ** (attempt - 1))
        return base * (1 - self.jitter * random.random())


@dataclass(frozen=True)
class CircuitBreaker:
    """Per-Space protection: after repeated failures, stop sending to that Space for a while.

    Attributes:
        failures: Consecutive failed calls that open the circuit.
        cooldown: Seconds the circuit stays open before one probe is allowed."""
    failures: int = 3
    cooldown: float = 60.0


@dataclass(frozen=True)
class Options:
    """Everything tunable about the client, in one object. Applies to the Hub, every Space and the Aggregator.

    Attributes:
        timeout: Per-phase timeouts.
        retries: Backoff policy.
        circuit_breaker: Per-Space breaker.
        concurrency: Space calls in flight at once during a fan-out.
        http_client: The transport. In the real SDK an ``httpx.AsyncClient`` for proxies and tests; in this
            mock a ``syfthub.testing.MockTransport``.
        aggregator_url: Where the Aggregator lives. Defaults to ``{hub_url}/aggregator/api/v1``.
        user_agent_suffix: Appended to the SDK's ``User-Agent``.
        max_items: Auto-pagination cap for ``hub.endpoints.list()``.
        max_sources: How many free sources ``hub.search`` picks when you pass none."""
    timeout: Timeout = field(default_factory=Timeout)
    retries: Retry = field(default_factory=Retry)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    concurrency: int = 8
    http_client: Any = None
    aggregator_url: str | None = None
    user_agent_suffix: str | None = None
    max_items: int = 1000
    max_sources: int = 10

    def user_agent(self, version: str) -> str:
        import platform
        ua = f"syfthub-python/{version} python/{platform.python_version()}"
        return f"{ua} {self.user_agent_suffix}" if self.user_agent_suffix else ua


# ---------------------------------------------------------------------------- shared runtime state
class BreakerState:
    """Circuit-breaker bookkeeping for every Space host the session has talked to."""

    def __init__(self, policy: CircuitBreaker, clock=time.monotonic) -> None:
        self.policy, self.clock = policy, clock
        self.failures: dict[str, int] = {}
        self.opened_at: dict[str, float] = {}

    def is_open(self, host: str) -> bool:
        t = self.opened_at.get(host)
        if t is None:
            return False
        if self.clock() - t >= self.policy.cooldown:
            return False          # half-open: one probe allowed
        return True

    def record(self, host: str, ok: bool) -> None:
        if ok:
            self.failures.pop(host, None)
            self.opened_at.pop(host, None)
            return
        n = self.failures.get(host, 0) + 1
        self.failures[host] = n
        if n >= self.policy.failures:
            self.opened_at[host] = self.clock()
            log.warning("circuit open for %s after %d failures; cooling down %.0fs", host, n, self.policy.cooldown)

    def open_hosts(self) -> list[str]:
        return [h for h in self.opened_at if self.is_open(h)]


class TokenCache:
    """Satellite tokens keyed by (owner, resource). Refreshed at 80% of their lifetime."""

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self._tokens: dict[tuple[str, str, bool], tuple[str, float]] = {}
        self.mints = 0

    def get(self, owner: str, resource: str, guest: bool) -> str | None:
        hit = self._tokens.get((owner, resource, guest))
        if hit and self.clock() < hit[1]:
            return hit[0]
        return None

    def put(self, owner: str, resource: str, guest: bool, token: str, expires_in: float) -> None:
        self.mints += 1
        self._tokens[(owner, resource, guest)] = (token, self.clock() + 0.8 * expires_in)

    def drop(self, owner: str, resource: str, guest: bool) -> None:
        self._tokens.pop((owner, resource, guest), None)

    def clear(self) -> None:
        self._tokens.clear()

    def __len__(self) -> int:
        return len(self._tokens)


def redact(headers: dict[str, str]) -> dict[str, str]:
    """Headers safe to log: bearer tokens, payment credentials and challenges are masked."""
    out = {}
    for k, v in headers.items():
        out[k] = "<redacted>" if k.lower() in ("authorization", "x-payment", "www-authenticate") else v
    return out


# ---------------------------------------------------------------------------- the seam
@dataclass
class Response:
    """What a transport returns for one HTTP call."""
    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


class Transport(Protocol):
    """What the hand-written layer needs from the wire. Async throughout."""

    async def hub_login(self, method: str, **kw: Any) -> dict[str, Any]: ...
    async def hub_list(self, type_: str | None, owner: str | None, offset: int, limit: int) -> tuple[list[Any], int]: ...
    async def hub_search(self, text: str, type_: str | None) -> list[Any]: ...
    async def hub_get(self, path: str) -> Any | None: ...
    async def hub_collective(self, slug: str) -> list[str]: ...
    async def hub_token(self, owner: str, resource: str, *, guest: bool) -> tuple[str, float]: ...
    async def hub_wallet_balance(self) -> float: ...
    async def hub_wallet_pay(self, www_authenticate: str, slug: str, amount: float) -> str: ...
    async def space_query(self, url: str, slug: str, *, token: str, body: dict[str, Any], x_payment: str | None) -> Response: ...
    async def space_balance(self, url: str, wallet_id: str, *, token: str) -> Response: ...
    async def space_invoice(self, url: str, wallet_id: str, *, token: str, bundle: str) -> Response: ...
    async def aggregate(self, url: str, payload: dict[str, Any]) -> Response: ...
    async def sleep(self, seconds: float) -> None: ...
    def now(self) -> float: ...
