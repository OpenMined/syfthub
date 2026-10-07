"""The session. ``AsyncHub`` is the source of truth; ``Hub`` is its synchronous face.

Only this module and the namespaces talk to the transport. Retries, the circuit breaker, the token cache
and logging live in ``_call_space``; everything above it sees typed rows."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Iterable

from . import __version__
from ._transport import BreakerState, Options, Response, TokenCache, redact
from .aggregator import AggregatorClient
from .auth import AuthNamespace
from .chat import Chat
from .endpoints import EndpointsNamespace
from .errors import BudgetExceeded, ConfigurationError, NotLoggedIn, ValidationError
from .models import (Answer, Budget, Charge, Endpoint, Identity, Include, Message, Money, Outcome, RateLimit, Reason,
                     SourceResult, TopUp, Via, to_space_filters, split_filters)
from .results import Results
from .search import SearchPlan
from .wallets import WalletsNamespace

log = logging.getLogger("syfthub")
DEFAULT_URL = "https://hub.syfthub.org"


class AsyncHub:
    """Your session with a Hub. Everything starts here.

    Construct it, optionally sign in, then ``search`` or ``chat``. Discovery lives on ``hub.endpoints``,
    balances on ``hub.wallets``, sign-in on ``hub.auth``. Nothing is sent until you ask for something.

    Attributes:
        url: The Hub's base URL.
        options: The transport settings, applied to the Hub, every Space and the Aggregator.
        me: Who is signed in, or ``None``.
        budget: The session budget, or ``None``."""

    def __init__(self, url: str | None = None, *, token: str | None = None, options: Options | None = None) -> None:
        self.url = (url or os.environ.get("SYFTHUB_URL") or DEFAULT_URL).rstrip("/")
        if "://" not in self.url:
            raise ConfigurationError(f"url must include a scheme, got {self.url!r}")
        self.options = options or Options()
        if self.options.concurrency < 1:
            raise ConfigurationError("Options.concurrency must be at least 1")
        if self.options.http_client is None:
            from .testing import MockTransport          # this is a mock: no real wire
            self._t = MockTransport()
        else:
            self._t = self.options.http_client
        self._tokens = TokenCache(clock=self._t.now)
        self._breaker = BreakerState(self.options.circuit_breaker, clock=self._t.now)
        self._sem = asyncio.Semaphore(self.options.concurrency)
        self.me: Identity | None = None
        self.budget: Budget | None = None
        self.auth = AuthNamespace(self)
        self.endpoints = EndpointsNamespace(self)
        self.wallets = WalletsNamespace(self)
        self._aggregator = AggregatorClient(self)
        self._pending_token = token or os.environ.get("SYFTHUB_TOKEN")
        self.user_agent = self.options.user_agent(__version__)

    # -- lifecycle --------------------------------------------------------------------------
    async def __aenter__(self) -> "AsyncHub":
        await self._ensure_token_login()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        """Close pooled connections. Called by ``async with``."""
        self._tokens.clear()

    async def _ensure_token_login(self) -> None:
        if self._pending_token and self.me is None:
            tok, self._pending_token = self._pending_token, None
            await self.auth.login_with_token(tok)

    async def _sleep(self, seconds: float) -> None:
        await self._t.sleep(seconds)

    @property
    def transport(self) -> Any:
        """The transport in use. In this mock, the ``MockTransport`` whose ``world`` you can poke."""
        return self._t

    # -- the one top-level alias -----------------------------------------------------------
    async def login(self, *, username: str | None = None, password: str | None = None, token: str | None = None) -> Identity:
        """Sign in. The one top-level alias: ``hub.auth`` has the full set.

        Args:
            username: With ``password``: sign in with a password.
            password: Your Hub password.
            token: Instead: sign in with a personal access token.

        Returns:
            Your ``Identity``.

        Raises:
            ValidationError: When neither a password pair nor a token is given."""
        if token is not None:
            return await self.auth.login_with_token(token)
        if username is not None and password is not None:
            return await self.auth.login(username=username, password=password)
        raise ValidationError("login needs username= and password=, or token=")

    def set_budget(self, limit: Money | float, currency: str = "USD") -> Budget:
        """Cap how much this session may spend. Lives only in this client; every rail counts.

        Pre-flight holds any source whose estimate would cross the cap. Only amounts in the budget's
        currency count towards it.

        Args:
            limit: The most this session may spend.
            currency: The currency of ``limit`` when it is a number.

        Returns:
            The ``Budget``."""
        m = limit if isinstance(limit, Money) else Money.of(limit, currency)
        spent = self.budget.spent if self.budget and self.budget.spent.currency == m.currency else Money(currency=m.currency)
        self.budget = Budget(limit=m, spent=spent)
        return self.budget

    # -- compose ----------------------------------------------------------------------------
    def search(self, query: str, sources: Iterable | None = None, *, limit: int = 5, similarity_threshold: float = 0.5,
               history: list[Message] | None = None, filters: dict[str, Any] | None = None,
               max_sources: int | None = None) -> SearchPlan:
        """Compose a search. Free and synchronous; nothing is sent.

        ``await plan.preflight()`` shows what it will cost; ``await plan.execute()`` sends it. Without
        ``sources`` the search runs over free endpoints the Hub ranks for the query.

        Args:
            query: The question to send to every source.
            sources: Which endpoints to ask: an ``EndpointList``, ``Endpoint`` objects, ``owner/slug`` paths or
                ``collective/name``. Leave empty for free sources only.
            limit: How many passages to ask each source for.
            similarity_threshold: Drop passages scoring below this, from 0 to 1.
            history: Earlier turns to send along; pass ``chat.history`` to let the Spaces see the thread.
            filters: Metadata filters, same syntax as ``plan.filter(...)``.
            max_sources: Cap for the default free sources. Defaults to ``Options.max_sources``.

        Returns:
            A ``SearchPlan``."""
        return SearchPlan(self, query, sources, limit=limit, threshold=similarity_threshold, history=history,
                          filters=filters, max_sources=max_sources)

    def chat(self, models, *, sources: Iterable | None = None, via: Via | str = Via.DIRECT, limit: int = 5) -> Chat:
        """Open a chat with one model or several, without searching first. Free and synchronous.

        With ``sources``, every message searches those sources first and the passages become the models'
        context. Pre-flight runs on the first ``await`` (``preflight`` or ``send``).

        Args:
            models: One model path, a list of them, or ``Endpoint`` objects.
            sources: Endpoints to search before each message.
            via: Ask each model's Space directly, or go through the Aggregator (route proposed).
            limit: How many passages each search asks for.

        Returns:
            A ``Chat``."""
        return Chat(self, models, list(sources) if sources else None, via=via, limit=limit)

    async def aggregate(self, query: str, *, sources: Iterable, model: Endpoint | str, limit: int = 5) -> Answer:
        """Option 1 of the Aggregator proposal: one request, the Aggregator fans out.

        Pre-flight runs here first, so held sources are never sent. Any payment a Space asks for comes back
        on ``answer.pending`` with a ``job_id``; pay, then ``await answer.resume()``.

        Args:
            query: The question.
            sources: Endpoints to ask.
            model: The model the Aggregator should answer with.
            limit: Passages per source.

        Returns:
            An ``Answer``.

        Raises:
            AggregatorError: When the route is missing or fails."""
        plan = await self.search(query, sources, limit=limit).preflight()
        return await self._aggregator.from_sources(query, [r.endpoint for r in plan.sending], model, limit=limit)

    # -- tokens -----------------------------------------------------------------------------
    async def _token(self, owner: str, resource: str) -> str:
        guest = self.me is None
        tok = self._tokens.get(owner, resource, guest)
        if tok is None:
            tok, ttl = await self._t.hub_token(owner, resource, guest=guest)
            self._tokens.put(owner, resource, guest, tok, ttl)
            log.debug("minted satellite token for %s @ %s (%s)", owner, resource, "guest" if guest else self.me.username)
        return tok

    async def _token_for(self, ep: Endpoint) -> str:
        return await self._token(ep.owner_username, ep.url)

    # -- budget -----------------------------------------------------------------------------
    def _spend(self, amount: Money | None) -> None:
        if self.budget is not None and amount and amount.currency == self.budget.limit.currency:
            self.budget = self.budget.model_copy(update={"spent": self.budget.spent + amount})

    async def _pay_mpp(self, c: Charge) -> str:
        if self.me is None:
            raise NotLoggedIn("MPP charges are paid from your Hub wallet: sign in first")
        if self.budget is not None and c.amount.currency == self.budget.limit.currency and c.amount > self.budget.remaining:
            raise BudgetExceeded(c.amount, self.budget.remaining)
        return await self._t.hub_wallet_pay(c.www_authenticate, c.endpoint.slug, float(c.amount.amount))

    # -- the wire, with retries, breaker and logging -----------------------------------------
    async def _call_space(self, ep: Endpoint, body: dict[str, Any], x_payment: str | None) -> tuple[Response | None, str | None, Reason | None, int, str | None]:
        """One logical call: (response, error text, failure reason, attempts, note)."""
        pol, host = self.options.retries, ep.url
        if self._breaker.is_open(host):
            return None, f"{host}: circuit open", Reason.CIRCUIT_OPEN, 0, "circuit open, not sent"
        attempts, started, note, reminted, waited = 0, self._t.now(), None, False, False
        resp: Response | None = None
        err: tuple[str, Reason] | None = None
        while True:
            attempts += 1
            token = await self._token_for(ep)
            log.debug("POST %s/api/v1/endpoints/%s/query attempt %d headers=%s", host, ep.slug, attempts,
                      redact({"Authorization": f"Bearer {token}", "X-Payment": x_payment or "", "User-Agent": self.user_agent}))
            try:
                async with self._sem:
                    resp = await self._t.space_query(host, ep.slug, token=token, body=body, x_payment=x_payment)
                err = None
            except ConnectionError as e:
                resp, err = None, (str(e), Reason.UNREACHABLE)
            except asyncio.TimeoutError:
                resp, err = None, (f"{host}: timed out after {self.options.timeout.read}s", Reason.TIMEOUT)
            elapsed = self._t.now() - started
            can_retry = attempts < pol.max_attempts and elapsed < pol.max_elapsed
            if err is not None and pol.on_network and can_retry:
                await self._t.sleep(pol.delay(attempts)); continue
            if resp is not None and resp.status in pol.on_status and can_retry:
                await self._t.sleep(pol.delay(attempts)); continue
            if resp is not None and resp.status == 401 and not reminted:
                self._tokens.drop(ep.owner_username, ep.url, self.me is None); reminted = True; continue
            if resp is not None and resp.status == 403 and not waited:
                reset = _rate_limit(resp.body).reset_seconds if _rate_limit(resp.body) else None
                if reset is not None and reset <= pol.rate_limit_wait:
                    note = f"waited {reset}s for the rate limit to reset"
                    await self._t.sleep(reset); waited = True; continue
            break
        ok = resp is not None and resp.status < 500
        self._breaker.record(host, ok)
        if err is not None:
            return None, err[0], err[1], attempts, note
        if resp.status >= 500:
            return resp, f"HTTP {resp.status} after {attempts} attempts", Reason.SERVER_ERROR, attempts, note
        return resp, None, None, attempts, note

    async def _query_source(self, ep: Endpoint, query: str, limit: int, threshold: float, history: list[Message], *,
                            x_payment: str | None = None, max_tokens: int | None = None,
                            messages: list[dict[str, str]] | None = None, filters: dict[str, Any] | None = None) -> SourceResult:
        split = split_filters(filters or {}, ep.filterable)
        body: dict[str, Any] = {"messages": messages if messages is not None else [m.wire() for m in history] + [{"role": "user", "content": query}],
                                "limit": limit, "similarity_threshold": threshold}
        if max_tokens is not None or ep.type.returns_summary:
            body["max_tokens"] = max_tokens or 300
        if split.remote:
            body["filters"] = to_space_filters(split.remote)      # PROPOSED field; only for Spaces that advertise the field
        t0 = time.perf_counter()
        resp, error, reason, attempts, note = await self._call_space(ep, body, x_payment)
        ms = int((time.perf_counter() - t0) * 1000)
        if resp is None:
            return SourceResult(endpoint=ep, outcome=Outcome.FAILED, reason=reason, error=error, attempts=attempts,
                                elapsed_ms=ms, request=body, note=note, local_filters=split.local, remote_filters=split.remote)
        row = await self._row(ep, resp.status, resp.body, resp.headers, elapsed_ms=ms, attempts=attempts, request=body,
                              note=note, error=error if reason is Reason.SERVER_ERROR else None)
        return row.model_copy(update={"local_filters": split.local, "remote_filters": split.remote})

    async def _row(self, ep: Endpoint, status: int, body: dict[str, Any], headers: dict[str, str], *, elapsed_ms: int,
                   attempts: int, request: dict[str, Any] | None = None, note: str | None = None,
                   error: str | None = None) -> SourceResult:
        """Classify one Space response into a row, attaching the action it calls for."""
        outcome, reason = _classify(status, body)
        if error and status >= 500:
            outcome, reason = Outcome.FAILED, Reason.SERVER_ERROR
        row = SourceResult(endpoint=ep, status_code=status, raw=body, outcome=outcome, reason=reason, elapsed_ms=elapsed_ms,
                           attempts=attempts, request=request or {}, note=note, error=error, rate_limit=_rate_limit(body))
        if row.ok:
            self._spend(row.cost)
        elif reason is Reason.NO_CREDITS:
            rej = next((e for e in row.policy_metadata.get("entries", []) if e.get("status") == "rejected"), {})
            wallet = await self.wallets.for_endpoint(ep)
            need = Money.of(rej["amount"], rej.get("currency") or ep.pricing.currency) if rej.get("amount") is not None else None
            row = row.model_copy(update={"topup": TopUp(endpoint=ep, wallet=wallet, needed=need, waiting=(ep.path,))})
        elif outcome is Outcome.PAYMENT_REQUIRED:
            rej = next((e for e in row.policy_metadata.get("entries", []) if e.get("status") == "rejected"), {})
            amt = Money.of(rej.get("amount", ep.pricing.price.amount), rej.get("currency") or "USD")
            row = row.model_copy(update={"charge": Charge(endpoint=ep, amount=amt, www_authenticate=headers.get("WWW-Authenticate", ""))})
        return row

    async def _execute(self, plan: SearchPlan, *, ignore_budget: bool = False) -> Results:
        t0 = time.perf_counter()

        async def one(row) -> SourceResult:
            send = row.send or (ignore_budget and row.hold_reason is Reason.OVER_BUDGET)
            if send:
                return await self._query_source(row.endpoint, plan.query, plan.limit, plan.threshold, plan.history,
                                                filters=plan.filters)
            r = SourceResult(endpoint=row.endpoint, outcome=Outcome.HELD, reason=row.hold_reason, predicted=True, note=row.note)
            if row.hold_reason is Reason.NO_CREDITS and row.wallet is not None:
                r = r.model_copy(update={"topup": TopUp(endpoint=row.endpoint, wallet=row.wallet, needed=row.estimate,
                                                        waiting=(row.endpoint.path,))})
            return r

        rows = await asyncio.gather(*(one(r) for r in plan.rows))
        res = Results(self, plan.query, rows, limit=plan.limit, threshold=plan.threshold, history=plan.history,
                      estimate=plan.estimate, filters=plan.filters, note=plan.note)
        log.info('search "%s": %d returned, %d held, %d rejected, %d failed, %d waiting · %.1fs', plan.query, res.ok_count,
                 sum(r.outcome is Outcome.HELD for r in rows), sum(r.outcome is Outcome.REJECTED for r in rows),
                 sum(r.outcome is Outcome.FAILED for r in rows), sum(r.outcome is Outcome.PAYMENT_REQUIRED for r in rows),
                 time.perf_counter() - t0)
        return res

    def __repr__(self) -> str:
        who = self.me.username if self.me else "guest"
        return f"AsyncHub({self.url}, {who})"


def _rate_limit(body: dict[str, Any]) -> RateLimit | None:
    for e in (body.get("policy_metadata") or {}).get("entries", []):
        if e.get("reason_code") == "RATE_LIMITED":
            d = e.get("details") or {}
            return RateLimit(limit=d.get("limit"), remaining=d.get("remaining"), reset_seconds=d.get("reset_seconds"))
    return None


def _classify(status: int, body: dict[str, Any]) -> tuple[Outcome, Reason | None]:
    if status == 200:
        return Outcome.RETURNED, None
    if status == 404:
        return Outcome.FAILED, Reason.NOT_FOUND
    if status == 401:
        return Outcome.FAILED, Reason.AUTH
    if status >= 500:
        return Outcome.FAILED, Reason.SERVER_ERROR
    pm = body.get("policy_metadata") or {}
    codes = {e.get("reason_code") for e in pm.get("entries", [])} - {None}
    if status == 402 or "PAYMENT_REQUIRED" in codes:
        return Outcome.PAYMENT_REQUIRED, None
    for code, why in (("INSUFFICIENT_BALANCE", Reason.NO_CREDITS), ("RATE_LIMITED", Reason.RATE_LIMITED),
                      ("ACCESS_DENIED", Reason.ACCESS_DENIED), ("NO_PRICING_TIER", Reason.NO_PRICING_TIER)):
        if code in codes:
            return Outcome.REJECTED, why
    return Outcome.REJECTED, Reason.BLOCKED
