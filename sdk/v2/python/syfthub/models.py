"""Core data types. Space responses are kept exactly as returned (``raw``);
the SDK adds classification and rendering on top, never a new shape."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from . import render


class Rail(str, enum.Enum):
    """How an endpoint gets paid.

    Prepaid rails (``stripe``, ``xendit``, ``cluster``) hold credits you top up ahead of time; they
    are the default flow. ``mpp`` pays per request at query time and is experimental. ``free`` costs
    nothing.

    Attributes:
        FREE: No payment policy; calls cost nothing.
        STRIPE: Prepaid credits held by the Space, bought through Stripe.
        XENDIT: Prepaid credits held by the Space, bought through Xendit.
        CLUSTER: Prepaid credits held by a managed wallet that several Spaces share.
        MPP: Pay per request at query time; the Space answers 402 first. Experimental."""
    FREE = "free"
    STRIPE = "stripe"      # prepaid credits held by the Space
    XENDIT = "xendit"      # prepaid credits held by the Space
    CLUSTER = "cluster"    # prepaid credits held by a managed (shared) wallet
    MPP = "mpp"            # experimental: pay per query at request time (402)

    @property
    def prepaid(self) -> bool:
        """``True`` for the credit-based rails: stripe, xendit, and cluster."""
        return self in (Rail.STRIPE, Rail.XENDIT, Rail.CLUSTER)


class Outcome(str, enum.Enum):
    """What happened to one source, or one model, after sending.

    ``success`` means it answered. ``skipped`` means it did not; ``reason`` says why. ``payment_required``
    means an MPP Space asked for a payment first (experimental).

    Attributes:
        SUCCESS: The source answered.
        SKIPPED: The source was not answered. ``reason`` says why.
        PAYMENT_REQUIRED: An MPP Space asked for a payment first. Approve it with ``results.approve()``."""

    SUCCESS = "success"
    SKIPPED = "skipped"                     # not answered; see SourceResult.reason
    PAYMENT_REQUIRED = "payment_required"   # MPP (experimental): approve a charge, then it is retried


class SkipReason(str, enum.Enum):
    """Why a source was skipped.

    Decided from the client's pre-flight or from the ``reason_code`` the Space put in its
    ``policy_metadata`` envelope, never from the HTTP status alone. Reasons marked retryable are the
    ones ``results.retry()`` can act on.

    Attributes:
        NO_CREDITS: The prepaid wallet is short. A ``TopUp`` is attached. Retryable.
        OVER_BUDGET: Sending would cross the session budget. Decided in this client. Retryable.
        ACCESS_DENIED: The Space's access policy does not include you.
        RATE_LIMITED: The Space asked you to slow down. Retryable.
        NO_PRICING_TIER: The Space has no price that applies to you.
        UNREACHABLE: Network error, or the Space is down. Retryable.
        NOT_FOUND: The Space does not know this endpoint.
        BLOCKED: The Space refused with 403 and gave no reason code.
        BY_USER: You skipped it with ``results.skip(path)``."""

    NO_CREDITS = "no_credits"               # prepaid wallet short; TopUp attached
    OVER_BUDGET = "over_budget"             # client-side: estimate exceeds the session budget
    ACCESS_DENIED = "access_denied"
    RATE_LIMITED = "rate_limited"
    NO_PRICING_TIER = "no_pricing_tier"
    UNREACHABLE = "unreachable"             # network error / Space down
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"                     # 403 from a policy with no reason code
    BY_USER = "by_user"                     # results.skip(path)

    @property
    def retryable(self) -> bool:
        """``True`` for the reasons ``results.retry()`` can act on: no credits, over budget, unreachable, rate limited."""
        return self in (SkipReason.NO_CREDITS, SkipReason.OVER_BUDGET, SkipReason.UNREACHABLE, SkipReason.RATE_LIMITED)


# ------------------------------------------------------------------ Hub record
@dataclass(frozen=True)
class Policy:
    """One policy an endpoint publishes: how it is paid, who may use it, or how often.

    Attributes:
        type: For a payment policy, the wallet type (``stripe``, ``xendit``, ``cluster``, ``mpp``).
            Otherwise ``access``, ``rate_limit``, or ``pii_filter``.
        config: The policy's settings, exactly as the Space published them.
        version: The policy schema version.
        enabled: Whether the Space currently enforces it.
        description: The Space's own description of the policy."""

    type: str                   # payment: the wallet type (stripe|xendit|cluster|mpp); else access|rate_limit|pii_filter
    config: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"
    enabled: bool = True
    description: str = ""

    @property
    def is_payment(self) -> bool:
        """``True`` for a payment policy of any rail."""
        return self.type in {r.value for r in Rail if r is not Rail.FREE}


