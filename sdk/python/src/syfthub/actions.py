"""The actions a search raises, built in one place.

Pre-flight raises them from held rows; the send raises them again from what the Spaces answered.
Each builder names the fix in ``steps`` once, so the two moments agree.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .models.enums import Outcome, Reason, Verdict
from .models.money import Bundle, Money
from .models.results import SourceResult
from .models.search import (
    AccessDenied,
    AnyAction,
    CircuitOpen,
    OverBudget,
    PlanRow,
    Preflight,
    TopUp,
)
from .models.session import Budget
from .models.sources import Source
from .models.wallets import Wallet

if TYPE_CHECKING:
    from .preflight import Facts


# ── one builder per action ────────────────────────────────────────────────


def topup_steps(wallet: Wallet, suggested: Bundle | None) -> tuple[str, ...]:
    buy = (
        f"await action.top_up() buys the {suggested.id} bundle ({suggested.amount})"
        if suggested is not None
        else "await action.top_up(bundle) with a bundle from action.bundles"
    )
    return (
        f"{buy} on wallet {wallet.key}",
        "pay at invoice.checkout_url, then await invoice.wait_paid()",
        "plan.execute() again: pre-flight reads the new balance",
    )


def top_up(wallet: Wallet, shortfall: Money, affects: tuple[Source, ...]) -> TopUp:
    suggested = wallet.suggest(shortfall)
    return TopUp(
        wallet=wallet,
        shortfall=shortfall,
        bundles=wallet.bundles,
        suggested=suggested,
        affects=affects,
        steps=topup_steps(wallet, suggested),
    )


def over_budget(total: Money, budget: Budget, affects: tuple[Source, ...]) -> OverBudget:
    cur = total.currency
    return OverBudget(
        estimate=total,
        budget=budget,
        affects=affects,
        steps=(
            f'hub.set_budget({{"{cur}": x}}) with x covering {total} plus what is spent in {cur}, '
            "then plan.execute() again",
            "or plan.skip(*action.paths) to leave these sources out",
        ),
    )


def access_denied(rule: str | None, affects: tuple[Source, ...]) -> AccessDenied:
    return AccessDenied(
        rule=rule,
        affects=affects,
        steps=("plan.skip(*action.paths); the Space would refuse these",),
    )


def circuit_open(reopens_at: datetime, affects: tuple[Source, ...]) -> CircuitOpen:
    return CircuitOpen(
        reopens_at=reopens_at,
        affects=affects,
        steps=(
            f"wait until {reopens_at.isoformat(timespec='seconds')} and plan.execute() again",
            "or plan.skip(*action.paths)",
        ),
    )


# ── the two moments ───────────────────────────────────────────────────────


def preflight_actions(
    rows: list[PlanRow], shortfalls: dict[str, Money], over: dict[str, Money], facts: Facts
) -> tuple[AnyAction, ...]:
    """From held rows: one TopUp per short wallet, one OverBudget per crossed currency, one
    AccessDenied per rule, one CircuitOpen per host."""
    actions: list[AnyAction] = []
    for wallet_id, shortfall in shortfalls.items():
        affected = [r for r in rows if r.wallet is not None and r.wallet.id == wallet_id]
        wallet = affected[0].wallet
        assert wallet is not None
        actions.append(top_up(wallet, shortfall, tuple(r.source for r in affected)))
    for cur, total in over.items():
        over_rows = [
            r for r in rows if r.verdict is Verdict.OVER_BUDGET and r.estimate.currency == cur
        ]
        actions.append(over_budget(total, facts.budget, tuple(r.source for r in over_rows)))
    by_rule: dict[str | None, list[PlanRow]] = {}
    for r in rows:
        if r.verdict is Verdict.ACCESS_DENIED:
            by_rule.setdefault(r.note, []).append(r)
    for rule, denied in by_rule.items():
        actions.append(access_denied(rule, tuple(r.source for r in denied)))
    by_host: dict[str, list[PlanRow]] = {}
    for r in rows:
        if r.verdict is Verdict.CIRCUIT_OPEN and r.source.host:
            by_host.setdefault(r.source.host, []).append(r)
    for host, held in by_host.items():
        actions.append(circuit_open(facts.circuits[host], tuple(r.source for r in held)))
    return tuple(actions)


def actions_after(
    rows: tuple[SourceResult, ...],
    pre: Preflight,
    budget: Budget,
    reopens_at: Callable[[str], datetime | None],
) -> tuple[AnyAction, ...]:
    """From what the Spaces answered, on top of pre-flight's: a prepaid 402 is a TopUp with the
    Space's own shortfall, an MPP charge over the cap an OverBudget, a probe that failed a
    CircuitOpen for the rows it held."""
    actions: list[AnyAction] = []
    by_wallet: dict[str, list[SourceResult]] = {}
    for r in rows:
        if r.outcome is Outcome.REJECTED and r.reason is Reason.NO_CREDITS and r.topup:
            by_wallet.setdefault(r.topup.wallet.id, []).append(r)
    for group in by_wallet.values():
        topups = [r.topup for r in group if r.topup is not None]
        shortfall = max((t.shortfall for t in topups), default=topups[0].shortfall)
        actions.append(top_up(topups[0].wallet, shortfall, tuple(r.source for r in group)))
    by_currency: dict[str, list[SourceResult]] = {}
    for r in rows:
        if r.outcome is Outcome.PAYMENT_REQUIRED and r.reason is Reason.OVER_BUDGET and r.charge:
            by_currency.setdefault(r.charge.amount.currency, []).append(r)
    for cur, over in by_currency.items():
        total = Money.zero(cur)
        for r in over:
            assert r.charge is not None
            total = total + r.charge.amount
        actions.append(over_budget(total, budget, tuple(r.source for r in over)))
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
        reopens = reopens_at(host) or datetime.now(UTC)
        actions.append(circuit_open(reopens, tuple(r.source for r in held)))
    return tuple(actions)


__all__ = [
    "access_denied",
    "actions_after",
    "circuit_open",
    "over_budget",
    "preflight_actions",
    "top_up",
    "topup_steps",
]
