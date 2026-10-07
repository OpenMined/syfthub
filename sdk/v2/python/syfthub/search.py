"""A composed search. Composing is free and synchronous; pre-flight and execute are awaited.

Pre-flight is decided from Hub metadata, one balance call per prepaid wallet, the circuit breakers and
the session budget. Nothing is sent to a Space until ``execute()``."""
from __future__ import annotations

from fnmatch import fnmatch
from typing import TYPE_CHECKING, Any, Iterable

from .errors import InvalidState, ValidationError
from .models import (Endpoint, FilterSplit, Health, Invoice, Message, Money, PlanRow, Rail, Reason, TopUp, Verdict,
                     split_filters, total, validate_filters)

if TYPE_CHECKING:  # pragma: no cover
    from .hub import AsyncHub
    from .results import Results


class SearchPlan:
    """A search that has not been sent. Look at its pre-flight, pay what is short, then ``execute()``.

    ``hub.search(...)`` builds one without touching the network. ``await plan.preflight()`` fills ``rows``
    with the estimated cost per source, your balances and a verdict each. ``await plan.execute()`` sends
    it, running pre-flight first if you skipped it.

    Attributes:
        query: The question that will be sent.
        limit: How many passages each source is asked for.
        threshold: The similarity cut-off, from 0 to 1.
        history: Earlier conversation turns that travel with the query.
        filters: The metadata filters set with ``filter()``.
        kind: ``"search"``, or ``"chat"`` for the pre-flight of a chat's models.
        rows: One ``PlanRow`` per source once pre-flight has run, else ``None``."""

    def __init__(self, hub: "AsyncHub", query: str, sources: Iterable | None, *, limit: int = 5,
                 threshold: float = 0.5, history: list[Message] | None = None, filters: dict[str, Any] | None = None,
                 max_sources: int | None = None, kind: str = "search", max_tokens: int = 300) -> None:
        if limit < 1:
            raise ValidationError(f"limit must be at least 1, got {limit}")
        if not 0.0 <= threshold <= 1.0:
            raise ValidationError(f"similarity_threshold must be between 0 and 1, got {threshold}")
        if not query or not query.strip():
            raise ValidationError("query must not be empty")
        validate_filters(filters or {})
        self._hub = hub
        self.query, self.limit, self.threshold = query, limit, threshold
        self.history: list[Message] = list(history or [])
        self.filters: dict[str, Any] = dict(filters or {})
        self.kind, self.max_tokens = kind, max_tokens
        self.max_sources = max_sources if max_sources is not None else hub.options.max_sources
        self._sources = None if sources is None else list(sources)
        self._endpoints: list[Endpoint] | None = None
        self.rows: list[PlanRow] | None = None
        self.note: str | None = None

    # -- compose ---------------------------------------------------------------------------
    def filter(self, **filters: Any) -> "SearchPlan":
        """Only return passages whose metadata matches. Returns a new plan; pre-flight runs again on it.

        Write each condition as ``field=value`` for an exact match, or add a suffix: ``field_gte``,
        ``field_gt``, ``field_lte``, ``field_lt`` to compare, or ``field_contains`` for a substring.

        A Space that advertises the field as ``filterable`` gets the filter in the request: it filters
        before ``limit`` and bills only the passages it returns. Every other source is filtered here, after
        ``limit``, so raise ``limit`` when you filter hard. The pre-flight table says which happens per
        source. Server-side filtering is PROPOSED; no Space supports it today.

        Args:
            **filters: Conditions such as ``published_gte="2024-01-01"`` or ``author="R. Chitrakoot"``.

        Returns:
            A new ``SearchPlan``."""
        validate_filters(filters)
        plan = SearchPlan(self._hub, self.query, self._sources, limit=self.limit, threshold=self.threshold,
                          history=self.history, filters={**self.filters, **filters}, max_sources=self.max_sources,
                          kind=self.kind, max_tokens=self.max_tokens)
        plan._endpoints = self._endpoints
        return plan

    def filters_for(self, row: PlanRow) -> FilterSplit:
        """How one source's filters split between the Space and this client.

        Args:
            row: The source's pre-flight row.

        Returns:
            A ``FilterSplit`` with ``remote`` and ``local`` dicts."""
        return split_filters(self.filters, row.endpoint.filterable)

    # -- pre-flight ------------------------------------------------------------------------
    @property
    def ready(self) -> bool:
        """``True`` once pre-flight has run."""
        return self.rows is not None

    def _need_rows(self) -> list[PlanRow]:
        if self.rows is None:
            raise InvalidState("pre-flight has not run: await plan.preflight() first (execute() does it for you)")
        return self.rows

    async def endpoints(self) -> list[Endpoint]:
        """The sources, resolved. When none were given: free, healthy data sources the Hub's listing search
        ranks for the query, at most ``max_sources`` of them. Models are never picked implicitly.

        Returns:
            The endpoints."""
        if self._endpoints is None:
            if self._sources is None:
                found = await self._hub.endpoints.search(self.query)
                free = [e for e in found if not e.pricing.paid and e.health is not Health.UNHEALTHY and e.type.returns_references]
                self._endpoints = free[: self.max_sources]
                self.note = (f"no sources given: searching {len(self._endpoints)} free endpoints the Hub ranked for this "
                             f"query; pass sources= to include paid ones")
            else:
                self._endpoints = await self._hub.endpoints.resolve(self._sources)
        return self._endpoints

    async def preflight(self) -> "SearchPlan":
        """Decide, without sending anything, what each source would cost and whether it will be sent.

        Returns:
            This plan, with ``rows`` filled in."""
        eps = await self.endpoints()
        self.rows = await build_rows(self._hub, eps, limit=self.limit)
        return self

    async def refresh(self) -> "SearchPlan":
        """Run pre-flight again, for example after paying.

        Returns:
            This plan."""
        return await self.preflight()

    @property
    def estimate(self) -> dict[str, Money]:
        """The most this search can cost, per currency, if every source that passed pre-flight is sent."""
        return total(r.estimate for r in self.sending if r.estimate)

    @property
    def sending(self) -> list[PlanRow]:
        """The rows that will be sent."""
        return [r for r in self._need_rows() if r.send]

    @property
    def held(self) -> list[PlanRow]:
        """The rows pre-flight holds back, each with its reason."""
        return [r for r in self._need_rows() if not r.send]

    @property
    def pending(self) -> list[TopUp]:
        """One ``TopUp`` per prepaid wallet that is short, each listing the sources waiting on it."""
        return pending_topups(self._need_rows())

    async def top_up(self, wallet_or_path: str, bundle: str) -> Invoice:
        """Buy a credit bundle for a wallet that is short, before executing.

        Args:
            wallet_or_path: A wallet key, or the path of any source waiting on it. Every source behind the
                same wallet is unblocked at once.
            bundle: The bundle id, for example ``"starter"``.

        Returns:
            The ``Invoice``. Pay at its ``checkout_url``; then ``execute()``, which re-checks balances.

        Raises:
            InvalidState: When nothing is waiting on that wallet."""
        for t in self.pending:
            if wallet_or_path in t.waiting or t.wallet.key == wallet_or_path:
                return await t.buy(bundle)
        raise InvalidState(f"{wallet_or_path} is not short of credits in this plan; pending wallets: "
                           f"{[t.wallet.key for t in self.pending] or 'none'}")

    # -- execute ---------------------------------------------------------------------------
    async def execute(self, *, ignore_budget: bool = False) -> "Results":
        """Send the search to every source that passes pre-flight, in parallel.

        Pre-flight runs first (again, if it already ran, so fresh balances count). Held sources become
        rows with their reason and, where it applies, a ``TopUp``.

        Args:
            ignore_budget: Send sources pre-flight held as over budget, this once.

        Returns:
            The ``Results``, one row per source."""
        await self.preflight()
        return await self._hub._execute(self, ignore_budget=ignore_budget)

    def _repr_html_(self) -> str:
        from .notebook import render
        return render.plan_table(self)

    def __repr__(self) -> str:
        if not self.ready:
            n = len(self._sources) if self._sources is not None else "free"
            return f'SearchPlan("{self.query}", {n} sources, not pre-flighted: await plan.preflight())'
        est = " + ".join(str(v) for v in self.estimate.values()) or "free"
        lines = [f'SearchPlan "{self.query}"  est. max {est}  ({len(self.sending)} of {len(self.rows)} will be sent)']
        for r in self.rows:
            lines.append(f"  {r.endpoint.path:<24} {r.endpoint.pricing.label:<32} max {str(r.estimate):<8} "
                         f"{r.verdict.label}{'' if r.send else '  (held)'}")
        return "\n".join(lines)


