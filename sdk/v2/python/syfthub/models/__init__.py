"""Typed records and enums. Space responses are kept exactly as returned under ``raw``; the SDK adds
classification and typed views on top, never a new shape.

Every model is a frozen pydantic model. Every enum is a ``str`` enum, so ``type="model"`` and
``type=EndpointType.MODEL`` both work and the IDE still offers the members."""
from __future__ import annotations

import enum
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from ..errors import ValidationError

if TYPE_CHECKING:  # pragma: no cover
    from ..hub import AsyncHub


# ============================================================================ enums
class EndpointType(str, enum.Enum):
    """What an endpoint returns.

    Attributes:
        DATA_SOURCE: Returns passages (``references``).
        MODEL: Returns a generated answer (``summary``).
        MODEL_DATA_SOURCE: Returns both."""
    DATA_SOURCE = "data_source"
    MODEL = "model"
    MODEL_DATA_SOURCE = "model_data_source"

    @property
    def returns_references(self) -> bool:
        """``True`` for endpoints that return passages."""
        return self in (EndpointType.DATA_SOURCE, EndpointType.MODEL_DATA_SOURCE)

    @property
    def returns_summary(self) -> bool:
        """``True`` for endpoints that return a generated answer."""
        return self in (EndpointType.MODEL, EndpointType.MODEL_DATA_SOURCE)


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
    STRIPE = "stripe"
    XENDIT = "xendit"
    CLUSTER = "cluster"
    MPP = "mpp"

    @property
    def prepaid(self) -> bool:
        """``True`` for the credit-based rails: stripe, xendit, and cluster."""
        return self in (Rail.STRIPE, Rail.XENDIT, Rail.CLUSTER)


class PolicyType(str, enum.Enum):
    """The kinds of policy a Space can publish with an endpoint.

    Attributes:
        STRIPE: Payment, prepaid through Stripe.
        XENDIT: Payment, prepaid through Xendit.
        CLUSTER: Payment, prepaid through a managed wallet.
        MPP: Payment per request (experimental).
        ACCESS: Allow and deny lists on the caller's email.
        RATE_LIMIT: Requests per period.
        PII_FILTER: Redaction of personal data in responses."""
    STRIPE = "stripe"
    XENDIT = "xendit"
    CLUSTER = "cluster"
    MPP = "mpp"
    ACCESS = "access"
    RATE_LIMIT = "rate_limit"
    PII_FILTER = "pii_filter"

    @property
    def is_payment(self) -> bool:
        """``True`` for the four payment policies."""
        return self in (PolicyType.STRIPE, PolicyType.XENDIT, PolicyType.CLUSTER, PolicyType.MPP)


class PriceUnit(str, enum.Enum):
    """What a price is for.

    Attributes:
        REQUEST: One price per call.
        DOCUMENT: One price per passage returned."""
    REQUEST = "request"
    DOCUMENT = "document"


class Outcome(str, enum.Enum):
    """What happened to one source, or one model, and who stopped it when it did not answer.

    Attributes:
        RETURNED: The Space answered.
        HELD: Pre-flight did not send it. ``reason`` says why; nothing was spent.
        REJECTED: The Space refused with a policy decision (403). ``reason`` carries the policy's code.
        FAILED: Transport or server failure after retries: unreachable, timed out, 5xx, not found.
        PAYMENT_REQUIRED: An MPP Space asked for a payment first (402). Approve it with ``results.approve()``."""
    RETURNED = "returned"
    HELD = "held"
    REJECTED = "rejected"
    FAILED = "failed"
    PAYMENT_REQUIRED = "payment_required"


class Reason(str, enum.Enum):
    """Why a source was held, rejected or failed. Shared by all three outcomes.

    Attributes:
        NO_CREDITS: The prepaid wallet is short. A ``TopUp`` is attached.
        OVER_BUDGET: Sending would cross the session budget. Client-side only.
        ACCESS_DENIED: The caller's email is not on the allow list.
        BY_USER: You skipped it with ``results.skip()``.
        RATE_LIMITED: The Space's rate limit is spent; ``rate_limit.reset_seconds`` says for how long.
        NO_PRICING_TIER: An MPP Space has no tier for this caller.
        BLOCKED: A 403 from a policy that gave no reason code.
        UNREACHABLE: Connection refused after every retry.
        TIMEOUT: No answer within the timeout after every retry.
        SERVER_ERROR: 5xx after every retry.
        NOT_FOUND: The Space does not know this endpoint.
        AUTH: 401 that one re-mint of the token did not fix.
        CIRCUIT_OPEN: The Space's circuit breaker is open; nothing was sent."""
    NO_CREDITS = "no_credits"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"
    BY_USER = "by_user"
    RATE_LIMITED = "rate_limited"
    NO_PRICING_TIER = "no_pricing_tier"
    BLOCKED = "blocked"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    NOT_FOUND = "not_found"
    AUTH = "auth"
    CIRCUIT_OPEN = "circuit_open"

    @property
    def retryable(self) -> bool:
        """``True`` when the condition can change, so ``retry()`` sends the source again."""
        return self in (Reason.NO_CREDITS, Reason.OVER_BUDGET, Reason.RATE_LIMITED, Reason.UNREACHABLE,
                        Reason.TIMEOUT, Reason.SERVER_ERROR, Reason.CIRCUIT_OPEN)


