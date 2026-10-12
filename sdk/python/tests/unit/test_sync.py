"""``syfthub.Hub``: the same flows with no ``await``, plus the two loop guards."""

from __future__ import annotations

import asyncio
import threading

import pytest

import syfthub
from syfthub import Hub, Money, Outcome, Results, SearchPlan, TopUp, Verdict, Wallet
from syfthub.testing import FakeHub


@pytest.fixture
def fake() -> FakeHub:
    f = FakeHub()
    f.add_source("alice", "notes", description="leave")
    f.add_source("erin", "trials", price=0.05)
    f.space("alice").reply("notes", documents=[{"content": "16 weeks", "score": 0.8}])
    f.space("erin").reply("trials", documents=[{"content": "phase 3", "score": 0.7}], cost=0.05)
    return f


@pytest.fixture
def hub(fake: FakeHub) -> Hub:
    h = Hub(fake.url, token="t", options=fake.options())
    yield h  # type: ignore[misc]
    h.close()


def test_same_names_no_await(fake: FakeHub, hub: Hub) -> None:
    assert repr(hub).startswith("Hub(")
    listing = hub.sources.list()
    assert listing.paths == ("alice/notes", "erin/trials") and len(listing) == 2
    assert isinstance(listing[0], syfthub.Source) and listing["erin/trials"].pricing is not None

    plan = hub.search("leave", listing)  # a proxied SourceList resolves like the real one
    assert isinstance(plan, SearchPlan) and plan.sources == ("alice/notes", "erin/trials")
    pre = plan.preflight()
    assert [r.verdict for r in pre] == [Verdict.READY, Verdict.NEEDS_CREDITS]
    (action,) = pre.actions
    assert isinstance(action, TopUp)
    match action:  # the proxy answers to the real class, so match-case works
        case TopUp():
            invoice = action.top_up()
        case _:
            pytest.fail("not a TopUp")
    fake.space("erin").pay(invoice.id)
    assert invoice.refresh().paid

    wallet = hub.wallets.list()[0]
    assert isinstance(wallet, Wallet) and wallet.balance == Money.zero()  # read at pre-flight
    wallet.refresh()
    assert wallet.balance == Money.of(1)  # updated in place through the proxy

    results = plan.skip("alice/notes").execute()
    assert isinstance(results, Results)
    assert results["alice/notes"].outcome is Outcome.HELD and results["erin/trials"].ok
    assert [p for p, _ in results.documents] == ["erin/trials"]
    assert hub.spent == Money.of("0.05") and results.cost == {"USD": Money.of("0.05")}

    restored = hub.load(SearchPlan, plan.to_dict())
    assert restored == plan and restored.execute().plan == plan
    again = results.retry()
    assert again is results or again == results


def test_sync_calls_work_inside_a_running_event_loop(hub: Hub) -> None:
    async def notebook_cell() -> int:
        return len(hub.sources.list())  # blocks this loop's thread, runs on the private one

    assert asyncio.run(notebook_cell()) == 2


def test_sync_call_from_the_private_loop_thread_is_refused(hub: Hub) -> None:
    seen: list[BaseException | None] = [None]

    async def inside() -> None:
        try:
            hub.sources.list()
        except RuntimeError as e:
            seen[0] = e

    hub.async_hub._searcher  # noqa: B018 - the async hub exists on the loop
    loop = hub._loop  # type: ignore[attr-defined]
    asyncio.run_coroutine_threadsafe(inside(), loop.loop).result(timeout=5)
    assert isinstance(seen[0], RuntimeError) and "own event-loop thread" in str(seen[0])


def test_close_is_idempotent_and_refuses_calls_after(fake: FakeHub) -> None:
    hub = Hub(fake.url, token="t", options=fake.options())
    thread_names = {t.name for t in threading.enumerate()}
    assert "syfthub-sync" in thread_names
    hub.close()
    hub.close()
    with pytest.raises(RuntimeError):
        hub.sources.list()
    with Hub(fake.url, token="t", options=fake.options()) as h:
        assert h.sources.get("alice/notes").path == "alice/notes"


def test_async_hub_is_reachable_for_mixed_code(hub: Hub) -> None:
    async def on_the_loop() -> int:
        return len(await hub.async_hub.sources.list())

    assert asyncio.run_coroutine_threadsafe(on_the_loop(), hub._loop.loop).result(5) == 2  # type: ignore[attr-defined]
