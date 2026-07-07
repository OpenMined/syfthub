"""Reusable per-IP rate limiting as a FastAPI dependency.

A fixed-window Redis limiter (``SET key 0 EX window NX`` then ``INCR``) keyed by
client IP. Built as a dependency *factory* so different endpoint groups can use
independent buckets with their own configured max/window.

Design choices:
- **Fixed window, one round-trip.** ``SET NX`` seeds the key with a TTL on the
  first hit; ``INCR`` returns the running count. Cheap and race-free enough for
  abuse prevention (this is not a billing-grade limiter).
- **Fail-open by default** (``settings.rate_limit_fail_open``): if Redis is
  unreachable the request is allowed, because auth availability outranks the
  marginal brute-force exposure during a Redis outage — and nginx ``limit_req``
  is an independent outer guard that does not depend on Redis. Flip the setting
  to fail closed where strictness matters more.
- Client IP comes from ``request.client.host``, which is the real client only
  when uvicorn runs with ``--proxy-headers`` (it does in the container image);
  otherwise it is the proxy's IP and the limit becomes global.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status

from syfthub.core.config import get_settings
from syfthub.core.redis_client import get_redis_client
from syfthub.observability.logger import get_logger

logger = get_logger(__name__)


def get_client_ip(request: Request) -> str:
    """Return the trusted client IP for rate-limit keying.

    Prefers nginx's ``X-Real-IP`` header, which the proxy sets from
    ``$remote_addr`` and **overwrites** on every request — so, unlike
    ``X-Forwarded-For`` (which nginx *appends* to and a client can seed), it
    cannot be spoofed. The backend port is only reachable via nginx on the
    internal network, so a client can never set ``X-Real-IP`` directly.

    Falls back to ``request.client.host`` only when the header is absent (e.g.
    a direct/local request with no proxy in front).
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def per_ip_rate_limit(
    scope: str,
    max_attr: str,
    window_attr: str,
    *,
    fail_open: bool | None = None,
    respect_enabled_switch: bool = True,
) -> Callable[[Request], Awaitable[None]]:
    """Build a per-IP rate-limit dependency for one endpoint group.

    Args:
        scope: Short label used in the Redis key and log lines (e.g. ``"auth"``).
        max_attr: Settings attribute name holding the max requests per window.
        window_attr: Settings attribute name holding the window length (seconds).
        fail_open: Behavior when Redis is unavailable. ``None`` (default) uses
            ``settings.rate_limit_fail_open``; pass ``False`` to force
            fail-closed for a security-sensitive scope regardless of the global
            default (e.g. unauthenticated token minting).
        respect_enabled_switch: When ``True`` (default), the limiter is skipped
            if ``settings.rate_limit_enabled`` is False. Pass ``False`` for a
            limiter that must stay active even when the global auth-limiter
            switch is off.

    Returns:
        An async FastAPI dependency that raises 429 when the caller exceeds the
        configured budget for this scope.
    """

    async def dependency(request: Request) -> None:
        settings = get_settings()
        if respect_enabled_switch and not settings.rate_limit_enabled:
            return

        effective_fail_open = (
            settings.rate_limit_fail_open if fail_open is None else fail_open
        )
        max_requests: int = getattr(settings, max_attr)
        window_seconds: int = getattr(settings, window_attr)

        ip = get_client_ip(request)
        key = f"ratelimit:{scope}:{ip}"

        try:
            redis = await get_redis_client()
            async with redis.pipeline(transaction=False) as pipe:
                # SET NX seeds the counter with a TTL on the first hit of the
                # window; INCR returns the running count; TTL gives Retry-After.
                pipe.set(key, 0, ex=window_seconds, nx=True)
                pipe.incr(key)
                pipe.ttl(key)
                _, count, ttl = await pipe.execute()
        except Exception as exc:
            # Redis unavailable/slow. Fail open (default) or closed per config.
            if effective_fail_open:
                logger.warning(
                    "rate_limit.redis_unavailable_fail_open",
                    scope=scope,
                    error=str(exc),
                )
                return
            logger.warning(
                "rate_limit.redis_unavailable_fail_closed",
                scope=scope,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limiting temporarily unavailable. Try again shortly.",
                headers={"Retry-After": "1"},
            ) from exc

        if count > max_requests:
            retry_after = ttl if isinstance(ttl, int) and ttl > 0 else window_seconds
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again later.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    # Unix-epoch seconds when the window resets (GitHub-style),
                    # not a duration — avoids clients misreading it as epoch 0.
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

    return dependency
