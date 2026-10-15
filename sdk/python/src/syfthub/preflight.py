"""The pre-flight rules: which rows send, which are held, and why. Pure.

Everything a rule needs is read first into ``Facts``; the rules never touch the network, so they
run in tests as plain functions. ``Searcher`` gathers the facts and calls ``plan_preflight``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .actions import preflight_actions
from .models.enums import Rail, Reason, Verdict
from .models.money import Money
from .models.search import PlanRow, Preflight, SearchPlan, as_path
from .models.session import Budget
from .models.sources import Source, SourceList
from .models.wallets import Wallet


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
            elif wallet.balance is None:  # the wallet host did not answer: do not send
                return PlanRow(
                    source=source,
                    verdict=Verdict.UNREACHABLE,
                    reason=Reason.UNREACHABLE,
                    estimate=estimate,
                    wallet=wallet,
                    note=facts.balance_errors.get(wallet.id) or "balance unknown",
                )
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


def plan_preflight(plan: SearchPlan, facts: Facts) -> Preflight:
    """The rules, in order: skips, reachability, access, circuit, credits, budget."""
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
        actions=preflight_actions(rows, shortfalls, over, facts),
        estimate=estimate,
        budget=facts.budget,
    )


def pick_sources(
    candidates: Iterable[Source], plan: SearchPlan, email: str | None
) -> tuple[Source, ...]:
    """For a plan without explicit sources: every free, reachable document source the caller may
    use, in catalogue order, or the first ``max_sources`` of them when the plan sets a ceiling.
    Skipped ones are kept so they show as ``SKIPPED`` rows."""
    picked: list[Source] = []
    active = 0
    for source in candidates:
        if plan.max_sources is not None and active >= plan.max_sources:
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


__all__ = ["Facts", "paths_of", "pick_sources", "plan_preflight"]
