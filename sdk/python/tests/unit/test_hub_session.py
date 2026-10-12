"""AsyncHub session, login flows, token renewal and Hub error mapping, over respx."""

from __future__ import annotations

import httpx
import pytest
import respx

import syfthub
from syfthub import (
    AsyncHub,
    AuthError,
    AuthMethod,
    ConfigurationError,
    HubUnreachable,
    Options,
    Retry,
)

HUB = "https://hub.test"
LOGIN = {
    "user": {"username": "alice"},
    "access_token": "acc-1",
    "refresh_token": "ref-1",
    "token_type": "bearer",
}
ME = {"id": 1, "username": "alice", "email": "alice@example.com", "role": "user"}


def fast() -> Options:
    return Options(retry=Retry(attempts=3, backoff=0, max_backoff=0))


@pytest.fixture
def api() -> respx.MockRouter:
    with respx.mock(base_url=HUB, assert_all_called=False) as router:
        yield router


async def test_password_login_sets_identity_and_tokens(api: respx.MockRouter) -> None:
    api.post("/api/v1/auth/login").respond(200, json=LOGIN)
    me = api.get("/api/v1/auth/me").respond(200, json=ME)
    async with AsyncHub(HUB, options=fast()) as hub:
        assert not hub.authenticated and hub.me is None
        identity = await hub.login("alice", "pw")
        assert identity.username == "alice" and identity.auth is AuthMethod.PASSWORD
        assert hub.me == identity and hub.authenticated
        assert me.calls.last.request.headers["Authorization"] == "Bearer acc-1"
        assert me.calls.last.request.headers["User-Agent"].startswith("syfthub-sdk/")


async def test_bad_password_raises_auth_error(api: respx.MockRouter) -> None:
    api.post("/api/v1/auth/login").respond(401, json={"detail": "Incorrect username or password"})
    async with AsyncHub(HUB, options=fast()) as hub:
        with pytest.raises(AuthError, match="Incorrect"):
            await hub.login("alice", "wrong")


async def test_token_login_validates_once(
    api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = api.get("/api/v1/auth/me").respond(200, json=ME)
    monkeypatch.setenv("SYFTHUB_URL", HUB)
    monkeypatch.setenv("SYFTHUB_TOKEN", "env-token")
    async with AsyncHub(options=fast()) as hub:
        assert hub.url == HUB and hub.authenticated
        identity = await hub.auth.whoami()
        assert identity.auth is AuthMethod.TOKEN and identity.email == "alice@example.com"
        assert me.calls.last.request.headers["Authorization"] == "Bearer env-token"


async def test_login_argument_validation() -> None:
    hub = AsyncHub(HUB)
    with pytest.raises(ConfigurationError):
        await hub.login()
    with pytest.raises(ConfigurationError):
        await hub.login("a", "b", token="t")
    with pytest.raises(ConfigurationError):
        AsyncHub("hub.test")
    await hub.aclose()


async def test_401_is_renewed_once_via_refresh(api: respx.MockRouter) -> None:
    api.post("/api/v1/auth/login").respond(200, json=LOGIN)
    me = api.get("/api/v1/auth/me").mock(
        side_effect=[
            httpx.Response(200, json=ME),
            httpx.Response(401, json={"detail": "expired"}),
            httpx.Response(200, json=ME),
        ]
    )
    refresh = api.post("/api/v1/auth/refresh").respond(
        200, json={"access_token": "acc-2", "refresh_token": "ref-2"}
    )
    async with AsyncHub(HUB, options=fast()) as hub:
        await hub.login("alice", "pw")
        await hub.auth.whoami()
        assert refresh.calls.last.request.content == b'{"refresh_token":"ref-1"}'
        assert me.calls.last.request.headers["Authorization"] == "Bearer acc-2"


async def test_401_with_dead_refresh_relogins_with_password(api: respx.MockRouter) -> None:
    login = api.post("/api/v1/auth/login").respond(200, json=LOGIN)
    api.get("/api/v1/auth/me").mock(
        side_effect=[
            httpx.Response(200, json=ME),
            httpx.Response(401),
            httpx.Response(200, json=ME),
        ]
    )
    api.post("/api/v1/auth/refresh").respond(401)
    async with AsyncHub(HUB, options=fast()) as hub:
        await hub.login("alice", "pw")
        await hub.auth.whoami()
        assert login.call_count == 2


async def test_401_on_a_bare_token_raises_auth_error(api: respx.MockRouter) -> None:
    api.get("/api/v1/auth/me").respond(401, json={"detail": "Could not validate credentials"})
    async with AsyncHub(HUB, token="stale", options=fast()) as hub:
        with pytest.raises(AuthError):
            await hub.auth.whoami()


async def test_5xx_is_retried_then_succeeds(api: respx.MockRouter) -> None:
    me = api.get("/api/v1/auth/me").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=ME)]
    )
    async with AsyncHub(HUB, token="t", options=fast()) as hub:
        await hub.auth.whoami()
        assert me.call_count == 2


async def test_unreachable_hub_after_retries(api: respx.MockRouter) -> None:
    me = api.get("/api/v1/auth/me").mock(side_effect=httpx.ConnectError("refused"))
    async with AsyncHub(HUB, token="t", options=fast()) as hub:
        with pytest.raises(HubUnreachable):
            await hub.auth.whoami()
        assert me.call_count == 3


async def test_budget_and_repr() -> None:
    hub = AsyncHub(HUB, budget=2)
    assert hub.budget.limit == syfthub.Money.of(2) and hub.spent == syfthub.Money.zero()
    hub.set_budget("0.50")
    assert hub.budget.limit == syfthub.Money.of("0.5")
    hub._record_spend(syfthub.Money.of("0.2"))
    assert hub.spent == syfthub.Money.of("0.2") and hub.budget.remaining == syfthub.Money.of("0.3")
    assert hub.set_budget(None).limit is None and hub.spent == syfthub.Money.of("0.2")
    assert "token" not in repr(hub) and "anonymous" in repr(hub)
    await hub.aclose()
