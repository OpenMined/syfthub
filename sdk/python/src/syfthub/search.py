"""``hub.search``: compose a ``SearchPlan``, pre-flight it, execute it.

Two layers. The rules (which rows send, which are held, which actions they raise) are pure
functions over ``Facts``, a snapshot of everything pre-flight reads fresh, so they can be tested
without a network. ``Searcher`` gathers those facts from the Hub and the Spaces, sends the
queries, and is the ``SearchPort`` the ``SearchPlan`` and ``Results`` models call through.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pydantic
from pydantic import BaseModel, ConfigDict, Field

from ._transport import TransportError
from .errors import ActionRequired, AuthError, PaymentFailed, ValidationError
from .models.enums import Health, Outcome, Rail, Reason, Verdict
from .models.money import Money
from .models.results import Results, SourceResult
from .models.search import (
    AccessDenied,
    AnyAction,
    CircuitOpen,
    OverBudget,
    PlanRow,
    Preflight,
    SearchPlan,
    TopUp,
    as_path,
)
from .models.session import Budget
from .models.sources import Source, SourceList
from .models.wallets import Wallet
from .results import body_of, classify, entries_of, mpp_charge, query_body, topup_steps

if TYPE_CHECKING:
    from ._api.hub import HubApi
    from ._api.space import SpaceApi
    from ._transport import Breakers
    from .auth import AuthNamespace, Session, TokenCache
    from .models.session import Options
    from .sources import SourcesNamespace
    from .wallets import WalletsNamespace

log = logging.getLogger("syfthub")


# ── the pure rules ────────────────────────────────────────────────────────


class Facts(BaseModel):
    """What pre-flight reads fresh, in one object: the inputs to the rules."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    sources: tuple[Source, ...] = ()
    email: str | None = None
    wallets: dict[str, Wallet] = Field(default_factory=dict)  # by source path
    balance_errors: dict[str, str] = Field(default_factory=dict)  # by wallet id
    circuits: dict[str, datetime] = Field(default_factory=dict)  # open host -> reopens_at
    budget: Budget = Budget()


def _row(plan: SearchPlan, source: Source, facts: Facts) -> PlanRow:
    if source.path in plan.skips:
        return PlanRow(source=source, verdict=Verdict.SKIPPED, reason=Reason.BY_USER)
    host = source.host
    if not source.reachable or host is None:
        return PlanRow(
            source=source,
            verdict=Verdict.UNREACHABLE,
            reason=Reason.UNREACHABLE,
            note=f"no HTTP origin published: {source.space_url or 'none'}",
        )
    access = source.access(facts.email)
    if not access.allowed:
        return PlanRow(
            source=source,
            verdict=Verdict.ACCESS_DENIED,
            reason=Reason.ACCESS_DENIED,
            note=access.rule,
        )
    reopens = facts.circuits.get(host)
    if reopens is not None:
        return PlanRow(
            source=source,
            verdict=Verdict.CIRCUIT_OPEN,
            reason=Reason.CIRCUIT_OPEN,
            note=f"{host} is open until {reopens.isoformat(timespec='seconds')}",
        )
    verdict, estimate, wallet, note = Verdict.READY, Money(), None, None
    pricing = source.pricing
    if pricing is not None and not pricing.free and pricing.applies_to(facts.email):
        estimate = pricing.estimate(plan.limit)
        if pricing.rail is Rail.MPP:
            verdict, note = Verdict.WILL_ASK_TO_PAY, "MPP: the Space issues the charge"
        else:
            wallet = facts.wallets.get(source.path)
            if wallet is None:
                note = "prepaid policy publishes no credits_url; the Space decides"
            elif wallet.balance is None:
                note = facts.balance_errors.get(wallet.id) or "balance unknown"
    if verdict is Verdict.READY and source.health is Health.UNHEALTHY:
        verdict, note = Verdict.UNHEALTHY, "last Hub health check failed"
    return PlanRow(source=source, verdict=verdict, estimate=estimate, wallet=wallet, note=note)


def _hold_for_credits(rows: list[PlanRow]) -> tuple[list[PlanRow], dict[str, Money]]:
    """Per wallet: the sum of the estimates it would carry against its balance. Short by any
    amount, every row on that wallet is held and one shortfall is reported."""
    committed: dict[str, Money] = {}
    for row in rows:
        if row.send and row.wallet is not None and row.wallet.balance is not None:
            if row.estimate.currency != row.wallet.balance.currency:
                continue
            total = committed.get(row.wallet.id)
            committed[row.wallet.id] = total + row.estimate if total else row.estimate
    shortfalls: dict[str, Money] = {}
    out: list[PlanRow] = []
    for row in rows:
        wallet = row.wallet
        if row.send and wallet is not None and wallet.id in committed:
            balance = wallet.balance
            assert balance is not None
            total = committed[wallet.id]
            if balance < total:
                shortfalls[wallet.id] = total - balance
                row = row.model_copy(
                    update={
                        "verdict": Verdict.NEEDS_CREDITS,
                        "reason": Reason.NO_CREDITS,
                        "note": f"wallet {wallet.key} holds {balance}, this plan needs {total}",
                    }
                )
        out.append(row)
    return out, shortfalls


