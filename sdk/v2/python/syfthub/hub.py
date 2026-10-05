"""The Hub handle. Identity, browse, search (the fan-out), and the plumbing
that Results needs. In the real SDK this is the only module that speaks HTTP."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

from .errors import BudgetExceeded, NotLoggedIn
from .fake import FakeAggregator, FakeHub, FakeSpace
from .fake.space import World
from .models import (Answer, Budget, Charge, Document, Endpoint, Identity, Outcome, Rail, Selection,
                     SkipReason, SourceResult, TopUp, Wallet, Wallets, to_space_filters)
from .search import Search, build_search
from .results import Chat, Results


def connect(url: str = "https://hub.example.com", *, aggregator_url: str | None = None,
            interactive: bool = False) -> "Hub":
    """Open a session against a Hub.

    Nothing is sent until you browse, search, or chat. Sign in afterwards with ``hub.login``.

    Args:
        url: The Hub's base URL.
        aggregator_url: Where the Aggregator lives, if you use ``results.aggregate``. Defaults to
            ``{url}/aggregator/api/v1``.
        interactive: In a notebook, render anything that is waiting on a payment as a widget with
            buttons, so you can top up without typing code.

    Returns:
        A ``Hub`` you browse, search, and chat from."""
    return Hub(url, aggregator_url=aggregator_url, interactive=interactive)


class _Login:
    """Three ways to sign in, all reached from ``hub.login``.

    Call it with a username and password, or use ``.google()`` or ``.token(pat)``. Each returns your
    ``Identity`` and keeps the session signed in."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub

    def __call__(self, *, username: str, password: str) -> Identity:
        """Sign in with a username and password.

        Args:
            username: Your Hub username.
            password: Your Hub password.

        Returns:
            Your ``Identity``."""
        return self._hub._set_identity(self._hub._fake.login("password", username=username, password=password))

    def google(self) -> Identity:
        """Sign in with Google.

        Opens the browser for the Google flow and returns once the Hub confirms.

        Returns:
            Your ``Identity``."""
        return self._hub._set_identity(self._hub._fake.login("google"))

    def token(self, pat: str) -> Identity:
        """Sign in with a personal access token.

        Args:
            pat: A personal access token created in the Hub's settings.

        Returns:
            Your ``Identity``."""
        return self._hub._set_identity(self._hub._fake.login("token", token=pat))


