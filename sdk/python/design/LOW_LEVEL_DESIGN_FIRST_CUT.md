# SyftHub Python SDK v2, first cut: low-level design

Status: scoped and reviewed 2026-10-08. This document is the build spec for the **first cut**: a headless, search-only
SDK over what Syft Space and SyftHub serve today. It supersedes the full v2 design (`LOW_LEVEL_DESIGN.md` on
branch `feat/sdk-v2-ux-mock`, with the UX mock and `DESIGN_LOG.md`) for everything that ships first; that document
stays as the full v2 design (chat, filters, Aggregator, notebook skin) and records what the later cuts add. The scoping conversation and its research live in the shared doc "SDK v2 First Cut Scope"
(tabs *Scope* and *Schemas*); this file is the in-repo copy of those two tabs, kept in sync by hand.

Decisions that shape this cut, all taken on 2026-10-08: **sources, not endpoints**, as the SDK's noun; **one decision
verb** (`skip`) and **one override** (the session budget); **no event-driven client**; resume by **re-running
pre-flight** from the query and the skips, with `to_dict()` as an optional convenience; **MPP is not a priority**;
**pydantic v2 models for every object**, frozen except `Wallet`.

---

## 1. Scope

Everything in the first cut maps onto a route Syft Space or SyftHub serves today. The one exception is the Action
model in pre-flight, which is client logic over Hub metadata and wallet balances.

| Area | In the first cut | Deferred |
|---|---|---|
| Login | `login(username, password)`, `login(token)`, `SYFTHUB_TOKEN`, `hub.me` | Google login (browser flow does not suit headless) |
| Sources | `list(owner=, type=, free=, tag=)`, `get`, fuzzy `matching`, `filter(...)` on a held list; `source.policies`, `source.pricing` | Collectives as a source alias |
| Wallets | `list`, `for_source`, `balance`, `refresh`, `top_up(bundle)` → `Invoice` | Managed-wallet admin |
| Search | plain query, `sources=[...]`, `limit`, `similarity_threshold`, `include_metadata`; model sources alongside document sources | `plan.filter(**metadata)`: Spaces do not support it yet |
| Pre-flight | iterable `Preflight` with `actions`, per-source rows, estimate per wallet, session budget; `skip` as the one decision; `execute(strict=True)`; `to_dict`/`from_dict` for resuming | Health probes; any use of the Hub's `health_status` |
| Execute | one POST per Space in parallel, retries, per-Space circuit breaker, `Results` | Streaming |
| Payments | prepaid invoice with `checkout_url`, `status`, `refresh`, `wait_paid`; MPP 402 paid inside `execute()` while within budget, else a row with an action | Paying an MPP charge before the Space asks (no route) |
| Errors | exception hierarchy for faults that stop the call; per-source failures as rows | |
| Delivery | async API plus a sync twin (a runtime wrapper over it), `logging`, `to_dict`/`from_dict` for queues and caches | `syfthub.notebook` HTML and widgets |
| Chat | | `hub.chat`, `results.chat`, `results.ask` |
| Aggregator | | both forms; needs the new route |

**Vocabulary.** A Hub endpoint is a *source* in the SDK: some answer with document chunks, some with a model's reply,
and search treats them alike. The Hub's wire names (`EndpointPublicResponse`, `data_source`, `model`,
`model_data_source`) are unchanged under `raw` and in enum values.

**Model sources.** When a source of type `MODEL` is in `sources`, its `summary` comes back as one `Document` on that
row with `score=None`, because a reply is not a similarity match. `results.documents` lists scored chunks by score and
then the unscored summaries after them; `top(k)` trims the scored chunks only and always keeps the summaries.
`results.chunks` is the scored subset, `results.answers` the summaries alone.

---

## 2. Principles

The ten principles of the full v2 design (`LOW_LEVEL_DESIGN.md` section 1 on `feat/sdk-v2-ux-mock`) hold. The first cut adds three:

11. **One way to do each thing.** No plan-wide flag that duplicates a per-row verb, no second verb that a knob already
    covers, no path wildcard that a filter already covers.
12. **Headless first.** Nothing in the core needs a live process beyond the call, a terminal, or a browser. Every pause
    is a value the app can store; every resume is a call the app can make from another process.
13. **The SDK never offers to do what the Space will refuse.** A row held for `no_credits`, `access_denied` or
    `circuit_open` has no override; a row held for `over_budget` is released by raising the budget.

---

## 3. Package layout

