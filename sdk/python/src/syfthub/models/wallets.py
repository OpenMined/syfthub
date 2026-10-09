"""``Wallet``, ``Invoice``, and the payment records a result row carries."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, PrivateAttr

from ..errors import PaymentTimeout, ValidationError
from .base import Base, Bound, Frozen
from .enums import InvoiceStatus, Rail
from .money import Bundle, Money


class Wallet(Base):
    """A prepaid wallet with a publisher. Not frozen: ``refresh()`` updates the balance in place.

    ``id`` is the policy's ``wallet_id`` (the grouping key); ``key`` is the readable label
    ``owner/rail/currency``. The three URLs are followed exactly as the policy publishes them.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    key: str
    owner: str
    rail: Rail
    currency: str
    balance: Money | None = None
    refreshed_at: datetime | None = None
    sources: tuple[str, ...] = ()
    bundles: tuple[Bundle, ...] = ()
    payment_url: str | None = None
    credits_url: str | None = None
    invoices_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    _hub: Any = PrivateAttr(default=None)

    @classmethod
    def from_dict(cls, hub: Any, d: dict[str, Any]) -> Wallet:
        obj = cls.model_validate(d)
        obj._bind(hub)
        return obj

    def _bind(self, hub: Any) -> None:
        self._hub = hub

    def _require_hub(self) -> Any:
        if self._hub is None:
            raise ValidationError("Wallet is not bound to a hub; use Wallet.from_dict(hub, d)")
        return self._hub

    def bundle(self, bundle: str | Bundle) -> Bundle:
        """Resolve a bundle id against what this wallet sells."""
        if isinstance(bundle, Bundle):
            return bundle
        for b in self.bundles:
            if b.id == bundle:
                return b
        raise ValidationError(
            f"wallet {self.key} sells no bundle {bundle!r}; "
            f"choices: {', '.join(b.id for b in self.bundles) or 'none'}"
        )

    def suggest(self, shortfall: Money) -> Bundle | None:
        """The smallest bundle whose credits cover ``shortfall``; None if none does."""
        covering = [b for b in self.bundles if b.granted >= shortfall]
        return min(covering, key=lambda b: b.granted.amount) if covering else None

    async def refresh(self) -> Wallet:
        """One balance call to ``credits_url``; updates ``balance`` and ``refreshed_at``."""
        balance, at = await self._require_hub().wallet_balance(self)
        self.balance = balance
        self.refreshed_at = at
        return self

    async def top_up(self, bundle: str | Bundle) -> Invoice:
        """``POST payment_url`` with the bundle; returns a ``PENDING`` invoice."""
        invoice: Invoice = await self._require_hub().wallet_top_up(self, self.bundle(bundle))
        return invoice

    async def invoices(self) -> tuple[Invoice, ...]:
        """``GET invoices_url``: my invoices on this wallet."""
        invoices: tuple[Invoice, ...] = await self._require_hub().wallet_invoices(self)
        return invoices


