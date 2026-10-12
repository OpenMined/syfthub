"""Async interplay: no deadlocks, no re-entrant locks, one renewal per 401 storm, one mint per
satellite token. Every test is wrapped in a hard timeout so a hang fails instead of stalling CI."""

from __future__ import annotations

import asyncio
import itertools

import httpx
import pytest
import respx

from syfthub import AsyncHub, AuthError, Options, Retry

from .conftest import hub_body, xendit_policy

HUB = "https://hub.test"
SPACE = "https://erin.space.test"
ME = {"id": 1, "username": "alice", "email": "alice@example.com", "role": "user"}
LOGIN = {"user": {}, "access_token": "acc-1", "refresh_token": "ref-1"}


async def within(coro, seconds: float = 5.0):  # type: ignore[no-untyped-def]
    return await asyncio.wait_for(coro, timeout=seconds)


@pytest.fixture
def api() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
async def hub() -> AsyncHub:
    h = AsyncHub(HUB, token="acc-0", options=Options(retry=Retry(attempts=1)))
    yield h
    await h.aclose()


def first_401_then_ok(valid: set[str]):  # type: ignore[no-untyped-def]
    """A /me handler that rejects any bearer not in ``valid``."""

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["Authorization"].removeprefix("Bearer ")
        return (
            httpx.Response(200, json=ME)
            if token in valid
            else httpx.Response(401, json={"detail": "expired"})
        )

    return handler


async def test_401_storm_renews_once(api: respx.MockRouter) -> None:
    api.post(f"{HUB}/api/v1/auth/login").respond(200, json=LOGIN)
    me = api.get(f"{HUB}/api/v1/auth/me").mock(side_effect=first_401_then_ok({"acc-1", "acc-2"}))
    refresh = api.post(f"{HUB}/api/v1/auth/refresh").respond(
        200, json={"access_token": "acc-2", "refresh_token": "ref-2"}
    )
    async with AsyncHub(HUB, options=Options(retry=Retry(attempts=1))) as hub:
        await within(hub.login("alice", "pw"))
        hub._session.access_token = "stale"  # simulate expiry
        results = await within(asyncio.gather(*(hub.auth.whoami() for _ in range(8))))
        assert all(r.username == "alice" for r in results)
        assert refresh.call_count == 1
        # login whoami + 8 calls + at most one retry each; the mock transport may let the
        # first renewal land before the other callers even start, so fewer retries are fine
        assert 1 + 8 <= me.call_count <= 1 + 8 + 8


async def test_token_only_session_401_raises_without_recursion(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    me = api.get(f"{HUB}/api/v1/auth/me").respond(401, json={"detail": "expired"})
    refresh = api.post(f"{HUB}/api/v1/auth/refresh").respond(401)
    with pytest.raises(AuthError):
        await within(hub.auth.whoami())
    assert me.call_count == 1 and refresh.call_count == 0  # no refresh token, nothing to retry with


async def test_dead_refresh_and_dead_password_do_not_loop(api: respx.MockRouter) -> None:
    login = api.post(f"{HUB}/api/v1/auth/login").mock(
        side_effect=[
            httpx.Response(200, json=LOGIN),
            httpx.Response(401, json={"detail": "locked"}),
        ]
    )
    api.get(f"{HUB}/api/v1/auth/me").mock(side_effect=first_401_then_ok({"acc-1"}))
    refresh = api.post(f"{HUB}/api/v1/auth/refresh").respond(401)
    async with AsyncHub(HUB, options=Options(retry=Retry(attempts=1))) as hub:
        await within(hub.login("alice", "pw"))
        hub._session.access_token = "stale"
        with pytest.raises(AuthError):
            await within(hub.auth.whoami())
        assert refresh.call_count == 1 and login.call_count == 2


async def test_concurrent_balance_reads_mint_one_satellite_token(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    api.get(f"{HUB}/api/v1/endpoints/public").respond(
        200, json=[hub_body("erin", "trials", policies=[xendit_policy()])]
    )
    mint = api.get(f"{HUB}/api/v1/token").respond(
        200, json={"target_token": "sat", "expires_in": 60}
    )
    balance = api.get(f"{SPACE}/api/credits").respond(200, json={"balance": 5, "currency": "USD"})
    (w,) = await within(hub.wallets.list())
    await within(asyncio.gather(*(w.refresh() for _ in range(10))))
    assert mint.call_count == 1 and balance.call_count == 10


async def test_nested_locks_token_mint_that_needs_a_renewal(api: respx.MockRouter) -> None:
    """TokenCache lock held while /token gets a 401 -> Session lock for the refresh. The order is
    always cache-then-session, so this must complete."""
    api.post(f"{HUB}/api/v1/auth/login").respond(200, json=LOGIN)
    api.get(f"{HUB}/api/v1/auth/me").respond(200, json=ME)
    api.get(f"{HUB}/api/v1/endpoints/public").respond(
        200, json=[hub_body("erin", "trials", policies=[xendit_policy()])]
    )
    counter = itertools.count()

    def mint(_request: httpx.Request) -> httpx.Response:
        if next(counter) == 0:
            return httpx.Response(401)
        return httpx.Response(200, json={"target_token": "sat", "expires_in": 60})

    api.get(f"{HUB}/api/v1/token").mock(side_effect=mint)
    refresh = api.post(f"{HUB}/api/v1/auth/refresh").respond(
        200, json={"access_token": "acc-2", "refresh_token": "ref-2"}
    )
    api.get(f"{SPACE}/api/credits").respond(200, json={"balance": 5, "currency": "USD"})
    async with AsyncHub(HUB, options=Options(retry=Retry(attempts=1))) as hub:
        await within(hub.login("alice", "pw"))
        (w,) = await within(hub.wallets.list())
        await within(asyncio.gather(w.refresh(), w.refresh(), w.refresh()))
        assert refresh.call_count == 1 and w.balance is not None


async def test_wait_paid_yields_to_the_loop(api: respx.MockRouter, hub: AsyncHub) -> None:
    """A tight poll must not starve other tasks: a sibling task gets to run while we poll."""
    api.get(f"{HUB}/api/v1/endpoints/public").respond(
        200, json=[hub_body("erin", "trials", policies=[xendit_policy()])]
    )
    api.get(f"{HUB}/api/v1/token").respond(200, json={"target_token": "sat", "expires_in": 60})
    api.post(f"{SPACE}/api/payments").respond(
        201,
        json={
            "id": "i",
            "bundle_name": "pro",
            "amount": 10,
            "currency": "USD",
            "status": "pending",
            "checkout_url": "u",
        },
    )
    api.get(f"{SPACE}/api/invoices").respond(
        200,
        json=[
            {"id": "i", "bundle_name": "pro", "amount": 10, "currency": "USD", "status": "pending"}
        ],
    )
    (w,) = await within(hub.wallets.list())
    inv = await within(w.top_up("pro"))
    ticks = 0

    async def sibling() -> None:
        nonlocal ticks
        for _ in range(5):
            ticks += 1
            await asyncio.sleep(0)

    from syfthub import PaymentTimeout

    with pytest.raises(PaymentTimeout):
        await within(asyncio.gather(inv.wait_paid(timeout=0.05, poll=0), sibling()))
    assert ticks == 5
