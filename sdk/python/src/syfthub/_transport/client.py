"""One ``httpx.AsyncClient`` with retries, timeouts, a user agent and redacted debug logging."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .._version import __version__
from ..models.enums import Reason
from ..models.session import Options
from .retry import delays, retryable_status

log = logging.getLogger("syfthub")

_REDACTED_HEADERS = frozenset({"authorization", "x-payment", "www-authenticate"})


class TransportError(Exception):
    """The request never produced a response, after retries. ``reason`` is TIMEOUT or UNREACHABLE."""

    def __init__(self, reason: Reason, message: str, attempts: int) -> None:
        super().__init__(message)
        self.reason = reason
        self.attempts = attempts


class Transport:
    def __init__(self, options: Options | None = None) -> None:
        self.options = options or Options()
        self.user_agent = self.options.user_agent or f"syfthub-sdk/{__version__}"
        client = self.options.http_client
        if client is None:
            t = self.options.timeout
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(t.total, connect=t.connect, read=t.read),
                limits=httpx.Limits(
                    max_connections=max(10, self.options.concurrency * 2),
                    max_keepalive_connections=max(5, self.options.concurrency),
                ),
                follow_redirects=True,
            )
            self._owns_client = True
        else:
            self._owns_client = False
        self._client: httpx.AsyncClient = client

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry: bool = True,
    ) -> httpx.Response:
        """Send once, or up to ``Retry.attempts`` times on network errors and 5xx.

        Returns the last response, whatever its status; raises ``TransportError`` only when no
        response was ever received.
        """
        hdrs = {"User-Agent": self.user_agent, **(headers or {})}
        plan = list(delays(self.options.retry)) if retry else []
        attempts = 0
        last_error: Exception | None = None
        while True:
            attempts += 1
            try:
                response = await self._client.request(
                    method, url, json=json, params=params, headers=hdrs
                )
            except httpx.TimeoutException as e:
                last_error = e
                log.debug("%s %s timed out (attempt %d)", method, url, attempts)
            except httpx.HTTPError as e:
                last_error = e
                log.debug("%s %s failed: %s (attempt %d)", method, url, e, attempts)
            else:
                log.debug(
                    "%s %s -> %d (attempt %d) headers=%s",
                    method,
                    url,
                    response.status_code,
                    attempts,
                    redact(dict(hdrs)),
                )
                if not retryable_status(response.status_code) or not plan:
                    return response
            if not plan:
                break
            await asyncio.sleep(plan.pop(0))
        assert last_error is not None
        reason = (
            Reason.TIMEOUT if isinstance(last_error, httpx.TimeoutException) else Reason.UNREACHABLE
        )
        raise TransportError(reason, f"{method} {url}: {last_error}", attempts)


def redact(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("<redacted>" if k.lower() in _REDACTED_HEADERS else v) for k, v in headers.items()}


def detail_of(response: httpx.Response) -> str:
    """The ``detail`` of a FastAPI error body, else a short slice of the text."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return str(detail)[:200]
    return response.text[:200]
