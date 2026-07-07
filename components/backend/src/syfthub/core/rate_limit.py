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

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status

from syfthub.core.config import get_settings
from syfthub.core.redis_client import get_redis_client
from syfthub.observability.logger import get_logger

logger = get_logger(__name__)


def get_client_ip(request: Request) -> str:
    """Return the client IP for rate-limit keying.

    Relies on uvicorn ``--proxy-headers`` to make ``request.client.host`` the
    real client IP behind the reverse proxy.
    """
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def per_ip_rate_limit(
    scope: str,
    max_attr: str,
    window_attr: str,
) -> Callable[[Request], Awaitable[None]]:
    """Build a per-IP rate-limit dependency for one endpoint group.

    Args:
        scope: Short label used in the Redis key and log lines (e.g. ``"auth"``).
        max_attr: Settings attribute name holding the max requests per window.
        window_attr: Settings attribute name holding the window length (seconds).

    Returns:
        An async FastAPI dependency that raises 429 when the caller exceeds the
        configured budget for this scope.
    """

    async def dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

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
            if settings.rate_limit_fail_open:
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
                    "X-RateLimit-Reset": str(retry_after),
                },
            )

    return dependency
