from __future__ import annotations

from datetime import datetime, timezone

import pydantic
import pytest

import syfthub
from syfthub import (
    AccessDenied,
    Budget,
    Money,
    OverBudget,
    PlanRow,
    Preflight,
    Reason,
    SearchPlan,
    Source,
    StaleSnapshot,
    TopUp,
    ValidationError,
    Verdict,
    Wallet,
)


def test_plan_defaults_and_validation() -> None:
    plan = SearchPlan(query="q", sources=("a/b",))
    assert plan.limit == 5 and plan.similarity_threshold == 0.5 and plan.include_metadata
    assert plan.version == syfthub.__version__ and plan.created_at.tzinfo is not None
    for bad in (
        {"query": " "},
        {"limit": 0},
        {"similarity_threshold": 1.5},
        {"sources": ("nope",)},
    ):
        with pytest.raises(pydantic.ValidationError):
            SearchPlan(**{"query": "q", **bad})  # type: ignore[arg-type]


def test_skip_is_pure_and_validated(paid_source: Source) -> None:
    plan = SearchPlan(query="q", sources=("a/b", "erin/trials"))
    skipped = plan.skip("a/b").skip(paid_source).skip("a/b")
    assert plan.skips == () and skipped.skips == ("a/b", "erin/trials")
    assert skipped.active == ()
    with pytest.raises(ValidationError):
        plan.skip("not/here")
    implicit = SearchPlan(query="q")
    assert not implicit.explicit and implicit.skip("x/y").skips == ("x/y",)


def test_snapshot_roundtrip_and_stale_version() -> None:
    plan = SearchPlan(query="q", sources=("a/b",)).skip("a/b")
    d = plan.to_dict()
    assert set(d) >= {"query", "sources", "skips", "version", "created_at"}
    back = SearchPlan.from_dict(hub=None, d=d)
    assert back == plan
    with pytest.raises(StaleSnapshot):
        SearchPlan.from_dict(None, {**d, "version": "1.9.0"})
    with pytest.raises(StaleSnapshot):
        SearchPlan.from_dict(None, {k: v for k, v in d.items() if k != "version"})
    with pytest.raises(ValidationError):
        SearchPlan.from_dict(None, {**d, "limit": "many"})


async def test_unbound_plan_cannot_run() -> None:
    with pytest.raises(ValidationError):
        await SearchPlan(query="q").preflight()


def test_preflight_views(free_source: Source, paid_source: Source, wallet: Wallet) -> None:
    rows = (
        PlanRow(source=free_source, verdict=Verdict.READY),
        PlanRow(
            source=paid_source,
            verdict=Verdict.NEEDS_CREDITS,
            estimate=Money.of("0.05"),
            wallet=wallet,
            reason=Reason.NO_CREDITS,
        ),
    )
    topup = TopUp(
        wallet=wallet,
        shortfall=Money.of("0.05"),
        bundles=wallet.bundles,
        suggested=wallet.suggest(Money.of("0.05")),
        affects=(paid_source,),
    )
    pre = Preflight(
        rows=rows, actions=(topup,), estimate={"USD": Money.of("0.05")}, budget=Budget()
    )
    assert not pre.ready
    assert [r.path for r in pre.sending] == ["alice/free-docs"]
    assert [r.path for r in pre.held] == ["erin/trials"]
    assert pre["erin/trials"].reason is Reason.NO_CREDITS and len(pre) == 2
    assert pre.actions[0].paths == ("erin/trials",)
    assert topup.suggested is not None and topup.suggested.id == "starter"


def test_wallet_suggest_and_bundle_lookup(wallet: Wallet) -> None:
    assert wallet.suggest(Money.of(1)) is not None and wallet.suggest(Money.of(1)).id == "starter"  # type: ignore[union-attr]
    assert wallet.suggest(Money.of(5)).id == "pro"  # type: ignore[union-attr]
    assert wallet.suggest(Money.of(50)) is None
    assert wallet.bundle("pro").amount == Money.of(10)
    with pytest.raises(ValidationError):
        wallet.bundle("enterprise")


async def test_topup_without_suggestion_requires_explicit_bundle(
    wallet: Wallet, paid_source: Source
) -> None:
    topup = TopUp(
        wallet=wallet, shortfall=Money.of(50), bundles=wallet.bundles, affects=(paid_source,)
    )
    with pytest.raises(ValidationError):
        await topup.top_up()


def test_budget_math() -> None:
    b = Budget(limit=Money.of(2), spent=Money.of("0.5"))
    assert (
        b.remaining == Money.of("1.5") and b.allows(Money.of("1.5")) and not b.allows(Money.of(2))
    )
    assert Budget().remaining is None and Budget().allows(Money.of(1000))


def test_action_kinds_serialise(paid_source: Source) -> None:
    ob = OverBudget(estimate=Money.of(3), budget=Budget(limit=Money.of(2)), affects=(paid_source,))
    assert ob.to_dict()["kind"] == "over_budget"
    ad = AccessDenied(affects=(paid_source,), rule="allow list")
    assert ad.to_dict()["rule"] == "allow list"
    assert datetime.now(timezone.utc).tzinfo is timezone.utc
