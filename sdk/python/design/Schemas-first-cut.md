# Schemas

Every object the first cut exposes, as pydantic v2 models. Data objects are frozen; the three stateful ones, `SearchPlan`, `Results` and `Wallet`, say so. A Hub endpoint is a `Source` here; otherwise field names follow the Hub and Space response bodies wherever one exists, so `raw` and the typed fields never disagree on a name. Methods are listed under each model as signatures only; their behaviour is in the Scope tab.

## Conventions

```python
from decimal import Decimal
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class Frozen(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="ignore"
    )  # unknown Hub/Space fields are kept in .raw, never rejected
```

- Enums are `str` enums, so they compare and serialise as their value.
- Collections are tuples on frozen models, so a model is hashable and cannot be mutated in place.
- Every model has `to_dict()` and `from_dict()`; the dict is plain JSON (Decimals as strings, datetimes as ISO 8601).
- `raw` holds the verbatim server body where there is one. Typed fields are a view over it.
- Objects that call the network hold the hub in a private attribute, never in a field, so `to_dict()` is always safe to store.

## Enums

```python
class SourceType(str, Enum):  # values are the Hub's endpoint types, unchanged
    DOCUMENTS = "data_source"
    MODEL = "model"
    BOTH = "model_data_source"

    @property
    def returns_documents(self) -> bool: ...  # DOCUMENTS, BOTH


class Rail(str, Enum):  # how a source is paid; read off the payment policy
    FREE = "free"
    STRIPE = "stripe"
    XENDIT = "xendit"
    CLUSTER = "cluster"
    MPP = "mpp"

    @property
    def prepaid(self) -> bool: ...  # STRIPE, XENDIT, CLUSTER


class PolicyType(str, Enum):
    STRIPE = "stripe"
    XENDIT = "xendit"
    CLUSTER = "cluster"
    MPP = "mpp"
    ACCESS = "access"
    RATE_LIMIT = "rate_limit"
    PII_FILTER = "pii_filter"


class PriceUnit(str, Enum):
    REQUEST = "request"
    DOCUMENT = "document"


class AuthMethod(str, Enum):
    PASSWORD = "password"
    TOKEN = "token"
    GOOGLE = "google"


class Verdict(str, Enum):  # pre-flight, per row
    READY = "ready"
    WILL_ASK_TO_PAY = "will_ask_to_pay"  # sent
    NEEDS_CREDITS = "needs_credits"
    OVER_BUDGET = "over_budget"  # held
    ACCESS_DENIED = "access_denied"
    CIRCUIT_OPEN = "circuit_open"
    SKIPPED = "skipped"  # held


class ActionKind(str, Enum):
    TOP_UP = "top_up"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"
    CIRCUIT_OPEN = "circuit_open"


class Outcome(str, Enum):  # execute, per row
    RETURNED = "returned"
    HELD = "held"
    REJECTED = "rejected"
    FAILED = "failed"
    PAYMENT_REQUIRED = "payment_required"


class Reason(str, Enum):
    NO_CREDITS = "no_credits"
    OVER_BUDGET = "over_budget"
    ACCESS_DENIED = "access_denied"  # held or rejected
    CIRCUIT_OPEN = "circuit_open"
    BY_USER = "by_user"  # held
    RATE_LIMITED = "rate_limited"
    NO_PRICING_TIER = "no_pricing_tier"
    BLOCKED = "blocked"  # rejected (403)
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"  # failed
    NOT_FOUND = "not_found"
    AUTH = "auth"  # failed


class ReturnKind(str, Enum):
    REFERENCES = "references"
    SUMMARIES = "summaries"
    BOTH = "both"
    NOTHING = "nothing"


class InvoiceStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"
```

## Money and pricing

```python
class Money(Frozen):
    amount: Decimal = Decimal(0)
    currency: str = "USD"

    @classmethod
    def of(cls, amount: Decimal | float | str | int, currency: str = "USD") -> "Money": ...
    def __add__(self, other: "Money") -> "Money": ...  # raises ValidationError across currencies
    def __lt__(self, other: "Money") -> bool: ...
    def __str__(self) -> str: ...  # "0.35 USD"


class Bundle(Frozen):  # one purchasable top-up, from the payment policy
    id: str
    amount: Money  # what the user pays
    credits: Money | None = None  # what lands in the wallet, when the policy says


class Pricing(Frozen):  # read off a source's payment policy; nothing added
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
    def free(self) -> bool: ...
    def estimate(self, limit: int) -> Money: ...  # max cost for one query: price x (1 or limit)
```

