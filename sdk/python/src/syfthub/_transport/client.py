"""One ``httpx.AsyncClient`` with retries, timeouts, a user agent and redacted debug logging."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from typing import Any

import httpx

from .._version import __version__
from ..errors import ConfigurationError, TransportError
from ..models.enums import Reason
from ..models.session import Options
from .retry import delays, retryable_status

log = logging.getLogger("syfthub")

_REDACTED_HEADERS = frozenset({"authorization", "x-payment", "www-authenticate"})
# Idle pooled connections live this long. httpx's default of 5 s meant every Hub call after a slow
# fan-out paid a new TCP+TLS handshake; nginx and most proxies keep an idle connection for 75 s.
KEEPALIVE_SECONDS = 60.0


class Transport:
    """The one HTTP client of a session. Owns the pool unless ``Options.http_client`` was given;
    ``request`` is the only way out to the network."""

    def __init__(self, options: Options | None = None) -> None:
        self.options = options or Options()
        self.user_agent = self.options.user_agent or f"syfthub-sdk/{__version__}"
        client = self.options.http_client
        if client is None:
            if self.options.http2 and importlib.util.find_spec("h2") is None:
                raise ConfigurationError(
                    "Options(http2=True) needs the h2 package: pip install 'syfthub-sdk[http2]'"
                )
            t = self.options.timeout
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(t.total, connect=t.connect, read=t.read),
                limits=httpx.Limits(
                    max_connections=max(10, self.options.concurrency * 2),
                    max_keepalive_connections=max(5, self.options.concurrency),
                    keepalive_expiry=KEEPALIVE_SECONDS,
                ),
                follow_redirects=True,
                http2=self.options.http2,  # opt-in: one multiplexed connection per host
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
        read_timeout: float | None = None,
    ) -> httpx.Response:
        """Send once, or up to ``Retry.attempts`` times on network errors; a 5xx is retried at
        most ``Retry.server_errors`` times within that. ``read_timeout`` overrides
        ``Timeout.read`` for this request.

        Returns the last response, whatever its status; raises ``TransportError`` only when no
        response was ever received.
        """
        hdrs = {"User-Agent": self.user_agent, **(headers or {})}
        t = self.options.timeout
        timeout: httpx.Timeout | httpx._client.UseClientDefault = (
            httpx.Timeout(t.total, connect=t.connect, read=read_timeout)
            if read_timeout is not None
            else httpx.USE_CLIENT_DEFAULT
        )
        plan = list(delays(self.options.retry)) if retry else []
        server_retries = self.options.retry.server_errors
        attempts = 0
        last_error: Exception | None = None
        while True:
            attempts += 1
            try:
                response = await self._client.request(
                    method, url, json=json, params=params, headers=hdrs, timeout=timeout
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
                if not retryable_status(response.status_code) or not plan or not server_retries:
                    return response
                server_retries -= 1
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