```
syfthub/
  __init__.py          AsyncHub, Hub, models, errors, __version__
  hub.py               AsyncHub: session, namespaces, search(), budget
  auth.py              AuthNamespace, Identity
  sources.py           SourcesNamespace, Source, SourceList
  wallets.py           WalletsNamespace, Wallet, Invoice
  search.py            SearchPlan, Preflight, PlanRow, Action and subclasses
  results.py           Results, SourceResult, Document, views
  (package level, 2026-10-14 split)
  search.py            Searcher: the runner (facts, send host by host, classify, bind)
  preflight.py         the pure rules over Facts: plan_preflight, pick_sources, paths_of
  actions.py           one builder per Action; preflight_actions and actions_after
  classify.py          one Space response -> one SourceResult (per-status handlers over a parsed _Reply)
  models/              pydantic v2 models and enums (section 6)
  errors.py            exception hierarchy (section 7)
  _transport/          httpx client, Retry, CircuitBreaker, TokenCache, logging, user agent
  _api/                hand-written route clients: hub, space; detail.py parses the FastAPI error body for every caller   (async)
  _sync.py             Hub and friends: a runtime wrapper over the async package (private loop on a background thread)
  _sync.pyi, sync.py   GENERATED by scripts/gen_sync_stub.py: the sync faces for type checkers, and the public names to annotate with
  testing/             FakeHub, FakeSpace, MockTransport                extra: syfthub[testing]
```

Not in this cut: `chat.py`, `aggregator.py`, `notebook/`, `adapters/`.

---

## 4. Hello world

```python
import syfthub

async with syfthub.AsyncHub() as hub:  # SYFTHUB_URL, SYFTHUB_TOKEN from the environment
    results = await hub.search("adverse events in phase 3").execute()
    for path, doc in results.documents[:3]:
        print(path, doc.score, doc.content[:80])
```

