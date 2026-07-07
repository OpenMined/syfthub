"""Tests for the per-IP Redis rate-limit dependency (core/rate_limit.py)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from syfthub.core.rate_limit import per_ip_rate_limit

MODULE = "syfthub.core.rate_limit"


class _FakePipe:
    """Minimal async-context-manager stand-in for redis.pipeline()."""

    def __init__(self, count: int, ttl: int):
        self._count = count
        self._ttl = ttl

    async def __aenter__(self) -> "_FakePipe":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    # Queued commands are no-ops in the stub.
    def set(self, *args: object, **kwargs: object) -> None:
        return None

    def incr(self, *args: object, **kwargs: object) -> None:
        return None

    def ttl(self, *args: object, **kwargs: object) -> None:
        return None

    async def execute(self) -> list:
        # Mirrors [set_result, incr_count, ttl]
        return [True, self._count, self._ttl]


class _FakeRedis:
    def __init__(self, count: int, ttl: int = 60):
        self._count = count
        self._ttl = ttl

    def pipeline(self, transaction: bool = False) -> _FakePipe:
        return _FakePipe(self._count, self._ttl)


def _request(ip: str = "1.2.3.4") -> MagicMock:
    req = MagicMock()
    req.client.host = ip
    return req


def _settings(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "rate_limit_enabled": True,
        "rate_limit_fail_open": True,
        "auth_rate_limit_max": 10,
        "auth_rate_limit_window_seconds": 60,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_dep():
    return per_ip_rate_limit(
        "auth", "auth_rate_limit_max", "auth_rate_limit_window_seconds"
    )


@pytest.mark.asyncio
async def test_under_limit_passes() -> None:
    dep = _make_dep()
    with (
        patch(f"{MODULE}.get_settings", return_value=_settings()),
        patch(
            f"{MODULE}.get_redis_client",
            new=AsyncMock(return_value=_FakeRedis(count=5)),
        ),
    ):
        # Should not raise.
        await dep(_request())


@pytest.mark.asyncio
async def test_over_limit_raises_429_with_retry_after() -> None:
    dep = _make_dep()
    with (
        patch(f"{MODULE}.get_settings", return_value=_settings()),
        patch(
            f"{MODULE}.get_redis_client",
            new=AsyncMock(return_value=_FakeRedis(count=11, ttl=42)),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await dep(_request())

    exc = exc_info.value
    assert exc.status_code == 429
    assert exc.headers is not None
    assert exc.headers["Retry-After"] == "42"
    assert exc.headers["X-RateLimit-Limit"] == "10"
    assert exc.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_fail_open_when_redis_unavailable() -> None:
    dep = _make_dep()

    with (
        patch(
            f"{MODULE}.get_settings", return_value=_settings(rate_limit_fail_open=True)
        ),
        patch(
            f"{MODULE}.get_redis_client",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ),
    ):
        # Fail-open: no exception even though Redis is unreachable.
        await dep(_request())


@pytest.mark.asyncio
async def test_fail_closed_when_configured() -> None:
    dep = _make_dep()

    with (
        patch(
            f"{MODULE}.get_settings",
            return_value=_settings(rate_limit_fail_open=False),
        ),
        patch(
            f"{MODULE}.get_redis_client",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await dep(_request())
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_disabled_switch_skips_redis_entirely() -> None:
    dep = _make_dep()

    with (
        patch(
            f"{MODULE}.get_settings", return_value=_settings(rate_limit_enabled=False)
        ),
        patch(
            f"{MODULE}.get_redis_client",
            new=AsyncMock(side_effect=AssertionError("Redis must not be consulted")),
        ),
    ):
        # Master switch off → returns before touching Redis.
        await dep(_request())