def _hold_for_budget(rows: list[PlanRow], budget: Budget) -> tuple[list[PlanRow], dict[str, Money]]:
    """Walk the sending rows in plan order, per currency: the first paid row that would cross its
    currency's cap and every paid row in that currency after it are held. A currency with no cap
    is not budgeted. Returns, for each currency that crossed, what its paid rows would have cost."""
    if not budget.capped:
        return rows, {}
    running: dict[str, Money] = {}
    total: dict[str, Money] = {}
    crossed: set[str] = set()
    out: list[PlanRow] = []
    for row in rows:
        if row.send and row.estimate.positive and budget.counts(row.estimate):
            cur = row.estimate.currency
            total[cur] = total[cur] + row.estimate if cur in total else row.estimate
            so_far = running.get(cur) or Money.zero(cur)
            if cur in crossed or not budget.allows(so_far + row.estimate):
                crossed.add(cur)
                row = row.model_copy(
                    update={
                        "verdict": Verdict.OVER_BUDGET,
                        "reason": Reason.OVER_BUDGET,
                        "note": f"estimate {row.estimate} would exceed the {cur} budget",
                    }
                )
            else:
                running[cur] = so_far + row.estimate
        elif row.send and row.estimate.positive:
            row = row.model_copy(
                update={"note": f"no budget set for {row.estimate.currency}; not capped"}
            )
        out.append(row)
    return out, {cur: t for cur, t in total.items() if cur in crossed}  # plan order


def _actions(
    rows: list[PlanRow], shortfalls: dict[str, Money], over: dict[str, Money], facts: Facts
) -> list[AnyAction]:
    actions: list[AnyAction] = []
    for wallet_id, shortfall in shortfalls.items():
        affected = [r for r in rows if r.wallet is not None and r.wallet.id == wallet_id]
        wallet = affected[0].wallet
        assert wallet is not None
        suggested = wallet.suggest(shortfall)
        actions.append(
            TopUp(
                wallet=wallet,
                shortfall=shortfall,
                bundles=wallet.bundles,
                suggested=suggested,
                affects=tuple(r.source for r in affected),
                steps=topup_steps(wallet, suggested),
            )
        )
    for cur, total in over.items():
        over_rows = [
            r for r in rows if r.verdict is Verdict.OVER_BUDGET and r.estimate.currency == cur
        ]
        actions.append(
            OverBudget(
                estimate=total,
                budget=facts.budget,
                affects=tuple(r.source for r in over_rows),
                steps=(
                    f'hub.set_budget({{"{cur}": x}}) with x covering {total} plus what is '
                    f"spent in {cur}, then plan.execute() again",
                    "or plan.skip(*action.paths) to leave these sources out",
                ),
            )
        )
    by_rule: dict[str | None, list[PlanRow]] = {}
    for r in rows:
        if r.verdict is Verdict.ACCESS_DENIED:
            by_rule.setdefault(r.note, []).append(r)
    for rule, denied in by_rule.items():
        actions.append(
            AccessDenied(
                rule=rule,
                affects=tuple(r.source for r in denied),
                steps=("plan.skip(*action.paths); the Space would refuse these",),
            )
        )
    by_host: dict[str, list[PlanRow]] = {}
    for r in rows:
        if r.verdict is Verdict.CIRCUIT_OPEN and r.source.host:
            by_host.setdefault(r.source.host, []).append(r)
    for host, held in by_host.items():
        actions.append(
            CircuitOpen(
                reopens_at=facts.circuits[host],
                affects=tuple(r.source for r in held),
                steps=(
                    f"wait until {facts.circuits[host].isoformat(timespec='seconds')} and "
                    "plan.execute() again",
                    "or plan.skip(*action.paths)",
                ),
            )
        )
    return actions


def plan_preflight(plan: SearchPlan, facts: Facts) -> Preflight:
    """The rules, in order: skips, reachability, access, circuit, credits, budget, health."""
    rows = [_row(plan, s, facts) for s in facts.sources]
    rows, shortfalls = _hold_for_credits(rows)
    rows, over = _hold_for_budget(rows, facts.budget)
    estimate: dict[str, Money] = {}
    for row in rows:
        if row.send and row.estimate.positive:
            cur = row.estimate.currency
            estimate[cur] = estimate[cur] + row.estimate if cur in estimate else row.estimate
    return Preflight(
        rows=tuple(rows),
        actions=tuple(_actions(rows, shortfalls, over, facts)),
        estimate=estimate,
        budget=facts.budget,
    )


