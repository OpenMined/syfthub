"""``hub.wallets``: your prepaid balances, one wallet per owner, rail and currency."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Iterable

from .errors import InvoiceError, NotFound, SpaceError
from .models import Endpoint, Invoice, InvoiceStatus, Money, Wallet, WalletList

if TYPE_CHECKING:  # pragma: no cover
    from .hub import AsyncHub


def wallet_key(ep: Endpoint) -> str:
    p = ep.pricing
    return p.wallet_id or p.credits_url or ep.path


class WalletsNamespace:
    """Prepaid wallets and credit purchases. Reached as ``hub.wallets``.

    One wallet often funds several endpoints, so wallets are grouped by the published ``wallet_id`` (else
    the credits URL), the same way the Hub's web UI does. Balances come from each Space's balance route."""

    def __init__(self, hub: "AsyncHub") -> None:
        self._hub = hub
        self._known: dict[str, Wallet] = {}

    # -- building wallets from endpoints ------------------------------------------------------
    def _group(self, eps: Iterable[Endpoint]) -> dict[str, list[Endpoint]]:
        groups: dict[str, list[Endpoint]] = {}
        for e in eps:
            if e.pricing.prepaid:
                groups.setdefault(wallet_key(e), []).append(e)
        return groups

    async def _fetch_balance(self, w: Wallet) -> Money:
        ep = await self._hub.endpoints.get(w.endpoints[0])
        token = await self._hub._token(w.owner, w.credits_url or ep.url)
        base = (w.credits_url or ep.url).split("/api/")[0]
        resp = await self._hub._t.space_balance(base, w.key, token=token)
        if resp.status >= 400:
            raise SpaceError(f"could not read the balance of wallet {w.key}: HTTP {resp.status} {resp.body.get('detail')}",
                             status=resp.status, path=ep.path, url=base, body=resp.body)
        return Money.of(resp.body["balance"], resp.body.get("currency") or w.currency)

    async def _wallets_for(self, eps: Iterable[Endpoint]) -> dict[str, Wallet]:
        """Wallets behind these endpoints, balances fetched in parallel."""
        groups = self._group(eps)
        shells: list[Wallet] = []
        for key, group in groups.items():
            p = group[0].pricing
            w = Wallet(key=key, owner=p.wallet_owner or group[0].owner_username, rail=p.rail, currency=p.currency,
                       endpoints=tuple(sorted(e.path for e in group)), bundles=p.bundles,
                       payment_url=p.payment_url, credits_url=p.credits_url)
            shells.append(w)
        balances = await asyncio.gather(*(self._fetch_balance(w) for w in shells))
        out: dict[str, Wallet] = {}
        for w, b in zip(shells, balances):
            w = w.model_copy(update={"balance": b})
            w._hub = self._hub
            out[w.key] = w
            self._known[w.key] = w
        return out

    async def _balance_of(self, key: str) -> Money:
        w = self._known.get(key) or (await self.get(key))
        return await self._fetch_balance(w)

    # -- public ------------------------------------------------------------------------------
    async def list(self, endpoints: Iterable | None = None) -> WalletList:
        """Your prepaid wallets, with live balances.

        Args:
            endpoints: Only the wallets behind these endpoints. Leave empty for every endpoint you can see.

        Returns:
            A ``WalletList`` you can index by wallet key or by the path of an endpoint it funds."""
        eps = await self._hub.endpoints.resolve(endpoints) if endpoints is not None else await self._hub.endpoints.list()
        return WalletList((await self._wallets_for(eps)).values())

    async def get(self, key: str) -> Wallet:
        """One wallet by its key, with its current balance.

        Args:
            key: The published ``wallet_id``, or the credits URL for wallets without one.

        Returns:
            The ``Wallet``.

        Raises:
            NotFound: When no endpoint you can see bills that wallet."""
        eps = [e for e in await self._hub.endpoints.list() if e.pricing.prepaid and wallet_key(e) == key]
        if not eps:
            raise NotFound(f"no wallet {key!r} behind any endpoint you can see", status=404)
        return (await self._wallets_for(eps))[key]

    async def for_endpoint(self, endpoint: Endpoint | str) -> Wallet:
        """The prepaid wallet behind one endpoint, with every other endpoint it funds listed.

        Args:
            endpoint: An ``Endpoint`` or its ``owner/slug`` path.

        Returns:
            The ``Wallet``.

        Raises:
            NotFound: When the endpoint is free or pays per request (MPP)."""
        ep = await self._hub.endpoints.get(endpoint) if isinstance(endpoint, str) else endpoint
        if not ep.pricing.prepaid:
            raise NotFound(f"{ep.path} does not bill a prepaid wallet ({ep.pricing.label})", status=404)
        return await self.get(wallet_key(ep))

    async def balance(self, endpoint: Endpoint | str) -> Money | None:
        """Your balance on the wallet behind one endpoint.

        Args:
            endpoint: An ``Endpoint`` or its ``owner/slug`` path.

        Returns:
            The balance, or ``None`` when the endpoint is free or pays per request."""
        ep = await self._hub.endpoints.get(endpoint) if isinstance(endpoint, str) else endpoint
        if not ep.pricing.prepaid:
            return None
        return (await self.for_endpoint(ep)).balance

    # -- invoices --------------------------------------------------------------------------
    async def _create_invoice(self, w: Wallet, bundle_id: str) -> Invoice:
        b = w.bundle(bundle_id)
        ep = await self._hub.endpoints.get(w.endpoints[0])
        token = await self._hub._token(w.owner, w.credits_url or ep.url)
        base = (w.payment_url or ep.url).split("/api/")[0]
        resp = await self._hub._t.space_invoice(base, w.key, token=token, bundle=b.id)
        if resp.status >= 400:
            raise InvoiceError(f"{ep.owner_username}'s Space refused the invoice for {b.id!r} on {w.key}: {resp.body.get('detail')}",
                               status=resp.status, path=ep.path, url=base, body=resp.body)
        body = resp.body
        inv = Invoice(id=body["id"], wallet_key=w.key, bundle=body.get("bundle_name") or b.id,
                      amount=Money.of(body.get("amount"), body.get("currency") or w.currency),
                      status=InvoiceStatus(body.get("status", "pending")), checkout_url=body.get("checkout_url"),
                      created_at=body.get("created_at"), raw=body)
        inv._hub = self._hub
        inv._balance_before = w.balance if w.balance is not None else await self._fetch_balance(w)
        return inv
