"""``hub.search`` end to end over respx: compose, pre-flight, execute, actions, retry, budget, MPP."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
import respx

from syfthub import (
    ActionRequired,
    AsyncHub,
    AuthError,
    CircuitBreaker,
    CircuitOpen,
    Money,
    Options,
    Outcome,
    OverBudget,
    PaymentFailed,
    Reason,
    Results,
    Retry,
    SearchPlan,
    SourceNotFound,
    TopUp,
    ValidationError,
    Verdict,
)

from .conftest import hub_body, xendit_policy

HUB = "https://hub.test"
QUERY = "/api/v1/endpoints/{slug}/query"


def ok_body(
    *chunks: tuple[str, float], summary: str | None = None, cost: float | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": summary,
        "references": {
            "documents": [
                {"document_id": f"d{i}", "content": text, "metadata": {}, "similarity_score": score}
                for i, (text, score) in enumerate(chunks)
            ]
        },
        "policy_metadata": {"outcome": "success", "entries": []},
    }
    if cost is not None:
        body["cost"], body["currency"] = cost, "USD"
        body["policy_metadata"]["entries"].append(
            {
                "policy_type": "xendit_per_request",
                "kind": "payment",
                "status": "charged",
                "amount": cost,
                "currency": "USD",
                "transaction": {"rail": "xendit", "id": "tx"},
            }
        )
    return body


MPP_POLICY = {"type": "mpp", "config": {"price": 0.02, "currency": "USD"}}
SOURCES = {
    "alice/free-docs": hub_body("alice", "free-docs"),
    "alice/more": hub_body("alice", "more"),
    "erin/trials": hub_body("erin", "trials", policies=[xendit_policy()]),
    "erin/notes": hub_body("erin", "notes", policies=[xendit_policy(price=0.02)]),
    "kim/metered": hub_body("kim", "metered", policies=[MPP_POLICY]),
    "kim/assistant": hub_body("kim", "assistant", type="model"),
}


@pytest.fixture
def api() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{HUB}/api/v1/auth/me", name="me").respond(
            200, json={"username": "me", "email": "me@x.org"}
        )
        router.get(f"{HUB}/api/v1/token", name="token").respond(
            200, json={"target_token": "sat", "expires_in": 60}
        )
        for path, body in SOURCES.items():
            router.get(f"{HUB}/api/v1/endpoints/public/{path}", name=f"source:{path}").respond(
                200, json=body
            )
        router.get("https://erin.space.test/api/credits", name="credits").respond(
            200,
            json={
                "wallet_id": "w-erin",
                "user_email": "me@x.org",
                "balance": 1.0,
                "currency": "USD",
            },
        )
        yield router


@pytest.fixture
async def hub() -> AsyncHub:
    h = AsyncHub(
        HUB,
        token="t",
        options=Options(
            retry=Retry(attempts=2, backoff=0, max_backoff=0),
            circuit_breaker=CircuitBreaker(failures=2, cooldown=30),
        ),
    )
    yield h
    await h.aclose()


def space(api: respx.MockRouter, path: str) -> respx.Route:
    owner, slug = path.split("/")
    return api.post(f"https://{owner}.space.test{QUERY.format(slug=slug)}")


# ── compose ───────────────────────────────────────────────────────────────


def test_compose_validates_and_binds(hub: AsyncHub) -> None:
    plan = hub.search("q", ["alice/free-docs", "erin/trials"], limit=3)
    assert (
        plan.sources == ("alice/free-docs", "erin/trials") and plan.limit == 3 and plan.pre is None
    )
    with pytest.raises(ValidationError):
        hub.search(" ")
    with pytest.raises(ValidationError):
        hub.search("q", ["not a path"])
    with pytest.raises(ValidationError):
        hub.search("q", limit=0)


# ── preflight ─────────────────────────────────────────────────────────────


async def test_preflight_reads_identity_sources_and_balances_once_each(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    plan = hub.search("q", ["alice/free-docs", "erin/trials", "erin/notes", "kim/metered"])
    pre = await plan.preflight()
    assert pre.ready and plan.pre is pre
    assert [r.verdict for r in pre] == [
        Verdict.READY,
        Verdict.READY,
        Verdict.READY,
        Verdict.WILL_ASK_TO_PAY,
    ]
    assert pre.estimate == {"USD": Money.of("0.09")}
    assert pre["erin/trials"].wallet is pre["erin/notes"].wallet
    assert pre["erin/trials"].wallet.balance == Money.of(1)  # type: ignore[union-attr]
    assert api["me"].call_count == 1
    assert api["credits"].call_count == 1
    assert hub.me is not None and hub.me.email == "me@x.org"


async def test_preflight_holds_for_credits_and_the_topup_resolves_it(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    api.get("https://erin.space.test/api/credits").respond(
        200, json={"balance": 0.04, "currency": "USD"}
    )
    plan = hub.search("q", ["erin/trials", "erin/notes"])
    pre = await plan.preflight()
    assert [r.verdict for r in pre] == [Verdict.NEEDS_CREDITS] * 2 and not pre.ready
    (action,) = pre.actions
    assert (
        isinstance(action, TopUp)
        and action.shortfall == Money.of("0.03")
        and action.paths == ("erin/trials", "erin/notes")
    )
    payments = api.post("https://erin.space.test/api/payments").respond(
        200,
        json={
            "id": "inv-1",
            "bundle_name": "starter",
            "amount": 1,
            "currency": "USD",
            "status": "pending",
            "checkout_url": "https://pay",
        },
    )
    invoice = await action.top_up()
    assert invoice.checkout_url == "https://pay" and invoice.bundle == "starter"
    sent = json.loads(payments.calls.last.request.content)
    assert sent == {"bundle_name": "starter", "endpoint_slug": "trials"}


async def test_preflight_unknown_source_raises(api: respx.MockRouter, hub: AsyncHub) -> None:
    api.get(f"{HUB}/api/v1/endpoints/public/alice/nope").respond(404, json={"detail": "no"})
    with pytest.raises(SourceNotFound):
        await hub.search("q", ["alice/nope"]).preflight()


async def test_balance_failure_does_not_block_the_row(api: respx.MockRouter, hub: AsyncHub) -> None:
    api.get("https://erin.space.test/api/credits").respond(503)
    pre = await hub.search("q", ["erin/trials"]).preflight()
    row = pre["erin/trials"]
    assert row.verdict is Verdict.READY and "balance unavailable" in (row.note or "")


# ── execute ───────────────────────────────────────────────────────────────


async def test_execute_fans_out_and_merges(api: respx.MockRouter, hub: AsyncHub) -> None:
    free = space(api, "alice/free-docs").respond(200, json=ok_body(("a", 0.9), ("b", 0.4)))
    paid = space(api, "erin/trials").respond(200, json=ok_body(("c", 0.7), cost=0.05))
    model = space(api, "kim/assistant").respond(
        200,
        json={"summary": {"message": {"content": "an answer"}}, "references": {"documents": []}},
    )
    plan = hub.search(
        "what?",
        ["alice/free-docs", "erin/trials", "kim/assistant"],
        limit=2,
        similarity_threshold=0.3,
    )
    results = await plan.execute()
    assert results.plan is plan and len(results) == 3 and len(results.ok) == 3
    assert [(p, d.content) for p, d in results.chunks] == [
        ("alice/free-docs", "a"),
        ("erin/trials", "c"),
        ("alice/free-docs", "b"),
    ]
    assert results.answers == {"kim/assistant": "an answer"} and results.kind.value == "both"
    assert results.cost == {"USD": Money.of("0.05")} and hub.spent == {"USD": Money.of("0.05")}
    assert (
        results["erin/trials"].paid_from == "erin/xendit/USD"
        and results["erin/trials"].rail.value == "xendit"
    )  # type: ignore[union-attr]
    assert results["alice/free-docs"].elapsed_ms >= 0 and results["alice/free-docs"].attempts == 1
    body = json.loads(free.calls.last.request.content)
    assert body == {
        "messages": "what?",
        "similarity_threshold": 0.3,
        "limit": 2,
        "include_metadata": True,
    }
    assert free.calls.last.request.headers["Authorization"] == "Bearer sat"
    assert paid.called and model.called
    assert results["alice/free-docs"].request["url"].endswith("/api/v1/endpoints/free-docs/query")
    assert "Authorization" not in json.dumps(results["alice/free-docs"].request)


async def test_execute_holds_skips_and_credits_rows_without_sending(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    api.get("https://erin.space.test/api/credits").respond(
        200, json={"balance": 0, "currency": "USD"}
    )
    free = space(api, "alice/free-docs").respond(200, json=ok_body(("a", 0.9)))
    paid = space(api, "erin/trials")
    results = (
        await hub.search("q", ["alice/free-docs", "erin/trials", "alice/more"])
        .skip("alice/more")
        .execute()
    )
    assert free.called and not paid.called
    held = results["erin/trials"]
    assert (
        held.outcome is Outcome.HELD and held.reason is Reason.NO_CREDITS and held.topup is not None
    )
    assert held.topup.shortfall == Money.of("0.05") and held.status_code == 0
    assert results["alice/more"].reason is Reason.BY_USER
    assert [a.kind.value for a in results.actions] == ["top_up"]
    assert results.held == (held, results["alice/more"]) and not results.retryable


async def test_strict_raises_before_sending(api: respx.MockRouter, hub: AsyncHub) -> None:
    api.get("https://erin.space.test/api/credits").respond(
        200, json={"balance": 0, "currency": "USD"}
    )
    free = space(api, "alice/free-docs").respond(200, json=ok_body())
    with pytest.raises(ActionRequired) as info:
        await hub.search("q", ["alice/free-docs", "erin/trials"]).execute(strict=True)
    assert isinstance(info.value.actions[0], TopUp) and not free.called
    # skips are the user's own decision, not an open action
    results = (
        await hub.search("q", ["alice/free-docs", "erin/trials"])
        .skip("erin/trials")
        .execute(strict=True)
    )
    assert free.called and results["erin/trials"].reason is Reason.BY_USER


@pytest.mark.usefixtures("api")
async def test_execute_without_a_token_raises_auth_error() -> None:
    async with AsyncHub(HUB) as anonymous:
        pre = await anonymous.search("q", ["alice/free-docs"]).preflight()
        assert pre.ready
        with pytest.raises(AuthError):
            await anonymous.search("q", ["alice/free-docs"]).execute()


async def test_space_errors_become_rows_and_retry_resends_only_them(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    space(api, "alice/free-docs").respond(200, json=ok_body(("a", 0.9)))
    limited = space(api, "erin/trials").respond(
        403,
        json={
            "detail": "Rate limit exceeded",
            "policy_metadata": {
                "outcome": "rate_limited",
                "entries": [
                    {
                        "policy_type": "rate_limit",
                        "kind": "rate_limit",
                        "status": "rejected",
                        "reason_code": "RATE_LIMITED",
                        "details": {"retry_after_seconds": 3},
                    }
                ],
            },
        },
    )
    gone = space(api, "alice/more").mock(side_effect=httpx.ConnectError("refused"))
    missing = space(api, "kim/assistant").respond(404, json={"detail": "unknown slug"})
    results = await hub.search(
        "q", ["alice/free-docs", "erin/trials", "alice/more", "kim/assistant"]
    ).execute()
    assert [r.outcome for r in results] == [
        Outcome.RETURNED,
        Outcome.REJECTED,
        Outcome.FAILED,
        Outcome.FAILED,
    ]
    assert results["erin/trials"].rate_limit.reset_seconds == 3  # type: ignore[union-attr]
    assert (
        results["alice/more"].reason is Reason.UNREACHABLE and results["alice/more"].attempts == 2
    )
    assert results["kim/assistant"].reason is Reason.NOT_FOUND
    assert [r.path for r in results.retryable] == ["erin/trials", "alice/more"]
    assert gone.call_count == 2 and limited.call_count == 1 and missing.call_count == 1

    limited.respond(200, json=ok_body(("late", 0.5), cost=0.05))
    gone.mock(return_value=httpx.Response(200, json=ok_body(("back", 0.8))))
    merged = await results.retry()
    assert len(merged) == 4 and [r.path for r in merged.ok] == [
        "alice/free-docs",
        "erin/trials",
        "alice/more",
    ]
    assert merged["kim/assistant"].reason is Reason.NOT_FOUND and merged.plan is results.plan
    assert api["source:alice/free-docs"].call_count == 1  # source cache


async def test_401_from_a_space_mints_a_fresh_token_once(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    route = space(api, "alice/free-docs")
    route.side_effect = [
        httpx.Response(401, json={"detail": "expired"}),
        httpx.Response(200, json=ok_body(("a", 0.9))),
    ]
    results = await hub.search("q", ["alice/free-docs"]).execute()
    assert results.ok and results["alice/free-docs"].attempts == 2
    assert api["token"].call_count == 2
    route.side_effect = [
        httpx.Response(401, json={"detail": "x"}),
        httpx.Response(401, json={"detail": "x"}),
    ]
    again = await hub.search("q", ["alice/free-docs"]).execute()
    assert (
        again["alice/free-docs"].outcome is Outcome.FAILED
        and again["alice/free-docs"].reason is Reason.AUTH
    )


async def test_5xx_after_retries_opens_the_breaker_and_holds_the_host(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    broken = space(api, "alice/free-docs").respond(503)
    first = await hub.search("q", ["alice/free-docs"]).execute()
    assert first["alice/free-docs"].reason is Reason.SERVER_ERROR and broken.call_count == 2
    assert not hub.breakers.is_open("alice.space.test")
    second = await hub.search("q", ["alice/free-docs"]).execute()
    assert second["alice/free-docs"].outcome is Outcome.FAILED and hub.breakers.is_open(
        "alice.space.test"
    )
    third = await hub.search("q", ["alice/free-docs", "alice/more"]).execute()
    assert (
        third["alice/free-docs"].reason is Reason.CIRCUIT_OPEN
        and third["alice/more"].reason is Reason.CIRCUIT_OPEN
    )
    assert broken.call_count == 4
    (action,) = third.actions
    assert isinstance(action, CircuitOpen) and action.paths == ("alice/free-docs", "alice/more")


async def test_half_open_host_sends_one_probe_first(
    api: respx.MockRouter, hub: AsyncHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    hub.breakers.failure("alice.space.test")
    hub.breakers.failure("alice.space.test")
    assert hub.breakers.is_open("alice.space.test")
    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now + 31)
    probe = space(api, "alice/free-docs").respond(503)
    rest = space(api, "alice/more").respond(200, json=ok_body())
    results = await hub.search("q", ["alice/free-docs", "alice/more"]).execute()
    assert probe.called and not rest.called
    assert results["alice/free-docs"].reason is Reason.SERVER_ERROR
    assert (
        results["alice/more"].outcome is Outcome.HELD
        and results["alice/more"].reason is Reason.CIRCUIT_OPEN
    )
    assert isinstance(results.actions[0], CircuitOpen) and hub.breakers.is_open("alice.space.test")

    monkeypatch.setattr(time, "monotonic", lambda: now + 62)
    probe.respond(200, json=ok_body(("ok", 0.9)))
    results = await hub.search("q", ["alice/free-docs", "alice/more"]).execute()
    assert len(results.ok) == 2 and rest.called and not hub.breakers.is_open("alice.space.test")


async def test_concurrency_is_bounded(api: respx.MockRouter) -> None:
    active = 0
    peak = 0

    async def slow(_request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json=ok_body())

    paths = []
    for i in range(6):
        body = hub_body("alice", f"d{i}")
        api.get(f"{HUB}/api/v1/endpoints/public/alice/d{i}").respond(200, json=body)
        api.post(f"https://alice.space.test{QUERY.format(slug=f'd{i}')}").mock(side_effect=slow)
        paths.append(f"alice/d{i}")
    async with AsyncHub(HUB, token="t", options=Options(concurrency=2)) as h:
        results = await h.search("q", paths).execute()
    assert len(results.ok) == 6 and peak == 2


# ── budget and MPP ────────────────────────────────────────────────────────


async def test_budget_holds_paid_rows_and_set_budget_releases_them(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    space(api, "alice/free-docs").respond(200, json=ok_body())
    paid = space(api, "erin/trials").respond(200, json=ok_body(cost=0.05))
    hub.set_budget("0.04")
    plan = hub.search("q", ["alice/free-docs", "erin/trials"])
    results = await plan.execute()
    assert results["erin/trials"].reason is Reason.OVER_BUDGET and not paid.called
    (action,) = results.actions
    assert isinstance(action, OverBudget) and action.estimate == Money.of("0.05")
    hub.set_budget(0.08)
    results = await plan.execute()
    assert paid.called and results.ok and hub.spent == {"USD": Money.of("0.05")}
    assert hub.budget.remaining == {"USD": Money.of("0.03")}
    results = await plan.execute()
    assert results["erin/trials"].reason is Reason.OVER_BUDGET and paid.call_count == 1


async def test_mpp_challenge_is_paid_through_the_hub_within_budget(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    challenge = 'Payment realm="kim", amount="0.02", currency="USD", request="abc"'
    route = space(api, "kim/metered")
    route.side_effect = [
        httpx.Response(
            402, json={"detail": "payment required"}, headers={"WWW-Authenticate": challenge}
        ),
        httpx.Response(200, json=ok_body(("paid", 0.9))),
    ]
    pay = api.post(f"{HUB}/api/v1/wallet/pay").respond(200, json={"x_payment": "cred-1"})
    results = await hub.search("q", ["kim/metered"]).execute()
    row = results["kim/metered"]
    assert row.ok and row.charge is not None and row.charge.amount == Money.of("0.02")
    assert (
        row.cost == Money.of("0.02")
        and row.attempts == 2
        and hub.spent == {"USD": Money.of("0.02")}
    )
    assert json.loads(pay.calls.last.request.content) == {
        "www_authenticate": challenge,
        "endpoint_slug": "metered",
    }
    assert route.calls.last.request.headers["X-Payment"] == "cred-1"
    assert "X-Payment" not in route.calls[0].request.headers


async def test_mpp_challenge_over_budget_or_refused_is_payment_required(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    challenge = 'Payment realm="kim", amount="0.50", currency="USD"'
    route = space(api, "kim/metered").respond(
        402, json={"detail": "pay"}, headers={"WWW-Authenticate": challenge}
    )
    pay = api.post(f"{HUB}/api/v1/wallet/pay")
    hub.set_budget(0.10)
    results = await hub.search("q", ["kim/metered"]).execute()
    row = results["kim/metered"]
    assert row.outcome is Outcome.PAYMENT_REQUIRED and row.reason is Reason.OVER_BUDGET
    assert row.charge is not None and row.charge.amount == Money.of("0.50") and not pay.called
    (action,) = results.actions
    assert (
        isinstance(action, OverBudget)
        and action.estimate == Money.of("0.50")
        and action.paths == ("kim/metered",)
    )

    hub.set_budget(None)
    pay.respond(400, json={"detail": {"code": "INSUFFICIENT_BALANCE", "message": "empty"}})
    results = await hub.search("q", ["kim/metered"]).execute()
    row = results["kim/metered"]
    assert row.outcome is Outcome.PAYMENT_REQUIRED and row.reason is None
    assert (
        row.error is not None
        and "INSUFFICIENT_BALANCE: empty" in row.error
        and results.actions == ()
    )
    assert hub.spent == {} and route.call_count == 2
    with pytest.raises(PaymentFailed) as info:
        await hub._hub_api.pay_mpp("Payment realm=kim", "metered")
    assert info.value.code == "INSUFFICIENT_BALANCE"


async def test_prepaid_402_from_the_space_is_rejected_with_a_topup_action(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    space(api, "erin/trials").respond(
        402,
        json={
            "detail": "Insufficient balance",
            "policy_metadata": {
                "outcome": "payment_required",
                "entries": [
                    {
                        "policy_type": "xendit_per_request",
                        "kind": "payment",
                        "status": "rejected",
                        "amount": 0.05,
                        "currency": "USD",
                        "reason_code": "INSUFFICIENT_BALANCE",
                        "details": {"wallet_id": "w-erin", "balance": 0.0},
                    }
                ],
            },
        },
    )
    space(api, "erin/notes").respond(
        402,
        json={
            "detail": "Insufficient balance",
            "policy_metadata": {
                "outcome": "payment_required",
                "entries": [
                    {
                        "policy_type": "xendit_per_request",
                        "kind": "payment",
                        "status": "rejected",
                        "amount": 0.02,
                        "currency": "USD",
                        "reason_code": "INSUFFICIENT_BALANCE",
                        "details": {"balance": 0.0},
                    }
                ],
            },
        },
    )
    results = await hub.search("q", ["erin/trials", "erin/notes"]).execute()
    assert all(r.outcome is Outcome.REJECTED and r.reason is Reason.NO_CREDITS for r in results)
    (action,) = results.actions
    assert isinstance(action, TopUp) and action.paths == ("erin/trials", "erin/notes")
    assert action.shortfall == Money.of("0.05") and action.wallet.key == "erin/xendit/USD"
    assert results.retryable == results.rows


# ── implicit sources and snapshots ───────────────────────────────────────


async def test_implicit_plan_lets_the_hub_pick_free_document_sources(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    search = api.post(f"{HUB}/api/v1/endpoints/search").respond(
        200,
        json={
            "results": [
                SOURCES["erin/trials"],
                SOURCES["alice/free-docs"],
                SOURCES["kim/assistant"],
                SOURCES["alice/more"],
            ],
            "total": 4,
            "query": "q",
        },
    )
    space(api, "alice/free-docs").respond(200, json=ok_body(("a", 0.9)))
    space(api, "alice/more").respond(200, json=ok_body(("b", 0.8)))
    plan = hub.search("q", max_sources=1)
    assert not plan.explicit
    results = await plan.execute()
    assert results.paths == ("alice/free-docs",) and results.ok
    assert json.loads(search.calls.last.request.content) == {"query": "q", "top_k": 10}
    results = await plan.skip("alice/free-docs").execute()
    assert results.paths == ("alice/free-docs", "alice/more")
    assert results["alice/free-docs"].reason is Reason.BY_USER and results["alice/more"].ok


async def test_plan_and_results_survive_a_snapshot(api: respx.MockRouter, hub: AsyncHub) -> None:
    space(api, "alice/free-docs").respond(200, json=ok_body(("a", 0.9)))
    saved = hub.search("q", ["alice/free-docs", "alice/more"]).skip("alice/more").to_dict()
    plan = SearchPlan.from_dict(hub, saved)
    results = await plan.execute()
    assert results["alice/free-docs"].ok and results["alice/more"].reason is Reason.BY_USER
    back = Results.from_dict(hub, results.to_dict())
    assert back == results and back.plan.skips == ("alice/more",)
    assert (await back.retry()) is back  # nothing retryable: no network
