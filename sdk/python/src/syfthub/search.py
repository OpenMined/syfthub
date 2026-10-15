"""``hub.search``: compose a ``SearchPlan``, pre-flight it, execute it.

``Searcher`` is the runner: it gathers ``Facts`` for the rules in ``preflight``, sends the queries
host by host, classifies each answer, and is the ``SearchPort`` the ``SearchPlan`` and
``Results`` models call through. ``AsyncHub`` owns one.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
import pydantic
from pydantic import BaseModel, ConfigDict

from .actions import actions_after
from .classify import body_of, classify, entries_of, mpp_charge, query_body
from .errors import ActionRequired, AuthError, PaymentFailed, TransportError, ValidationError
from .models.enums import Outcome, Rail, Reason, Verdict
from .models.ports import HubPorts
from .models.results import Results, SourceResult
from .models.search import PlanRow, Preflight, SearchPlan, TopUp
from .models.session import Ledger
from .models.sources import Source, SourceList
from .models.wallets import Charge, Wallet
from .preflight import Facts, paths_of, pick_sources, plan_preflight

if TYPE_CHECKING:
    from ._api.hub import HubApi
    from ._api.space import SpaceApi
    from ._transport import Breakers
    from .auth import AuthNamespace, Session, TokenCache
    from .models.session import Options
    from .sources import SourcesNamespace
    from .wallets import WalletsNamespace

log = logging.getLogger("syfthub")


class _Attempt(BaseModel):
    """One row's send, as it unfolds: what every way out of it reports on the row."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    row: PlanRow
    url: str
    host: str
    body: dict[str, Any]
    started: float
    attempts: int = 0
    charge: Charge | None = None

    @property
    def source(self) -> Source:
        return self.row.source

    @property
    def request(self) -> dict[str, Any]:
        return {"method": "POST", "url": self.url, "json": self.body, "tenant": self.source.tenant}

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def failed(self, reason: Reason, error: str, *, extra_attempts: int = 0) -> SourceResult:
        return SourceResult(
            source=self.source,
            outcome=Outcome.FAILED,
            reason=reason,
            error=error,
            request=self.request,
            attempts=self.attempts + extra_attempts,
            elapsed_ms=self.elapsed_ms,
        )

    def payment_required(
        self, reason: Reason | None, error: str, response: httpx.Response
    ) -> SourceResult:
        body = body_of(response)
        return SourceResult(
            source=self.source,
            outcome=Outcome.PAYMENT_REQUIRED,
            reason=reason,
            status_code=response.status_code,
            charge=self.charge,
            charges=entries_of(self.source, body),
            rail=Rail.MPP,
            error=error,
            request=self.request,
            attempts=self.attempts,
            elapsed_ms=self.elapsed_ms,
            raw=body,
        )