def pick_sources(
    candidates: Iterable[Source], plan: SearchPlan, email: str | None
) -> tuple[Source, ...]:
    """For a plan without explicit sources: free, reachable document sources the caller may use,
    ``max_sources`` of them. Skipped ones are kept so they show as ``SKIPPED`` rows."""
    picked: list[Source] = []
    active = 0
    for source in candidates:
        if active >= plan.max_sources:
            break
        if not (source.free and source.reachable and source.type.returns_documents):
            continue
        if not source.access(email).allowed:
            continue
        picked.append(source)
        if source.path not in plan.skips:
            active += 1
    return tuple(picked)


def paths_of(sources: Iterable[str | Source] | SourceList | None) -> tuple[str, ...]:
    if sources is None:
        return ()
    if isinstance(sources, (str, Source)):
        sources = (sources,)
    return tuple(dict.fromkeys(as_path(s) for s in sources))


# ── the runner ────────────────────────────────────────────────────────────


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
        hub: Any,
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
        self._hub = hub

    # ── compose ───────────────────────────────────────────────────────────

    def compose(
        self,
        query: str,
        sources: Iterable[str | Source] | SourceList | None = None,
        *,
        limit: int = 5,
        similarity_threshold: float = 0.5,
        include_metadata: bool = True,
        max_sources: int = 10,
    ) -> SearchPlan:
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
            rows[row.path] = SourceResult(
                source=row.source,
                outcome=Outcome.HELD,
                reason=row.reason,
                topup=topup,
                error=row.note,
            )
        rows.update(await self._send_all(pre.sending, plan))
        ordered = tuple(rows[r.path] for r in pre.rows)
        actions = tuple(pre.actions) + self._actions_after(ordered, pre)
        results = Results(rows=ordered, plan=plan, actions=actions)
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
            wallet = await self._wallets.for_source(s)
            if wallet is not None:
                wallets[s.path] = wallet
        errors: dict[str, str] = {}

        async def read(wallet: Wallet) -> None:
            try:
                await wallet.refresh()
            except (PaymentFailed, AuthError) as e:
                wallet.balance = None
                errors[wallet.id] = f"balance unavailable: {e}"

        await asyncio.gather(*(read(w) for w in {w.id: w for w in wallets.values()}.values()))
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
            budget=self._hub.budget,
        )

    async def _email(self) -> str | None:
        if self._auth.me is None and self._session.authenticated:
            await self._auth.whoami()
        return self._auth.me.email or None if self._auth.me else None

    async def _candidates(self, plan: SearchPlan, email: str | None) -> tuple[Source, ...]:
        if plan.explicit:
            resolved = await self._sources.resolve(plan.sources)
            return tuple(resolved[p] for p in plan.sources)
        listing = await self._sources.search(plan.query, top_k=max(plan.max_sources * 2, 10))
        return pick_sources(listing, plan, email)

    # ── send ──────────────────────────────────────────────────────────────

    async def _send_all(
        self, rows: tuple[PlanRow, ...], plan: SearchPlan
    ) -> dict[str, SourceResult]:
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
                        out[row.path] = SourceResult(
                            source=row.source,
                            outcome=Outcome.HELD,
                            reason=Reason.CIRCUIT_OPEN,
                            error=f"{host}: the probe to {probe.path} failed",
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
        source = row.source
        url, host = source.query_url, source.host
        assert url is not None and host is not None  # pre-flight sends only reachable rows
        request = {"method": "POST", "url": url, "json": body, "tenant": source.tenant}
        started = time.monotonic()
        attempts = 0
        charge = None
        async with sem:
            try:
                token = await self._tokens.get(source.owner_username, url)
            except ValidationError as e:
                return self._failed(source, Reason.AUTH, str(e), request, attempts, started)
            try:
                attempts += 1
                response = await self._space.query(url, token, body, tenant=source.tenant)
                if response.status_code == 401:
                    self._tokens.forget(source.owner_username, url)
                    token = await self._tokens.get(source.owner_username, url)
                    attempts += 1
                    response = await self._space.query(url, token, body, tenant=source.tenant)
                if response.status_code == 402 and response.headers.get("www-authenticate"):
                    charge = mpp_charge(source, response, row.estimate)
                    if not self._hub.budget.allows(charge.amount):
                        return self._payment_required(
                            source,
                            charge,
                            Reason.OVER_BUDGET,
                            f"charge {charge.amount} would exceed the {charge.amount.currency} budget",
                            request,
                            attempts,
                            started,
                            response,
                        )
                    try:
                        credential = await self._hub_api.pay_mpp(
                            charge.www_authenticate, source.slug
                        )
                    except PaymentFailed as e:
                        return self._payment_required(
                            source, charge, None, str(e), request, attempts, started, response
                        )
                    attempts += 1
                    response = await self._space.query(
                        url, token, body, tenant=source.tenant, x_payment=credential
                    )
                    if response.status_code < 300:
                        self._hub._record_spend(charge.amount)
            except TransportError as e:
                self._breakers.failure(host)
                return self._failed(
                    source, e.reason, str(e), request, attempts + e.attempts - 1, started
                )
        if response.status_code >= 500:
            self._breakers.failure(host)
        else:
            self._breakers.success(host)
        result = classify(
            source,
            response,
            wallet=row.wallet,
            estimate=row.estimate,
            charge=charge,
            request=request,
            attempts=attempts,
            elapsed_ms=_elapsed(started),
        )
        if result.ok and charge is None and result.cost is not None and result.cost.positive:
            self._hub._record_spend(result.cost)
        return result

    @staticmethod
    def _failed(
        source: Source,
        reason: Reason,
        error: str,
        request: dict[str, Any],
        attempts: int,
        started: float,
    ) -> SourceResult:
        return SourceResult(
            source=source,
            outcome=Outcome.FAILED,
            reason=reason,
            error=error,
            request=request,
            attempts=attempts,
            elapsed_ms=_elapsed(started),
        )

    @staticmethod
    def _payment_required(
        source: Source,
        charge: Any,
        reason: Reason | None,
        error: str,
        request: dict[str, Any],
        attempts: int,
        started: float,
        response: Any,
    ) -> SourceResult:
        body = body_of(response)
        return SourceResult(
            source=source,
            outcome=Outcome.PAYMENT_REQUIRED,
            reason=reason,
            status_code=response.status_code,
            charge=charge,
            charges=entries_of(source, body),
            rail=Rail.MPP,
            error=error,
            request=request,
            attempts=attempts,
            elapsed_ms=_elapsed(started),
            raw=body,
        )

    # ── after ─────────────────────────────────────────────────────────────

    def _actions_after(
        self, rows: tuple[SourceResult, ...], pre: Preflight
    ) -> tuple[AnyAction, ...]:
        """Actions the Spaces raised during the send, on top of pre-flight's."""
        actions: list[AnyAction] = []
        by_wallet: dict[str, list[SourceResult]] = {}
        for r in rows:
            if r.outcome is Outcome.REJECTED and r.reason is Reason.NO_CREDITS and r.topup:
                by_wallet.setdefault(r.topup.wallet.id, []).append(r)
        for group in by_wallet.values():
            first = group[0].topup
            assert first is not None
            shortfall = first.shortfall
            for r in group[1:]:
                assert r.topup is not None
                if r.topup.shortfall > shortfall:
                    shortfall = r.topup.shortfall
            suggested = first.wallet.suggest(shortfall)
            actions.append(
                first.model_copy(
                    update={
                        "shortfall": shortfall,
                        "suggested": suggested,
                        "affects": tuple(r.source for r in group),
                        "steps": topup_steps(first.wallet, suggested),
                    }
                )
            )
        by_currency: dict[str, list[SourceResult]] = {}
        for r in rows:
            if (
                r.outcome is Outcome.PAYMENT_REQUIRED
                and r.reason is Reason.OVER_BUDGET
                and r.charge
            ):
                by_currency.setdefault(r.charge.amount.currency, []).append(r)
        for cur, over in by_currency.items():
            total = Money.zero(cur)
            for r in over:
                assert r.charge is not None
                total = total + r.charge.amount
            actions.append(
                OverBudget(
                    estimate=total,
                    budget=self._hub.budget,
                    affects=tuple(r.source for r in over),
                    steps=(
                        f'hub.set_budget({{"{cur}": x}}) with x covering {total} plus what is '
                        f"spent in {cur}, then plan.execute() again",
                        "or plan.skip(*action.paths)",
                    ),
                )
            )
        pre_held = {r.path for r in pre.held}
        by_host: dict[str, list[SourceResult]] = {}
        for r in rows:
            if (
                r.outcome is Outcome.HELD
                and r.reason is Reason.CIRCUIT_OPEN
                and r.path not in pre_held
                and r.source.host
            ):
                by_host.setdefault(r.source.host, []).append(r)
        for host, held in by_host.items():
            reopens = self._breakers.reopens_at(host) or datetime.now(timezone.utc)
            actions.append(
                CircuitOpen(
                    reopens_at=reopens,
                    affects=tuple(r.source for r in held),
                    steps=(
                        "wait for the cooldown and plan.execute() again",
                        "or plan.skip(*action.paths)",
                    ),
                )
            )
        return tuple(actions)

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


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


__all__ = ["Facts", "Searcher", "paths_of", "pick_sources", "plan_preflight"]