## Sources

```python
class Policy(Frozen):  # Hub EndpointPublicResponse.policies[]
    type: PolicyType
    config: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0"
    enabled: bool = True
    description: str = ""


class Connection(Frozen):  # Hub EndpointPublicResponse.connect[]
    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class Source(Frozen):  # Hub EndpointPublicResponse; a Hub endpoint is a Source
    name: str
    slug: str
    type: SourceType
    owner_username: str
    description: str = ""
    version: str = "0.1.0"
    tags: tuple[str, ...] = ()
    stars_count: int = 0
    policies: tuple[Policy, ...] = ()
    connect: tuple[Connection, ...] = ()
    readme: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def path(self) -> str: ...  # "owner/slug"; the key used everywhere else
    @property
    def pricing(self) -> Pricing | None: ...  # None when no payment policy
    @property
    def free(self) -> bool: ...
    @property
    def space_url(self) -> str | None: ...  # from connect[]


class SourceList(Frozen):  # what hub.sources.list() returns
    items: tuple[Source, ...]
    total: int  # the Hub's count, before any local view

    def __iter__(self): ...
    def __len__(self) -> int: ...
    def __getitem__(self, key: int | str) -> Source: ...  # index, or "owner/slug"
    def matching(self, text: str) -> "SourceList": ...  # fuzzy over name, slug, description, tags
    def filter(
        self,
        *,
        type: SourceType | None = None,
        owner: str | None = None,
        free: bool | None = None,
        tag: str | None = None,
    ) -> "SourceList": ...
    def pick(self, *paths: str) -> "SourceList": ...
    def __add__(self, other: "SourceList") -> "SourceList": ...
    @property
    def paths(self) -> tuple[str, ...]: ...
```

## Session

```python
class Identity(Frozen):  # hub.me, after login
    username: str
    email: str
    auth: AuthMethod


class Budget(Frozen):  # hub.budget; set with hub.set_budget(x)
    limits: dict[str, Money] = {}  # one cap per currency; {}: no budget
    spent: dict[str, Money] = {}  # every charge, per currency, capped or not

    @property
    def remaining(self) -> dict[str, Money]: ...  # per capped currency
    def remaining_in(self, currency: str) -> Money | None: ...
    def allows(self, extra: Money) -> bool: ...  # True when its currency has no cap


class Timeout(Frozen):
    connect: float = 5.0
    read: float = 30.0
    total: float = 60.0
    lookup: float = 5.0  # read timeout of listing-time balance reads (2026-10-13)


class Retry(Frozen):  # network errors and 5xx only; never a 403 rate limit
    attempts: int = 3
    server_errors: int = 1  # retries a 5xx may use of `attempts` (2026-10-13)
    backoff: float = 0.5  # seconds, doubled per attempt, with jitter
    max_backoff: float = 8.0


class CircuitBreaker(Frozen):
    failures: int = 5  # consecutive failures per Space before opening
    cooldown: float = 30.0  # seconds


class Options(Frozen):  # one per AsyncHub; applies to the whole client
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    timeout: Timeout = Timeout()
    retry: Retry = Retry()
    http2: bool = False  # opt-in, extra syfthub-sdk[http2] (2026-10-13)
    circuit_breaker: CircuitBreaker = CircuitBreaker()
    concurrency: int = 8  # parallel Space calls per execute()
    max_items: int = 1000  # auto-pagination cap for list()
    user_agent: str | None = None
    http_client: Any = None  # injectable transport; tests pass MockTransport
```

## Wallets and payments