Two concepts before the first call: a token and a query. Without `sources`, the search runs over free document
every free document source in the catalogue the caller may use (the listing, not the Hub's keyword search; decided 2026-10-15), capped only when `max_sources` is set (default None). Paid sources are never
included implicitly. The sync twin is the same with `syfthub.Hub()` and no `await`.

---

## 5. Public API by functionality

### 5.1 Session and authentication

```python
hub = syfthub.AsyncHub(url=None, *, token=None, budget=None, options=None)
await hub.login(username=, password=)   |   await hub.login(token=)        # alias of hub.auth.*
hub.me -> Identity | None ; await hub.auth.whoami() -> Identity
hub.budget -> Budget ; hub.set_budget(2.00) | hub.set_budget({"USD": 2.00, "IDR": 50000}) ; hub.spent -> dict[str, Money]
```

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| Construct | `AsyncHub(url=None, *, token=None, budget=None, options=None)` | `AsyncHub` | `url` from `SYFTHUB_URL`, `token` from `SYFTHUB_TOKEN`. No network. |
| Context | `async with hub:` | | Closes the HTTP client. |
| Password login | `await hub.login(username=, password=)` | `Identity` | |
| Token login | `await hub.login(token=)` | `Identity` | Validates once. |
| Who am I | `hub.me`, `await hub.auth.whoami()` | `Identity` | |
| Budget | `hub.set_budget(x)`, `hub.budget`, `hub.spent` | `Budget`, `Money` | Per session, across searches; one cap per currency, no budget until set, a currency with no cap is not budgeted. The one override for `over_budget` rows. |

### 5.2 Sources  (`hub.sources`)

```python
sources = await hub.sources.list(
    owner=None, type=None, free=None, tag=None, matching=None
)  # SourceList, all pages
bobs = await hub.sources.list(owner="bob")
picks = sources.matching("clinical trials").filter(type="data_source")  # local views
src = await hub.sources.get("erin/trials")  # Source
src.policies
src.pricing
src.path
src.free
src.reachable
```

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| List | `await hub.sources.list(...)` | `SourceList` | Server filters where the Hub supports them, local otherwise; pages followed up to `Options.max_items`. |
| One source | `await hub.sources.get("owner/slug")` | `Source` | Raises `SourceNotFound`. |
| Semantic search of the listing | `await hub.sources.search(text)` | `SourceList` | Hub `POST /endpoints/search`. |
| Narrow a held list | `.matching(text)`, `.filter(type=, owner=, free=, tag=)`, `.pick(*paths)`, `a + b` | `SourceList` | Views; new list each time. |
| Policies and price | `source.policies`, `source.pricing` | `tuple[Policy]`, `Pricing \| None` | Read off the payment policy; nothing added. |

Listing by owner is the `owner` filter, on the Hub call or on a held list. There is no `"bob/*"` path wildcard.

### 5.3 Wallets and payment  (`hub.wallets`)

```python
wallets = await hub.wallets.list()  # [Wallet]: owner, rail, currency, balance, sources
w = await hub.wallets.for_source("erin/trials")
await w.refresh()  # one balance call; w.balance, w.refreshed_at
invoice = await w.top_up("starter")  # Invoice: checkout_url, amount, status
await invoice.refresh()
await invoice.wait_paid(timeout=600, poll=5)
await hub.wallets.invoice(wallet_key, invoice_id)  # re-read by handle from another process
```

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| List | `await hub.wallets.list()` | `tuple[Wallet]` | Built from the source listing: payment policies grouped by wallet id (else `credits_url`). The three URLs a policy publishes, `payment_url`, `credits_url`, `invoices_url`, are followed as given; the SDK never builds a wallet URL, which is why station-hosted wallets need no special case. |
| For a source | `await hub.wallets.for_source(path)` | `Wallet \| None` | None for free and MPP sources. |
| Balance | `await wallet.refresh()` | `Wallet` | Pre-flight always refreshes the wallets it needs; `balance` carries `refreshed_at`. |
| Top up | `await wallet.top_up(bundle)` | `Invoice` | Space invoice route. |
| Invoice status | `await invoice.refresh()` | `Invoice` | `GET invoices_url` (my invoices), match by id; not listed means unchanged, never paid on other evidence (2026-10-14; the balance fallback marked unpaid invoices PAID). There is no invoice-by-id route. |
| Wait | `await invoice.wait_paid(timeout=600, poll=5)` | `Invoice` | Headless convenience; raises `PaymentTimeout`. |
| Re-read | `await hub.wallets.invoice(wallet_key, id)` | `Invoice` | For a pause that spans processes. |

Invoice states and what the app does:

| Status | Meaning | App should |
|---|---|---|
| `PENDING` | invoice created, checkout not completed | show `checkout_url`, store `invoice.id`, poll or `wait_paid` |
| `PAID` | provider webhook landed, balance rose | `plan.execute()` again |
| `EXPIRED` | checkout link lapsed | `top_up` again |
| `FAILED` | provider declined | surface to the user; do not retry automatically |

### 5.4 Search: compose, pre-flight, decide, execute

```python
plan = hub.search(query, sources=None, *, limit=5, similarity_threshold=0.5,
                  include_metadata=True, max_sources=10)          # sync, free, nothing sent
pre  = await plan.preflight()                                     # Preflight: rows, actions, estimate; nothing sent
plan = plan.skip("carol/papers")                                  # the one decision; new plan
results = await plan.execute()                                    # pre-flight again, send allowed rows, hold the rest
results = await plan.execute(strict=True)                         # or raise ActionRequired before sending anything
```

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| Compose | `hub.search(query, sources=, ...)` | `SearchPlan` | `sources`: paths, `Source` objects or a `SourceList`; resolved to paths at compose. |
| Pre-flight | `await plan.preflight()` | `Preflight` | One Hub read per unknown source, one balance call per prepaid wallet. Idempotent. |
| Decide | `plan.skip(*paths)` | `SearchPlan` | Rows become `HELD by_user`. The only decision verb. |
| Execute | `await plan.execute(strict=False)` | `Results` | Always runs pre-flight first. `strict=True` raises `ActionRequired` if any row is held. |
| Snapshot | `plan.to_dict()`, `SearchPlan.from_dict(hub, d)` | `dict`, `SearchPlan` | Optional; see 5.6. |

`similarity_threshold`, `limit` and `include_metadata` travel to the Space in the query body exactly as the current SDK
sends them. Nothing else is added to the request.

**Pre-flight as data.** `Preflight` is iterable over `PlanRow` (source, verdict, estimate, wallet, reason, note) and
carries `actions`, one per cause, not per source: two sources billed to the same wallet produce one `TopUp` whose
`shortfall` covers both.

| Verdict | Sent? | Meaning |
|---|---|---|
| `READY` | yes | |
| `WILL_ASK_TO_PAY` | yes | MPP source; only the Space issues the challenge |
| `NEEDS_CREDITS` | held | prepaid wallet below the committed estimate |
| `OVER_BUDGET` | held | the estimate would cross the cap for its currency; one `OverBudget` per currency |
| `ACCESS_DENIED` | held | allow or deny list excludes the caller |
| `CIRCUIT_OPEN` | held | the Space's breaker is open |
| `SKIPPED` | held | `plan.skip` |

| Action | Fields | Resolve by |
|---|---|---|
| `TopUp` | `wallet`, `shortfall`, `bundles`, `suggested`, `affects` | `await action.top_up()` (the suggested bundle) or `top_up(bundle)`, pay at `checkout_url`, execute again |
| `OverBudget` | `estimate`, `budget`, `affects` | `hub.set_budget(x)` and execute again; or `plan.skip(*paths)` |
| `AccessDenied` | `affects`, `rule` | `plan.skip(*paths)` |
| `CircuitOpen` | `affects`, `reopens_at` | wait, or `plan.skip(*paths)` |

### 5.5 Results: rows, views, re-run

```python
results["erin/trials"] -> SourceResult        # outcome, reason, documents, summary, cost, charges, raw ...
results.documents -> [(path, Document)]      # by score, across sources
results.ok / results.failed / results.held ; results.actions ; results.cost ; results.raw
results.only(*paths) / .drop(*paths) / .top(k) / a + b      # views: new Results
results.plan -> SearchPlan                                  # the plan behind the rows, skips included
await results.retry() -> Results                            # re-send retryable rows
results.to_dict() ; Results.from_dict(hub, d)
```

| Outcome | Who stopped it | `reason` values | Retryable |
|---|---|---|---|
| `RETURNED` | nobody | | |
| `HELD` | pre-flight, nothing spent | `no_credits`, `over_budget`, `access_denied`, `circuit_open`, `by_user` | after the action |
| `REJECTED` | the Space's policy, 403 | `no_credits`, `rate_limited`, `access_denied`, `no_pricing_tier`, `blocked` | `rate_limited`, `no_credits` |
| `FAILED` | transport or server, after retries | `unreachable`, `timeout`, `server_error`, `not_found`, `auth` | all but `not_found` |
| `PAYMENT_REQUIRED` | an MPP Space, 402, over budget | | raise the budget, execute again |

Every `SourceResult` keeps `status_code`, `error`, `attempts`, `elapsed_ms`, `paid_from`, `rail` and the verbatim
`raw` body, so a row is its own billing and served-by record. A rate limit is never waited out inside the call: the
Space's 403 comes back as `REJECTED rate_limited` with `rate_limit.reset_seconds` on the row, retryable, and the app
decides when to call `results.retry()`.

### 5.6 Decisions and resuming

Actions fall into two groups.

- **Facts the SDK observes.** Paying an invoice, adding credits, a Space coming back. The app tells the SDK nothing;
  the next `execute()` runs pre-flight again, reads the balances, and the row passes. There is no "I paid" call.
- **Decisions the SDK must apply.** There is one: `plan.skip(*paths)`. There is no force: a row held for
  `no_credits`, `access_denied` or `circuit_open` would only be refused by the Space if sent, so the SDK never offers to
  send it; a row held for `over_budget` is released by raising the budget.

A plan is a pure function of its query, sources, options and skips. Everything else, prices, access and
balances, is read fresh at pre-flight. So the SDK holds no state between a pause and a resume, and the app has two
equivalent ways back:

```python
# process A: hand control back to the app's user
pre = await plan.preflight()
if pre.actions:
    ...  # show pre.actions; each names the paths it affects
    saved = plan.to_dict()  # optional: query, sources, options, skips, version, created_at

# process B, either way: apply what the user chose, run again
plan = hub.search(query, sources=S).skip("carol/papers")
plan = syfthub.SearchPlan.from_dict(hub, saved).skip("carol/papers")
results = await plan.execute()  # pre-flight re-runs: paid wallets pass, skips hold
```

The app owns persistence: where the dict goes, what key it sits under, when a saved plan is abandoned. The SDK stamps
`version` and `created_at` so a stale snapshot is re-priced rather than trusted, and `from_dict` raises `StaleSnapshot`
on an incompatible version. The dict is authority to spend money: write it server-side, never round-trip it through a
browser. `results.plan` returns the plan behind a `Results`, carrying its skips, so retrying after a restart is the same
call as executing after one.

**Why not an event-driven client.** A callback needs a live process and the app's user may take days; a pending
action is a one-shot outcome, which belongs in a value, not a listener; emitters bring their own error and lifetime
semantics; and no server-side SDK surveyed (Stripe, Plaid, Auth0, Okta, GitHub, OpenRouter) invokes user code on state
change. The full comparison is in `reports/Resumable user actions in SDKs.md` at the repo root (untracked).

### 5.7 MPP (experimental, not a priority)

No charge exists before the Space answers 402, so pre-flight can only flag `WILL_ASK_TO_PAY`. During `execute()` the
SDK pays each 402 challenge through the Hub wallet route and re-sends with `X-Payment`, as long as the charge fits the
remaining cap for its currency; the row comes back `RETURNED` with `charge` filled in and `hub.spent` updated. A charge
that would cross the cap comes back `PAYMENT_REQUIRED` with a `Charge` and an `OverBudget` action; the app raises the
budget and executes again, or skips the source. With no budget set, MPP charges are paid as the Spaces ask. The Hub
wallet itself is topped up outside the SDK; if it cannot cover a challenge, the row is `PAYMENT_REQUIRED` with `error`
from the Hub and steps that say to top up in the SyftHub UI. The pay call carries a client-generated `Idempotency-Key`,
stored in the snapshot, so a crash between paying and re-sending cannot charge twice once the Hub honours the header
(a key-to-response table with a 24 h expiry, as a follow-up).

---

## 6. Models and enums

Every object, as pydantic v2 models. Conventions:

```python
class Frozen(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="ignore"
    )  # unknown Hub/Space fields are kept in .raw, never rejected
```

- Enums are `str` enums; they compare and serialise as their value.
- Collections are tuples on frozen models.
- Every model has `to_dict()` and `from_dict()`; the dict is plain JSON (Decimals as strings, datetimes ISO 8601).
- `raw` holds the verbatim server body where there is one. Typed fields are a view over it.
- Objects that call the network hold the hub in a `PrivateAttr`, never in a field, so `to_dict()` is always safe to
  store.

### 6.1 Enums

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

### 6.2 Money and pricing

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

### 6.3 Sources

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

### 6.4 Session

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

### 6.5 Wallets and payments

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
    ) -> "Invoice": ...  # new Invoice: GET invoices_url, match by id; not listed = unchanged
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