class Searcher:
    """Gathers ``Facts``, applies the rules, sends the queries. ``AsyncHub`` owns one."""

    def __init__(
        self,
        *,
        hub_api: HubApi,
        space: SpaceApi,
        tokens: TokenCache,
        sources: SourcesNamespace,
        wallets: WalletsNamespace,
        auth: AuthNamespace,
        session: Session,
        breakers: Breakers,
        options: Options,
        ledger: Ledger,
        hub: HubPorts,
    ) -> None:
        self._hub_api = hub_api
        self._space = space
        self._tokens = tokens
        self._sources = sources
        self._wallets = wallets
        self._auth = auth
        self._session = session
        self._breakers = breakers
        self._options = options
        self._ledger = ledger
        self._hub = hub  # what plans and results are bound to

    # ── compose ───────────────────────────────────────────────────────────

    def compose(
        self,
        query: str,
        sources: Iterable[str | Source] | SourceList | None = None,
        *,
        limit: int = 5,
        similarity_threshold: float = 0.5,
        include_metadata: bool = True,
        max_sources: int | None = None,
    ) -> SearchPlan:
        """A validated, bound ``SearchPlan``. No network: the plan is a value until pre-flight."""
        try:
            plan = SearchPlan(
                query=query,
                sources=paths_of(sources),
                limit=limit,
                similarity_threshold=similarity_threshold,
                include_metadata=include_metadata,
                max_sources=max_sources,
            )
        except pydantic.ValidationError as e:
            raise ValidationError(str(e)) from e
        plan._bind(self._hub)
        return plan

    # ── SearchPort ────────────────────────────────────────────────────────

    async def preflight(self, plan: SearchPlan) -> Preflight:
        return plan_preflight(plan, await self.facts(plan))

    async def execute(self, plan: SearchPlan, *, strict: bool = False) -> Results:
        pre = await self.preflight(plan)
        plan._pre = pre
        if strict and pre.actions:
            raise ActionRequired(pre.actions)
        if pre.sending and not self._session.authenticated:
            raise AuthError("log in first: Spaces accept only a SyftHub satellite token")
        topups = {a.wallet.id: a for a in pre.actions if isinstance(a, TopUp)}
        rows: dict[str, SourceResult] = {}
        for row in pre.held:
            topup = (
                topups.get(row.wallet.id)
                if row.wallet is not None and row.verdict is Verdict.NEEDS_CREDITS
                else None
            )
            rows[row.path] = _held(row.source, row.reason, row.note, topup)
        rows.update(await self._send_all(pre.sending, plan))
        ordered = tuple(rows[r.path] for r in pre.rows)
        after = actions_after(ordered, pre, self._ledger.budget, self._breakers.reopens_at)
        results = Results(rows=ordered, plan=plan, actions=tuple(pre.actions) + after)
        results._bind(self._hub)
        self._log(results)
        return results

    # ── facts ─────────────────────────────────────────────────────────────

    async def facts(self, plan: SearchPlan) -> Facts:
        email = await self._email()
        sources = await self._candidates(plan, email)
        wallets: dict[str, Wallet] = {}
        for s in sources:
            if s.path in plan.skips or not s.reachable:
                continue
            pricing = s.pricing
            if (
                pricing is None
                or pricing.free
                or not pricing.rail.prepaid
                or not pricing.applies_to(email)
            ):
                continue
            wallet = self._wallets.wallet_of(s)
            if wallet is not None:
                wallets[s.path] = wallet
        # a host that does not answer holds its rows, see preflight._row
        errors = await self._wallets.read_balances(list(wallets.values()))
        circuits: dict[str, datetime] = {}
        for s in sources:
            host = s.host
            if host:
                at = self._breakers.reopens_at(host)
                if at is not None:
                    circuits[host] = at
        return Facts(
            sources=sources,
            email=email,
            wallets=wallets,
            balance_errors=errors,
            circuits=circuits,
            budget=self._ledger.budget,
        )

    async def _email(self) -> str | None:
        """The caller's email, read once per session; None when anonymous or unset."""
        if self._auth.me is None and self._session.authenticated:
            await self._auth.whoami()
        if self._auth.me is None:
            return None
        return self._auth.me.email or None

    async def _candidates(self, plan: SearchPlan, email: str | None) -> tuple[Source, ...]:
        if plan.explicit:
            resolved = await self._sources.resolve(plan.sources)
            return tuple(resolved[p] for p in plan.sources)
        listing = await self._sources.list()  # the whole public catalogue, not a keyword match
        return pick_sources(listing, plan, email)

    # ── send ──────────────────────────────────────────────────────────────

    async def _send_all(
        self, rows: tuple[PlanRow, ...], plan: SearchPlan
    ) -> dict[str, SourceResult]:
        """Every host in parallel, at most ``Options.concurrency`` queries in flight. A half-open
        host gets one probe first; if the probe trips the breaker the rest of its rows are held."""
        sem = asyncio.Semaphore(self._options.concurrency)
        body = query_body(plan)
        by_host: dict[str, list[PlanRow]] = {}
        for row in rows:
            by_host.setdefault(row.source.host or "", []).append(row)
        out: dict[str, SourceResult] = {}

        async def run_host(host: str, hrows: list[PlanRow]) -> None:
            if self._breakers.half_open(host):
                probe, hrows = hrows[0], hrows[1:]
                out[probe.path] = await self._send_one(probe, body, sem)
                if self._breakers.is_open(host):
                    for row in hrows:
                        out[row.path] = _held(
                            row.source,
                            Reason.CIRCUIT_OPEN,
                            f"{host}: the probe to {probe.path} failed",
                        )
                    return
            sent = await asyncio.gather(*(self._send_one(r, body, sem) for r in hrows))
            for row, result in zip(hrows, sent, strict=True):
                out[row.path] = result

        await asyncio.gather(*(run_host(h, rs) for h, rs in by_host.items()))
        return out

    async def _send_one(
        self, row: PlanRow, body: dict[str, Any], sem: asyncio.Semaphore
    ) -> SourceResult:
        """One row: mint the token, query, re-mint once on a 401, pay once on an MPP 402, then
        classify whatever came back last. Network faults never raise: they are the row."""
        source = row.source
        url, host = source.query_url, source.host
        assert url is not None and host is not None  # pre-flight sends only reachable rows
        at = _Attempt(row=row, url=url, host=host, body=body, started=time.monotonic())
        async with sem:
            try:
                token = await self._tokens.get(source.owner_username, url)
            except ValidationError as e:
                return at.failed(Reason.AUTH, str(e))
            try:
                response = await self._query(at, token)
                if response.status_code == 401:
                    self._tokens.forget(source.owner_username, url)
                    try:
                        token = await self._tokens.get(source.owner_username, url)
                    except ValidationError as e:
                        return at.failed(Reason.AUTH, str(e))
                    response = await self._query(at, token)
                if response.status_code == 402 and response.headers.get("www-authenticate"):
                    paid = await self._pay(at, response)
                    if isinstance(paid, SourceResult):
                        return paid
                    response = await self._query(at, token, x_payment=paid)
            except TransportError as e:
                self._breakers.failure(host, connection=True)
                return at.failed(e.reason, str(e), extra_attempts=e.attempts - 1)
        if response.status_code >= 500:
            self._breakers.failure(host)
        else:
            self._breakers.success(host)
        result = classify(
            source,
            response,
            wallet=row.wallet,
            estimate=row.estimate,
            charge=at.charge,
            request=at.request,
            attempts=at.attempts,
            elapsed_ms=at.elapsed_ms,
        )
        if result.ok and at.charge is None and result.cost is not None and result.cost.positive:
            self._ledger.record(result.cost)
        return result

    async def _query(
        self, at: _Attempt, token: str, *, x_payment: str | None = None
    ) -> httpx.Response:
        at.attempts += 1
        return await self._space.query(
            at.url, token, at.body, tenant=at.source.tenant, x_payment=x_payment
        )

    async def _pay(self, at: _Attempt, challenge: httpx.Response) -> str | SourceResult:
        """Answer an MPP 402 through the Hub: the ``X-Payment`` credential to re-send with, or the
        ``PAYMENT_REQUIRED`` row when the budget or the Hub says no."""
        at.charge = charge = mpp_charge(at.source, challenge, at.row.estimate)
        if not self._ledger.budget.allows(charge.amount):
            return at.payment_required(
                Reason.OVER_BUDGET,
                f"charge {charge.amount} would exceed the {charge.amount.currency} budget",
                challenge,
            )
        try:
            credential = await self._hub_api.pay_mpp(charge.www_authenticate, at.source.slug)
        except PaymentFailed as e:
            return at.payment_required(None, str(e), challenge)
        # The Hub debited the wallet at /wallet/pay: the charge counts from here, whatever the
        # re-send answers.
        self._ledger.record(charge.amount)
        return credential

    @staticmethod
    def _log(results: Results) -> None:
        cost = ", ".join(str(m) for m in results.cost.values()) or "0"
        log.info(
            "search: %d returned, %d failed, %d held, %d payment required; cost %s",
            len(results.ok),
            len(results.failed),
            len(results.held),
            sum(1 for r in results.rows if r.outcome is Outcome.PAYMENT_REQUIRED),
            cost,
        )


def _held(
    source: Source, reason: Reason | None, error: str | None, topup: TopUp | None = None
) -> SourceResult:
    return SourceResult(
        source=source, outcome=Outcome.HELD, reason=reason, topup=topup, error=error
    )


__all__ = ["Searcher"]