class Verdict(str, enum.Enum):
    """Pre-flight's one-word decision for a source.

    Attributes:
        READY: Will be sent.
        WILL_ASK_TO_PAY: MPP source; sent, and expected to answer 402 first.
        NEEDS_CREDITS: Held: the prepaid wallet is short.
        OVER_BUDGET: Held: the session budget would be crossed.
        ACCESS_DENIED: Held: the allow list excludes you.
        UNHEALTHY: Sent, but the last health check failed.
        CIRCUIT_OPEN: Held: the Space failed repeatedly a moment ago."""
    READY = "ready"
    WILL_ASK_TO_PAY = "will_ask_to_pay"
    NEEDS_CREDITS = "needs_credits"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"
    UNHEALTHY = "unhealthy"
    CIRCUIT_OPEN = "circuit_open"

    @property
    def label(self) -> str:
        """The verdict in words, for tables."""
        return self.value.replace("_", " ")


class ReturnKind(str, enum.Enum):
    """What a response, or a whole result set, carries.

    Attributes:
        REFERENCES: Passages only.
        SUMMARIES: Generated answers only.
        BOTH: Passages and answers.
        NOTHING: Nothing came back."""
    REFERENCES = "references"
    SUMMARIES = "summaries"
    BOTH = "both"
    NOTHING = "nothing"


class Include(str, enum.Enum):
    """What a chat hands its models as context.

    Attributes:
        REFERENCES: The passages.
        SUMMARIES: Other endpoints' answers.
        BOTH: Both."""
    REFERENCES = "references"
    SUMMARIES = "summaries"
    BOTH = "both"


class Via(str, enum.Enum):
    """How a chat reaches its models.

    Attributes:
        DIRECT: One request to each model's Space.
        AGGREGATOR: Through the Aggregator (route proposed)."""
    DIRECT = "direct"
    AGGREGATOR = "aggregator"


class AuthMethod(str, enum.Enum):
    """How the session was signed in.

    Attributes:
        PASSWORD: Username and password.
        GOOGLE: Google sign-in.
        TOKEN: A personal access token.
        GUEST: Not signed in."""
    PASSWORD = "password"
    GOOGLE = "google"
    TOKEN = "token"
    GUEST = "guest"


class Role(str, enum.Enum):
    """Who said a message in a transcript."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Health(str, enum.Enum):
    """The Space's last heartbeat to the Hub."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class InvoiceStatus(str, enum.Enum):
    """Where a credit purchase stands."""
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"