class Hub:
    """Your session with a Hub.

    Everything starts here: sign in with ``hub.login``, find endpoints with ``browse`` or ``find``,
    compose a search with ``search``, open a chat with ``chat``, and check your prepaid balances with
    ``wallets``. The Hub only talks to the Hub API and to Spaces when you ask it to."""

    def __init__(self, url: str, *, aggregator_url: str | None = None, interactive: bool = False) -> None:
        self.url = url
        self.aggregator_url = aggregator_url or f"{url}/aggregator/api/v1"
        self.interactive = interactive
        self._world = World()
        self._fake = FakeHub(self._world)
        self._agg = FakeAggregator(self._world, self.aggregator_url)
        self._spaces: dict[str, FakeSpace] = {}
        self.me: Identity | None = None
        self.login = _Login(self)
        self.budget: Budget | None = None

    # -- identity ------------------------------------------------------------------
    def _set_identity(self, u: dict[str, Any]) -> Identity:
        self.me = Identity(u["username"], u["email"], u["auth"], self._fake.hub_wallet, self.budget)
        return self.me

    def whoami(self) -> Identity:
        """Who is signed in right now.

        Returns:
            Your ``Identity``: username, email, how you signed in, your Hub wallet balance, and the
            session budget if you set one.

        Raises:
            NotLoggedIn: When nobody is signed in."""
        if not self.me:
            raise NotLoggedIn("Call hub.login(...) first")
        self.me.hub_wallet_balance, self.me.budget = self._fake.hub_wallet, self.budget
        return self.me

    def set_budget(self, limit: float, currency: str = "USD") -> Budget:
        """Cap how much this session may spend.

        The cap lives only in this client. During pre-flight, any source whose estimate would push the
        session past the cap is held as "over budget" instead of being sent. Every rail counts towards it.

        Args:
            limit: The most this session may spend.
            currency: The currency the limit is in.

        Returns:
            The ``Budget`` you just set."""
        self.budget = Budget(limit, currency=currency)
        return self.budget

    # -- discovery -------------------------------------------------------------------
    def browse(self, type: str | None = None, *, owner: str | None = None, free: bool | None = None,
               tag: str | None = None, matching: str | None = None) -> Selection:
        """List everything the Hub offers: data sources and models together.

        Returns one table you can keep narrowing. ``type`` and ``owner`` are applied by the Hub; the
        other three are applied in this client, so they cost no extra round trips. The same narrowing is
        available afterwards on the returned ``Selection`` through ``.filter(...)``, ``.matching(text)``
        and ``.pick(...)``.

        Args:
            type: Keep one kind of endpoint: ``"data_source"`` or ``"model"``.
            owner: Keep endpoints published by this username.
            free: ``True`` keeps only free endpoints, ``False`` only paid ones.
            tag: Keep endpoints carrying this tag.
            matching: Fuzzy, typo-tolerant text match over name, owner, description, and tags.

        Returns:
            A ``Selection`` of endpoints, ready to pass to ``hub.search(sources=...)``."""
        sel = self._fake.browse(type)
        if owner is not None:
            sel = sel.filter(owner=owner)
        sel = sel.filter(free=free, tag=tag)
        return sel.matching(matching) if matching else sel

    def find(self, text: str, *, type: str | None = None) -> Selection:
        """Ask the Hub to search its listings semantically.

        Use this on a large Hub when you do not know what exists yet. If you already have a short list,
        ``hub.browse().matching(text)`` narrows it without a round trip.

        Args:
            text: What you are looking for, in plain words.
            type: Keep one kind of endpoint: ``"data_source"`` or ``"model"``.

        Returns:
            A ``Selection`` of matching endpoints, best first."""
        return self._fake.search(text, type)

    def get(self, path: str) -> Endpoint:
        """Open one endpoint's public record.

        Args:
            path: The endpoint as ``owner/slug``, for example ``"dave/notes"``.

        Returns:
            The ``Endpoint``: name, description, pricing, every policy, and the fields it can filter on."""
        return self._fake.get(path)

    # -- wallets: your prepaid balances, one per (owner, type, currency) ----------------------
    def wallets(self, endpoints: Iterable | None = None) -> Wallets:
        """Your prepaid wallets, with live balances.

        One wallet often funds several endpoints, so this groups endpoints by the wallet they bill
        against, the same way the Hub's web UI does.

        Args:
            endpoints: Only the wallets behind these endpoints. Leave empty for every endpoint you can see.

        Returns:
            ``Wallets``: a list you can index by wallet key or by the path of an endpoint it funds."""
        eps = self._resolve(endpoints) if endpoints is not None else list(self.browse())
        groups: dict[str, list[Endpoint]] = {}
        for e in eps:
            p = e.pricing
            if p.rail.prepaid:
                groups.setdefault(p.wallet_id or p.credits_url or e.path, []).append(e)
        out = Wallets()
        for key, group in groups.items():
            p = group[0].pricing
            w = Wallet(key, p.wallet_owner or group[0].owner_username, p.rail, p.currency, None,
                       tuple(sorted(e.path for e in group)), p.bundles, p.payment_url, p.credits_url, _hub=self)
            w.balance = self._wallet_balance(w)
            out.append(w)
        return out

    def wallet(self, endpoint_or_key: Endpoint | str) -> Wallet:
        """The prepaid wallet behind one endpoint.

        Args:
            endpoint_or_key: An ``Endpoint``, its ``owner/slug`` path, or a wallet key.

        Returns:
            The ``Wallet``, with its current balance."""
        if isinstance(endpoint_or_key, Endpoint) or "/" in endpoint_or_key:
            e = self.get(endpoint_or_key) if isinstance(endpoint_or_key, str) else endpoint_or_key
            return self.wallets([e] + [x for x in self.browse() if x.pricing.wallet_id and x.pricing.wallet_id == e.pricing.wallet_id])[e.path]
        return self.wallets()[endpoint_or_key]

    def balance(self, endpoint: Endpoint | str) -> float | None:
        """Your balance on the wallet behind one endpoint.

        Args:
            endpoint: An ``Endpoint`` or its ``owner/slug`` path.

        Returns:
            The balance in the wallet's currency, or ``None`` when the endpoint is free or pays per
            request."""
        e = self.get(endpoint) if isinstance(endpoint, str) else endpoint
        return self.wallet(e).balance if e.pricing.rail.prepaid else None

    def _wallet_balance(self, w: Wallet) -> float:
        e = self.get(w.endpoints[0])
        token = self._fake.satellite_token(w.owner, w.credits_url or e.url)
        return self._space(e.url).balance(w.key, token=token).body["balance"]

    def _create_invoice_for_wallet(self, w: Wallet, bundle: str) -> dict[str, Any]:
        e = self.get(w.endpoints[0])
        token = self._fake.satellite_token(w.owner, w.credits_url or e.url)
        resp = self._space(e.url).create_invoice(w.key, token=token, bundle_name=bundle, endpoint_slug=None)
        if resp.status >= 400:
            raise ValueError(resp.body.get("detail"))
        return resp.body

    def _resolve(self, sources: Iterable) -> list[Endpoint]:
        out: list[Endpoint] = []
        for s in sources:
            if isinstance(s, Endpoint):
                out.append(s)
            elif isinstance(s, str) and s.startswith("collective/"):
                out.extend(self.get(m) for m in self._fake.expand_collective(s.split("/", 1)[1]))
            elif isinstance(s, str):
                out.append(self.get(s))
            else:
                out.extend(self._resolve(s))
        seen, uniq = set(), []
        for e in out:
            if e.path not in seen:
                seen.add(e.path); uniq.append(e)
        return uniq

    # -- compose a search (pre-flight, nothing sent), then execute it -------------------------
    def search(self, query: str, *, sources: Iterable, limit: int = 5, similarity_threshold: float = 0.5,
               history: list[dict[str, str]] | None = None) -> Search:
        """Compose a search over several sources. Nothing is sent yet.

        Pre-flight runs immediately from Hub metadata and your wallet balances: it estimates the cost of
        each source, checks prepaid balances, access lists and the session budget, and tells you which
        sources will be sent and which are held, and why. Review it, top up what is short, then call
        ``.execute()``.

        Args:
            query: The question to send to every source.
            sources: Which endpoints to ask: a ``Selection``, ``Endpoint`` objects, or ``owner/slug`` paths.
            limit: How many passages to ask each source for.
            similarity_threshold: Drop passages scoring below this, from 0 to 1.
            history: Earlier conversation turns to send along, in ``{"role": ..., "content": ...}`` form.
                Pass ``chat.history`` to let the Spaces see the thread.

        Returns:
            A ``Search`` showing its pre-flight. Call ``.execute()`` to send it."""
        return build_search(self, query, self._resolve(sources), limit=limit, threshold=similarity_threshold,
                            history=history or [])

    def _execute(self, plan: Search) -> Results:
        def one(row):
            if row.send:
                to_space, here = plan.filters_for(row)
                r = self._query_source(row.endpoint, plan.query, plan.limit, plan.threshold, plan.history,
                                       max_tokens=plan.max_tokens, filters=to_space)
                r.filters, r.space_filters = here, to_space
                return r
            r = SourceResult(row.endpoint, 0, {}, Outcome.SKIPPED, row.hold_reason, 0, predicted=True, note=row.note)
            if row.hold_reason is SkipReason.NO_CREDITS:
                r.topup = TopUp(row.endpoint, row.wallet, row.estimate)
            return r
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(one, plan.rows))
        return Results(self, plan.query, rows, limit=plan.limit, threshold=plan.threshold, history=plan.history,
                       estimate=plan.total_estimate, filters=dict(plan.filters))

    def chat(self, models, *, sources: Iterable | None = None, via: str = "direct", limit: int = 5) -> Chat:
        """Open a chat with one model or several, without searching first.

        With ``sources``, every message searches those sources first and the passages become the model's
        context. Without them, you are simply talking to the models. Pre-flight runs on every model right
        away, so you see the price per message and your balance before sending anything.

        Args:
            models: One model path, or a list of them, for example ``["ivan/gpt-mini", "bob/llama-3"]``.
            sources: Endpoints to search before each message.
            via: ``"direct"`` asks the model's Space; ``"aggregator"`` routes through the Aggregator.
            limit: How many passages each search asks for.

        Returns:
            A ``Chat``. Nothing is sent until ``.send(prompt)``."""
        return Chat(self, models, list(sources) if sources else None, via=via, limit=limit)

    # -- plumbing ---------------------------------------------------------------------------
    def _space(self, url: str) -> FakeSpace:
        return self._spaces.setdefault(url, FakeSpace(url, self._world))

    def _token_for(self, ep: Endpoint) -> str:
        return self._fake.satellite_token(ep.owner_username, ep.url, guest=self.me is None)

    def _wallet_token(self, ep: Endpoint) -> str:
        return self._fake.satellite_token(ep.pricing.wallet_owner or ep.owner_username, ep.pricing.credits_url or ep.url)

    def _spend(self, amount: float) -> None:
        if self.budget is not None and amount:
            self.budget.spent = round(self.budget.spent + amount, 6)

    def _query_source(self, ep: Endpoint, query: str, limit: int, threshold: float,
                      history: list[dict[str, str]], *, x_payment: str | None = None,
                      max_tokens: int | None = None, messages: list[dict[str, str]] | None = None,
                      filters: dict[str, Any] | None = None) -> SourceResult:
        body: dict[str, Any] = {"messages": messages if messages is not None else history + [{"role": "user", "content": query}],
                                "limit": limit, "similarity_threshold": threshold}
        if max_tokens is not None or "model" in ep.type:
            body["max_tokens"] = max_tokens or 300
        if filters:
            body["filters"] = to_space_filters(filters)      # PROPOSED field; only sent to Spaces that advertise support
        t0 = time.perf_counter()
        try:
            resp = self._space(ep.url).query(ep.slug, token=self._token_for(ep), body=body, x_payment=x_payment)
        except ConnectionError as e:
            return SourceResult(ep, 0, {}, Outcome.SKIPPED, SkipReason.UNREACHABLE,
                                int((time.perf_counter() - t0) * 1000), error=str(e))
        ms = int((time.perf_counter() - t0) * 1000)
        outcome, reason = self._classify(resp.status, resp.body)
        r = SourceResult(ep, resp.status, resp.body, outcome, reason, ms, request=body)
        if r.ok:
            self._spend(r.cost)
        elif r.reason is SkipReason.NO_CREDITS:
            rej = next((e for e in r.policy_metadata["entries"] if e.get("status") == "rejected"), {})
            r.topup = TopUp(ep, self.wallet(ep), rej.get("amount"))
        elif r.outcome is Outcome.PAYMENT_REQUIRED:
            rej = next((e for e in r.policy_metadata["entries"] if e.get("status") == "rejected"), {})
            r.charge = Charge(ep, rej.get("amount", ep.pricing.price), rej.get("currency", "USD"),
                              resp.headers.get("WWW-Authenticate", ""))
        return r

    @staticmethod
    def _classify(status: int, body: dict[str, Any]) -> tuple[Outcome, SkipReason | None]:
        if status == 200:
            return Outcome.SUCCESS, None
        if status == 404:
            return Outcome.SKIPPED, SkipReason.NOT_FOUND
        pm = body.get("policy_metadata") or {}
        codes = {e.get("reason_code") for e in pm.get("entries", [])} - {None}
        if status == 402 or "PAYMENT_REQUIRED" in codes:
            return Outcome.PAYMENT_REQUIRED, None
        for code, why in (("INSUFFICIENT_BALANCE", SkipReason.NO_CREDITS), ("RATE_LIMITED", SkipReason.RATE_LIMITED),
                          ("ACCESS_DENIED", SkipReason.ACCESS_DENIED), ("NO_PRICING_TIER", SkipReason.NO_PRICING_TIER)):
            if code in codes:
                return Outcome.SKIPPED, why
        return Outcome.SKIPPED, (SkipReason.BLOCKED if status == 403 else SkipReason.UNREACHABLE)

    def _create_invoice(self, ep: Endpoint, bundle: str) -> dict[str, Any]:
        return self._create_invoice_for_wallet(self.wallet(ep), bundle)

    def _pay_mpp(self, c: Charge) -> str:
        if self.budget is not None and c.amount > self.budget.remaining:
            raise BudgetExceeded(c.amount, self.budget.remaining)
        return self._fake.wallet_pay(c.www_authenticate, c.endpoint.slug, c.amount)

    def _aggregate(self, res: Results, m: Endpoint, prompt: str, aggregator: str | None) -> Answer:
        docs = [(p, {"document_id": d.document_id, "content": d.content, "similarity_score": d.similarity_score,
                     "metadata": d.metadata}) for p, d in res.documents]
        out = self._agg.aggregate(prompt=prompt, documents=docs, model_path=m.path, model_token=self._token_for(m),
                                  x_payment=None, top_k=res.limit)
        if out["status"] != 200:
            raise RuntimeError(f"aggregator: HTTP {out['status']} {out['body'].get('detail')}")
        b = out["body"]
        self._spend(b.get("cost") or 0.0)
        rer = [(d["path"], Document(d["document_id"], d["content"], d["similarity_score"], d.get("metadata", {})))
               for d in b["reranked"]]
        return Answer(b["response"], "aggregator", m, {int(k): v for k, v in b["citations"].items()},
                      b.get("usage", {}), b.get("cost") or 0.0, b.get("currency"), b["policy_metadata"], reranked=rer)

    # -- mock-only hooks ---------------------------------------------------------------------
    def _simulate_checkout_paid(self, invoice_id: str) -> None:
        """Pretend the user paid an invoice.

        In real life the user pays at the invoice's ``checkout_url`` and the payment provider's webhook
        credits the wallet. This mock hook does the crediting directly.

        Args:
            invoice_id: The ``id`` of the invoice returned by a top-up."""
        self._world.webhook_paid(invoice_id)

    def _simulate_space_up(self, path: str) -> None:
        """Pretend a Space that was unreachable is back.

        Args:
            path: The endpoint, as ``owner/slug``."""
        self._world.down[path] = False