### 6.6 Search: plan, pre-flight, actions

```python
class SearchPlan(Frozen):  # frozen; skip() returns a new plan
    query: str
    sources: tuple[str, ...]  # source paths, resolved at compose time
    limit: int = 5
    similarity_threshold: float = 0.5
    include_metadata: bool = True
    skips: tuple[str, ...] = ()  # the one decision
    max_sources: int | None = None  # a ceiling on the automatic pick only; never caps named sources
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

### 6.7 Results

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

Not in the first cut: `Chat`, `Reply`, `Replies`, `Context`, `Message`, `Include`, `Via`, `Answer`, `FilterSplit`,
and the `filterable` field on `Source`.

---

## 7. Errors

The rule: a fault that stops the whole call raises; a fault that stops one source becomes a row. An app catches
`syfthub.SyftHubError` once and reads `results.failed` for the rest.

```
SyftHubError
├─ ConfigurationError        bad url, no token and no credentials, invalid Options
├─ ValidationError           limit < 1, threshold outside 0..1, unknown source path format
├─ AuthError                 login failed, token expired and re-mint failed
├─ HubUnreachable            the Hub itself cannot be reached after retries
├─ SourceNotFound            hub.sources.get on a path the Hub does not know
├─ PaymentError
│  ├─ PaymentTimeout         invoice.wait_paid ran out
│  └─ PaymentFailed          Hub wallet pay or invoice route returned an error
├─ StaleSnapshot             SearchPlan.from_dict on a dict from an incompatible SDK version
└─ ActionRequired            execute(strict=True) with open actions; carries .actions
```

There is no `BudgetExceeded`: budget overruns are rows with an `OverBudget` action. Logging goes to
`logging.getLogger("syfthub")`: one INFO line per `execute()` with counts and cost, DEBUG per request with
`Authorization`, `X-Payment` and `WWW-Authenticate` redacted.

---

## 8. Transport and resilience  (`syfthub._transport`)

`Options` is in section 6.4. Behaviour carries over from the full v2 design (`LOW_LEVEL_DESIGN.md` section 7 on `feat/sdk-v2-ux-mock`) unchanged:

| Concern | Behaviour |
|---|---|
| Connections | One `httpx.AsyncClient` with keep-alive; pool limits scale with `concurrency`. |
| Retries | Exponential backoff with full jitter on network errors and 500/502/503/504. Never on 4xx: a 403 rate limit is a `REJECTED rate_limited` row with `reset_seconds`, and the app decides. A search POST is treated as idempotent because Spaces bill on success. |
| Circuit breaker | Per Space host. After `failures` consecutive failures the host is open for `cooldown`; rows become `HELD circuit_open` with a `CircuitOpen` action and no request; one probe after cooldown. |
| Tokens | `TokenCache` keyed by (owner, resource). Refresh at 80% of lifetime. One re-mint on 401. `satellite_id` sent where the multi-host contract requires it. |
| Pagination | `list()` follows pages until `max_items`. |
| Metadata | `User-Agent` on every request. Rate-limit data from headers or `details.reset_seconds` surfaced on `SourceResult.rate_limit`. `Idempotency-Key` on every Hub wallet-pay call. |
| Concurrency | `asyncio.Semaphore(concurrency)` around Space calls. |
| Budget | Pre-flight is the only reader of money and always runs before a send. The Space's own 402 or 403 remains authoritative and surfaces as a row; the client's `committed` accounting per wallet is a convenience. |

---

## 9. Sync twin, serialisation, build

- The async package is the source. `syfthub.Hub` and the sync faces of every object are a runtime wrapper: each call
  runs the coroutine on a private event loop in a background thread, so the wrapper also works inside Jupyter where a
  loop is already running. Tests run against both faces. Generated `.pyi` stubs for IDE typing of the sync face can
  come later.
- `to_dict()` / `from_dict()` on every model; `Money` as `{"amount": "1.25", "currency": "USD"}`; enums as values;
  datetimes ISO 8601. `SearchPlan`, `Invoice` and `Results` are the three an app stores.
- Low-level clients generated from both OpenAPI specs into `syfthub._api`; contract tests in both servers' CI;
  `MIN_HUB_VERSION` and `MIN_SPACE_VERSION` with one warning per session. mypy strict, `py.typed`. Semver, two-minor
  deprecation window, `CHANGELOG.md`. PyPI `syfthub`, extra `testing`. Python 3.11+.
- Docs: getting started, how-to for the headless pause and resume, reference generated from docstrings with a runnable
  example per member, executed in CI.

---

## 10. Reference example: a chat app on OpenAI with SyftHub as retrieval

```python
import os
from openai import AsyncOpenAI
import syfthub