@dataclass(frozen=True)
class Connection:
    """How to reach the Space that serves an endpoint.

    Attributes:
        type: The connection kind, normally ``"http"``.
        config: Settings for it; ``config["url"]`` is the Space's base URL.
        enabled: Whether this connection is active."""
    type: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True)
class Pricing:
    """What one call to an endpoint costs, read from its payment policy.

    Nothing here is invented: every field is something the Space wrote into the policy when it
    published.

    Attributes:
        rail: How the endpoint is paid.
        price: The price per ``unit``.
        unit: What the price is for: ``"request"`` or ``"document"``.
        currency: The currency of ``price``.
        wallet_id: The prepaid wallet this endpoint bills against, when published.
        wallet_owner: The account that hosts that wallet.
        bundles: The credit bundles the Space sells.
        payment_url: Where invoices are created.
        credits_url: Where balances are read.
        invoices_url: Where past invoices are listed."""

    rail: Rail = Rail.FREE
    price: float = 0.0
    unit: str = "request"          # config.unit_type
    currency: str = "USD"
    wallet_id: str | None = None
    wallet_owner: str | None = None
    bundles: tuple[dict[str, Any], ...] = ()
    payment_url: str | None = None
    credits_url: str | None = None
    invoices_url: str | None = None

    @property
    def paid(self) -> bool:
        """``True`` when a call costs something."""
        return self.rail is not Rail.FREE and self.price > 0

    def label(self) -> str:
        """A short human label for the price.

        Returns:
            Text such as ``"$0.02/document via xendit"``, ``"free"``, or with ``"(experimental)"``
            appended for MPP."""
        if not self.paid:
            return "free"
        tag = " (experimental)" if self.rail is Rail.MPP else ""
        return f"{render.money(self.price, self.currency)}/{self.unit} via {self.rail.value}{tag}"

    @classmethod
    def from_policies(cls, policies: list[Policy]) -> "Pricing":
        """Decode the first enabled payment policy in a list.

        Args:
            policies: An endpoint's policies.

        Returns:
            The ``Pricing``, or a free one when no payment policy is present."""
        for p in policies:
            if p.is_payment and p.enabled:
                c = p.config
                return cls(Rail(p.type), float(c.get("price", c.get("price_per_request", 0)) or 0),
                           c.get("unit_type", "request"), c.get("currency", "USD"), c.get("wallet_id"),
                           c.get("wallet_owner"), tuple(c.get("bundles", [])), c.get("payment_url"),
                           c.get("credits_url"), c.get("invoices_url"))
        return cls()


@dataclass(frozen=True)
class Endpoint:
    """The Hub's public record of one endpoint, as its Space published it.

    Attributes:
        name: Display name.
        slug: URL-safe name; with the owner it forms the ``path``.
        type: ``"data_source"``, ``"model"``, or ``"model_data_source"``.
        owner_username: Who published it.
        description: One paragraph about it.
        version: The endpoint's own version string.
        tags: Free-form tags.
        stars_count: How many users starred it on the Hub.
        policies: Payment, access, and rate-limit policies.
        connect: How to reach its Space.
        readme: Longer documentation, in Markdown.
        health_status: ``"healthy"``, ``"unhealthy"``, or ``None`` when the Space has not reported.
        filterable: Metadata fields the Space can filter on before returning results. PROPOSED: the
            Hub record does not carry this today."""

    name: str
    slug: str
    type: str                        # data_source | model | model_data_source
    owner_username: str
    description: str = ""
    version: str = "0.1.0"
    tags: tuple[str, ...] = ()
    stars_count: int = 0
    policies: tuple[Policy, ...] = ()
    connect: tuple[Connection, ...] = ()
    readme: str = ""
    health_status: str | None = None     # from the Space's heartbeat to the Hub: healthy | unhealthy | None
    filterable: tuple[str, ...] = ()     # PROPOSED: metadata fields the Space filters on server-side (published by the Space)

    @property
    def path(self) -> str:
        """``owner/slug``, the name used everywhere else in the SDK."""
        return f"{self.owner_username}/{self.slug}"

    @property
    def url(self) -> str:
        """The Space's base URL, from the first enabled connection."""
        for c in self.connect:
            if c.enabled and c.config.get("url"):
                return str(c.config["url"]).rstrip("/")
        return ""

    @property
    def pricing(self) -> Pricing:
        """What a call costs, decoded from the payment policy."""
        return Pricing.from_policies(list(self.policies))

    def _repr_html_(self) -> str:
        return render.endpoint_card(self)

    def __repr__(self) -> str:
        return f"Endpoint({self.path}, {self.type}, {self.pricing.label()})"


