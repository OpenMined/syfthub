"""hub.wallets over respx: grouping, satellite tokens, balance, top-up, invoices, refresh."""

from __future__ import annotations

import httpx
import pytest
import respx

from syfthub import AsyncHub, InvoiceStatus, Money, Options, PaymentFailed, Rail, Retry

from .conftest import hub_body, xendit_policy

HUB = "https://hub.test"
SPACE = "https://erin.space.test"


@pytest.fixture
def api() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{HUB}/api/v1/token").respond(
            200, json={"target_token": "sat-1", "expires_in": 60}
        )
        router.get(f"{HUB}/api/v1/endpoints/public").respond(
            200,
            json=[
                hub_body("erin", "trials", policies=[xendit_policy()]),
                hub_body("erin", "notes", policies=[xendit_policy(price=0.02)]),  # same wallet_id
                hub_body("alice", "free-docs"),
                hub_body(
                    "kim",
                    "metered",
                    policies=[{"type": "mpp", "config": {"price": 0.01, "currency": "USD"}}],
                ),
            ],
        )
        yield router


@pytest.fixture
async def hub() -> AsyncHub:
    h = AsyncHub(HUB, token="t", options=Options(retry=Retry(attempts=1)))
    yield h
    await h.aclose()


@pytest.mark.usefixtures("api")
async def test_list_groups_sources_by_wallet_id(hub: AsyncHub) -> None:
    wallets = await hub.wallets.list()
    assert len(wallets) == 1
    w = wallets[0]
    assert w.id == "w-erin" and w.key == "erin/xendit/USD" and w.rail is Rail.XENDIT
    assert w.sources == ("erin/trials", "erin/notes") and w.balance is None
    assert [b.id for b in w.bundles] == ["starter", "pro"]
    assert hub.wallets.get("erin/xendit/USD") is w and hub.wallets.get("w-erin") is w


async def test_for_source_free_and_mpp_return_none(api: respx.MockRouter, hub: AsyncHub) -> None:
    api.get(f"{HUB}/api/v1/endpoints/public/alice/free-docs").respond(
        200, json=hub_body("alice", "free-docs")
    )
    api.get(f"{HUB}/api/v1/endpoints/public/kim/metered").respond(
        200, json=hub_body("kim", "metered", policies=[{"type": "mpp", "config": {"price": 0.01}}])
    )
    api.get(f"{HUB}/api/v1/endpoints/public/erin/trials").respond(
        200, json=hub_body("erin", "trials", policies=[xendit_policy()])
    )
    assert await hub.wallets.for_source("alice/free-docs") is None
    assert await hub.wallets.for_source("kim/metered") is None
    w = await hub.wallets.for_source("erin/trials")
    assert w is not None and w.sources == ("erin/trials",)