openai = AsyncOpenAI()
hub = syfthub.AsyncHub(
    token=os.environ["SYFTHUB_TOKEN"], budget=1.00
)  # USD per process lifetime; caps MPP charges too

SOURCES = ["erin/trials", "carol/papers", "kim/ledger"]

SYSTEM = (
    "Answer from the numbered context only. Cite passages as [n]. "
    "If the context does not answer, say so."
)


async def retrieve(plan: syfthub.SearchPlan) -> syfthub.Results | syfthub.TopUp:
    pre = await plan.preflight()
    for action in pre.actions:
        match action:
            case syfthub.TopUp():
                return action  # needs the user; see answer() and resume()
            case syfthub.OverBudget() | syfthub.AccessDenied() | syfthub.CircuitOpen():
                plan = plan.skip(*action.affects)  # drop the source, keep going
    return await plan.execute()  # MPP charges within budget are paid on the way


async def answer(question: str, job_id: str) -> dict:
    plan = hub.search(question, sources=SOURCES, limit=5, similarity_threshold=0.6)
    outcome = await retrieve(plan)
    if isinstance(outcome, syfthub.TopUp):
        invoice = (
            await outcome.top_up()
        )  # the suggested bundle; PENDING invoice, nothing charged yet
        store.save(
            job_id, {"plan": plan.to_dict(), "invoice": invoice.to_dict()}
        )  # the app's store, the app's key
        return {"payment_required": {"url": invoice.checkout_url, "amount": str(invoice.amount)}}
    return await compose(question, outcome)


