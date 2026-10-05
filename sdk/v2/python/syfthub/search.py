"""A composed search: pre-flight decided from Hub metadata, one balance call per
prepaid wallet, and the session budget. Nothing is sent to a Space."""
from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Any

from . import render
from .models import Endpoint, Rail, SkipReason, TopUp, Wallet, split_filters

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub
    from .results import Results


@dataclass
class SearchRow:
    """One source's pre-flight: what it would cost and whether it will be sent.

    Attributes:
        endpoint: The source.
        estimate: The most one call can cost: price times ``limit`` for per-document pricing, or the
            price per request.
        verdict: One phrase: ``ready``, ``will ask to pay``, ``needs credits``, ``over budget``, or
            ``access denied``.
        send: ``True`` when the source will be sent on ``execute()``.
        hold_reason: Why it is held, when it is.
        wallet: The prepaid wallet it bills against, when it has one.
        warnings: Anything worth knowing before sending, such as an unhealthy Space.
        note: Pre-flight's explanation, shown in the table."""
    endpoint: Endpoint
    estimate: float                    # max cost of one call: price × (limit if per-document else 1)
    verdict: str                       # ready | will ask to pay | needs credits | over budget | access denied
    send: bool                         # False: held back, decided client-side
    hold_reason: SkipReason | None = None
    wallet: Wallet | None = None
    warnings: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class Search:
    """A composed search. Pre-flight has run; nothing has been sent.

    Look at it to see the estimated cost per source, your balances, and which sources are held and
    why. Narrow it with ``filter``, pay what is short with ``top_up``, then ``execute()``.

    Attributes:
        query: The question that will be sent.
        rows: One ``SearchRow`` per source.
        limit: How many passages each source is asked for.
        threshold: The similarity cut-off, from 0 to 1.
        history: Earlier conversation turns that travel with the query.
        kind: ``"search"``, or ``"chat"`` for the pre-flight of a chat model.
        max_tokens: For chat models: how long an answer may be.
        filters: The metadata filters set with ``filter()``."""
    query: str
    rows: list[SearchRow]
    limit: int
    threshold: float
    history: list[dict[str, str]]
    _hub: Any = field(repr=False)
    kind: str = "search"                  # search | chat (pre-flight on a chat model)
    max_tokens: int = 300
    filters: dict[str, Any] = field(default_factory=dict)   # document metadata filters; see filter() / filters_for()
    _invoices: dict[str, dict] = field(default_factory=dict, repr=False)

    @property
    def total_estimate(self) -> dict[str, float]:
        """The most this search can cost, per currency, if every source that passed pre-flight is sent."""
        tot: dict[str, float] = {}
        for r in self.sending:
            if r.estimate:
                cur = r.endpoint.pricing.currency
                tot[cur] = round(tot.get(cur, 0.0) + r.estimate, 6)
        return tot

    @property
    def sending(self) -> list[SearchRow]:
        """The sources that passed pre-flight and will be sent."""
        return [r for r in self.rows if r.send]

    @property
    def held(self) -> list[SearchRow]:
        """The sources pre-flight held back, each with its reason."""
        return [r for r in self.rows if not r.send]

    def filter(self, **filters: Any) -> "Search":
        """Only return passages whose metadata matches.

        Write each condition as ``field=value`` for an exact match, or add a suffix: ``field_gte``,
        ``field_gt``, ``field_lte``, ``field_lt`` to compare, or ``field_contains`` for a substring.

        Where the filtering happens depends on the source. A Space that advertises the field as
        ``filterable`` gets the filter in the request: it filters before ``limit`` and bills only the
        passages it returns. Every other source is filtered here, after ``limit``, so raise ``limit`` when
        you filter hard. The pre-flight table says which happens for each source. Server-side filtering
        is PROPOSED; no Space supports it today.

        Args:
            **filters: Conditions such as ``published_gte="2024-01-01"`` or ``author="R. Chitrakoot"``.

        Returns:
            This search, narrowed. Chainable."""
        self.filters.update(filters)
        return self

    def filters_for(self, row: SearchRow) -> tuple[dict[str, Any], dict[str, Any]]:
        """How one source's filters are split.

        Args:
            row: The source's pre-flight row.

        Returns:
            Two dicts: the filters the Space will apply, and the ones this client applies after the
            response."""
        return split_filters(self.filters, row.endpoint.filterable)

    # -- act before sending ------------------------------------------------------------------
    @property
    def pending(self) -> list[TopUp]:
        """One ``TopUp`` per prepaid wallet that is short, each listing the sources waiting on it."""
        out: dict[str, TopUp] = {}
        for r in self.rows:
            if r.hold_reason is SkipReason.NO_CREDITS and r.wallet is not None:
                t = out.get(r.wallet.key)
                if t is None:
                    out[r.wallet.key] = t = TopUp(r.endpoint, r.wallet, 0.0, invoice=self._invoices.get(r.wallet.key))
                t.waiting = t.waiting + (r.endpoint.path,)
                t.needed = round((t.needed or 0) + r.estimate, 6)
        return list(out.values())

    def top_up(self, path_or_wallet: str, *, bundle: str) -> TopUp:
        """Buy a credit bundle for a wallet that is short, before executing.

        Args:
            path_or_wallet: An endpoint path such as ``"dave/notes"``, or a wallet key. Every source
                behind the same wallet is unblocked at once.
            bundle: The bundle's id, for example ``"starter"``.

        Returns:
            The ``TopUp`` with the Space's invoice attached. Pay at its ``checkout_url``, then
            ``refresh()`` or just ``execute()``."""
        for t in self.pending:
            if path_or_wallet in t.waiting or t.wallet.key == path_or_wallet:
                t.invoice = t.wallet.top_up(bundle)
                self._invoices[t.wallet.key] = t.invoice
                return t
        raise KeyError(f"{path_or_wallet} is not short of credits")

    def refresh(self) -> "Search":
        """Run pre-flight again, for example after paying.

        Returns:
            This search, with fresh balances and verdicts."""
        fresh = build_search(self._hub, self.query, [r.endpoint for r in self.rows],
                             limit=self.limit, threshold=self.threshold, history=self.history)
        self.rows = fresh.rows
        return self

    def execute(self) -> "Results":
        """Send the search to every source that passes pre-flight.

        Pre-flight is checked once more, then the passing sources are called in parallel. Sources that
        are held become skipped rows with their reason and, where it applies, a top-up attached.

        Returns:
            The ``Results``, one row per source."""
        self.refresh()
        return self._hub._execute(self)

    def _repr_html_(self) -> str:
        return render.search_table(self)

    def __repr__(self) -> str:
        est = " + ".join(render.money(v, k) for k, v in self.total_estimate.items()) or "free"
        lines = [f'{self.kind.title()} "{self.query}"  est. max {est}  (not executed)']
        for r in self.rows:
            lines.append(f"  {r.endpoint.path:<24} {r.endpoint.pricing.label():<32} max {render.money(r.estimate):<8} "
                         f"{r.verdict}{'' if r.send else '  (held)'}")
        return "\n".join(lines)