def pending_topups(rows: Iterable[PlanRow]) -> list[TopUp]:
    out: dict[str, TopUp] = {}
    for r in rows:
        if r.hold_reason is Reason.NO_CREDITS and r.wallet is not None:
            t = out.get(r.wallet.key)
            if t is None:
                out[r.wallet.key] = TopUp(endpoint=r.endpoint, wallet=r.wallet, needed=r.estimate, waiting=(r.endpoint.path,))
            else:
                out[r.wallet.key] = t.model_copy(update={"needed": (t.needed or Money(currency=r.estimate.currency)) + r.estimate,
                                                         "waiting": t.waiting + (r.endpoint.path,)})
    return list(out.values())


async def build_rows(hub: "AsyncHub", eps: list[Endpoint], *, limit: int) -> list[PlanRow]:
    """Pre-flight: one row per endpoint, from Hub metadata, wallet balances, breakers and the budget."""
    me = hub.me.email if hub.me else "guest@example.com"
    wallets = await hub.wallets._wallets_for(eps)
    hub_wallet = Money.of(await hub._t.hub_wallet_balance()) if any(e.pricing.rail is Rail.MPP for e in eps) else None
    running: dict[str, Money] = {}
    committed: dict[str, Money] = {}          # estimates already counted against each wallet
    rows: list[PlanRow] = []
    for ep in eps:
        p = ep.pricing
        est = p.estimate(limit)
        verdict, send, reason, wallet, note = Verdict.READY, True, None, None, None
        warnings: list[str] = []
        # access: allow/deny globs against my email ----------------------------------------
        acc = ep.policy("access")
        if acc:
            allowed, denied = acc.config.get("allowed_users") or [], acc.config.get("denied_users") or []
            if any(fnmatch(me, g) for g in denied) or (allowed and not any(fnmatch(me, g) for g in allowed)):
                verdict, send, reason = Verdict.ACCESS_DENIED, False, Reason.ACCESS_DENIED
                note = f"{me} is not on the allow list ({', '.join(allowed) or 'nobody'})"
        # circuit breaker ------------------------------------------------------------------
        if send and hub._breaker.is_open(ep.url):
            verdict, send, reason = Verdict.CIRCUIT_OPEN, False, Reason.CIRCUIT_OPEN
            note = f"{ep.url} failed {hub._breaker.failures.get(ep.url, 0)} times in a row; cooling down"
        # money ----------------------------------------------------------------------------
        if send and p.paid:
            if p.rail is Rail.MPP:
                verdict = Verdict.WILL_ASK_TO_PAY
                note = f"MPP challenge for {est} on run (experimental)"
                if hub_wallet is not None and hub_wallet < est:
                    warnings.append(f"Hub wallet has {hub_wallet} < {est}")
            else:
                wallet = wallets.get(p.wallet_id or p.credits_url or ep.path)
                if wallet is not None:
                    already = committed.get(wallet.key, Money(currency=p.currency))
                    if (wallet.balance or Money(currency=p.currency)) < already + est:
                        verdict, send, reason = Verdict.NEEDS_CREDITS, False, Reason.NO_CREDITS
                        note = (f"balance {wallet.balance} < {est}" if not already else
                                f"balance {wallet.balance} < {already + est} with the other sources on this wallet")
                    else:
                        committed[wallet.key] = already + est
                        note = f"deducted from wallet {wallet.owner} {p.rail.value} {p.currency}"
            b = hub.budget
            if send and b is not None and b.limit.currency == est.currency:
                so_far = running.get(est.currency, Money(currency=est.currency))
                if so_far + est > b.remaining:
                    verdict, send, reason = Verdict.OVER_BUDGET, False, Reason.OVER_BUDGET
                    note = f"would bring this session to {b.spent + so_far + est}, budget is {b.limit}"
            if send:
                running[est.currency] = running.get(est.currency, Money(currency=est.currency)) + est
        # health and rate limits -----------------------------------------------------------
        if ep.health is Health.UNHEALTHY:
            warnings.append("last health check: unhealthy")
            if verdict is Verdict.READY:
                verdict = Verdict.UNHEALTHY
        rl = ep.policy("rate_limit")
        if rl:
            warnings.append(f"rate limit {rl.config.get('limit')} {rl.config.get('scope', '')}".strip())
        rows.append(PlanRow(endpoint=ep, estimate=est, verdict=verdict, send=send, hold_reason=reason, wallet=wallet,
                            warnings=tuple(warnings), note=note))
    return rows