async def test_refresh_reads_balance_with_a_cached_satellite_token(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    balance = api.get(f"{SPACE}/api/credits").respond(
        200, json={"wallet_id": "w-erin", "user_email": "a@b", "balance": 24.95, "currency": "USD"}
    )
    (w,) = await hub.wallets.list()
    await w.refresh()
    await w.refresh()
    assert w.balance == Money.of("24.95") and w.refreshed_at is not None
    assert balance.calls.last.request.headers["Authorization"] == "Bearer sat-1"
    token_route = api.get(f"{HUB}/api/v1/token")
    assert token_route.call_count == 1
    params = token_route.calls.last.request.url.params
    assert params["owner_username"] == "erin" and params["resource"] == SPACE


async def test_cluster_wallet_mints_token_for_the_wallet_owner(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    station = "https://station.test"
    cfg = {
        **xendit_policy()["config"],
        "wallet_owner": "station-admin",
        "wallet_id": "w-shared",
        "credits_url": f"{station}/api/v1/credits/w-shared/balance",
    }
    api.get(f"{HUB}/api/v1/endpoints/public/erin/shared").respond(
        200, json=hub_body("erin", "shared", policies=[{"type": "cluster", "config": cfg}])
    )
    api.get(f"{station}/api/v1/credits/w-shared/balance").respond(
        200, json={"balance": 1, "currency": "USD"}
    )
    w = await hub.wallets.for_source("erin/shared")
    assert w is not None and w.owner == "station-admin" and w.rail is Rail.CLUSTER
    await w.refresh()
    params = api.get(f"{HUB}/api/v1/token").calls.last.request.url.params
    assert params["owner_username"] == "station-admin" and params["resource"] == station


async def test_top_up_posts_bundle_and_returns_pending_invoice(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    invoice_body = {
        "id": "inv-1",
        "wallet_id": "w-erin",
        "user_email": "a@b",
        "provider": "xendit",
        "client_reference": "x",
        "checkout_url": "https://checkout.test/x",
        "bundle_name": "pro",
        "amount": 10.0,
        "currency": "USD",
        "status": "pending",
        "paid_at": None,
        "created_at": "2026-10-09T10:40:00Z",
        "updated_at": "2026-10-09T10:40:00Z",
    }
    pay = api.post(f"{SPACE}/api/payments").respond(201, json=invoice_body)
    (w,) = await hub.wallets.list()
    inv = await w.top_up("pro")
    assert inv.id == "inv-1" and inv.open and inv.checkout_url == "https://checkout.test/x"
    assert inv.amount == Money.of(10) and inv.wallet_key == w.key
    assert pay.calls.last.request.content == b'{"bundle_name":"pro","endpoint_slug":"trials"}'

    api.get(f"{SPACE}/api/invoices").respond(
        200, json=[{**invoice_body, "status": "paid", "paid_at": "2026-10-09T10:41:00Z"}]
    )
    fresh = await inv.refresh()
    assert fresh.status is InvoiceStatus.PAID and fresh.paid_at is not None
    again = await hub.wallets.invoice(w.key, "inv-1")
    assert again.paid
    with pytest.raises(PaymentFailed):
        await hub.wallets.invoice(w.key, "inv-404")


async def test_top_up_errors_surface_as_payment_failed(
    api: respx.MockRouter, hub: AsyncHub
) -> None:
    api.post(f"{SPACE}/api/payments").respond(
        422, json={"detail": "Unknown bundle for currency USD"}
    )
    (w,) = await hub.wallets.list()
    with pytest.raises(PaymentFailed, match="Unknown bundle"):
        await w.top_up("pro")
    api.post(f"{SPACE}/api/payments").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(PaymentFailed):
        await w.top_up("pro")


async def test_invoice_refresh_falls_back_to_balance(api: respx.MockRouter, hub: AsyncHub) -> None:
    (w,) = await hub.wallets.list()
    api.get(f"{SPACE}/api/invoices").respond(200, json=[])
    api.get(f"{SPACE}/api/credits").respond(200, json={"balance": 10, "currency": "USD"})
    from syfthub import Invoice

    inv = Invoice.from_dict(
        hub,
        {
            "id": "ghost",
            "wallet_key": w.key,
            "bundle": "pro",
            "amount": {"amount": "10", "currency": "USD"},
        },
    )
    assert (await inv.refresh()).paid
    api.get(f"{SPACE}/api/credits").respond(200, json={"balance": 1, "currency": "USD"})
    assert (await inv.refresh()).open


async def test_wallet_invoices_lists_mine(api: respx.MockRouter, hub: AsyncHub) -> None:
    api.get(f"{SPACE}/api/invoices").respond(
        200,
        json=[
            {
                "id": "a",
                "bundle_name": "pro",
                "amount": 10,
                "currency": "USD",
                "status": "expired",
                "checkout_url": "u",
            }
        ],
    )
    (w,) = await hub.wallets.list()
    (inv,) = await w.invoices()
    assert inv.status is InvoiceStatus.EXPIRED and inv._hub is hub