def build_search(hub: "Hub", query: str, eps: list[Endpoint], *, limit: int, threshold: float,
               history: list[dict[str, str]]) -> Search:
    me = hub.me.email if hub.me else "guest@example.com"
    wallets: dict[str, Wallet] = {}
    rows: list[SearchRow] = []
    budget = hub.budget
    running = 0.0
    for ep in eps:
        p = ep.pricing
        est = round(p.price * (limit if p.unit == "document" else 1), 6) if p.paid else 0.0
        row = SearchRow(ep, est, "ready", True)
        # access: allow/deny globs against my email ---------------------------------------
        acc = next((pol for pol in ep.policies if pol.type == "access" and pol.enabled), None)
        if acc:
            allowed, denied = acc.config.get("allowed_users") or [], acc.config.get("denied_users") or []
            if any(fnmatch(me, g) for g in denied) or (allowed and not any(fnmatch(me, g) for g in allowed)):
                row.verdict, row.send, row.hold_reason = "access denied", False, SkipReason.ACCESS_DENIED
                row.note = f"{me} is not on the allow list ({', '.join(allowed) or 'nobody'})"
        # money ---------------------------------------------------------------------------
        if row.send and p.paid:
            if p.rail is Rail.MPP:
                row.verdict = "will ask to pay"
                row.note = f"MPP challenge for {render.money(est, p.currency)} on run (experimental)"
                if hub._fake.hub_wallet < est:
                    row.warnings.append(f"Hub wallet has {render.money(hub._fake.hub_wallet)} < {render.money(est)}")
            else:
                key = p.wallet_id or p.credits_url or ep.path
                if key not in wallets:
                    wallets[key] = hub.wallet(ep)
                row.wallet = wallets[key]
                if (row.wallet.balance or 0) + 1e-9 < est:
                    row.verdict, row.send, row.hold_reason = "needs credits", False, SkipReason.NO_CREDITS
                    row.note = f"balance {render.money(row.wallet.balance, p.currency)} < {render.money(est, p.currency)}"
                else:
                    row.note = f"deducted from wallet {row.wallet.owner} {p.rail.value} {p.currency}"
            if row.send and budget is not None and running + est > budget.remaining + 1e-9:
                row.verdict, row.send, row.hold_reason = "over budget", False, SkipReason.OVER_BUDGET
                row.note = (f"would bring this session to {render.money(running + est)}, "
                            f"budget has {render.money(budget.remaining)} left")
            if row.send:
                running = round(running + est, 6)
        # health ----------------------------------------------------------------------------
        if ep.health_status and ep.health_status != "healthy":
            row.warnings.append(f"last health check: {ep.health_status}")
        rl = next((pol for pol in ep.policies if pol.type == "rate_limit" and pol.enabled), None)
        if rl:
            row.warnings.append(f"rate limit {rl.config.get('limit')} {rl.config.get('scope', '')}".strip())
        rows.append(row)
    return Search(query, rows, limit, threshold, history, _hub=hub)