class Selection(list):
    """A list of endpoints you can keep narrowing.

    This is what ``hub.browse()`` and ``hub.find()`` return. It renders as a table, narrows without
    any round trips, and goes straight into ``hub.search(sources=...)``."""

    def _repr_html_(self) -> str:
        return render.selection_table(self)

    @property
    def paths(self) -> list[str]:
        """The ``owner/slug`` of every endpoint, in order."""
        return [e.path for e in self]

    def filter(self, *, type: str | None = None, owner: str | None = None, free: bool | None = None,
               tag: str | None = None) -> "Selection":
        """Keep only the endpoints that match every condition given.

        Args:
            type: ``"data_source"`` or ``"model"``.
            owner: The publisher's username.
            free: ``True`` keeps free endpoints, ``False`` keeps paid ones.
            tag: A tag the endpoint must carry.

        Returns:
            A new, smaller ``Selection``. The original is unchanged."""
        out = []
        for e in self:
            if type is not None and e.type != type:
                continue
            if owner is not None and e.owner_username != owner:
                continue
            if free is not None and e.pricing.paid == free:
                continue
            if tag is not None and tag not in e.tags:
                continue
            out.append(e)
        return Selection(out)

    def matching(self, text: str, *, cutoff: float = 0.6) -> "Selection":
        """Keep the endpoints whose name, owner, description, or tags resemble some text.

        Typo-tolerant and ranked by how well they match.

        Args:
            text: Words to look for.
            cutoff: How much of the text must match, from 0 to 1. Lower it to see more results.

        Returns:
            A new ``Selection``, best match first."""
        from difflib import SequenceMatcher
        words = [w for w in text.lower().split() if w]
        scored = []
        for e in self:
            hay = " ".join([e.name, e.slug, e.owner_username, e.description, *e.tags]).lower()
            tokens = hay.replace("/", " ").replace("-", " ").replace("(", " ").replace(")", " ").replace(",", " ").split()
            score = 0.0
            for w in words:
                if w in hay:
                    score += 1.0
                    continue
                best = max((SequenceMatcher(None, w, t).ratio() for t in tokens if abs(len(t) - len(w)) <= 2), default=0.0)
                if best >= 0.85:
                    score += best
            if words and score / len(words) >= cutoff:
                scored.append((score, e))
        scored.sort(key=lambda t: (-t[0], -t[1].stars_count))
        return Selection(e for _, e in scored)

    def pick(self, *paths: str) -> "Selection":
        """Keep only the named endpoints.

        Args:
            *paths: Endpoints as ``owner/slug``.

        Returns:
            A new ``Selection`` in the order the paths were given."""
        wanted = set(paths)
        return Selection(e for e in self if e.path in wanted)

    def __add__(self, other) -> "Selection":
        """Combine two selections.

        Returns:
            A new ``Selection`` with every endpoint from both, each listed once."""
        seen, out = set(), []
        for e in list(self) + list(other):
            if e.path not in seen:
                seen.add(e.path); out.append(e)
        return Selection(out)


@dataclass
class Identity:
    """Who is signed in.

    Attributes:
        username: Your Hub username.
        email: Your email address.
        auth: How you signed in: ``"password"``, ``"google"``, or ``"token"``.
        hub_wallet_balance: Your Hub wallet balance. Used only to settle MPP charges.
        budget: The session budget, if you set one."""
    username: str
    email: str
    auth: str
    hub_wallet_balance: float          # Hub wallet; only used to settle MPP challenges
    budget: "Budget | None" = None

    def _repr_html_(self) -> str:
        return render.identity_card(self)


