from __future__ import annotations

from datetime import datetime, timezone

import pytest

from syfthub import Invoice, InvoiceStatus, Money, PaymentTimeout, Wallet


class FakeWalletPort:
    """Ten-line fake of the wallet port the models call through."""

    def __init__(self, statuses: list[InvoiceStatus] | None = None) -> None:
        self.statuses = list(statuses or [])
        self.calls: list[str] = []

    async def wallet_balance(self, wallet: Wallet) -> tuple[Money, datetime]:
        self.calls.append("balance")
        return Money.of("3.5", wallet.currency), datetime.now(timezone.utc)

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
