"""The two interfaces the data objects call the network through.

They are owned by the models, not by the hub: ``AsyncHub`` implements both and injects itself. A
test can bind any object to a ten-line fake.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .money import Bundle, Money
    from .results import Results
    from .search import Preflight, SearchPlan
    from .wallets import Invoice, Wallet


class WalletPort(Protocol):
    """What ``Wallet`` and ``Invoice`` need from the network."""

    async def wallet_balance(self, wallet: Wallet) -> tuple[Money, datetime]: ...

    async def wallet_top_up(self, wallet: Wallet, bundle: Bundle) -> Invoice: ...

    async def wallet_invoices(self, wallet: Wallet) -> tuple[Invoice, ...]: ...

    async def invoice_refresh(self, invoice: Invoice) -> Invoice: ...


class SearchPort(Protocol):
    """What ``SearchPlan`` and ``Results`` need from the network."""

    async def preflight(self, plan: SearchPlan) -> Preflight: ...

    async def execute(self, plan: SearchPlan, *, strict: bool) -> Results: ...


class HubPorts(SearchPort, WalletPort, Protocol):
    """Both ports on one object: what a bound model is bound to. ``AsyncHub`` satisfies it; a
    test can bind any object with these six coroutines."""