@dataclass
class Budget:
    """A spending cap for this session.

    It lives only in this client; the server never sees it. Every rail counts towards it.

    Attributes:
        limit: The cap.
        spent: How much this session has spent so far.
        currency: The currency of both numbers."""

    limit: float
    spent: float = 0.0
    currency: str = "USD"

    @property
    def remaining(self) -> float:
        """How much of the cap is left."""
        return round(self.limit - self.spent, 6)


# ---------------------------------------------------------------------- wallets
@dataclass
class Wallet:
    """One of your prepaid balances.

    A wallet belongs to a Space owner (or to a wallet-hosting account, for managed wallets) and there
    is one per owner, rail, and currency. Several endpoints can bill against the same wallet, so one
    top-up funds all of them.

    Attributes:
        key: The wallet's identifier: its published ``wallet_id``, or its credits URL when there is
            none.
        owner: The account that hosts the wallet.
        type: The rail: stripe, xendit, or cluster.
        currency: The currency the balance is in.
        balance: Your current credit, or ``None`` until it has been fetched.
        endpoints: Paths of the endpoints that bill against this wallet.
        bundles: The credit bundles you can buy.
        payment_url: Where invoices are created.
        credits_url: Where the balance is read."""

    key: str
    owner: str                       # wallet-hosting account (wallet_owner or the endpoint owner)
    type: Rail
    currency: str
    balance: float | None            # None until fetched from the Space
    endpoints: tuple[str, ...]       # paths billed against this wallet
    bundles: tuple[dict[str, Any], ...]
    payment_url: str | None
    credits_url: str | None
    _hub: Any = field(default=None, repr=False, compare=False)

    def top_up(self, bundle: str) -> dict[str, Any]:
        """Buy a credit bundle for this wallet.

        Args:
            bundle: The bundle's id, for example ``"starter"``. See ``bundles`` for what is on offer.

        Returns:
            The Space's invoice. Pay at its ``checkout_url``; the balance updates once the payment
            provider confirms."""
        return self._hub._create_invoice_for_wallet(self, bundle)

    def refresh(self) -> "Wallet":
        """Fetch the balance again.

        Returns:
            This wallet, with ``balance`` updated."""
        self.balance = self._hub._wallet_balance(self)
        return self

    def _repr_html_(self) -> str:
        return render.wallets_table([self])

    def __repr__(self) -> str:
        return f"Wallet({self.owner} {self.type.value} {self.currency}: {self.balance}, backs {len(self.endpoints)} endpoints)"


class Wallets(list):
    """Your prepaid wallets, as returned by ``hub.wallets()``.

    A list that also lets you look a wallet up by its key, or by the path of any endpoint it funds."""

    def __getitem__(self, key):  # by index, wallet key, or an endpoint path it backs
        """One wallet by position, by wallet key, or by the path of an endpoint it funds.

        Raises:
            KeyError: When no wallet matches."""
        if isinstance(key, int):
            return super().__getitem__(key)
        for w in self:
            if w.key == key or key in w.endpoints:
                return w
        raise KeyError(key)

    def _repr_html_(self) -> str:
        return render.wallets_table(self)


# ------------------------------------------------------------- Space responses
_OPS = ("_gte", "_gt", "_lte", "_lt", "_contains")


def filter_field(key: str) -> tuple[str, str]:
    """``published_gte`` -> ``("published", "gte")``; ``author`` -> ``("author", "eq")``."""
    for op in _OPS:
        if key.endswith(op):
            return key[: -len(op)], op[1:]
    return key, "eq"


