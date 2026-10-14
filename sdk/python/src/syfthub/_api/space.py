"""Syft Space routes: the query route, and the three wallet routes a policy publishes.

Every call takes the full URL and a satellite token; the SDK never builds a wallet URL.
"""

from __future__ import annotations

from typing import Any

import httpx

from .._transport import Transport
from ..errors import AuthError, PaymentFailed, TransportError
from .detail import detail_of


def _headers(
    token: str, tenant: str | None = None, extra: dict[str, str] | None = None
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if tenant:
        headers["X-Tenant-Name"] = tenant
    if extra:
        headers.update(extra)
    return headers


class SpaceApi:
    """The four Space routes, each at a URL the Hub published. Wallet routes raise
    ``PaymentFailed`` for any failure and ``AuthError`` for a rejected satellite token."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    async def query(
        self,
        url: str,
        token: str,
        body: dict[str, Any],
        *,
        tenant: str | None = None,
        x_payment: str | None = None,
    ) -> httpx.Response:
        """The raw response: callers classify 2xx, 402, 403 and the rest into rows.

        Raises ``TransportError`` when nothing came back after retries. A query POST is retried
        on network errors and 5xx because Spaces bill on success only.
        """
        extra = {"X-Payment": x_payment} if x_payment else None
        return await self.transport.request(
            "POST", url, json=body, headers=_headers(token, tenant, extra)
        )

    async def balance(
        self, credits_url: str, token: str, *, retry: bool = True, read_timeout: float | None = None
    ) -> dict[str, Any]:
        """``GET credits_url``: the wallet's balance body."""
        try:
            response = await self.transport.request(
                "GET", credits_url, headers=_headers(token), retry=retry, read_timeout=read_timeout
            )
        except TransportError as e:
            raise PaymentFailed(f"balance unavailable: {e}") from e
        _raise_payment(response, "balance")
        body: dict[str, Any] = response.json()
        return body

    async def create_invoice(
        self, payment_url: str, token: str, *, bundle_name: str, endpoint_slug: str | None = None
    ) -> dict[str, Any]:
        """``POST payment_url``: a pending invoice for one bundle. Never retried: a retry could
        issue two invoices."""
        body: dict[str, Any] = {"bundle_name": bundle_name}
        if endpoint_slug:
            body["endpoint_slug"] = endpoint_slug
        try:
            response = await self.transport.request(
                "POST", payment_url, json=body, headers=_headers(token), retry=False
            )
        except TransportError as e:
            raise PaymentFailed(f"invoice not created: {e}") from e
        _raise_payment(response, "invoice")
        result: dict[str, Any] = response.json()
        return result

    async def invoices(
        self, invoices_url: str, token: str, *, status: str | None = None
    ) -> list[dict[str, Any]]:
        """``GET invoices_url``: the caller's invoices on this wallet."""
        params = {"status": status} if status else None
        try:
            response = await self.transport.request(
                "GET", invoices_url, params=params, headers=_headers(token)
            )
        except TransportError as e:
            raise PaymentFailed(f"invoices unavailable: {e}") from e
        _raise_payment(response, "invoices")
        items: list[dict[str, Any]] = response.json()
        return items


def _raise_payment(response: httpx.Response, what: str) -> None:
    code = response.status_code
    if code < 400:
        return
    detail = detail_of(response)
    if code == 401:
        raise AuthError(f"{what}: {detail or 'satellite token rejected'}")
    raise PaymentFailed(f"{what}: HTTP {code} {detail}")