```python
class Wallet(BaseModel):  # not frozen: refresh() updates balance in place
    model_config = ConfigDict(extra="ignore")
    id: str  # config.wallet_id from the payment policy; identity and grouping key
    key: str  # "owner/rail/currency"; the readable label
    owner: str
    rail: Rail
    currency: str
    balance: Money | None = None  # None until refresh()
    refreshed_at: datetime | None = None
    sources: tuple[str, ...] = ()  # paths billed to this wallet
    bundles: tuple[Bundle, ...] = ()
    payment_url: str | None = None  # POST bundle -> invoice (published on the policy)
    credits_url: str | None = None  # GET balance
    invoices_url: str | None = None  # GET my invoices on this wallet
    raw: dict[str, Any] = Field(default_factory=dict)
    _hub: Any = PrivateAttr(default=None)

    async def refresh(self) -> "Wallet": ...  # GET credits_url; returns self
    async def top_up(self, bundle: str | Bundle) -> "Invoice": ...  # POST payment_url
    async def invoices(self) -> tuple["Invoice", ...]: ...  # GET invoices_url


class Invoice(Frozen):  # Space InvoiceResponse
    id: str
    wallet_key: str
    bundle: str
    amount: Money
    status: InvoiceStatus = InvoiceStatus.PENDING
    checkout_url: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    _hub: Any = PrivateAttr(default=None)

    async def refresh(
        self,
    ) -> "Invoice": ...  # new Invoice: GET invoices_url, match by id; balance as fallback
    async def wait_paid(
        self, *, timeout: float = 600, poll: float = 5
    ) -> "Invoice": ...  # raises PaymentTimeout
    @property
    def paid(self) -> bool: ...


class Charge(Frozen):  # one MPP 402 challenge
    source: Source
    amount: Money
    www_authenticate: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ChargeEntry(Frozen):  # Space policy_metadata.entries[] for a payment policy
    source: str
    policy_type: PolicyType | None = None
    status: str | None = None
    amount: Money | None = None
    wallet: str | None = None
    rail: Rail | None = None
    transaction_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class RateLimit(Frozen):  # from the Space's rate-limit policy entry or headers
    limit: str | None = None  # e.g. "100/hour"
    remaining: int | None = None
    reset_seconds: int | None = None
```

## Search: plan, pre-flight, actions

```python
class SearchPlan(Frozen):  # frozen; skip() returns a new plan
    query: str
    sources: tuple[str, ...]  # source paths, resolved at compose time
    limit: int = 5
    similarity_threshold: float = 0.5
    include_metadata: bool = True
    skips: tuple[str, ...] = ()  # the one decision
    max_sources: int = 10  # only when sources was None at compose
    version: str  # SDK version that made the dict
    created_at: datetime
    _hub: Any = PrivateAttr(default=None)
    _pre: Any = PrivateAttr(default=None)  # last Preflight, if any

    def skip(self, *paths: str) -> "SearchPlan": ...
    async def preflight(self) -> "Preflight": ...
    async def execute(
        self, *, strict: bool = False
    ) -> "Results": ...  # strict: raise ActionRequired if any row is held
    @property
    def pre(self) -> "Preflight | None": ...
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(
        cls, hub: "AsyncHub", d: dict[str, Any]
    ) -> "SearchPlan": ...  # raises StaleSnapshot


class PlanRow(Frozen):
    source: Source
    verdict: Verdict
    send: bool  # True for READY, WILL_ASK_TO_PAY
    estimate: Money
    wallet: Wallet | None = None  # the prepaid wallet this row bills
    reason: Reason | None = None  # why it is held
    note: str | None = None  # one line for a log or a UI


class Action(Frozen):  # base; one per cause, not per source
    kind: ActionKind
    affects: tuple[Source, ...]
    steps: tuple[str, ...]  # plain-English steps to resolve it


class TopUp(Action):
    kind: ActionKind = ActionKind.TOP_UP
    wallet: Wallet
    shortfall: Money  # committed estimate on this wallet minus balance
    bundles: tuple[Bundle, ...]  # what the wallet sells; prepaid rails sell fixed bundles only
    suggested: Bundle | None = None  # smallest bundle that covers shortfall; None if none does
    _hub: Any = PrivateAttr(default=None)

    async def top_up(self, bundle: str | Bundle | None = None) -> Invoice: ...

    # same route and return as wallet.top_up; bundle omitted -> suggested; ValidationError if that is None.
    # Creates a PENDING invoice with checkout_url. Nothing is charged until the user pays there.


class OverBudget(Action):
    kind: ActionKind = ActionKind.OVER_BUDGET
    estimate: Money  # total if these rows were sent
    budget: Budget


class AccessDenied(Action):
    kind: ActionKind = ActionKind.ACCESS_DENIED
    rule: str | None = None  # the policy entry that excluded the caller


class CircuitOpen(Action):
    kind: ActionKind = ActionKind.CIRCUIT_OPEN
    reopens_at: datetime


class Preflight(Frozen):  # snapshot; plan.preflight() again for a fresh one
    rows: tuple[PlanRow, ...]
    actions: tuple[Action, ...]
    estimate: dict[str, Money]  # per currency, summed per wallet
    budget: Budget
    checked_at: datetime

    @property
    def ready(self) -> bool: ...  # no held rows
    @property
    def sending(self) -> tuple[PlanRow, ...]: ...
    @property
    def held(self) -> tuple[PlanRow, ...]: ...
    def __iter__(self): ...  # over rows
    def __getitem__(self, path: str) -> PlanRow: ...
```