def split_filters(filters: dict[str, Any], filterable: tuple[str, ...] | list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Which filter keys a Space will apply itself (its field is advertised as filterable) and which stay on the client."""
    space, client = {}, {}
    for k, v in filters.items():
        (space if filter_field(k)[0] in filterable else client)[k] = v
    return space, client


def to_space_filters(filters: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """PROPOSED request-body shape: ``{"published": {"gte": "2024-01-01"}, "author": {"eq": "R. Chitrakoot"}}``."""
    out: dict[str, dict[str, Any]] = {}
    for k, v in filters.items():
        f, op = filter_field(k)
        out.setdefault(f, {})[op] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def from_space_filters(filters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {f if op == "eq" else f"{f}_{op}": v for f, ops in filters.items() for op, v in ops.items()}


def match_metadata(meta: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Client-side filter over a document's ``metadata``. ``key`` = equals; ``key_gte/_gt/_lte/_lt`` compare
    (dates as ISO strings or date objects); ``key_contains`` = substring, case-insensitive."""
    for k, want in filters.items():
        for suffix in ("_gte", "_gt", "_lte", "_lt", "_contains"):
            if k.endswith(suffix):
                key, op = k[: -len(suffix)], suffix[1:]
                break
        else:
            key, op = k, "eq"
        have = meta.get(key)
        if have is None:
            return False
        if hasattr(want, "isoformat"):
            want = want.isoformat()
        if op == "eq" and have != want:
            return False
        if op == "contains" and str(want).lower() not in str(have).lower():
            return False
        if op in ("gte", "gt", "lte", "lt"):
            a, b = str(have), str(want)
            if (op == "gte" and not a >= b) or (op == "gt" and not a > b) or (op == "lte" and not a <= b) or (op == "lt" and not a < b):
                return False
    return True


@dataclass(frozen=True)
class Document:
    """One passage a source returned.

    Field names are exactly as the Space returns them.

    Attributes:
        document_id: The Space's id for the passage.
        content: The passage text.
        similarity_score: How well it matched the query, from 0 to 1.
        metadata: Whatever the Space attached, such as ``published`` or ``author``."""

    document_id: str
    content: str
    similarity_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TopUp:
    """A prepaid wallet that does not have enough credit, and what to do about it.

    Pre-flight attaches one of these to every source that is short. Choose a bundle with
    ``search.top_up(...)``, ``chat.top_up(...)`` or ``results.top_up(...)``, pay at ``checkout_url``,
    and the wallet is credited once the payment provider confirms.

    Attributes:
        endpoint: The endpoint whose call was held.
        wallet: The wallet that is short.
        needed: How much more credit the call needs, or ``None`` when unknown.
        invoice: The Space's invoice, once you chose a bundle.
        waiting: Every source in the same search that is blocked on this wallet."""

    endpoint: Endpoint
    wallet: Wallet
    needed: float | None
    invoice: dict[str, Any] | None = None     # the Space's InvoiceResponse once created
    waiting: tuple[str, ...] = ()             # every source in this search blocked on this wallet

    @property
    def balance(self) -> float | None:
        """The wallet's balance when the shortfall was found."""
        return self.wallet.balance

    @property
    def currency(self) -> str:
        """The wallet's currency."""
        return self.wallet.currency

    @property
    def bundles(self) -> tuple[dict[str, Any], ...]:
        """The credit bundles the Space sells for this wallet."""
        return self.wallet.bundles

    @property
    def checkout_url(self) -> str | None:
        """Where to pay. ``None`` until you choose a bundle with a ``top_up`` call."""
        return self.invoice.get("checkout_url") if self.invoice else None

    def _repr_html_(self) -> str:
        return render.topup_card(self)


@dataclass
class Charge:
    """A payment an MPP Space asked for before answering (experimental).

    Attributes:
        endpoint: The endpoint that asked.
        amount: How much it wants.
        currency: In which currency.
        www_authenticate: The challenge header, verbatim."""

    endpoint: Endpoint
    amount: float
    currency: str
    www_authenticate: str

    def _repr_html_(self) -> str:
        return render.charge_card(self)


@dataclass
class SourceResult:
    """One source's response, exactly as the Space returned it, plus views over it.

    Attributes:
        endpoint: Which endpoint answered.
        status_code: The HTTP status.
        raw: The response body, untouched.
        outcome: ``success``, ``skipped``, or ``payment_required``.
        reason: Why it was skipped, when it was.
        latency_ms: How long the call took.
        topup: The top-up to make, when the wallet was short.
        charge: The MPP charge to approve, when the Space asked for one.
        error: Transport error text, when there was no response at all.
        predicted: ``True`` when pre-flight decided this row and nothing was sent.
        note: Pre-flight's explanation for a predicted row.
        filters: Metadata filters applied in this client, after the Space answered.
        space_filters: Filters the Space applied itself, before returning.
        request: The request body that was sent, kept for inspection.
        keep_ids: Set by ``results.top(k)``: only these passages are shown."""

    endpoint: Endpoint
    status_code: int
    raw: dict[str, Any]                 # the response body, exactly as returned
    outcome: Outcome
    reason: SkipReason | None = None    # set when outcome is SKIPPED
    latency_ms: int = 0
    topup: TopUp | None = None
    charge: Charge | None = None
    error: str | None = None            # transport error text when there was no response
    predicted: bool = False             # True: decided client-side in pre-flight, nothing was sent
    note: str | None = None             # pre-flight explanation
    filters: dict[str, Any] = field(default_factory=dict)   # client-side document filters (see match_metadata)
    space_filters: dict[str, Any] = field(default_factory=dict)   # filters that went to the Space in the request body
    request: dict[str, Any] = field(default_factory=dict)   # the body that was sent (mock keeps it for inspection)
    keep_ids: frozenset[str] | None = None                  # set by Results.top(k): only these document ids

    # convenience views over ``raw`` --------------------------------------------
    @property
    def ok(self) -> bool:
        """``True`` when the Space answered."""
        return self.outcome is Outcome.SUCCESS

    @property
    def all_documents(self) -> list[Document]:
        """Every passage the Space returned, before any client-side filtering."""
        refs = (self.raw.get("references") or {}).get("documents") or []
        return [Document(d["document_id"], d["content"], d["similarity_score"], d.get("metadata") or {}) for d in refs]

    @property
    def documents(self) -> list[Document]:
        """The passages after client-side filters and ``top(k)``. This is what chat uses as context."""
        docs = self.all_documents
        if self.filters:
            docs = [d for d in docs if match_metadata(d.metadata, self.filters)]
        if self.keep_ids is not None:
            docs = [d for d in docs if d.document_id in self.keep_ids]
        return docs

    @property
    def returns(self) -> str:
        """What the response carries: ``"references"``, ``"summary"``, ``"both"``, or ``"nothing"``."""
        has_refs = bool((self.raw.get("references") or {}).get("documents"))
        has_sum = bool(self.raw.get("summary"))
        return "both" if has_refs and has_sum else "references" if has_refs else "summary" if has_sum else "nothing"

    @property
    def summary(self) -> str | None:
        """The model's text, when the endpoint returns a summary."""
        s = self.raw.get("summary")
        return s["message"]["content"] if s else None

    @property
    def cost(self) -> float:
        """What this call cost, from the response body."""
        return float(self.raw.get("cost") or 0.0)

    @property
    def currency(self) -> str | None:
        """The currency of ``cost``, from the response body."""
        return self.raw.get("currency")

    @property
    def policy_metadata(self) -> dict[str, Any]:
        """The Space's ``policy_metadata`` envelope: the outcome and every payment or policy entry."""
        return self.raw.get("policy_metadata") or {"outcome": None, "entries": []}

    @property
    def detail(self) -> str | None:
        """The Space's explanation on a rejection, or pre-flight's note on a predicted row."""
        return self.error or self.raw.get("detail") or self.note

    def _repr_html_(self) -> str:
        return render.source_card(self)

    @property
    def skipped(self) -> bool:
        """``True`` when the source was not answered."""
        return self.outcome is Outcome.SKIPPED

    def __repr__(self) -> str:
        why = f" ({self.reason.value})" if self.reason else ""
        what = f"{len(self.documents)} docs" + (" + summary" if self.summary else "")
        return f"SourceResult({self.endpoint.path}, {self.outcome.value}{why}, {what})"


@dataclass
class Answer:
    """A model's answer with citations, built over a set of results.

    Returned by ``results.aggregate``. The Aggregator route does not exist yet; this shape is a
    proposal.

    Attributes:
        text: The answer.
        via: ``"direct"`` or ``"aggregator"``.
        model: The model that answered.
        citations: Which source each ``[n]`` marker points at, by number.
        usage: Token counts reported by the model.
        cost: What the answer cost.
        currency: The currency of ``cost``.
        policy_metadata: The payment envelope, as returned.
        reranked: The passages in the order the Aggregator ranked them, when it did.
        results: The ``Results`` the answer was built from."""
    text: str
    via: str                            # direct | aggregator
    model: Endpoint
    citations: dict[int, str]           # [n] -> owner/slug of the cited document's source
    usage: dict[str, int]
    cost: float
    currency: str | None
    policy_metadata: dict[str, Any]
    reranked: list[tuple[str, Document]] | None = None
    results: "Any" = None               # the Results this answer was built from

    def _repr_html_(self) -> str:
        return render.answer_card(self)

    def __repr__(self) -> str:
        return f"Answer(via={self.via}, model={self.model.path}, {len(self.text)} chars)"
