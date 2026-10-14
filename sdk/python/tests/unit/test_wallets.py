from __future__ import annotations

from datetime import UTC, datetime

import pytest

from syfthub import Invoice, InvoiceStatus, Money, PaymentTimeout, Source, Wallet

from .conftest import hub_body, xendit_policy


class FakeWalletPort:
    """Ten-line fake of the wallet port the models call through."""

    def __init__(self, statuses: list[InvoiceStatus] | None = None) -> None:
        self.statuses = list(statuses or [])
        self.calls: list[str] = []

    async def wallet_balance(self, wallet: Wallet) -> tuple[Money, datetime]:
        self.calls.append("balance")
        return Money.of("3.5", wallet.currency), datetime.now(UTC)

    async def wallet_top_up(self, wallet: Wallet, bundle):  # type: ignore[no-untyped-def]
        self.calls.append(f"top_up:{bundle.id}")
        inv = Invoice(
            id="inv-1",
            wallet_key=wallet.key,
            bundle=bundle.id,
            amount=bundle.amount,
            checkout_url="https://pay",
        )
        inv._bind(self)
        return inv

    async def wallet_invoices(self, wallet: Wallet):  # type: ignore[no-untyped-def]  # noqa: ARG002
        return ()

    async def invoice_refresh(self, invoice: Invoice) -> Invoice:
        self.calls.append("refresh")
        status = self.statuses.pop(0) if self.statuses else invoice.status
        fresh = invoice.model_copy(update={"status": status})
        fresh._bind(self)
        return fresh


async def test_wallet_refresh_updates_in_place(wallet: Wallet) -> None:
    port = FakeWalletPort()
    wallet._bind(port)
    assert wallet.balance is None
    same = await wallet.refresh()
    assert same is wallet and wallet.balance == Money.of("3.5") and wallet.refreshed_at is not None


async def test_top_up_by_id_returns_pending_invoice(wallet: Wallet) -> None:
    port = FakeWalletPort()
    wallet._bind(port)
    inv = await wallet.top_up("starter")
    assert inv.open and inv.checkout_url == "https://pay" and port.calls == ["top_up:starter"]
    d = inv.to_dict()
    assert Invoice.from_dict(port, d) == inv


async def test_wait_paid_polls_until_paid(wallet: Wallet) -> None:
    port = FakeWalletPort([InvoiceStatus.PENDING, InvoiceStatus.PAID])
    wallet._bind(port)
    inv = await wallet.top_up("starter")
    paid = await inv.wait_paid(timeout=5, poll=0)
    assert paid.paid and port.calls.count("refresh") == 2


async def test_wait_paid_times_out(wallet: Wallet) -> None:
    port = FakeWalletPort()
    wallet._bind(port)
    inv = await wallet.top_up("starter")
    with pytest.raises(PaymentTimeout):
        await inv.wait_paid(timeout=0, poll=0)


async def test_wait_paid_returns_early_on_expired(wallet: Wallet) -> None:
    port = FakeWalletPort([InvoiceStatus.EXPIRED])
    wallet._bind(port)
    inv = await wallet.top_up("starter")
    assert (await inv.wait_paid(timeout=5, poll=0)).status is InvoiceStatus.EXPIRED


def test_wallet_dict_roundtrip(wallet: Wallet) -> None:
    d = wallet.to_dict()
    assert "_hub" not in d and d["rail"] == "xendit"
    assert Wallet.from_dict(None, d) == wallet


def test_invoice_from_space_body() -> None:
    body = {
        "id": "0d1e2f3a",
        "wallet_id": "77aa",
        "user_email": "alice@example.com",
        "provider": "stripe",
        "checkout_url": "https://checkout.stripe.com/c/pay/cs_test",
        "bundle_name": "Basic",
        "amount": 25.0,
        "currency": "USD",
        "status": "processing",
        "paid_at": None,
        "created_at": "2026-10-09T10:40:00.000Z",
        "updated_at": "2026-10-09T10:40:00.000Z",
    }
    inv = Invoice.from_space("acme/stripe/USD", body)
    assert inv.id == "0d1e2f3a" and inv.bundle == "Basic" and inv.amount == Money.of(25, "USD")
    assert inv.status is InvoiceStatus.PROCESSING and inv.open and not inv.paid
    assert inv.created_at is not None and inv.raw == body
    assert Invoice.from_space("k", {**body, "status": "cancelled"}).open is False


async def test_wait_paid_polls_through_processing(wallet: Wallet) -> None:
    port = FakeWalletPort([InvoiceStatus.PROCESSING, InvoiceStatus.PAID])
    wallet._bind(port)
    inv = await wallet.top_up("starter")
    assert (await inv.wait_paid(timeout=5, poll=0)).paid and port.calls.count("refresh") == 2


def test_rate_limit_from_entry_reads_both_spellings() -> None:
    from syfthub import RateLimit

    assert (
        RateLimit.from_entry({"reset_seconds": 41, "remaining": 0, "limit": "20/m"}).reset_seconds
        == 41
    )
    assert RateLimit.from_entry({"retry_after_seconds": "7"}).reset_seconds == 7
    hdr = RateLimit.from_entry({}, {"Retry-After": "12", "X-RateLimit-Remaining": "3"})
    assert hdr.reset_seconds == 12 and hdr.remaining == 3 and hdr.limit is None


def test_wallet_id_falls_back_to_the_uuid_in_the_credits_url() -> None:
    from syfthub.models.sources import wallet_id_from_url
    from syfthub.wallets import group_wallets

    base = "https://syft.republika.co.id/api/v1/payments/gateway/wallets"
    uid = "F95FE14C-6CF7-423C-AF95-79E7E4BE6DE6"
    urls = {
        "credits_url": f"{base}/{uid}/balance",
        "payment_url": f"{base}/{uid}/invoices",
        "invoices_url": f"{base}/{uid}/invoices/me",
    }
    archive = Source.from_hub(
        hub_body("republika", "archive", policies=[xendit_policy(wallet_id=None, **urls)])
    )
    dataset = Source.from_hub(
        hub_body("republika", "dataset", policies=[xendit_policy(wallet_id=None, **urls)])
    )
    assert archive.pricing is not None and archive.pricing.wallet_id == uid.lower()  # validator
    (wallet,) = group_wallets([archive, dataset]).values()
    assert wallet.id == uid.lower() and wallet.key == "republika/xendit/USD"
    assert wallet.sources == ("republika/archive", "republika/dataset")
    assert wallet.credits_url == urls["credits_url"]

    # an explicit wallet_id wins; a URL without a UUID stays the id as a whole
    explicit = Source.from_hub(hub_body("erin", "paid", policies=[xendit_policy(wallet_id="w-1")]))
    assert explicit.pricing is not None and explicit.pricing.wallet_id == "w-1"
    (w,) = group_wallets([explicit]).values()
    assert w.id == "w-1"
    plain = Source.from_hub(
        hub_body(
            "erin",
            "plain",
            policies=[xendit_policy(wallet_id=None, credits_url="https://erin.test/credits")],
        )
    )
    (w,) = group_wallets([plain]).values()
    assert w.id == "https://erin.test/credits"
    assert wallet_id_from_url(None) is None and wallet_id_from_url("https://x/y?z=1") is None