class Invoice(Bound):
    """A top-up invoice from the Space's payment route."""

    id: str
    wallet_key: str
    bundle: str
    amount: Money
    status: InvoiceStatus = InvoiceStatus.PENDING
    checkout_url: str | None = None
    created_at: datetime | None = None
    paid_at: datetime | None = None
    expires_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_space(cls, wallet_key: str, body: dict[str, Any]) -> Invoice:
        """Build from the Space's ``InvoiceResponse`` body, kept verbatim in ``raw``."""
        status_value = body.get("status")
        status = (
            InvoiceStatus(status_value)
            if status_value in {s.value for s in InvoiceStatus}
            else InvoiceStatus.PENDING
        )
        return cls.model_validate(
            {
                "id": str(body.get("id", "")),
                "wallet_key": wallet_key,
                "bundle": body.get("bundle_name") or body.get("bundle") or "",
                "amount": Money.of(body.get("amount", 0), body.get("currency") or "USD"),
                "status": status,
                "checkout_url": body.get("checkout_url"),
                "created_at": body.get("created_at"),
                "paid_at": body.get("paid_at"),
                "expires_at": body.get("expires_at"),
                "raw": body,
            }
        )

    @property
    def paid(self) -> bool:
        return self.status is InvoiceStatus.PAID

    @property
    def open(self) -> bool:
        """Still in flight: pending, or processing (checkout done, settlement pending)."""
        return self.status.open

    async def refresh(self) -> Invoice:
        """A new ``Invoice`` read back from ``invoices_url`` (balance as the fallback)."""
        fresh: Invoice = await self._require_hub().invoice_refresh(self)
        return fresh

    async def wait_paid(self, *, timeout: float = 600, poll: float = 5) -> Invoice:
        """Poll ``refresh()`` until settled. Keeps polling through ``processing``; returns early
        on ``expired`` or ``cancelled`` so the app can act. Raises ``PaymentTimeout``."""
        deadline = time.monotonic() + timeout
        current = self
        while True:
            current = await current.refresh()
            if not current.open:
                return current
            if time.monotonic() >= deadline:
                raise PaymentTimeout(self.id, timeout)
            await asyncio.sleep(min(poll, max(0.0, deadline - time.monotonic())))


class Charge(Frozen):
    """One MPP 402 challenge."""

    source: str
    amount: Money
    www_authenticate: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class ChargeEntry(Frozen):
    """One ``policy_metadata.entries[]`` item from a Space response."""

    source: str
    policy_type: str | None = None
    kind: str | None = None
    status: str | None = None
    amount: Money | None = None
    wallet: str | None = None
    rail: Rail | None = None
    transaction_id: str | None = None
    reason_code: str | None = None
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_space(cls, source: str, entry: dict[str, Any]) -> ChargeEntry:
        amount = entry.get("amount")
        currency = entry.get("currency") or "USD"
        tx_raw = entry.get("transaction")
        tx: dict[str, Any] = tx_raw if isinstance(tx_raw, dict) else {}
        recipient_raw = entry.get("recipient")
        recipient: dict[str, Any] = recipient_raw if isinstance(recipient_raw, dict) else {}
        rail_value = tx.get("rail")
        rail: Rail | None
        try:
            rail = Rail(rail_value) if isinstance(rail_value, str) else None
        except ValueError:
            rail = None
        return cls(
            source=source,
            policy_type=entry.get("policy_type"),
            kind=entry.get("kind"),
            status=entry.get("status"),
            amount=Money.of(amount, currency) if amount is not None else None,
            wallet=recipient.get("wallet_address"),
            rail=rail,
            transaction_id=tx.get("id"),
            reason_code=entry.get("reason_code"),
            reason=entry.get("reason"),
            details=entry.get("details") or {},
            raw=entry,
        )

    @property
    def charged(self) -> bool:
        return self.status == "charged" and self.amount is not None and self.amount.positive


class RateLimit(Frozen):
    """From the Space's rate-limit policy entry (``details``) or response headers."""

    limit: str | None = None
    remaining: int | None = None
    reset_seconds: int | None = None

    @classmethod
    def from_entry(
        cls, details: dict[str, Any], headers: dict[str, str] | None = None
    ) -> RateLimit:
        """Read ``reset_seconds`` (code) or ``retry_after_seconds`` (docs), then ``Retry-After``."""
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        reset = details.get("reset_seconds", details.get("retry_after_seconds"))
        if reset is None and "retry-after" in headers:
            reset = headers["retry-after"]
        remaining = details.get("remaining")
        if remaining is None and "x-ratelimit-remaining" in headers:
            remaining = headers["x-ratelimit-remaining"]
        limit = details.get("limit")
        if limit is None and "x-ratelimit-limit" in headers:
            limit = headers["x-ratelimit-limit"]
        return cls(
            limit=str(limit) if limit is not None else None,
            remaining=_int(remaining),
            reset_seconds=_int(reset),
        )


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
