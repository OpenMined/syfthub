"""``AsyncHub``: the session, its namespaces, the budget, and the ports the data objects use."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from datetime import datetime
from types import TracebackType

from ._api import HubApi, SpaceApi
from ._transport import Breakers, Transport
from .auth import AuthNamespace, Session, TokenCache
from .errors import ConfigurationError
from .models.filters import SourceSelection
from .models.money import Bundle, Money
from .models.results import Results
from .models.search import Preflight, SearchPlan
from .models.session import Budget, Identity, Ledger, Options
from .models.sources import Source, SourceList
from .models.wallets import Invoice, Wallet
from .search import Searcher
from .sources import SourcesNamespace
from .wallets import WalletsNamespace

BudgetLike = Money | float | int | str | Mapping[str, Money | float | int | str] | None

DEFAULT_URL = "https://syfthub.openmined.org"


class AsyncHub:
    """One session with a SyftHub: the catalogue, a search over it, and the money.

    The Hub serves the catalogue, the per-Space tokens and, for metered sources, the payment
    credential; every query goes from this process straight to the publisher's Space. The
    namespaces are ``auth`` (login, ``me``), ``sources`` (browse and ``get``) and ``wallets``
    (balances, top-ups). ``search`` composes a plan; the plan prices itself with ``preflight``
    and runs with ``execute``. ``budget`` caps what a session may spend.

    ``url`` falls back to ``SYFTHUB_URL``, ``token`` to ``SYFTHUB_TOKEN``. No network until the
    first call. Use ``async with`` or call ``aclose()`` to release the HTTP client. ``Hub`` is
    the sync twin with the same names and no ``await``::

        async with syfthub.AsyncHub(token=...) as hub:
            source = await hub.sources.get("nasa/news")
            plan = hub.search("Artemis launches", [source], limit=3)
            results = await plan.execute()
    """

    url: str
    options: Options
    breakers: Breakers
    auth: AuthNamespace
    sources: SourcesNamespace
    wallets: WalletsNamespace

    def __init__(
        self,
        url: str | None = None,
        *,
        token: str | None = None,
        budget: BudgetLike = None,
        options: Options | None = None,
    ) -> None:
        """Open a session; no request is made until the first call.

        Args:
            url: the Hub's origin; ``SYFTHUB_URL`` or the public Hub when omitted.
            token: a personal access token; ``SYFTHUB_TOKEN`` when omitted. Without one, ``login``
                later.
            budget: a cap on spend: a number caps USD, a mapping caps several currencies, None caps
                nothing.
            options: timeouts, retries, concurrency and the HTTP client; the defaults when omitted.
        """
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
        self.sources = SourcesNamespace(
            self._hub_api, max_items=self.options.max_items, concurrency=self.options.concurrency
        )
        self.wallets = WalletsNamespace(
            self._space_api, self._tokens, self.sources, hub=self, options=self.options
        )
        self._ledger = Ledger(budget=Budget(limits=_limits(budget)))
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
            ledger=self._ledger,
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
        """Release the HTTP client. ``async with`` does this on exit."""
        await self._transport.aclose()

    # ── session ───────────────────────────────────────────────────────────

    async def login(
        self, username: str | None = None, password: str | None = None, *, token: str | None = None
    ) -> Identity:
        """Sign in with a username and password, or with a personal access ``token``.

        A token given to the constructor or ``SYFTHUB_TOKEN`` is used without this call.

        Args:
            username: the Hub account name.
            password: its password.
            token: a personal access token instead of a username and password.

        Returns:
            Who you are, as the Hub sees it.
        """
        return await self.auth.login(username, password, token=token)

    @property
    def me(self) -> Identity | None:
        """Who is signed in, once known; None before ``login`` or ``auth.whoami()``."""
        return self.auth.me

    @property
    def authenticated(self) -> bool:
        """True when the session holds a token."""
        return self._session.authenticated

    # ── search ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        sources: Iterable[str | Source | SourceSelection] | SourceList | None = None,
        *,
        limit: int = 5,
        similarity_threshold: float = 0.5,
        include_metadata: bool = True,
        max_sources: int | None = None,
    ) -> SearchPlan:
        """Compose a plan.

        Nothing is sent: ``await plan.preflight()`` prices it, ``await plan.execute()`` runs
        it. Without ``sources`` the plan covers every free document source in the catalogue
        that you may use; ``max_sources`` caps that pick and never a list you name. A
        ``source.where(filter)`` selection narrows that source by metadata. For the Hub's
        keyword ranking pass ``await hub.sources.search(text)``.

        Args:
            query: the text to search for.
            sources: paths, ``Source`` objects or ``source.where(...)`` selections; every free
                source you may use when omitted.
            limit: passages per source.
            similarity_threshold: the lowest score a passage may have, 0 to 1.
            include_metadata: ask each Space for document metadata.
            max_sources: a ceiling on the automatic pick; never caps a list you name.

        Returns:
            The plan, unsent.
        """
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
        """Caps and spend per currency, as of now."""
        return self._ledger.budget

    @property
    def spent(self) -> dict[str, Money]:
        """What this session has paid, per currency."""
        return self._ledger.budget.spent

    def set_budget(self, limit: BudgetLike) -> Budget:
        """Replace the caps; spend is kept.

        The one override for ``over_budget`` rows. ``None`` clears every cap, a number caps
        USD, a mapping caps several currencies at once.

        Args:
            limit: a number caps USD, a mapping caps several currencies, None clears every cap.

        Returns:
            The budget now in force.
        """
        return self._ledger.set_limits(_limits(limit))

    # ── SearchPort: the plan and results models call back through the hub ──

    async def preflight(self, plan: SearchPlan) -> Preflight:
        """``plan.preflight()``.

        Args:
            plan: the plan to price and check.

        Returns:
            The pre-flight snapshot.
        """
        return await self._searcher.preflight(plan)

    async def execute(self, plan: SearchPlan, *, strict: bool = False) -> Results:
        """``plan.execute()``.

        Args:
            plan: the plan to send.
            strict: raise on a held or failed row instead of returning it.

        Returns:
            One row per source.
        """
        return await self._searcher.execute(plan, strict=strict)

    # ── WalletPort: delegated to hub.wallets so bound models can call the hub ──

    async def wallet_balance(self, wallet: Wallet) -> tuple[Money, datetime]:
        """``wallet.balance()``: the Space's current balance and when it was read.

        Args:
            wallet: the wallet to read.

        Returns:
            The balance and when it was read.
        """
        return await self.wallets.wallet_balance(wallet)

    async def wallet_top_up(self, wallet: Wallet, bundle: Bundle) -> Invoice:
        """``wallet.top_up(bundle)``: an invoice to pay; credits land when it is paid.

        Args:
            wallet: the wallet to credit.
            bundle: the bundle to buy.

        Returns:
            The invoice to pay.
        """
        return await self.wallets.wallet_top_up(wallet, bundle)

    async def wallet_invoices(self, wallet: Wallet) -> tuple[Invoice, ...]:
        """``wallet.invoices()``: every invoice this wallet issued to you.

        Args:
            wallet: the wallet to list.

        Returns:
            Every invoice it issued to you.
        """
        return await self.wallets.wallet_invoices(wallet)

    async def invoice_refresh(self, invoice: Invoice) -> Invoice:
        """``invoice.refresh()``: the invoice with its current status.

        Args:
            invoice: the invoice to re-read.

        Returns:
            The invoice with its current status.
        """
        return await self.wallets.invoice_refresh(invoice)

    def __repr__(self) -> str:
        who = self.me.username if self.me else ("token" if self.authenticated else "anonymous")
        return f"AsyncHub({self.url!r}, as={who})"


def _limits(value: BudgetLike) -> dict[str, Money]:
    """``None``: no caps.

    A number or string: that much USD. ``Money``: a cap in its currency. A mapping: one cap per
    currency, ``{"USD": 1.00, "IDR": 50000}``.
    """
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