async def resume(question: str, job_id: str) -> dict:
    saved = store.load(job_id)
    invoice = syfthub.Invoice.from_dict(hub, saved["invoice"])
    await invoice.refresh()  # or trust the provider webhook that called this route
    if invoice.status != syfthub.InvoiceStatus.PAID:
        return {"payment_required": {"url": invoice.checkout_url, "status": invoice.status}}
    plan = syfthub.SearchPlan.from_dict(hub, saved["plan"])
    outcome = await retrieve(plan)  # pre-flight again: the paid wallet now passes
    return await compose(question, outcome)


async def compose(question: str, results: syfthub.Results) -> dict:
    context = "\n\n".join(
        f"[{i}] ({path}) {doc.content}" for i, (path, doc) in enumerate(results.documents, 1)
    )
    completion = await openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return {
        "answer": completion.choices[0].message.content,
        "sources": [
            {"path": path, "title": doc.title, "score": doc.score}
            for path, doc in results.documents
        ],
        "cost": {cur: str(m) for cur, m in results.cost.items()},
        "unavailable": [{"path": r.source.path, "reason": r.reason} for r in results.failed],
    }
```

`store` and `job_id` are the app's own. The SDK hands over plain dicts and takes them back; it never decides where
they live.

---

## 11. Decisions taken on 2026-10-08, and what is still open

Taken:

1. First cut is headless and search-only; chat, metadata filters, Aggregator and the notebook skin are deferred.
2. `sources` is the SDK's noun. `hub.sources`, `Source`, `SourceList`, `SourceType.DOCUMENTS / MODEL / BOTH` with the
   Hub's values; `for_source`, `Wallet.sources`, `SourceNotFound`. The doc says once that a Hub endpoint is a source.
3. Model sources are accepted in `sources`; a summary becomes one `Document`.
4. Pre-flight returns data: iterable rows plus one `Action` per cause.
5. `skip` is the only decision verb. No `force`, no `approve`, no `ignore_budget` flag, no `without`.
6. The session budget is the only override, and the only knob for MPP. No `auto_approve` ceiling. It is one cap per
   currency (`budget=1.00` caps USD; a mapping caps several); money is never converted, and a currency with no cap is
   not budgeted. Decided 2026-10-12.
7. `execute()` always re-runs pre-flight, sends allowed rows and holds the rest; `execute(strict=True)` raises
   `ActionRequired` before sending anything.
8. No event-driven client. Resume is rebuild-from-query or `from_dict`; the SDK and the Hub hold no pause state.
9. The app owns persistence and the key. `to_dict()` is a convenience; `version` and `created_at` are stamped.
10. MPP is in but not a priority; paid inside `execute()` within budget, else a `PAYMENT_REQUIRED` row.
11. `BudgetExceeded` dropped; `StaleSnapshot` added.
12. Every object is a pydantic v2 model, frozen except `Wallet`; `Options` is pydantic too.
13. Listing by owner is the `owner` filter; no path wildcard.
14. One verb to create an invoice, `top_up(bundle)`, on the wallet and on the `TopUp` action; `buy`, `buy_enough`
    and `plan.top_up` are gone. The action carries `suggested`, the smallest bundle covering the shortfall, as data.
15. Wallet calls follow the three URLs the policy publishes (`payment_url`, `credits_url`, `invoices_url`); the SDK
    never builds a wallet URL. `Wallet.id` is the wallet id; `key` is the readable label.

16. MPP with no session budget pays every challenge as asked. The Hub wallet is topped up outside the SDK; an empty one
    surfaces as a `PAYMENT_REQUIRED` row.
17. The SDK sends a client-generated `Idempotency-Key` on the Hub wallet-pay call from day one and stores it in the
    snapshot; the Hub honours it as a follow-up.
18. A model's summary is a `Document` with `score=None`; scored chunks first, summaries after; `top(k)` trims chunks
    only. `results.chunks` and `results.answers` are the two subsets.
19. The sync twin is a runtime wrapper over the async client, not a generated package. Its *types* are generated (decision 25).
20. Rate limits are the app's call: no in-call wait, `REJECTED rate_limited` with `reset_seconds`, retryable.
    `Retry.rate_limit_wait` is gone.
21. The policy config carries `wallet_id`; `Wallet.id` reads it and wallets group by it. Invoice status is read by
    listing `invoices_url` and matching by id (no invoice-by-id route exists).
22. Reads are never stale behind a flag (2026-10-12): `sources.list/get/search` and `wallets.list/for_source` read now;
    `wallets.list` reads balances once per wallet with no retries and leaves `balance=None` for a host that does not
    answer. The budget is one cap per currency; no budget until set.
23. No health flag in the SDK (2026-10-13; a 2026-10-12 decision to filter and hold on it, then a same-day
    informational variant, were both dropped). The Hub's `health_status` is the Space's own dataset/model self-check
    reported every 30 s; the Hub's monitor already deactivates (delists) an endpoint whose reports stop or fail for
    three cycles, and the flag says nothing about whether a query will succeed, so surfacing it misinforms. The SDK
    lists what the Hub lists and leaves `health_*` in `Source.raw`. The Space has no per-endpoint health route the SDK
    could probe (its dataset/model health routes are keyed by internal names the Hub does not publish). A prepaid wallet
    host that does not answer the pre-flight balance read holds its rows as `UNREACHABLE` with the error in the note;
    those reads make one attempt.
24. A connection failure (timeout, refused, DNS) opens the host's circuit at once; 5xx counts toward the threshold.
    A row held for `circuit_open` is `retryable`, so `results.retry()` after the cooldown re-sends it.
25. The sync twin's types are generated, not hand-written (2026-10-13; user: "type hints aren't available in case of
    sync system"). Python's type system cannot express "this class with every coroutine method made blocking", and
    the ecosystem answer is committed codegen (unasync for httpcore/psycopg/pymongo, Playwright's generated sync
    facade, Stainless for openai/anthropic). We keep the runtime proxy and generate only the static half:
    `scripts/gen_sync_stub.py` walks the classes reachable from `AsyncHub`, and for each one that has a coroutine
    method or carries an object that has one, emits into `_sync.pyi` a subclass of the real class redeclaring the
    coroutine methods as plain calls and the fields/properties that carry faces; `Hub` is declared in full. Faces
    subclass the real classes so `isinstance`/`match` narrow the same way statically as they do at runtime (the
    `__class__` trick); the cost is that a checker will not catch a sync object passed where an async one is awaited.
    `syfthub.sync` exposes the names for annotations (real classes at runtime, faces under TYPE_CHECKING). A unit
    test regenerates and diffs, and runs mypy over a probe to pin the revealed types. A Rust core would not remove
    the duplication: PyO3 exposes sync and async as separate functions and needs stubs of its own (pyo3-stub-gen).
26. Opt-in HTTP/2 and one retry on 5xx (2026-10-13, from the first live latency profile; `examples/profile_hub.py`).
    The profile showed the client at 0% of wall time, a ~300 ms round trip to the Hub from the user's location, and
    parallel fan-outs (five `/token` calls in `wallets.list`) each opening a new HTTP/1.1 connection at ~430 ms of
    TCP+TLS. `Options(http2=True)` (user: off by default, switchable) asks for HTTP/2 so concurrent requests to one
    host share a connection; `h2` is the optional extra `syfthub-sdk[http2]`, missing it raises `ConfigurationError`.
    ALPN decides per host: the Hub and the station negotiate h2; a Space on bare uvicorn (HTTP/1.1 only) or on
    cleartext stays 1.1, so only hosts behind an h2-capable TLS proxy gain, and only on concurrent requests. A 5xx
    retried three times with backoff turned a failing Space's 650 ms answer into a 5 s execute; `Retry.server_errors=1`
    bounds 5xx retries while network errors keep `Retry.attempts`; the row is reported retryable either way.
27. Idle connections live 60 s and listing-time balance reads time out in 5 s (2026-10-13, second live profile). httpx's
    5 s keepalive meant every Hub call after a fan-out longer than that paid a fresh TCP+TLS handshake (~570 ms from
    the user's location); `KEEPALIVE_SECONDS = 60` in the transport, inside nginx's 75 s, not an option. One wallet
    host answering a balance read in 10 s made `wallets.list` take 11 s; `Timeout.lookup` (default 5 s) is the read
    timeout only for the single-attempt reads behind `wallets.list` and pre-flight, passed per request through
    `Transport.request(read_timeout=)`; a host over it is `balance=None` and held, as before. `refresh`, top-ups,
    invoice polls and the query keep `Timeout.read`.

28. The ports are typed and the budget has an owner (2026-10-14, Clean Architecture audit). `models/ports.py` gains
    `HubPorts(SearchPort, WalletPort, Protocol)`; `Bound._hub`, `Wallet._hub`, every `from_dict(hub, d)` and `_bind`
    are typed against it instead of `Any`, so mypy checks that `AsyncHub` satisfies the ports (the stub test's probe
    assigns `hub.async_hub` to a `HubPorts`) and that the models call them correctly. `Bound._derive(**update)` is
    the one binding-preserving copy the views use. `Ledger` (`models/session.py`, mutable) holds the session's
    `Budget`: `AsyncHub` owns it and shows `budget`, `Searcher` records charges against it; `AsyncHub._record_spend`
    is gone and nothing reaches into another object's privates for money. `WalletsNamespace` takes `options`
    explicitly rather than reading them off the hub. Protocols are excluded from the sync stub's twins.

29. Smaller modules, one owner per piece of knowledge (2026-10-14, after the Clean Architecture audit).
    `search.py` kept only the runner; the pure rules moved to `preflight.py` and the action builders to
    `actions.py`, so the hint text of each action exists once and pre-flight and the send agree.
    `syfthub/results.py` became `classify.py` (it never held the data objects; `models/results.py` does).
    `ErrorDetail`/`detail_of` moved from `_transport` to `_api/detail.py`: the FastAPI error-body shape is
    adapter knowledge, not driver code, and `classify` now uses the same parser instead of its own copy.
    `TransportError` joined `errors.py` as a `SyftHubError`, so no use-case module imports from `_transport`.
    `_send_one` is a short script over an `_Attempt` (parameter object: url, body, attempts, charge, and the
    two row constructors) with `_query` and `_pay` extracted; `classify` builds one `_Reply` and dispatches
    on status to `_returned`, `_payment`, `_forbidden`, `_throttled`, `_failed`.

Open: nothing, as of 2026-10-14.

---

## 12. From the v2 mock to the first cut: rename and removal table

| Mock (`syfthub/` today) | First cut |
|---|---|
| `hub.endpoints`, `Endpoint`, `EndpointList`, `EndpointType` | `hub.sources`, `Source`, `SourceList`, `SourceType` |
| `EndpointType.DATA_SOURCE / MODEL / MODEL_DATA_SOURCE`, `returns_references` | `SourceType.DOCUMENTS / MODEL / BOTH`, `returns_documents` |
| `hub.wallets.for_endpoint`, `Wallet.endpoints` | `for_source`, `Wallet.sources` |
| `PlanRow.endpoint`, `SourceResult.endpoint`, `Charge.endpoint` | `.source` |
| `EndpointNotFound` | `SourceNotFound` |
| `plan.filter(**conditions)`, `FilterSplit`, `Endpoint.filterable` | removed (deferred) |
| `plan.rows / .pending / .held` on the plan | `Preflight` object returned by `preflight()`; `plan.pre` keeps the last |
| `TopUp.needed`, `TopUp.waiting`, `topup.buy(bundle)`, `plan.top_up(...)` | `TopUp.shortfall`, `TopUp.affects`, `TopUp.suggested`, `topup.top_up(bundle=None)`; plus `OverBudget`, `AccessDenied`, `CircuitOpen` |
| `results.pending: list[TopUp \| Charge]` | `results.actions: tuple[Action]` |
| `results.approve()`, `results.skip()`, `results.retry(ignore_budget=)`, `execute(ignore_budget=)` | `plan.skip()`, `results.plan`, `results.retry()`, `execute(strict=)` |
| `BudgetExceeded` | removed; `StaleSnapshot`, `ActionRequired` added |
| `Document.document_id`, `Document.similarity_score` | `Document.id`, `Document.score` (aliases keep the wire names) |
| `Results.from_dict` only | `to_dict`/`from_dict` on every model; `SearchPlan.from_dict`, `Invoice.from_dict` |
| `Options` dataclasses (`Timeout(write, pool)`, `Retry(max_attempts, initial, multiplier, ...)`) | pydantic `Options`; `Timeout(connect, read, total)`, `Retry(attempts, backoff, max_backoff)` |
| `hub.chat`, `results.chat`, `results.ask`, `results.aggregate`, `hub.aggregate`, `syfthub.notebook` | not in the first cut |