## Results

```python
class Document(Frozen):  # Space references.documents[]
    id: str = Field(alias="document_id")
    content: str
    score: float | None = Field(
        default=None, alias="similarity_score"
    )  # None for a model's summary
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str  # source path; added by the SDK

    @property
    def title(self) -> str | None: ...  # metadata.get("title")


class SourceResult(Frozen):  # one per source in the plan
    source: Source
    outcome: Outcome
    reason: Reason | None = None
    status_code: int = 0  # 0 when nothing was sent
    documents: tuple[Document, ...] = ()  # a model's summary becomes one Document with score=None
    summary: str | None = None  # verbatim, for model sources
    cost: Money | None = None  # Space-reported cost of this call
    charges: tuple[ChargeEntry, ...] = ()
    paid_from: str | None = None  # wallet key, when a prepaid rail paid
    rail: Rail | None = None
    charge: Charge | None = None  # on PAYMENT_REQUIRED
    topup: TopUp | None = None  # on HELD no_credits
    rate_limit: RateLimit | None = None  # on REJECTED rate_limited; the app decides when to retry
    elapsed_ms: int = 0
    attempts: int = 0
    error: str | None = None  # message from the 403 envelope or the transport
    request: dict[str, Any] = Field(default_factory=dict)  # body sent, headers redacted
    raw: dict[str, Any] = Field(default_factory=dict)  # body received, verbatim

    @property
    def ok(self) -> bool: ...  # outcome is RETURNED
    @property
    def retryable(self) -> bool: ...


class Results(Frozen):  # immutable; views and actions return a new Results
    rows: tuple[SourceResult, ...]
    plan: SearchPlan  # the plan behind these rows, skips included
    actions: tuple[Action, ...]  # still open after execute
    executed_at: datetime
    _hub: Any = PrivateAttr(default=None)

    def __iter__(self): ...
    def __getitem__(self, path: str) -> SourceResult: ...
    @property
    def documents(
        self,
    ) -> tuple[tuple[str, Document], ...]: ...  # scored chunks by score, then unscored summaries
    @property
    def chunks(self) -> tuple[tuple[str, Document], ...]: ...  # scored only
    @property
    def answers(self) -> dict[str, str]: ...  # path -> summary, model sources
    @property
    def kind(self) -> ReturnKind: ...
    @property
    def ok(self) -> tuple[SourceResult, ...]: ...
    @property
    def failed(self) -> tuple[SourceResult, ...]: ...  # REJECTED and FAILED
    @property
    def held(self) -> tuple[SourceResult, ...]: ...
    @property
    def cost(self) -> dict[str, Money]: ...  # per currency, never converted
    @property
    def raw(self) -> dict[str, dict[str, Any]]: ...
    def only(self, *paths: str) -> "Results": ...
    def drop(self, *paths: str) -> "Results": ...
    def top(self, k: int) -> "Results": ...  # trims scored chunks to k; summaries always kept
    def __add__(self, other: "Results") -> "Results": ...
    async def retry(
        self,
    ) -> "Results": ...  # re-send retryable rows; same as self.plan.execute() for them
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, hub: "AsyncHub", d: dict[str, Any]) -> "Results": ...
```

## Not in the first cut

`Chat`, `Reply`, `Replies`, `Context`, `Message`, `Include`, `Via`, `Answer`, `FilterSplit` and the `filterable` field on `Source`. They stay in the mock and come back with chat, filters and the Aggregator.
