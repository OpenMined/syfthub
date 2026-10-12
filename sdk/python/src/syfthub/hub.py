"""``AsyncHub``: the session, its namespaces, the budget, and the ports the data objects use."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from datetime import datetime
from types import TracebackType

from ._api import HubApi, SpaceApi
from ._transport import Breakers, Transport
from .auth import AuthNamespace, Session, TokenCache
from .errors import ConfigurationError
from .models.money import Bundle, Money
from .models.results import Results
from .models.search import Preflight, SearchPlan
from .models.session import Budget, Identity, Options
from .models.sources import Source, SourceList
from .models.wallets import Invoice, Wallet
from .search import Searcher
from .sources import SourcesNamespace
from .wallets import WalletsNamespace

BudgetLike = Money | float | int | str | Mapping[str, Money | float | int | str] | None

DEFAULT_URL = "https://syfthub.openmined.org"
log = logging.getLogger("syfthub")


class AsyncHub:
    """One session with a SyftHub. No network until the first call.

    ``url`` falls back to ``SYFTHUB_URL``, ``token`` to ``SYFTHUB_TOKEN``. Use ``async with`` or
    call ``aclose()`` to release the HTTP client.
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        token: str | None = None,
        budget: BudgetLike = None,
        options: Options | None = None,
    ) -> None:
        self.url = (url or os.environ.get("SYFTHUB_URL") or DEFAULT_URL).rstrip("/")
        if not self.url.startswith(("http://", "https://")):
            raise ConfigurationError(f"url must start with http:// or https://: {self.url!r}")
        self.options = options or Options()
        self._transport = Transport(self.options)
        self._session = Session(access_token=token or os.environ.get("SYFTHUB_TOKEN") or None)
        self._hub_api = HubApi(self._transport, self.url, self._session)
        self._session.attach(self._hub_api)
        self._space_api = SpaceApi(self._transport)
        self._tokens = TokenCache(self._hub_api)
        self.breakers = Breakers(settings=self.options.circuit_breaker)
        self.auth = AuthNamespace(self._hub_api, self._session)
        self.sources = SourcesNamespace(self._hub_api, max_items=self.options.max_items)
        self.wallets = WalletsNamespace(self._space_api, self._tokens, self.sources, self)
        self._budget = Budget(limits=_limits(budget))
        self._searcher = Searcher(
            hub_api=self._hub_api,
            space=self._space_api,
            tokens=self._tokens,
            sources=self.sources,
            wallets=self.wallets,
            auth=self.auth,
            session=self._session,
            breakers=self.breakers,
            options=self.options,
            hub=self,
        )

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def __aenter__(self) -> AsyncHub:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._transport.aclose()

    # ── session ───────────────────────────────────────────────────────────

    async def login(
        self, username: str | None = None, password: str | None = None, *, token: str | None = None
    ) -> Identity:
        return await self.auth.login(username, password, token=token)

    @property
    def me(self) -> Identity | None:
        return self.auth.me

    @property
    def authenticated(self) -> bool:
        return self._session.authenticated

    # ── search ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        sources: Iterable[str | Source] | SourceList | None = None,
        *,
        limit: int = 5,
        similarity_threshold: float = 0.5,
        include_metadata: bool = True,
        max_sources: int = 10,
    ) -> SearchPlan:
        """Compose a plan. Nothing is sent: ``await plan.preflight()`` prices it,
        ``await plan.execute()`` runs it. Without ``sources`` the Hub picks free document
        sources for the query, at most ``max_sources``."""
        return self._searcher.compose(
            query,
            sources,
            limit=limit,
            similarity_threshold=similarity_threshold,
            include_metadata=include_metadata,
            max_sources=max_sources,
        )

    # ── budget ────────────────────────────────────────────────────────────

    @property
    def budget(self) -> Budget:
        return self._budget

    @property
    def spent(self) -> dict[str, Money]:
        """What this session has paid, per currency."""
        return self._budget.spent

    def set_budget(self, limit: BudgetLike) -> Budget:
        """Replace the caps; spend is kept. The one override for ``over_budget`` rows. ``None``
        clears every cap, a number caps USD, a mapping caps several currencies at once."""
        self._budget = Budget(limits=_limits(limit), spent=self._budget.spent)
        return self._budget

    def _record_spend(self, amount: Money) -> None:
        """Add a charge to the spend in its currency."""
        self._budget = self._budget.record(amount)

    # ── SearchPort: the plan and results models call back through the hub ──

    async def preflight(self, plan: SearchPlan) -> Preflight:
        return await self._searcher.preflight(plan)

    async def execute(self, plan: SearchPlan, *, strict: bool = False) -> Results:
        return await self._searcher.execute(plan, strict=strict)

    # ── WalletPort: delegated to hub.wallets so bound models can call the hub ──

    async def wallet_balance(self, wallet: Wallet) -> tuple[Money, datetime]:
        return await self.wallets.wallet_balance(wallet)

    async def wallet_top_up(self, wallet: Wallet, bundle: Bundle) -> Invoice:
        return await self.wallets.wallet_top_up(wallet, bundle)

    async def wallet_invoices(self, wallet: Wallet) -> tuple[Invoice, ...]:
        return await self.wallets.wallet_invoices(wallet)

    async def invoice_refresh(self, invoice: Invoice) -> Invoice:
        return await self.wallets.invoice_refresh(invoice)

    def __repr__(self) -> str:
        who = self.me.username if self.me else ("token" if self.authenticated else "anonymous")
        return f"AsyncHub({self.url!r}, as={who})"


def _limits(value: BudgetLike) -> dict[str, Money]:
    """``None``: no caps. A number or string: that much USD. ``Money``: a cap in its currency.
    A mapping: one cap per currency, ``{"USD": 1.00, "IDR": 50000}``."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        caps: dict[str, Money] = {}
        for currency, amount in value.items():
            money = amount if isinstance(amount, Money) else Money.of(amount, currency)
            if money.currency != currency:
                raise ConfigurationError(f"budget[{currency!r}] is in {money.currency}")
            caps[currency] = money
        return caps
    money = value if isinstance(value, Money) else Money.of(value)
    return {money.currency: money}
