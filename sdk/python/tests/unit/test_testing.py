"""The ``syfthub.testing`` fakes drive the real SDK end to end without respx."""

from __future__ import annotations

import pytest

from syfthub import AuthError, Money, Outcome, Reason, SourceNotFound, TopUp, Verdict
from syfthub.testing import FakeHub


@pytest.fixture
def fake() -> FakeHub:
    f = FakeHub()
    f.add_source("alice", "notes", description="parental leave policy", tags=["hr"])
    f.add_source("erin", "trials", price=0.05)
    f.add_source("kim", "metered", mpp_price=0.02)
    f.add_source("kim", "assistant", type="model")
    f.space("alice").reply("notes", documents=[{"content": "16 weeks", "score": 0.8}])
    f.space("erin").reply("trials", documents=[{"content": "phase 3", "score": 0.7}], cost=0.05)
    f.space("kim").reply("assistant", summary="an answer")
    return f


async def test_catalogue_and_search(fake: FakeHub) -> None:
    async with fake.hub() as hub:
        listing = await hub.sources.list()
        assert listing.paths == ("alice/notes", "erin/trials", "kim/metered", "kim/assistant")
        assert (await hub.sources.list(owner="kim")).paths == ("kim/metered", "kim/assistant")
        assert (await hub.sources.list(type="model")).paths == ("kim/assistant",)
        assert (await hub.sources.search("leave")).paths == ("alice/notes",)
        assert (await hub.sources.get("erin/trials")).pricing is not None
        with pytest.raises(SourceNotFound):
            await hub.sources.get("nobody/here")
        assert (await hub.me) if False else hub.me is None
        assert (await hub.auth.whoami()).email == "me@example.org"


async def test_full_search_flow_with_prepaid_topup_and_mpp(fake: FakeHub) -> None:
    async with fake.hub(budget=1.0) as hub:
        plan = hub.search("leave", ["alice/notes", "erin/trials", "kim/metered", "kim/assistant"])
        pre = await plan.preflight()
        assert pre["erin/trials"].verdict is Verdict.NEEDS_CREDITS and not pre.ready
        (action,) = pre.actions
        assert isinstance(action, TopUp) and action.shortfall == Money.of("0.05")

        invoice = await action.top_up()
        assert invoice.open and invoice.checkout_url is not None
        fake.space("erin").pay(invoice.id)
        paid = await invoice.refresh()
        assert paid.paid and fake.space("erin").balance == 1.0

        results = await plan.execute()
        assert [r.outcome for r in results] == [Outcome.RETURNED] * 4
        assert results["erin/trials"].paid_from == "erin/xendit/USD"
        assert results["kim/metered"].charge is not None and results[
            "kim/metered"
        ].cost == Money.of("0.02")
        assert results.answers == {"kim/assistant": "an answer"}
        assert hub.spent == Money.of("0.07") and fake.space("erin").balance == 0.95
        assert results.cost == {"USD": Money.of("0.07")}

    pay_calls = [c for c in fake.calls if c.path == "/api/v1/wallet/pay"]
    assert len(pay_calls) == 1 and pay_calls[0].headers["authorization"] == "<redacted>"
    assert pay_calls[0].json_body["endpoint_slug"] == "metered"


async def test_rejections_and_hub_errors(fake: FakeHub) -> None:
    fake.space("alice").reject(
        "notes",
        outcome="rate_limited",
        details={"retry_after_seconds": 9},
        headers={"Retry-After": "9"},
    )
    fake.mpp_error = ("WALLET_NOT_CONFIGURED", "No wallet configured")
    async with fake.hub() as hub:
        results = await hub.search("q", ["alice/notes", "kim/metered"]).execute()
        limited = results["alice/notes"]
        assert limited.reason is Reason.RATE_LIMITED and limited.rate_limit is not None
        assert limited.rate_limit.reset_seconds == 9
        metered = results["kim/metered"]
        assert metered.outcome is Outcome.PAYMENT_REQUIRED
        assert metered.error is not None and "WALLET_NOT_CONFIGURED" in metered.error


async def test_login_is_checked_when_users_are_set(fake: FakeHub) -> None:
    fake.users = {"me": "secret"}
    async with fake.hub(token=None) as hub:
        with pytest.raises(AuthError):
            await hub.login("me", "wrong")
        identity = await hub.login("me", "secret")
        assert identity.username == "me" and hub.authenticated
        assert (await hub.sources.list()).total == 4
    async with fake.hub(token="not-issued") as stranger:
        with pytest.raises(AuthError):
            await stranger.sources.list()
