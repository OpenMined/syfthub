"""SyftHub routes the first cut uses. Thin and hand-written; no business logic here."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from .._transport import Transport
from ..errors import (
    AuthError,
    HubUnreachable,
    PaymentFailed,
    SourceNotFound,
    SyftHubError,
    TransportError,
    ValidationError,
)
from .detail import ErrorDetail, detail_of

if TYPE_CHECKING:
    from ..auth import Session


class HubApi:
    """The SyftHub routes the SDK calls, one method per route, bodies returned as dicts.

    Every authenticated call carries the session's bearer token and renews it once on a 401.
    Hub errors become ``AuthError``, ``ValidationError``, ``SourceNotFound`` or ``SyftHubError``;
    a Hub that does not answer is ``HubUnreachable``.
    """

    def __init__(self, transport: Transport, base_url: str, session: Session) -> None:
        self.transport = transport
        self.base_url = base_url.rstrip("/")
        self.session = session

    def url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> httpx.Response:
        """Send with the session's bearer token; on a 401, renew once and resend."""
        try:
            response = await self.transport.request(
                method,
                self.url(path),
                json=json,
                params=params,
                headers=self.session.headers() if auth else {},
            )
            if response.status_code == 401 and auth and await self.session.renew():
                response = await self.transport.request(
                    method, self.url(path), json=json, params=params, headers=self.session.headers()
                )
        except TransportError as e:
            raise HubUnreachable(str(e)) from e
        return response

    @staticmethod
    def _raise_for(response: httpx.Response, *, not_found: SyftHubError | None = None) -> None:
        code = response.status_code
        if code < 400:
            return
        detail = detail_of(response)
        if code == 401:
            raise AuthError(detail or "not authenticated")
        if code == 404 and not_found is not None:
            raise not_found
        if code == 422:
            raise ValidationError(detail)
        raise SyftHubError(f"Hub returned {code}: {detail}")

    # ── auth ──────────────────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> dict[str, Any]:
        """``POST /auth/login``: the token pair for a password."""
        response = await self._send(
            "POST", "/auth/login", json={"username": username, "password": password}, auth=False
        )
        if response.status_code in (400, 401, 403):
            raise AuthError(detail_of(response) or "login failed")
        self._raise_for(response)
        body: dict[str, Any] = response.json()
        return body

    async def refresh(self, refresh_token: str) -> dict[str, Any] | None:
        """``POST /auth/refresh``: a new token pair, or None when the refresh token is dead.
        Goes to the transport directly so a renewal never re-enters the 401 handler."""
        try:
            response = await self.transport.request(
                "POST", self.url("/auth/refresh"), json={"refresh_token": refresh_token}
            )
        except TransportError:
            return None
        if response.status_code >= 400:
            return None
        body: dict[str, Any] = response.json()
        return body

    async def me(self) -> dict[str, Any]:
        """``GET /auth/me``: who the session's token belongs to."""
        response = await self._send("GET", "/auth/me")
        self._raise_for(response)
        body: dict[str, Any] = response.json()
        return body

    async def satellite_token(self, owner_username: str, resource: str) -> tuple[str, float]:
        """``GET /token``: a short-lived token for one owner's Space at ``resource`` and its
        lifetime in seconds. A 400 (no access) is ``ValidationError``."""
        response = await self._send(
            "GET", "/token", params={"owner_username": owner_username, "resource": resource}
        )
        if response.status_code == 400:
            raise ValidationError(
                f"no satellite token for {owner_username} at {resource}: {detail_of(response)}"
            )
        self._raise_for(response)
        body = response.json()
        return str(body["target_token"]), float(body.get("expires_in") or 60)

    # ── endpoints as sources ──────────────────────────────────────────────

    async def list_public(
        self, *, skip: int, limit: int, endpoint_type: str | None = None, search: str | None = None
    ) -> list[dict[str, Any]]:
        """``GET /endpoints/public``: one page of the public catalogue."""
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if endpoint_type:
            params["endpoint_type"] = endpoint_type
        if search:
            params["search"] = search
        response = await self._send("GET", "/endpoints/public", params=params)
        self._raise_for(response)
        items: list[dict[str, Any]] = response.json()
        return items

    async def list_by_owner(self, owner: str, *, skip: int, limit: int) -> list[dict[str, Any]]:
        """``GET /endpoints/public/by-owner/{owner}``: one page of one owner's endpoints."""
        response = await self._send(
            "GET", f"/endpoints/public/by-owner/{owner}", params={"skip": skip, "limit": limit}
        )
        self._raise_for(response)
        items: list[dict[str, Any]] = response.json()
        return items

    async def get_public(self, owner: str, slug: str) -> dict[str, Any]:
        """``GET /endpoints/public/{owner}/{slug}``: one endpoint; a 404 is ``SourceNotFound``."""
        response = await self._send("GET", f"/endpoints/public/{owner}/{slug}")
        self._raise_for(response, not_found=SourceNotFound(f"{owner}/{slug}"))
        body: dict[str, Any] = response.json()
        return body

    async def search(self, query: str, *, top_k: int) -> dict[str, Any]:
        """``POST /endpoints/search``: the Hub's semantic match of endpoints to a query."""
        response = await self._send(
            "POST", "/endpoints/search", json={"query": query, "top_k": top_k}
        )
        self._raise_for(response)
        body: dict[str, Any] = response.json()
        return body

    # ── MPP: the Hub pays a Space's 402 challenge from the user's wallet ──

    async def pay_mpp(self, www_authenticate: str, endpoint_slug: str) -> str:
        """``POST /wallet/pay``: returns the ``X-Payment`` credential for one challenge.

        Hub errors (no wallet, insufficient balance, bad challenge, chain timeout) come back as
        ``PaymentFailed`` with the Hub's ``code`` and ``message``; the row stays unpaid.
        """
        response = await self._send(
            "POST",
            "/wallet/pay",
            json={"www_authenticate": www_authenticate, "endpoint_slug": endpoint_slug},
        )
        if response.status_code == 401:
            raise AuthError(detail_of(response) or "not authenticated")
        if response.status_code >= 400:
            detail = ErrorDetail.of(response)
            raise PaymentFailed(f"MPP payment refused by the Hub: {detail}", code=detail.code)
        body = response.json()
        credential = body.get("x_payment") if isinstance(body, dict) else None
        if not isinstance(credential, str) or not credential:
            raise PaymentFailed("MPP payment: the Hub returned no credential")
        return credential
