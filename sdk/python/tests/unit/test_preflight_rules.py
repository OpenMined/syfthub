"""The pure pre-flight rules over ``Facts``: no network, no hub."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from syfthub import (
    AccessDenied,
    Budget,
    CircuitOpen,
    Money,
    OverBudget,
    Reason,
    SearchPlan,
    Source,
    TopUp,
    Verdict,
    Wallet,
)
from syfthub.search import Facts, paths_of, pick_sources, plan_preflight

from .conftest import hub_body, xendit_policy


def plan_for(*sources: Source, **kw: object) -> SearchPlan:
    return SearchPlan(query="q", sources=tuple(s.path for s in sources), **kw)  # type: ignore[arg-type]


def test_free_rows_are_ready_whatever_the_hub_reports_as_health(free_source: Source) -> None:
    flagged = Source.from_hub(hub_body("bob", "flaky"))
    assert flagged.raw["health_status"] == "healthy" and not hasattr(flagged, "health")
    pre = plan_preflight(plan_for(free_source, flagged), Facts(sources=(free_source, flagged)))
    assert pre.ready and [r.verdict for r in pre] == [Verdict.READY, Verdict.READY]
    assert pre.sending == tuple(pre) and pre.held == () and pre.actions == ()
    assert pre.estimate == {}


def test_skip_unreachable_and_access_denied_hold_without_sending(free_source: Source) -> None:
    tunnelled = Source.from_hub(
        {
            **hub_body("bob", "nats"),
            "connect": [{"type": "http", "config": {"url": "tunneling:bob"}}],
        }
    )
    gated = Source.from_hub(
        hub_body(
            "carol",
            "private",
            policies=[{"type": "access", "config": {"allowed_users": ["*@carol.org"]}}],
        )
    )
    plan = plan_for(free_source, tunnelled, gated).skip(free_source)
    pre = plan_preflight(plan, Facts(sources=(free_source, tunnelled, gated), email="me@other.org"))
    assert not pre.ready and pre.sending == ()
    assert pre[free_source.path].reason is Reason.BY_USER
    assert pre["bob/nats"].verdict is Verdict.UNREACHABLE
    denied = pre["carol/private"]
    assert (
        denied.verdict is Verdict.ACCESS_DENIED
        and denied.note == "not in allowed_users: *@carol.org"
    )
    (action,) = pre.actions
    assert isinstance(action, AccessDenied) and action.paths == ("carol/private",)
    assert action.rule == denied.note


def test_circuit_open_rows_group_into_one_action_per_host(free_source: Source) -> None:
    other = Source.from_hub(hub_body("alice", "more-docs"))
    reopens = datetime.now(UTC) + timedelta(seconds=20)
    pre = plan_preflight(
        plan_for(free_source, other),
        Facts(sources=(free_source, other), circuits={"alice.space.test": reopens}),
    )
    assert all(r.verdict is Verdict.CIRCUIT_OPEN for r in pre)
    (action,) = pre.actions
    assert isinstance(action, CircuitOpen) and action.reopens_at == reopens
    assert action.paths == (free_source.path, "alice/more-docs")


def test_prepaid_rows_price_per_wallet_and_hold_on_shortfall(
    paid_source: Source, wallet: Wallet
) -> None:
    notes = Source.from_hub(hub_body("erin", "notes", policies=[xendit_policy(price=0.02)]))
    wallet.balance = Money.of("0.06")
    facts = Facts(
        sources=(paid_source, notes),
        email="me@x.org",
        wallets={paid_source.path: wallet, notes.path: wallet},
    )
    pre = plan_preflight(plan_for(paid_source, notes), facts)
    assert [r.verdict for r in pre] == [Verdict.NEEDS_CREDITS] * 2
    assert pre.estimate == {} and not pre.ready
    (action,) = pre.actions
    assert isinstance(action, TopUp) and action.shortfall == Money.of("0.01")
    assert action.suggested is not None and action.suggested.id == "starter"
    assert action.paths == ("erin/trials", "erin/notes") and action.wallet is wallet
    wallet.balance = Money.of("0.07")
    pre = plan_preflight(plan_for(paid_source, notes), facts)
    assert pre.ready and pre.estimate == {"USD": Money.of("0.07")}
    assert pre[paid_source.path].wallet is wallet and pre[notes.path].estimate == Money.of("0.02")


def test_per_document_price_scales_with_limit(wallet: Wallet) -> None:
    per_doc = Source.from_hub(
        hub_body("erin", "chunks", policies=[xendit_policy(price=0.01, unit_type="document")])
    )
    wallet.balance = Money.of(1)
    pre = plan_preflight(
        plan_for(per_doc, limit=7), Facts(sources=(per_doc,), wallets={per_doc.path: wallet})
    )
    assert pre[per_doc.path].estimate == Money.of("0.07")


def test_applied_to_decides_who_pays(wallet: Wallet) -> None:
    gated = Source.from_hub(
        hub_body("erin", "members", policies=[xendit_policy(applied_to=["*@outside.org"])])
    )
    wallet.balance = Money.zero()
    pre = plan_preflight(
        plan_for(gated),
        Facts(sources=(gated,), email="me@erin.org", wallets={gated.path: wallet}),
    )
    assert pre.ready and pre[gated.path].estimate == Money.zero() and pre[gated.path].wallet is None


def test_unknown_balance_sends_and_notes_it(paid_source: Source, wallet: Wallet) -> None:
    wallet.balance = None
    pre = plan_preflight(
        plan_for(paid_source),
        Facts(
            sources=(paid_source,),
            wallets={paid_source.path: wallet},
            balance_errors={wallet.id: "balance unavailable: 503"},
        ),
    )
    row = pre[paid_source.path]
    assert row.verdict is Verdict.UNREACHABLE and row.note == "balance unavailable: 503"
    assert row.reason is Reason.UNREACHABLE and not row.send
    assert row.estimate == Money.of("0.05") and pre.actions == ()


def test_mpp_rows_will_ask_to_pay() -> None:
    metered = Source.from_hub(
        hub_body("kim", "metered", policies=[{"type": "mpp", "config": {"price": 0.01}}])
    )
    pre = plan_preflight(plan_for(metered), Facts(sources=(metered,)))
    row = pre[metered.path]
    assert row.verdict is Verdict.WILL_ASK_TO_PAY and row.send and row.estimate == Money.of("0.01")
    assert pre.estimate == {"USD": Money.of("0.01")}


def test_budget_holds_the_first_row_that_crosses_and_every_paid_row_after(
    free_source: Source, paid_source: Source, wallet: Wallet
) -> None:
    cheap = Source.from_hub(hub_body("erin", "cheap", policies=[xendit_policy(price=0.01)]))
    wallet.balance = Money.of(10)
    facts = Facts(
        sources=(paid_source, free_source, cheap),
        wallets={paid_source.path: wallet, cheap.path: wallet},
        budget=Budget(limits={"USD": Money.of("0.05")}, spent={"USD": Money.of("0.01")}),
    )
    pre = plan_preflight(plan_for(paid_source, free_source, cheap), facts)
    assert [r.verdict for r in pre] == [Verdict.OVER_BUDGET, Verdict.READY, Verdict.OVER_BUDGET]
    (action,) = pre.actions
    assert isinstance(action, OverBudget) and action.estimate == Money.of("0.06")
    assert action.paths == ("erin/trials", "erin/cheap") and action.budget == facts.budget
    assert pre.estimate == {}
    facts = facts.model_copy(
        update={"sources": (cheap, paid_source), "budget": Budget(limits={"USD": Money.of("0.05")})}
    )
    pre = plan_preflight(plan_for(cheap, paid_source), facts)
    assert [r.verdict for r in pre] == [Verdict.READY, Verdict.OVER_BUDGET]


def test_a_currency_without_a_cap_has_no_budget(wallet: Wallet) -> None:
    idr = Source.from_hub(
        hub_body("erin", "idr", policies=[xendit_policy(price=1000, currency="IDR")])
    )
    idr_wallet = wallet.model_copy(update={"currency": "IDR", "balance": Money.of(5000, "IDR")})
    pre = plan_preflight(
        plan_for(idr),
        Facts(
            sources=(idr,),
            wallets={idr.path: idr_wallet},
            budget=Budget(limits={"USD": Money.of(1)}),
        ),
    )
    row = pre[idr.path]
    assert row.verdict is Verdict.READY and "no budget set for IDR" in (row.note or "")
    assert pre.estimate == {"IDR": Money.of(1000, "IDR")} and pre.actions == ()


def test_each_currency_is_capped_on_its_own(paid_source: Source, wallet: Wallet) -> None:
    cheap = Source.from_hub(hub_body("erin", "cheap", policies=[xendit_policy(price=0.01)]))
    idr = Source.from_hub(
        hub_body("budi", "idr", policies=[xendit_policy(price=1000, currency="IDR")])
    )
    idr2 = Source.from_hub(
        hub_body("budi", "idr2", policies=[xendit_policy(price=1000, currency="IDR")])
    )
    wallet.balance = Money.of(10)
    idr_wallet = wallet.model_copy(
        update={
            "id": "w-budi",
            "key": "budi/xendit/IDR",
            "owner": "budi",
            "currency": "IDR",
            "balance": Money.of(5000, "IDR"),
        }
    )
    facts = Facts(
        sources=(paid_source, idr, cheap, idr2),
        wallets={
            paid_source.path: wallet,
            cheap.path: wallet,
            idr.path: idr_wallet,
            idr2.path: idr_wallet,
        },
        budget=Budget(
            limits={"USD": Money.of("0.05"), "IDR": Money.of(1500, "IDR")},
            spent={"IDR": Money.of(200, "IDR")},
        ),
    )
    pre = plan_preflight(plan_for(paid_source, idr, cheap, idr2), facts)
    assert [r.verdict for r in pre] == [
        Verdict.READY,  # 0.05 USD fits the USD cap exactly
        Verdict.READY,  # 200 + 1000 IDR fits
        Verdict.OVER_BUDGET,  # 0.06 USD would cross; held on the USD cap alone
        Verdict.OVER_BUDGET,  # 2200 IDR would cross; held on the IDR cap alone
    ]
    assert pre.estimate == {"USD": Money.of("0.05"), "IDR": Money.of(1000, "IDR")}
    usd, idr_action = pre.actions
    assert isinstance(usd, OverBudget) and isinstance(idr_action, OverBudget)
    assert usd.estimate == Money.of("0.06") and usd.paths == ("erin/cheap",)
    assert idr_action.estimate == Money.of(2000, "IDR") and idr_action.paths == ("budi/idr2",)
    assert 'set_budget({"IDR": x})' in idr_action.steps[0]
    assert pre.budget.remaining == {"USD": Money.of("0.05"), "IDR": Money.of(1300, "IDR")}


def test_budget_math_across_currencies() -> None:
    b = Budget(
        limits={"USD": Money.of(1), "IDR": Money.of(50000, "IDR")},
        spent={"IDR": Money.of(20000, "IDR")},
    )
    assert b.remaining == {"USD": Money.of(1), "IDR": Money.of(30000, "IDR")}
    assert b.allows(Money.of(1)) and not b.allows(Money.of("1.01"))
    assert b.allows(Money.of(30000, "IDR")) and not b.allows(Money.of(30001, "IDR"))
    assert b.allows(Money.of(1000, "EUR")) and not b.counts(Money.of(1000, "EUR"))
    assert b.remaining_in("EUR") is None and b.currencies == ("USD", "IDR")
    after = b.record(Money.of(5, "EUR")).record(Money.of("0.25"))
    assert after.spent["EUR"] == Money.of(5, "EUR") and after.remaining["USD"] == Money.of("0.75")
    with pytest.raises(ValueError, match="holds EUR"):
        Budget(limits={"USD": Money.of(1, "EUR")})


def test_pick_sources_for_an_implicit_plan(free_source: Source, paid_source: Source) -> None:
    model = Source.from_hub(hub_body("kim", "assistant", type="model"))
    both = Source.from_hub(hub_body("kim", "hybrid", type="model_data_source"))
    gated = Source.from_hub(
        hub_body(
            "carol", "private", policies=[{"type": "access", "config": {"allowed_users": ["x@y"]}}]
        )
    )
    more = [Source.from_hub(hub_body("alice", f"d{i}")) for i in range(3)]
    plan = SearchPlan(query="q", max_sources=3).skip("alice/d0")
    picked = pick_sources([free_source, paid_source, model, both, gated, *more], plan, "me@x")
    assert [s.path for s in picked] == ["alice/free-docs", "kim/hybrid", "alice/d0", "alice/d1"]
    pre = plan_preflight(plan, Facts(sources=picked, email="me@x"))
    assert [r.path for r in pre.sending] == ["alice/free-docs", "kim/hybrid", "alice/d1"]


def test_paths_of_accepts_strings_sources_and_lists(free_source: Source) -> None:
    from syfthub import SourceList

    listing = SourceList(items=(free_source,), total=1)
    assert paths_of(None) == ()
    assert paths_of("a/b") == ("a/b",)
    assert paths_of(["a/b", free_source, "a/b"]) == ("a/b", "alice/free-docs")
    assert paths_of(listing) == ("alice/free-docs",)