# ============================================================================ money
class Money(BaseModel):
    """An amount in one currency. Amounts in different currencies never add up by accident.

    Attributes:
        amount: The amount, as a ``Decimal``.
        currency: The ISO code, such as ``"USD"`` or ``"IDR"``."""
    model_config = ConfigDict(frozen=True)

    amount: Decimal = Decimal(0)
    currency: str = "USD"

    @classmethod
    def of(cls, amount: Any, currency: str | None = "USD") -> "Money":
        """Build from anything numeric, parsing floats through ``str`` so ``0.02`` stays ``0.02``.

        Args:
            amount: A number, a string, or ``None`` for zero.
            currency: The currency; ``None`` means USD.

        Returns:
            The ``Money``."""
        return cls(amount=Decimal(str(amount if amount is not None else 0)), currency=currency or "USD")

    def _check(self, other: "Money") -> None:
        if other.currency != self.currency:
            raise ValidationError(f"cannot combine {self.currency} with {other.currency}: keep totals per currency")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, n: Any) -> "Money":
        return Money(amount=self.amount * Decimal(str(n)), currency=self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check(other); return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check(other); return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check(other); return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check(other); return self.amount >= other.amount

    def __bool__(self) -> bool:
        return self.amount != 0

    @property
    def is_zero(self) -> bool:
        """``True`` when the amount is zero."""
        return self.amount == 0

    def __str__(self) -> str:
        sym = {"USD": "$", "EUR": "€", "IDR": "Rp"}.get(self.currency, f"{self.currency} ")
        return f"{sym}{self.amount:,.0f}" if self.currency == "IDR" else f"{sym}{self.amount:,.2f}"

    def __repr__(self) -> str:
        return f"Money({self.amount}, {self.currency!r})"


def total(amounts: Iterable[Money | None]) -> dict[str, Money]:
    """Add amounts up per currency.

    Args:
        amounts: Any iterable of ``Money`` (``None`` entries are skipped).

    Returns:
        ``{currency: Money}``, only for currencies that appear."""
    out: dict[str, Money] = {}
    for m in amounts:
        if m is None:
            continue
        out[m.currency] = out[m.currency] + m if m.currency in out else m
    return out


# ============================================================================ Hub records
class Bundle(BaseModel):
    """A credit bundle a Space sells for one of its wallets.

    Attributes:
        id: The bundle's id, what you pass to ``top_up``.
        amount: What it costs, which is also the credit it adds."""
    model_config = ConfigDict(frozen=True)

    id: str
    amount: Money

    @classmethod
    def _from_config(cls, b: dict[str, Any], currency: str) -> "Bundle":
        return cls(id=str(b.get("name") or b.get("id")), amount=Money.of(b.get("amount"), currency))


class Policy(BaseModel):
    """One policy a Space published with an endpoint, exactly as published.

    Attributes:
        type: The policy kind. For payment policies this is the wallet type.
        config: The policy's settings, verbatim.
        version: The policy schema version.
        enabled: Whether the Space currently enforces it.
        description: The Space's own description of the policy."""
    model_config = ConfigDict(frozen=True)

    type: PolicyType
    config: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0"
    enabled: bool = True
    description: str = ""

    @property
    def is_payment(self) -> bool:
        """``True`` for a payment policy of any rail."""
        return self.type.is_payment


class Connection(BaseModel):
    """How to reach the Space that serves an endpoint.

    Attributes:
        type: The connection kind, normally ``"https"``.
        config: Settings for it; ``config["url"]`` is the Space's base URL.
        enabled: Whether this connection is active."""
    model_config = ConfigDict(frozen=True)

    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class Pricing(BaseModel):
    """What one call to an endpoint costs, read from its payment policy. Nothing here is invented.

    Attributes:
        rail: How the endpoint is paid.
        price: The price per ``unit``.
        unit: What the price is for.
        wallet_id: The prepaid wallet this endpoint bills against, when published.
        wallet_owner: The account that hosts that wallet, for managed wallets.
        bundles: The credit bundles the Space sells.
        payment_url: Where invoices are created.
        credits_url: Where balances are read.
        invoices_url: Where past invoices are listed."""
    model_config = ConfigDict(frozen=True)

    rail: Rail = Rail.FREE
    price: Money = Money()
    unit: PriceUnit = PriceUnit.REQUEST
    wallet_id: str | None = None
    wallet_owner: str | None = None
    bundles: tuple[Bundle, ...] = ()
    payment_url: str | None = None
    credits_url: str | None = None
    invoices_url: str | None = None

    @property
    def currency(self) -> str:
        """The currency of ``price``."""
        return self.price.currency

    @property
    def paid(self) -> bool:
        """``True`` when a call costs something."""
        return self.rail is not Rail.FREE and bool(self.price)

    @property
    def prepaid(self) -> bool:
        """``True`` when the endpoint bills a prepaid wallet."""
        return self.paid and self.rail.prepaid

    @property
    def label(self) -> str:
        """A short label such as ``"$0.02/document via xendit"`` or ``"free"``."""
        if not self.paid:
            return "free"
        tag = " (experimental)" if self.rail is Rail.MPP else ""
        return f"{self.price}/{self.unit.value} via {self.rail.value}{tag}"

    def estimate(self, limit: int) -> Money:
        """The most one call can cost: price times ``limit`` per document, or the price per request.

        Args:
            limit: How many passages the call asks for.

        Returns:
            The maximum cost."""
        if not self.paid:
            return Money(currency=self.currency)
        return self.price * (limit if self.unit is PriceUnit.DOCUMENT else 1)

    @classmethod
    def from_policies(cls, policies: Iterable[Policy]) -> "Pricing":
        """Decode the first enabled payment policy; free when there is none."""
        for p in policies:
            if p.is_payment and p.enabled:
                c = p.config
                cur = c.get("currency", "USD")
                return cls(rail=Rail(p.type.value), price=Money.of(c.get("price", c.get("price_per_request", 0)), cur),
                           unit=PriceUnit(c.get("unit_type", "request")), wallet_id=c.get("wallet_id"),
                           wallet_owner=c.get("wallet_owner"),
                           bundles=tuple(Bundle._from_config(b, cur) for b in c.get("bundles", [])),
                           payment_url=c.get("payment_url"), credits_url=c.get("credits_url"),
                           invoices_url=c.get("invoices_url"))
        return cls()


class Endpoint(BaseModel):
    """The Hub's public record of one endpoint, as its Space published it.

    Attributes:
        name: Display name.
        slug: URL-safe name; with the owner it forms the ``path``.
        type: What it returns.
        owner_username: Who published it.
        description: One paragraph about it.
        version: The endpoint's own version string.
        tags: Free-form tags.
        stars_count: How many users starred it on the Hub.
        policies: Payment, access, and rate-limit policies.
        connect: How to reach its Space.
        readme: Longer documentation, in Markdown.
        health: The Space's last heartbeat.
        filterable: Metadata fields the Space filters on before returning results. PROPOSED: the Hub
            record does not carry this today."""
    model_config = ConfigDict(frozen=True)

    name: str
    slug: str
    type: EndpointType
    owner_username: str
    description: str = ""
    version: str = "0.1.0"
    tags: tuple[str, ...] = ()
    stars_count: int = 0
    policies: tuple[Policy, ...] = ()
    connect: tuple[Connection, ...] = ()
    readme: str = ""
    health: Health = Health.UNKNOWN
    filterable: tuple[str, ...] = ()

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
        return Pricing.from_policies(self.policies)

    def policy(self, type: PolicyType | str) -> Policy | None:
        """The enabled policy of one type, if any.

        Args:
            type: Which policy.

        Returns:
            The ``Policy`` or ``None``."""
        t = PolicyType(type)
        return next((p for p in self.policies if p.type is t and p.enabled), None)

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.endpoint_card(self)

    def __repr__(self) -> str:
        return f"Endpoint({self.path}, {self.type.value}, {self.pricing.label})"

    __str__ = __repr__


class EndpointList(list):
    """A list of endpoints you can keep narrowing without a round trip.

    Returned by ``hub.endpoints.list()`` and ``hub.endpoints.search()``; accepted by ``hub.search(sources=...)``."""

    @property
    def paths(self) -> list[str]:
        """The ``owner/slug`` of every endpoint, in order."""
        return [e.path for e in self]

    def filter(self, *, type: EndpointType | str | None = None, owner: str | None = None,
               free: bool | None = None, tag: str | None = None) -> "EndpointList":
        """Keep the endpoints that match every condition given.

        Args:
            type: ``EndpointType`` or its value.
            owner: The publisher's username.
            free: ``True`` keeps free endpoints, ``False`` keeps paid ones.
            tag: A tag the endpoint must carry.

        Returns:
            A new, smaller list. The original is unchanged."""
        t = EndpointType(type) if type is not None else None
        out = [e for e in self
               if (t is None or e.type is t) and (owner is None or e.owner_username == owner)
               and (free is None or e.pricing.paid != free) and (tag is None or tag in e.tags)]
        return EndpointList(out)

    def matching(self, text: str, *, cutoff: float = 0.6) -> "EndpointList":
        """Keep the endpoints whose name, owner, description, or tags resemble some text. Typo-tolerant.

        Args:
            text: Words to look for.
            cutoff: How much of the text must match, from 0 to 1. Lower it to see more.

        Returns:
            A new list, best match first."""
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
        return EndpointList(e for _, e in scored)

    def pick(self, *paths: str) -> "EndpointList":
        """Keep only the named endpoints, in the order given.

        Args:
            *paths: Endpoints as ``owner/slug``.

        Returns:
            A new list."""
        by = {e.path: e for e in self}
        return EndpointList(by[p] for p in paths if p in by)

    def __add__(self, other: Iterable[Endpoint]) -> "EndpointList":
        """Combine two lists, each endpoint listed once."""
        seen, out = set(), []
        for e in list(self) + list(other):
            if e.path not in seen:
                seen.add(e.path); out.append(e)
        return EndpointList(out)

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.endpoint_table(self)


class Page(BaseModel):
    """One page of a Hub listing, for Hubs too large for ``list()``.

    Attributes:
        items: The endpoints on this page.
        offset: Where this page starts.
        total: How many endpoints the listing has in all."""
    model_config = ConfigDict(frozen=True)

    items: tuple[Endpoint, ...]
    offset: int
    total: int


# ============================================================================ session
class Identity(BaseModel):
    """Who is signed in.

    Attributes:
        username: Your Hub username.
        email: Your email address.
        auth: How you signed in.
        hub_wallet_balance: Your Hub wallet. Used only to settle MPP charges."""
    model_config = ConfigDict(frozen=True)

    username: str
    email: str
    auth: AuthMethod
    hub_wallet_balance: Money = Money()

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.identity_card(self)

    def __repr__(self) -> str:
        return f"Identity({self.username}, {self.email}, {self.auth.value}, hub wallet {self.hub_wallet_balance})"

    __str__ = __repr__


class Budget(BaseModel):
    """A spending cap for this session. It lives only in this client; every rail counts towards it.

    Attributes:
        limit: The cap.
        spent: How much this session has spent so far."""
    model_config = ConfigDict(frozen=True)

    limit: Money
    spent: Money = Money()

    @property
    def remaining(self) -> Money:
        """How much of the cap is left."""
        return self.limit - self.spent

    def __repr__(self) -> str:
        return f"Budget({self.remaining} of {self.limit} left)"

    __str__ = __repr__


class RateLimit(BaseModel):
    """What a Space said about its rate limit, surfaced from the response rather than buried in ``raw``.

    Attributes:
        limit: The policy's limit, such as ``"2/m"``.
        remaining: Calls left in the window, when the Space says.
        reset_seconds: Seconds until the window resets, when the Space says."""
    model_config = ConfigDict(frozen=True)

    limit: str | None = None
    remaining: int | None = None
    reset_seconds: int | None = None


class Message(BaseModel):
    """One turn of a transcript, in the shape a Space's ``messages`` field takes.

    Attributes:
        role: Who said it.
        content: The text."""
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str

    def wire(self) -> dict[str, str]:
        return {"role": self.role.value, "content": self.content}


# ============================================================================ wallets and payment
class Invoice(BaseModel):
    """A credit purchase on a Space, as its ``InvoiceResponse`` returned it.

    Pay at ``checkout_url``. The payment provider's webhook credits the wallet; ``wait_paid()`` polls the
    balance until it does.

    Attributes:
        id: The invoice id.
        wallet_key: The wallet it credits.
        bundle: The bundle bought.
        amount: What it costs.
        status: Where the purchase stands.
        checkout_url: Where to pay.
        created_at: When the Space created it.
        raw: The ``InvoiceResponse`` verbatim."""
    model_config = ConfigDict(frozen=True)

    id: str
    wallet_key: str
    bundle: str
    amount: Money
    status: InvoiceStatus = InvoiceStatus.PENDING
    checkout_url: str | None = None
    created_at: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    _hub: Any = PrivateAttr(default=None)
    _balance_before: Any = PrivateAttr(default=None)

    @property
    def paid(self) -> bool:
        """``True`` once the wallet has been credited."""
        return self.status is InvoiceStatus.PAID

    async def wait_paid(self, timeout: float = 600.0, poll: float = 5.0) -> "Invoice":
        """Headless flow: poll the wallet's balance until it rises, then return the paid invoice.

        Args:
            timeout: Seconds to wait before giving up.
            poll: Seconds between balance reads.

        Returns:
            A copy of this invoice with ``status`` set to ``paid``.

        Raises:
            InvalidState: When the timeout passes with no payment."""
        from ..errors import InvalidState
        waited = 0.0
        while waited <= timeout:
            bal = await self._hub.wallets._balance_of(self.wallet_key)
            if self._balance_before is None or bal > self._balance_before:
                inv = self.model_copy(update={"status": InvoiceStatus.PAID})
                inv._hub, inv._balance_before = self._hub, self._balance_before
                return inv
            await self._hub._sleep(poll)
            waited += poll
        raise InvalidState(f"invoice {self.id} not paid after {timeout:.0f}s: pay at {self.checkout_url}, then retry()")

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.invoice_card(self)

    def __repr__(self) -> str:
        return f"Invoice({self.id}, {self.bundle} {self.amount}, {self.status.value})"

    __str__ = __repr__


class Wallet(BaseModel):
    """One of your prepaid balances.

    A wallet belongs to a Space owner, or to a wallet-hosting account for managed wallets, and there is
    one per owner, rail, and currency. Several endpoints can bill the same wallet, so one top-up funds all
    of them.

    Attributes:
        key: The wallet's identifier: its published ``wallet_id``, or its credits URL when there is none.
        owner: The account that hosts the wallet.
        rail: stripe, xendit, or cluster.
        currency: The currency the balance is in.
        balance: Your current credit, or ``None`` until fetched.
        endpoints: Paths of the endpoints that bill against this wallet.
        bundles: The credit bundles you can buy.
        payment_url: Where invoices are created.
        credits_url: Where the balance is read."""
    model_config = ConfigDict(frozen=True)

    key: str
    owner: str
    rail: Rail
    currency: str
    balance: Money | None = None
    endpoints: tuple[str, ...] = ()
    bundles: tuple[Bundle, ...] = ()
    payment_url: str | None = None
    credits_url: str | None = None
    _hub: Any = PrivateAttr(default=None)

    def bundle(self, id: str) -> Bundle:
        """One of this wallet's bundles by id.

        Raises:
            ValidationError: When the wallet sells no such bundle."""
        for b in self.bundles:
            if b.id == id:
                return b
        raise ValidationError(f"wallet {self.key} sells no bundle {id!r}; choose from {[b.id for b in self.bundles]}")

    async def top_up(self, bundle: Bundle | str) -> Invoice:
        """Buy a credit bundle for this wallet.

        Args:
            bundle: A ``Bundle`` or its id, for example ``"starter"``.

        Returns:
            The ``Invoice``. Pay at its ``checkout_url``; ``await invoice.wait_paid()`` in a script."""
        return await self._hub.wallets._create_invoice(self, bundle if isinstance(bundle, str) else bundle.id)

    async def refresh(self) -> "Wallet":
        """Fetch the balance again.

        Returns:
            A copy of this wallet with the current balance."""
        return await self._hub.wallets.get(self.key)

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.wallets_table([self])

    def __repr__(self) -> str:
        return f"Wallet({self.owner} {self.rail.value} {self.currency}: {self.balance}, backs {len(self.endpoints)} endpoints)"

    __str__ = __repr__


class WalletList(list):
    """Your prepaid wallets. Index by position, by wallet key, or by the path of an endpoint a wallet funds."""

    def __getitem__(self, key):
        """One wallet by position, key, or endpoint path.

        Raises:
            KeyError: When no wallet matches."""
        if isinstance(key, (int, slice)):
            return super().__getitem__(key)
        for w in self:
            if w.key == key or key in w.endpoints:
                return w
        raise KeyError(f"{key}: no wallet with that key, and no endpoint by that path bills a prepaid wallet")

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.wallets_table(self)


class TopUp(BaseModel):
    """A prepaid wallet that is short, and what to do about it.

    Attached to every held or rejected row whose reason is ``NO_CREDITS``; ``pending`` lists one per wallet.

    Attributes:
        endpoint: The endpoint whose call was held.
        wallet: The wallet that is short.
        needed: How much more credit the calls need, when known.
        waiting: Every source in the same plan or result blocked on this wallet."""
    model_config = ConfigDict(frozen=True)

    endpoint: Endpoint
    wallet: Wallet
    needed: Money | None = None
    waiting: tuple[str, ...] = ()

    @property
    def balance(self) -> Money | None:
        """The wallet's balance when the shortfall was found."""
        return self.wallet.balance

    @property
    def bundles(self) -> tuple[Bundle, ...]:
        """The bundles the Space sells for this wallet."""
        return self.wallet.bundles

    async def buy(self, bundle: Bundle | str) -> Invoice:
        """Buy a bundle for the short wallet. Same as ``wallet.top_up``.

        Args:
            bundle: A ``Bundle`` or its id.

        Returns:
            The ``Invoice``."""
        return await self.wallet.top_up(bundle)

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.topup_card(self)

    def __repr__(self) -> str:
        return f"TopUp({self.wallet.key}: needs {self.needed}, waiting {list(self.waiting)})"

    __str__ = __repr__


class Charge(BaseModel):
    """A payment an MPP Space asked for before answering (experimental).

    Attributes:
        endpoint: The endpoint that asked.
        amount: How much it wants.
        www_authenticate: The challenge header, verbatim. Redacted in ``repr``."""
    model_config = ConfigDict(frozen=True)

    endpoint: Endpoint
    amount: Money
    www_authenticate: str

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.charge_card(self)

    def __repr__(self) -> str:
        return f"Charge({self.endpoint.path}: {self.amount}, challenge <redacted>)"

    __str__ = __repr__


class ChargeEntry(BaseModel):
    """One payment entry from a Space's ``policy_metadata`` envelope, flattened.

    Attributes:
        source: The endpoint, as ``owner/slug``.
        policy_type: The policy that charged, such as ``xendit_per_document``.
        status: ``charged``, ``rejected``, ``refunded`` or ``free``.
        amount: The amount, when the entry has one.
        wallet: The prepaid wallet billed, when any.
        rail: The rail.
        transaction_id: The Space's ledger id, when any.
        details: Anything else the Space attached.
        raw: The entry verbatim."""
    model_config = ConfigDict(frozen=True)

    source: str
    policy_type: str | None
    status: str | None
    amount: Money | None
    wallet: str | None
    rail: str | None
    transaction_id: str | None
    details: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def signed(self) -> Money | None:
        """The amount with its sign: negative for refunds, zero for rejections."""
        if self.amount is None:
            return None
        if self.status == "refunded":
            return self.amount * -1
        return self.amount if self.status == "charged" else Money(currency=self.amount.currency)


# ============================================================================ documents and filters
_OPS = ("_gte", "_gt", "_lte", "_lt", "_contains")


def filter_field(key: str) -> tuple[str, str]:
    """``published_gte`` -> ``("published", "gte")``; ``author`` -> ``("author", "eq")``."""
    for op in _OPS:
        if key.endswith(op):
            return key[: -len(op)], op[1:]
    return key, "eq"


class FilterSplit(BaseModel):
    """Where one source's filters are applied.

    Attributes:
        remote: Filters the Space applies before ``limit`` (fields it advertises as filterable).
        local: Filters this client applies after the response."""
    model_config = ConfigDict(frozen=True)

    remote: dict[str, Any] = Field(default_factory=dict)
    local: dict[str, Any] = Field(default_factory=dict)


def split_filters(filters: dict[str, Any], filterable: Iterable[str]) -> FilterSplit:
    adv = set(filterable)
    remote, local = {}, {}
    for k, v in filters.items():
        (remote if filter_field(k)[0] in adv else local)[k] = v
    return FilterSplit(remote=remote, local=local)


def to_space_filters(filters: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """PROPOSED request-body shape: ``{"published": {"gte": "2024-01-01"}}``."""
    out: dict[str, dict[str, Any]] = {}
    for k, v in filters.items():
        f, op = filter_field(k)
        out.setdefault(f, {})[op] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def from_space_filters(filters: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {f if op == "eq" else f"{f}_{op}": v for f, ops in filters.items() for op, v in ops.items()}


def match_metadata(meta: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Client-side filter over a document's ``metadata``."""
    for k, want in filters.items():
        key, op = filter_field(k)
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


def validate_filters(filters: dict[str, Any]) -> None:
    for k in filters:
        f, _ = filter_field(k)
        if not f or not f.replace("_", "").isalnum():
            raise ValidationError(f"bad filter key {k!r}: use field, field_gte, field_gt, field_lte, field_lt or field_contains")


class Document(BaseModel):
    """One passage a source returned. Field names are exactly as the Space returns them.

    Attributes:
        document_id: The Space's id for the passage.
        content: The passage text.
        similarity_score: How well it matched the query, from 0 to 1.
        metadata: Whatever the Space attached, such as ``published`` or ``author``."""
    model_config = ConfigDict(frozen=True)

    document_id: str
    content: str
    similarity_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================================================ plan and result rows
class PlanRow(BaseModel):
    """One source's pre-flight: what it would cost and whether it will be sent.

    Attributes:
        endpoint: The source.
        estimate: The most one call can cost.
        verdict: Pre-flight's decision.
        send: ``True`` when the source will be sent on ``execute()``.
        hold_reason: Why it is held, when it is.
        wallet: The prepaid wallet it bills against, when it has one.
        warnings: Anything worth knowing before sending.
        note: Pre-flight's explanation, shown in the table."""
    model_config = ConfigDict(frozen=True)

    endpoint: Endpoint
    estimate: Money
    verdict: Verdict
    send: bool
    hold_reason: Reason | None = None
    wallet: Wallet | None = None
    warnings: tuple[str, ...] = ()
    note: str | None = None


class SourceResult(BaseModel):
    """One source's response, exactly as the Space returned it, plus typed views over it.

    Attributes:
        endpoint: Which endpoint.
        status_code: The HTTP status, or 0 when nothing was sent.
        raw: The response body, untouched.
        outcome: What happened.
        reason: Why, when it did not answer.
        elapsed_ms: How long the call took, including retries.
        attempts: How many requests were made.
        topup: The top-up to make, when the wallet was short.
        charge: The MPP charge to approve, when the Space asked for one.
        rate_limit: What the Space said about its rate limit, when it did.
        error: Transport error text, when there was no response at all.
        predicted: ``True`` when pre-flight decided this row and nothing was sent.
        note: Pre-flight's explanation for a predicted row.
        local_filters: Metadata filters applied in this client, after the Space answered.
        remote_filters: Filters the Space applied itself, before returning.
        request: The request body that was sent, kept for inspection.
        keep_ids: Set by ``results.top(k)``: only these passages are shown."""
    model_config = ConfigDict(frozen=True)

    endpoint: Endpoint
    status_code: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)
    outcome: Outcome
    reason: Reason | None = None
    elapsed_ms: int = 0
    attempts: int = 0
    topup: TopUp | None = None
    charge: Charge | None = None
    rate_limit: RateLimit | None = None
    error: str | None = None
    predicted: bool = False
    note: str | None = None
    local_filters: dict[str, Any] = Field(default_factory=dict)
    remote_filters: dict[str, Any] = Field(default_factory=dict)
    request: dict[str, Any] = Field(default_factory=dict)
    keep_ids: frozenset[str] | None = None

    @property
    def ok(self) -> bool:
        """``True`` when the Space answered."""
        return self.outcome is Outcome.RETURNED

    @property
    def retryable(self) -> bool:
        """``True`` when ``retry()`` would send this source again."""
        return not self.ok and self.reason is not None and self.reason.retryable

    @property
    def all_documents(self) -> list[Document]:
        """Every passage the Space returned, before any client-side filtering."""
        refs = (self.raw.get("references") or {}).get("documents") or []
        return [Document(document_id=d["document_id"], content=d["content"], similarity_score=d["similarity_score"],
                         metadata=d.get("metadata") or {}) for d in refs]

    @property
    def documents(self) -> list[Document]:
        """The passages after client-side filters and ``top(k)``. This is what a chat uses as context."""
        docs = self.all_documents
        if self.local_filters:
            docs = [d for d in docs if match_metadata(d.metadata, self.local_filters)]
        if self.keep_ids is not None:
            docs = [d for d in docs if d.document_id in self.keep_ids]
        return docs

    @property
    def kind(self) -> ReturnKind:
        """What the response carries."""
        has_refs = bool((self.raw.get("references") or {}).get("documents"))
        has_sum = bool(self.raw.get("summary"))
        if has_refs and has_sum:
            return ReturnKind.BOTH
        return ReturnKind.REFERENCES if has_refs else ReturnKind.SUMMARIES if has_sum else ReturnKind.NOTHING

    @property
    def summary(self) -> str | None:
        """The model's text, when the endpoint returns one."""
        s = self.raw.get("summary")
        return s["message"]["content"] if s else None

    @property
    def usage(self) -> dict[str, int]:
        """Token counts reported with a summary, when any."""
        return ((self.raw.get("summary") or {}).get("usage") or {})

    @property
    def cost(self) -> Money | None:
        """What this call cost, from the response body; ``None`` when the Space reported none."""
        if self.raw.get("cost") is None:
            return None
        return Money.of(self.raw["cost"], self.raw.get("currency") or self.endpoint.pricing.currency)

    @property
    def policy_metadata(self) -> dict[str, Any]:
        """The Space's ``policy_metadata`` envelope: the outcome and every payment or policy entry."""
        return self.raw.get("policy_metadata") or {"outcome": None, "entries": []}

    @property
    def charges(self) -> list[ChargeEntry]:
        """The payment entries of the envelope, typed."""
        out = []
        p = self.endpoint.pricing
        for e in self.policy_metadata.get("entries", []):
            if e.get("kind") != "payment":
                continue
            tx = e.get("transaction") or {}
            out.append(ChargeEntry(source=self.endpoint.path, policy_type=e.get("policy_type"), status=e.get("status"),
                                   amount=Money.of(e["amount"], e.get("currency") or p.currency) if e.get("amount") is not None else None,
                                   wallet=p.wallet_id, rail=tx.get("rail") or p.rail.value, transaction_id=tx.get("id"),
                                   details=e.get("details") or {}, raw=e))
        return out

    @property
    def detail(self) -> str | None:
        """The Space's explanation on a rejection, the transport error, or pre-flight's note."""
        return self.error or self.raw.get("detail") or self.note

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.source_card(self)

    def __repr__(self) -> str:
        why = f" ({self.reason.value})" if self.reason else ""
        what = f"{len(self.documents)} docs" + (" + summary" if self.summary else "")
        return f"SourceResult({self.endpoint.path}, {self.outcome.value}{why}, {what})"

    __str__ = __repr__


class Answer(BaseModel):
    """One reranked, cited answer from the Aggregator (route proposed).

    Attributes:
        text: The answer.
        model: The model that answered.
        citations: Which source each ``[n]`` marker points at.
        reranked: Passages in the Aggregator's order, as ``(source path, Document)``.
        usage: Token counts reported by the model.
        cost: What the answer cost at the model, when reported.
        per_source: Each Space's own result when the Aggregator fanned out (option 1), else empty.
        pending: Top-ups or charges the Aggregator forwarded (option 1), else empty.
        job_id: The Aggregator's job to resume once ``pending`` is paid (option 1).
        raw: The Aggregator's response body."""
    model_config = ConfigDict(frozen=True)

    text: str | None
    model: Endpoint
    citations: dict[int, str] = Field(default_factory=dict)
    reranked: tuple[tuple[str, Document], ...] = ()
    usage: dict[str, int] = Field(default_factory=dict)
    cost: Money | None = None
    per_source: tuple[SourceResult, ...] = ()
    pending: tuple[TopUp | Charge, ...] = ()
    job_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    _hub: Any = PrivateAttr(default=None)
    _request: Any = PrivateAttr(default=None)

    @property
    def ok(self) -> bool:
        """``True`` when the Aggregator produced an answer."""
        return self.text is not None

    async def resume(self) -> "Answer":
        """Option 1 only: once ``pending`` is paid, ask the Aggregator to finish the job.

        Returns:
            A new ``Answer``.

        Raises:
            InvalidState: When there is nothing to resume."""
        from ..errors import InvalidState
        if not self.job_id:
            raise InvalidState("nothing to resume: this answer did not leave anything pending")
        return await self._hub._aggregator.resume(self)

    async def approve(self) -> "Answer":
        """Option 1, MPP: pay the charges the Aggregator forwarded from your Hub wallet, then resume the job with
        the payment credentials attached (experimental).

        Returns:
            A new ``Answer``.

        Raises:
            BudgetExceeded: When paying would cross the session budget.
            InvalidState: When nothing is pending."""
        from ..errors import InvalidState
        charges = [p for p in self.pending if isinstance(p, Charge)]
        if not charges or not self.job_id:
            raise InvalidState("nothing to approve: no MPP charge is pending on this answer")
        payments = {c.endpoint.path: await self._hub._pay_mpp(c) for c in charges}
        return await self._hub._aggregator.resume(self, payments=payments)

    def _repr_html_(self) -> str:
        from ..notebook import render
        return render.answer_card(self)

    def __repr__(self) -> str:
        if not self.ok:
            return f"Answer(pending {len(self.pending)}, job {self.job_id})"
        return f"Answer(model={self.model.path}, {len(self.text or '')} chars, {len(self.citations)} citations)"

    __str__ = __repr__


__all__ = [n for n in dir() if not n.startswith("_") and n not in ("annotations", "enum", "Decimal", "Any", "Iterable",
                                                                    "BaseModel", "ConfigDict", "Field", "PrivateAttr",
                                                                    "TYPE_CHECKING", "ValidationError")]
