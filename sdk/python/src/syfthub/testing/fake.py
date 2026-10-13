"""``FakeHub`` and ``FakeSpace``: in-memory stand-ins for the two servers, speaking the same
routes the SDK speaks, routed through one ``httpx.MockTransport``."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .._transport import redact
from ..hub import AsyncHub
from ..models.session import Options

_QUERY_PREFIX = "/api/v1/endpoints/"
_QUERY_SUFFIX = "/query"


class Reply(BaseModel):
    """What a Space answers for one slug. Set with ``FakeSpace.reply`` or ``FakeSpace.reject``."""

    documents: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    cost: float | None = None
    currency: str = "USD"
    status: int = 200
    detail: str | None = None
    outcome: str | None = None
    reason_code: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    mpp_price: float | None = None


class Call(BaseModel):
    method: str
    url: str
    headers: dict[str, str]
    json_body: Any = None

    @property
    def host(self) -> str:
        return urlsplit(self.url).netloc

    @property
    def path(self) -> str:
        return urlsplit(self.url).path


class FakeSpace(BaseModel):
    """One Space origin: its query replies, one prepaid wallet, and the invoices it issued."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    origin: str
    owner: str
    balance: float = 0.0
    currency: str = "USD"
    wallet_id: str = ""
    bundles: list[dict[str, Any]] = Field(
        default_factory=lambda: [{"name": "starter", "amount": 1}]
    )
    replies: dict[str, Reply] = Field(default_factory=dict)
    invoices: list[dict[str, Any]] = Field(default_factory=list)
    accept_tokens: bool = True
    _charged: int = PrivateAttr(default=0)

    # ── configure ─────────────────────────────────────────────────────────

    def reply(
        self,
        slug: str,
        *,
        documents: list[dict[str, Any]] | None = None,
        summary: str | None = None,
        cost: float | None = None,
        mpp_price: float | None = None,
    ) -> Reply:
        """A 200 for ``slug``. ``documents`` items take ``content``, ``score``, ``metadata``,
        ``id``. ``cost`` makes it a prepaid charge against ``balance``; ``mpp_price`` makes the
        first call answer a 402 challenge until ``X-Payment`` arrives."""
        r = Reply(documents=documents or [], summary=summary, cost=cost, mpp_price=mpp_price)
        self.replies[slug] = r
        return r

    def reject(
        self,
        slug: str,
        *,
        status: int = 403,
        outcome: str = "access_denied",
        reason_code: str | None = None,
        detail: str | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Reply:
        """An error for ``slug`` in the Space's ``policy_metadata`` envelope."""
        r = Reply(
            status=status,
            outcome=outcome,
            reason_code=reason_code or outcome.upper(),
            detail=detail or outcome.replace("_", " "),
            details=details or {},
            headers=headers or {},
        )
        self.replies[slug] = r
        return r

    def pay(self, invoice_id: str) -> None:
        """Mark an invoice paid and credit the bundle to the balance."""
        for inv in self.invoices:
            if inv["id"] == invoice_id and inv["status"] != "paid":
                inv["status"] = "paid"
                inv["paid_at"] = "2026-01-01T00:00:00Z"
                self.balance += float(inv["amount"])
                return
        raise KeyError(invoice_id)

    @property
    def credits_url(self) -> str:
        return f"{self.origin}/api/v1/credits"

    @property
    def payment_url(self) -> str:
        return f"{self.origin}/api/v1/payments"

    @property
    def invoices_url(self) -> str:
        return f"{self.origin}/api/v1/invoices"

    def policy(
        self, price: float, *, unit: str = "request", rail: str = "xendit"
    ) -> dict[str, Any]:
        """A Hub-shaped payment policy billing this Space's wallet."""
        return {
            "type": rail,
            "enabled": True,
            "config": {
                "price": price,
                "unit_type": unit,
                "currency": self.currency,
                "wallet_id": self.wallet_id,
                "wallet_owner": self.owner,
                "bundles": self.bundles,
                "payment_url": self.payment_url,
                "credits_url": self.credits_url,
                "invoices_url": self.invoices_url,
            },
        }

    # ── serve ─────────────────────────────────────────────────────────────

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        auth = request.headers.get("Authorization", "")
        if self.accept_tokens and not auth.startswith("Bearer "):
            return httpx.Response(401, json={"detail": "missing token"})
        if path == urlsplit(self.credits_url).path:
            return httpx.Response(
                200,
                json={
                    "wallet_id": self.wallet_id,
                    "user_email": "",
                    "balance": self.balance,
                    "currency": self.currency,
                },
            )
        if path == urlsplit(self.payment_url).path and request.method == "POST":
            body = json.loads(request.content or b"{}")
            name = body.get("bundle_name")
            bundle = next((b for b in self.bundles if b["name"] == name), None)
            if bundle is None:
                return httpx.Response(400, json={"detail": f"unknown bundle {name!r}"})
            invoice = {
                "id": f"inv-{uuid.uuid4().hex[:8]}",
                "wallet_id": self.wallet_id,
                "user_email": "",
                "provider": "fake",
                "checkout_url": f"{self.origin}/checkout/{len(self.invoices) + 1}",
                "bundle_name": name,
                "amount": bundle["amount"],
                "currency": self.currency,
                "status": "pending",
                "paid_at": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
            self.invoices.insert(0, invoice)
            return httpx.Response(200, json=invoice)
        if path == urlsplit(self.invoices_url).path:
            status = request.url.params.get("status")
            items = [i for i in self.invoices if status is None or i["status"] == status]
            return httpx.Response(200, json=items)
        if path.startswith(_QUERY_PREFIX) and path.endswith(_QUERY_SUFFIX):
            slug = path[len(_QUERY_PREFIX) : -len(_QUERY_SUFFIX)]
            return self._query(slug, request)
        return httpx.Response(404, json={"detail": f"no route {path}"})

    def _query(self, slug: str, request: httpx.Request) -> httpx.Response:
        reply = self.replies.get(slug)
        if reply is None:
            return httpx.Response(404, json={"detail": f"Endpoint '{slug}' not found"})
        if reply.status != 200:
            entry: dict[str, Any] = {
                "policy_type": reply.outcome,
                "kind": reply.outcome,
                "status": "rejected",
                "amount": None,
                "currency": None,
                "recipient": None,
                "transaction": None,
                "reason_code": reply.reason_code,
                "reason": reply.detail,
                "details": reply.details,
            }
            return httpx.Response(
                reply.status,
                json={
                    "detail": reply.detail,
                    "policy_metadata": {"outcome": reply.outcome, "entries": [entry]},
                },
                headers=reply.headers,
            )
        entries: list[dict[str, Any]] = []
        cost: float | None = None
        if reply.mpp_price is not None:
            if not request.headers.get("X-Payment"):
                challenge = (
                    f'Payment realm="{self.owner}", amount="{reply.mpp_price}", '
                    f'currency="{self.currency}", request="fake"'
                )
                return httpx.Response(
                    402,
                    json={"detail": "payment required"},
                    headers={"WWW-Authenticate": challenge},
                )
            cost = reply.mpp_price
            entries.append(_charged("mpp_per_request", cost, self.currency, "mpp"))
        elif reply.cost is not None:
            if self.balance < reply.cost:
                short: dict[str, Any] = {
                    "policy_type": "xendit_per_request",
                    "kind": "payment",
                    "status": "rejected",
                    "amount": reply.cost,
                    "currency": self.currency,
                    "recipient": None,
                    "transaction": None,
                    "reason_code": "INSUFFICIENT_BALANCE",
                    "reason": f"Insufficient balance: {self.balance} available, {reply.cost} required",
                    "details": {"wallet_id": self.wallet_id, "balance": self.balance},
                }
                return httpx.Response(
                    402,
                    json={
                        "detail": short["reason"],
                        "policy_metadata": {"outcome": "payment_required", "entries": [short]},
                    },
                )
            self.balance = round(self.balance - reply.cost, 6)
            self._charged += 1
            cost = reply.cost
            entries.append(_charged("xendit_per_request", cost, self.currency, "xendit"))
        documents = [
            {
                "document_id": d.get("id") or f"{slug}-{i}",
                "content": d.get("content", ""),
                "metadata": d.get("metadata") or {},
                "similarity_score": d.get("score", 0.5),
            }
            for i, d in enumerate(reply.documents)
        ]
        body: dict[str, Any] = {
            "summary": {"message": {"role": "assistant", "content": reply.summary}}
            if reply.summary
            else None,
            "references": {"documents": documents},
            "policy_metadata": {"outcome": "success", "entries": entries},
        }
        if cost is not None:
            body["cost"], body["currency"] = cost, self.currency
        return httpx.Response(200, json=body)


def _charged(policy_type: str, amount: float, currency: str, rail: str) -> dict[str, Any]:
    return {
        "policy_type": policy_type,
        "kind": "payment",
        "status": "charged",
        "amount": amount,
        "currency": currency,
        "recipient": None,
        "transaction": {"rail": rail, "id": f"tx-{uuid.uuid4().hex[:8]}", "reference": None},
        "reason_code": None,
        "reason": None,
        "details": {},
    }


class FakeHub(BaseModel):
    """An in-memory SyftHub: users, the source catalogue, satellite tokens and the MPP pay route.

    Any bearer token is accepted unless ``users`` is set, in which case ``login`` must have
    produced it. ``mpp_error`` makes ``POST /wallet/pay`` fail with that Hub error code.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str = "https://hub.test"
    me: dict[str, Any] = Field(
        default_factory=lambda: {"id": 1, "username": "me", "email": "me@example.org"}
    )
    users: dict[str, str] = Field(default_factory=dict)  # username -> password
    sources: dict[str, dict[str, Any]] = Field(default_factory=dict)  # path -> Hub body
    spaces: dict[str, FakeSpace] = Field(default_factory=dict)  # owner -> space
    mpp_credential: str = "fake-credential"
    mpp_error: tuple[str, str] | None = None
    calls: list[Call] = Field(default_factory=list)
    _tokens: set[str] = PrivateAttr(default_factory=set)

    # ── configure ─────────────────────────────────────────────────────────

    def space(self, owner: str, origin: str | None = None) -> FakeSpace:
        """The Space that serves ``owner``'s sources, created on first use."""
        if owner not in self.spaces:
            self.spaces[owner] = FakeSpace(
                origin=origin or f"https://{owner}.space.test",
                owner=owner,
                wallet_id=f"w-{owner}",
            )
        return self.spaces[owner]

    def add_source(
        self,
        owner: str,
        slug: str,
        *,
        type: str = "data_source",
        price: float | None = None,
        unit: str = "request",
        rail: str = "xendit",
        mpp_price: float | None = None,
        policies: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        description: str = "",
        name: str | None = None,
    ) -> dict[str, Any]:
        """Register a source. ``price`` adds a prepaid policy on the owner's Space wallet;
        ``mpp_price`` adds an MPP policy and makes the Space challenge every query."""
        space = self.space(owner)
        pols = list(policies or [])
        if price is not None:
            pols.append(space.policy(price, unit=unit, rail=rail))
        if mpp_price is not None:
            pols.append(
                {
                    "type": "mpp",
                    "enabled": True,
                    "config": {"price": mpp_price, "currency": space.currency},
                }
            )
            space.reply(slug, mpp_price=mpp_price)
        body = {
            "name": name or slug.replace("-", " ").title(),
            "slug": slug,
            "description": description,
            "type": type,
            "owner_username": owner,
            "contributors_count": 1,
            "version": "1.0.0",
            "readme": "",
            "tags": tags or [],
            "stars_count": 0,
            "policies": pols,
            "connect": [{"type": "http", "enabled": True, "config": {"url": space.origin}}],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "health_status": "healthy",
            "health_checked_at": datetime.now(timezone.utc).isoformat(),
            "health_ttl_seconds": 90,
            "archived": False,
        }
        self.sources[f"{owner}/{slug}"] = body
        return body

    def options(self, **overrides: Any) -> Options:
        """``Options`` whose HTTP client is routed to this fake."""
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        return Options(http_client=client, **overrides)

    def hub(self, *, token: str | None = "fake-token", **kwargs: Any) -> AsyncHub:
        """An ``AsyncHub`` wired to this fake. Pass ``options=`` to override retry and friends."""
        options = kwargs.pop("options", None)
        overrides = options.model_dump(exclude={"http_client"}) if options else {}
        return AsyncHub(self.url, token=token, options=self.options(**overrides), **kwargs)

    # ── serve ─────────────────────────────────────────────────────────────

    def handle(self, request: httpx.Request) -> httpx.Response:
        body: Any = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = request.content.decode(errors="replace")
        self.calls.append(
            Call(
                method=request.method,
                url=str(request.url),
                headers=redact(dict(request.headers)),
                json_body=body,
            )
        )
        origin = f"{request.url.scheme}://{request.url.netloc.decode()}"
        if origin == self.url:
            return self._hub(request, body)
        for space in self.spaces.values():
            if space.origin == origin:
                return space.handle(request)
        return httpx.Response(502, json={"detail": f"no fake for {origin}"})

    def _authed(self, request: httpx.Request) -> bool:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        return not self.users or auth.removeprefix("Bearer ") in self._tokens

    def _hub(self, request: httpx.Request, body: Any) -> httpx.Response:
        path = request.url.path
        params = parse_qs(request.url.query.decode())
        if path == "/api/v1/auth/login":
            username = str((body or {}).get("username") or "")
            if self.users and self.users.get(username) != (body or {}).get("password"):
                return httpx.Response(401, json={"detail": "Incorrect username or password"})
            token = f"tok-{uuid.uuid4().hex[:8]}"
            self._tokens.add(token)
            return httpx.Response(
                200, json={"user": self.me, "access_token": token, "refresh_token": f"ref-{token}"}
            )
        if path == "/api/v1/auth/refresh":
            token = f"tok-{uuid.uuid4().hex[:8]}"
            self._tokens.add(token)
            return httpx.Response(
                200, json={"access_token": token, "refresh_token": f"ref-{token}"}
            )
        if not self._authed(request):
            return httpx.Response(401, json={"detail": "Could not validate credentials"})
        if path == "/api/v1/auth/me":
            return httpx.Response(200, json=self.me)
        if path == "/api/v1/token":
            owner = params.get("owner_username", [""])[0]
            return httpx.Response(200, json={"target_token": f"sat-{owner}", "expires_in": 60})
        if path == "/api/v1/endpoints/public":
            items = list(self.sources.values())
            kind = params.get("endpoint_type", [None])[0]
            text = params.get("search", [None])[0]
            if kind:
                items = [s for s in items if s["type"] == kind]
            if text:
                items = [s for s in items if _mentions(s, text)]
            return httpx.Response(200, json=_page(items, params))
        if path.startswith("/api/v1/endpoints/public/by-owner/"):
            owner = path.rsplit("/", 1)[1]
            items = [s for s in self.sources.values() if s["owner_username"] == owner]
            return httpx.Response(200, json=_page(items, params))
        if path.startswith("/api/v1/endpoints/public/"):
            key = path[len("/api/v1/endpoints/public/") :]
            source = self.sources.get(key)
            if source is None:
                return httpx.Response(404, json={"detail": "Endpoint not found"})
            return httpx.Response(200, json=source)
        if path == "/api/v1/endpoints/search":
            text = (body or {}).get("query", "")
            top_k = int((body or {}).get("top_k", 10))
            items = [s for s in self.sources.values() if _mentions(s, text)] or list(
                self.sources.values()
            )
            return httpx.Response(
                200, json={"results": items[:top_k], "total": len(items), "query": text}
            )
        if path == "/api/v1/wallet/pay":
            if self.mpp_error is not None:
                code, message = self.mpp_error
                return httpx.Response(400, json={"detail": {"code": code, "message": message}})
            return httpx.Response(200, json={"x_payment": self.mpp_credential})
        return httpx.Response(404, json={"detail": f"no route {path}"})


def _mentions(source: dict[str, Any], text: str) -> bool:
    needle = text.lower()
    hay = " ".join(
        [
            str(source.get("name", "")),
            str(source.get("slug", "")),
            str(source.get("description", "")),
            " ".join(source.get("tags") or []),
        ]
    ).lower()
    return any(tok in hay for tok in needle.split()) if needle.strip() else True


def _page(items: list[dict[str, Any]], params: dict[str, list[str]]) -> list[dict[str, Any]]:
    skip = int(params.get("skip", ["0"])[0])
    limit = int(params.get("limit", ["100"])[0])
    return items[skip : skip + limit]
