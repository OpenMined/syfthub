"""``hub.wallets``: wallets grouped from the source listing, balances, top-ups and invoices.

The three URLs a payment policy publishes (``payment_url``, ``credits_url``, ``invoices_url``)
are followed exactly as given, with a satellite token minted for the wallet's owner at that host.
This namespace is also the ``WalletPort`` the ``Wallet`` and ``Invoice`` models call through.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .errors import PaymentFailed, SyftHubError, ValidationError
from .models.enums import InvoiceStatus
from .models.money import Bundle, Money
from .models.sources import Pricing, Source
from .models.wallets import Invoice, Wallet

if TYPE_CHECKING:
    from ._api.space import SpaceApi
    from .auth import TokenCache
    from .sources import SourcesNamespace


log = logging.getLogger(__name__)


def wallet_key(owner: str, rail: str, currency: str) -> str:
    return f"{owner}/{rail}/{currency}"


def wallet_from(source: Source, pricing: Pricing) -> Wallet | None:
    """The prepaid wallet a source bills, or None for free and MPP sources."""
    if not pricing.rail.prepaid or not pricing.credits_url:
        return None
    owner = pricing.wallet_owner or source.owner_username
    return Wallet(
        id=pricing.wallet_id or pricing.credits_url,  # Pricing fills wallet_id from the URL
        key=wallet_key(owner, pricing.rail.value, pricing.currency),
        owner=owner,
        rail=pricing.rail,
        currency=pricing.currency,
        sources=(source.path,),
        bundles=pricing.bundles,
        payment_url=pricing.payment_url,
        credits_url=pricing.credits_url,
        invoices_url=pricing.invoices_url,
    )


def group_wallets(sources: list[Source] | tuple[Source, ...]) -> dict[str, Wallet]:
    """One ``Wallet`` per wallet id across sources; ``sources`` lists every path billed to it."""
    wallets: dict[str, Wallet] = {}
    for source in sources:
        pricing = source.pricing
        if pricing is None:
            continue
        wallet = wallet_from(source, pricing)
        if wallet is None:
            continue
        existing = wallets.get(wallet.id)
        if existing is None:
            wallets[wallet.id] = wallet
        elif source.path not in existing.sources:
            existing.sources = existing.sources + (source.path,)
    return wallets


class WalletsNamespace:
    def __init__(
        self, space: SpaceApi, tokens: TokenCache, sources: SourcesNamespace, hub: Any
    ) -> None:
        self._space = space
        self._tokens = tokens
        self._sources = sources
        self._hub = hub
        self._known: dict[str, Wallet] = {}  # by wallet id

    # ── public ────────────────────────────────────────────────────────────

    async def list(self) -> tuple[Wallet, ...]:
        """Every prepaid wallet the listing bills to, with its balance read now.

        One ``GET credits_url`` per wallet, in parallel. A wallet whose Space cannot be reached
        comes back with ``balance=None`` and a warning in the log; the rest are unaffected."""
        listing = await self._sources.list()
        wallets = [self._adopt(w) for w in group_wallets(listing.items).values()]
        await self._read_balances(wallets)
        return tuple(wallets)

    async def for_source(self, path: str | Source) -> Wallet | None:
        """The wallet a source bills, with its balance read now; None for free and MPP sources."""
        source = path if isinstance(path, Source) else await self._sources.get(path)
        wallet = self.wallet_of(source)
        if wallet is not None:
            await self._read_balances([wallet])
        return wallet

    def wallet_of(self, source: Source) -> Wallet | None:
        """The session's ``Wallet`` for a source, without reading its balance. Pre-flight uses
        this and reads every balance itself, once per wallet."""
        pricing = source.pricing
        if pricing is None:
            return None
        wallet = wallet_from(source, pricing)
        return self._adopt(wallet) if wallet is not None else None

    def get(self, key_or_id: str) -> Wallet:
        """A wallet already seen this session, by key or id; no request. Its ``balance`` is as
        of ``refreshed_at``; ``await wallet.refresh()`` reads it again."""
        for wallet in self._known.values():
            if wallet.id == key_or_id or wallet.key == key_or_id:
                return wallet
        raise ValidationError(f"unknown wallet {key_or_id!r}; call hub.wallets.list() first")

    async def invoice(self, wallet_key: str, invoice_id: str) -> Invoice:
        """Re-read an invoice by handle, for a pause that spans processes."""
        wallet = await self._wallet_by_key(wallet_key)
        for body in await self._space.invoices(
            self._require(wallet, "invoices_url"), await self._token(wallet)
        ):
            if str(body.get("id")) == invoice_id:
                return self._bind(Invoice.from_space(wallet.key, body))
        raise PaymentFailed(f"invoice {invoice_id} not found on wallet {wallet_key}")

    # ── WalletPort ────────────────────────────────────────────────────────

    async def wallet_balance(self, wallet: Wallet, *, retry: bool = True) -> tuple[Money, datetime]:
        body = await self._space.balance(
            self._require(wallet, "credits_url"), await self._token(wallet), retry=retry
        )
        currency = str(body.get("currency") or wallet.currency)
        return Money.of(body.get("balance", 0), currency), datetime.now(timezone.utc)

    async def wallet_top_up(self, wallet: Wallet, bundle: Bundle) -> Invoice:
        slug = wallet.sources[0].split("/", 1)[1] if wallet.sources else None
        body = await self._space.create_invoice(
            self._require(wallet, "payment_url"),
            await self._token(wallet),
            bundle_name=bundle.id,
            endpoint_slug=slug,
        )
        return self._bind(Invoice.from_space(wallet.key, body))

    async def wallet_invoices(self, wallet: Wallet) -> tuple[Invoice, ...]:
        bodies = await self._space.invoices(
            self._require(wallet, "invoices_url"), await self._token(wallet)
        )
        return tuple(self._bind(Invoice.from_space(wallet.key, b)) for b in bodies)

    async def invoice_refresh(self, invoice: Invoice) -> Invoice:
        """``GET invoices_url`` and match by id. If the id is not listed, the balance is the
        fallback: a balance at or above the invoice amount counts as paid."""
        wallet = await self._wallet_by_key(invoice.wallet_key)
        if wallet.invoices_url:
            for body in await self._space.invoices(wallet.invoices_url, await self._token(wallet)):
                if str(body.get("id")) == invoice.id:
                    return self._bind(Invoice.from_space(wallet.key, body))
        balance, _ = await self.wallet_balance(wallet)
        if balance >= invoice.amount:
            paid = invoice.model_copy(update={"status": InvoiceStatus.PAID})
            return self._bind(paid)
        return self._bind(invoice)

    # ── internals ─────────────────────────────────────────────────────────

    async def _read_balances(self, wallets: Sequence[Wallet]) -> None:
        """Read each balance once, at most ``Options.concurrency`` at a time. A listing is
        informational, so there are no retries: a dead Space costs one connect timeout, and its
        wallet is left at ``balance=None`` rather than a stale number."""
        gate = asyncio.Semaphore(self._hub.options.concurrency)

        async def read(wallet: Wallet) -> None:
            async with gate:
                try:
                    wallet.balance, wallet.refreshed_at = await self.wallet_balance(
                        wallet, retry=False
                    )
                except SyftHubError as e:
                    wallet.balance, wallet.refreshed_at = None, None
                    log.warning("wallet %s: balance unavailable: %s", wallet.key, e)

        await asyncio.gather(*(read(w) for w in {w.id: w for w in wallets}.values()))

    def _adopt(self, wallet: Wallet) -> Wallet:
        existing = self._known.get(wallet.id)
        if existing is None:
            wallet._bind(self._hub)
            self._known[wallet.id] = wallet
            return wallet
        for path in wallet.sources:
            if path not in existing.sources:
                existing.sources = existing.sources + (path,)
        return existing

    def _bind(self, invoice: Invoice) -> Invoice:
        invoice._bind(self._hub)
        return invoice

    async def _wallet_by_key(self, key: str) -> Wallet:
        """A handle lookup for invoices; adopts the listing without reading any balance."""
        try:
            return self.get(key)
        except ValidationError:
            listing = await self._sources.list()
            for wallet in group_wallets(listing.items).values():
                self._adopt(wallet)
            return self.get(key)

    async def _token(self, wallet: Wallet) -> str:
        url = wallet.credits_url or wallet.payment_url or wallet.invoices_url
        if not url:
            raise PaymentFailed(f"wallet {wallet.key} publishes no URL")
        return await self._tokens.get(wallet.owner, url)

    @staticmethod
    def _require(wallet: Wallet, attr: str) -> str:
        value = getattr(wallet, attr)
        if not value:
            raise PaymentFailed(f"wallet {wallet.key} publishes no {attr}")
        return str(value)
