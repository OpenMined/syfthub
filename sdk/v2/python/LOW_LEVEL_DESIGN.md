# SyftHub Python SDK v2: low-level design

Status: reviewed 2026-10-07; decisions in section 12 are taken unless marked open. Companion to `DESIGN_LOG.md`,
which records *why*; this file records *what*: every functionality the SDK offers, the name it gets, and the syntax a
user types. The mock in `syfthub/` implements this document against in-memory fakes, and `flows.ipynb` walks every
section of it; `syfthub._api` (generated clients) and the `unasync`-generated sync package are stood in by
`syfthub.testing.MockTransport` and a runtime proxy.

Decisions carried over from the design log and the SDK-references review: client-side fan-out, compose then execute,
payment as a state on a row and never an exception, prepaid first with MPP experimental, chat as a room, Aggregator
optional, no streaming (out of scope for v2), **async-first** (both servers are async; the sync face is generated).

---

## 1. Principles

1. **Hello world in three lines.** Install, construct, search. Credentials from the environment when present.
2. **The transport is the SDK's job.** Pooling, timeouts, backoff with jitter, per-Space circuit breaker, token caching
   and refresh, pagination, user agent. Users never see a header.
3. **Compose is free, network is awaited.** Building a search or a chat sends nothing and needs no `await`. Pre-flight,
   execute and send are coroutines.
4. **Rows, not exceptions, for anything a user can act on.** A source that needs credits, was rate limited or is down is
   a row with a reason and an attached action. Exceptions are for misuse and for failures with no in-flow remedy.
5. **Every object a user touches is typed.** Enums for closed sets, models for every dict, one return type per action.
6. **Methods are verb plus object; namespaces group endpoints.** One top-level domain verb per noun: `search`, `chat`.
7. **Immutable results.** Every method on `Results` returns a new `Results`. Nothing a user holds changes under them.
8. **Raw is always one attribute away.** Classification sits on top of the server's body, never replaces it.
9. **The core has no UI dependency.** Notebook rendering, widgets and framework adapters are optional extras.
10. **Semver, long deprecations, a changelog.** The SDK is the buffer between users and two moving servers.

---

## 2. Package layout

```
syfthub/
  __init__.py          AsyncHub, Hub, models, errors, __version__
  hub.py               AsyncHub: session, namespaces, search(), chat(), budget
  auth.py              AuthNamespace, Identity
  endpoints.py         EndpointsNamespace, EndpointList
  wallets.py           WalletsNamespace, Wallet, Invoice, TopUp
  search.py            SearchPlan, PlanRow
  results.py           Results, SourceResult, views and actions
  chat.py              Chat, Replies, Reply, Context
  aggregator.py        aggregate(), Answer                      (route proposed, not built)
  models/              pydantic v2 models and enums (section 5)
  errors.py            exception hierarchy (section 6)
  _transport/          httpx client, Retry, CircuitBreaker, TokenCache, logging, user agent
  _api/                generated low-level clients from both OpenAPI specs: hub, space   (async)
  _sync/               Hub and friends, generated from the async package with unasync
  notebook/            _repr_html_ renderers and ipywidgets cards       extra: syfthub[notebook]
  testing/             FakeHub, FakeSpace, MockTransport                extra: syfthub[testing]
  adapters/            langchain.py, llamaindex.py                       extras: syfthub[langchain] …
```

Public import surface is `syfthub.*`. Modules prefixed `_` are private and may change without a major bump.

---

## 3. Hello world

```python
import syfthub

async with syfthub.AsyncHub() as hub:                      # SYFTHUB_URL, SYFTHUB_TOKEN from the environment
    results = await hub.search("adverse events in phase 3").execute()
    for path, doc in results.documents[:3]:
        print(path, doc.similarity_score, doc.content[:80])
```

Without `sources`, the search runs over free endpoints only, chosen by the Hub's semantic listing search for the query
and capped at `max_sources` (default 10). Paid endpoints are never included implicitly. Sync twin:

```python
with syfthub.Hub() as hub:
    results = hub.search("adverse events in phase 3").execute()
```

---

## 4. Public API by functionality

Each table lists the functionality, the call, what it returns, and notes. Async signatures are shown; the sync twin
drops `await` and `async`.

### 4.1 Session

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| Open a session | `syfthub.AsyncHub(url=None, *, token=None, options=None)` | `AsyncHub` | `url` defaults to `SYFTHUB_URL`, then the public Hub. `token` defaults to `SYFTHUB_TOKEN`. Nothing is sent. |
| Context manager | `async with syfthub.AsyncHub() as hub:` | | Closes pooled connections on exit. `await hub.close()` otherwise. |
| Tune transport | `syfthub.Options(timeout=..., retries=..., concurrency=8, circuit_breaker=..., http_client=None, user_agent_suffix=None)` | `Options` | One object instead of a long parameter list. Section 7. |
| Session budget | `hub.set_budget(limit, currency="USD")`, `hub.budget` | `Budget` | Client-side cap. Per session; see open decision 3. |
| Who am I | `hub.me` | `Identity \| None` | Cached from login; `await hub.auth.whoami()` refreshes. |
| Sign in (alias) | `await hub.login(username=, password=)` or `await hub.login(token=)` | `Identity` | Thin alias for `hub.auth.login` / `login_with_token`. The only top-level alias: it is the first action in hello world. |

Not kept from the mock: `connect()` and `interactive=`. Construction is the class; notebook rendering is on when the
`notebook` extra is installed and a display hook fires, with buttons calling the same public methods.

### 4.2 Authentication  (`hub.auth`)

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| Password login | `await hub.auth.login(username=, password=)` | `Identity` | Stores the session token; refreshes it before expiry. |
| Token login | `syfthub.AsyncHub(token=pat)` or `await hub.auth.login_with_token(pat)` | `Identity` | Headless path. |
| Google login | `await hub.auth.login_with_google()` | `Identity` | Opens the browser; returns when the Hub confirms. |
| Current user | `await hub.auth.whoami()` | `Identity` | Raises `NotLoggedIn` when anonymous. |
| Log out | `await hub.auth.logout()` | `None` | Clears session and satellite-token cache. |
| Guest use | no login | | Discovery and free sources work anonymously; satellite tokens are guest tokens. |

Satellite tokens (per endpoint owner and resource) are minted, cached and refreshed inside the transport. A 401 from a
Space re-mints once, then surfaces as a row with reason `auth`.

### 4.3 Discovery  (`hub.endpoints`)

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| List | `await hub.endpoints.list(type=None, owner=None, free=None, tag=None, matching=None)` | `EndpointList` | `type` and `owner` go to the Hub; the rest are applied locally. Auto-paginates up to `max_items=1000`. |
| Semantic search of listings | `await hub.endpoints.search(text, type=None)` | `EndpointList` | `POST /endpoints/search`. Best first. |
| One endpoint | `await hub.endpoints.get("owner/slug")` | `Endpoint` | Public record: policies, pricing, connect, health, `filterable`. |
| Page by page | `async for page in hub.endpoints.pages(...)` | `Page[Endpoint]` | For a Hub too large for `list()`. |
| Narrow locally | `eps.filter(type=, owner=, free=, tag=)`, `eps.matching(text, cutoff=0.6)`, `eps.pick("a/b", "c/d")`, `eps + other` | `EndpointList` | Pure; no round trip. |
| Paths | `eps.paths` | `list[str]` | |

`EndpointList` is a `Sequence[Endpoint]` with the narrowing helpers; it is what `sources=` accepts.

Renames: `hub.browse` → `hub.endpoints.list`; `hub.find` → `hub.endpoints.search`; `hub.get` → `hub.endpoints.get`;
`Selection` → `EndpointList`.

### 4.4 Wallets and payment  (`hub.wallets`)

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| All my wallets | `await hub.wallets.list(endpoints=None)` | `WalletList` | One per owner × rail × currency, grouped by `wallet_id` else `credits_url`. Balances fetched in parallel. |
| Wallet by key | `await hub.wallets.get(key)` | `Wallet` | |
| Wallet behind an endpoint | `await hub.wallets.for_endpoint("owner/slug")` | `Wallet` | Replaces the slash-sniffing `hub.wallet()`. |
| Balance | `await hub.wallets.balance("owner/slug")` | `Money \| None` | `None` for free and MPP endpoints. |
| Refresh | `await wallet.refresh()` | `Wallet` | |
| Buy credits | `await wallet.top_up(bundle)` | `Invoice` | `bundle` is a `Bundle` or its id. Invoice has `checkout_url`, `id`, `amount`, `status`. |
| Wait for payment | `await invoice.wait_paid(timeout=600, poll=5)` | `Invoice` | Headless flow: polls the balance route until it rises (decision 4). |
| Index | `wallets["owner/slug"]`, `wallets[key]` | `Wallet` | |

MPP (experimental) settles through `Results.approve`; no wallet object is involved on the client side.

### 4.5 Search: compose, pre-flight, execute

```python
plan = hub.search(query, sources=None, *, limit=5, similarity_threshold=0.5,
                  history=None, filters=None, max_sources=10)        # sync, free, nothing sent
plan = plan.filter(published_gte="2024-01-01", author_contains="chitrakoot")
plan = await plan.preflight()                                        # estimates, balances, holds; still nothing sent
results = await plan.execute()                                       # runs preflight first if you skipped it
```

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| Compose | `hub.search(query, sources=, ...)` | `SearchPlan` | `sources`: `EndpointList`, `Endpoint`s, `"owner/slug"` paths, `"collective/name"`. |
| Metadata filters | `plan.filter(**conditions)` | `SearchPlan` | Suffixes `_gte _gt _lte _lt _contains`; bare key is equality. Travels to Spaces that advertise the field (proposed), applied locally after `limit` otherwise. |
| Pre-flight | `await plan.preflight()` | `SearchPlan` | Fills `plan.rows`, `plan.estimate`, `plan.sending`, `plan.held`, `plan.pending`. Idempotent; `await plan.refresh()` re-runs it. |
| Where a filter is applied | `plan.filters_for(row)` | `FilterSplit` | `.remote`, `.local`. |
| Top up before sending | `await plan.top_up(wallet_or_path, bundle)` | `Invoice` | Same object as `wallet.top_up`. |
| Execute | `await plan.execute(ignore_budget=False)` | `Results` | One `POST .../query` per sending row, bounded by `Options.concurrency`. |

Rename: `Search` → `SearchPlan`; `SearchRow` → `PlanRow`; `total_estimate` → `estimate`. `verdict` becomes the
`Verdict` enum: `READY`, `WILL_ASK_TO_PAY`, `NEEDS_CREDITS`, `OVER_BUDGET`, `ACCESS_DENIED`, `UNHEALTHY`.

### 4.6 Results: views and actions

Every method returns a new `Results`. Views reshape what you look at; actions talk to Spaces and return the updated set.

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| Per source | `results["owner/slug"]`, `for row in results` | `SourceResult` | |
| Passages | `results.documents` | `list[tuple[str, Document]]` | After the view's filters and `top`. |
| Summaries | `results.answers` | `dict[str, str]` | Model endpoints. |
| What came back | `results.kind` | `ReturnKind` | `REFERENCES`, `SUMMARIES`, `BOTH`. Was `returns`. |
| Raw bodies | `results.raw` | `dict[str, dict]` | Verbatim. |
| View: metadata | `results.filter(**conditions)` | `Results` | Same syntax as `plan.filter`; local only. |
| View: sources | `results.only(*paths)`, `results.drop(*paths)` | `Results` | |
| View: best passages | `results.top(k)` | `Results` | Across sources, by similarity. |
| Combine | `results + other` | `Results` | |
| Waiting on you | `results.pending` | `list[TopUp \| Charge]` | One `TopUp` per short wallet, one `Charge` per MPP source. |
| Top up | `await results.top_up(wallet_or_path, bundle)` or `await topup.buy(bundle)` | `Invoice` | |
| Re-send | `await results.retry(*paths, ignore_budget=False)` | `Results` | Rows whose reason is retryable. `ignore_budget=True` replaces `proceed()`. |
| Pay MPP | `await results.approve(*paths)` | `Results` | Raises `BudgetExceeded` before paying. |
| Give up on a source | `results.skip(*paths)` | `Results` | Reason `BY_USER`; `retry` leaves it alone. |
| Money | `results.charges`, `results.cost`, `results.spent`, `results.estimate` | `list[ChargeEntry]`, `dict[str, Money]`, ... | Per currency, never converted. |
| Counts | `results.ok_count`, `results.skipped`, `results.paths` | | |
| Serialise | `results.to_dict()`, `Results.from_dict(d)` | | Stable JSON for chatbots and caches. |
| Talk to a model | `results.chat(models, include=Include.BOTH)` | `Chat` | Section 4.7. |
| One-shot question | `await results.ask(model, prompt=None)` | `Reply` | No thread kept. |
| Aggregator | `await results.aggregate(model, prompt=None)` | `Answer` | Section 4.8. |

`SourceResult`: `endpoint`, `outcome: Outcome`, `reason: Reason | None`, `documents`, `summary`, `cost: Money | None`,
`charges`, `rate_limit: RateLimit | None`, `elapsed_ms`, `request`, `raw`, `topup`, `charge`, `ok`, `retryable`.

`Outcome` splits the old `SKIPPED` into who stopped the call:

| Outcome | Meaning | Typical reasons |
|---|---|---|
| `RETURNED` | The Space answered. | |
| `HELD` | Pre-flight did not send it. | `NO_CREDITS`, `OVER_BUDGET`, `ACCESS_DENIED`, `BY_USER` |
| `REJECTED` | The Space refused (403). | `NO_CREDITS`, `RATE_LIMITED`, `ACCESS_DENIED`, `NO_PRICING_TIER`, `BLOCKED` |
| `FAILED` | Transport or server failure after retries. | `UNREACHABLE`, `TIMEOUT`, `SERVER_ERROR`, `NOT_FOUND`, `AUTH` |
| `PAYMENT_REQUIRED` | MPP 402; `charge` attached. | |

### 4.7 Chat: a room with one transcript per model

```python
chat = hub.chat(models, sources=None, *, via=Via.DIRECT, limit=5)      # sync compose
chat = results.chat(models, include=Include.BOTH)
await chat.preflight()                                                 # optional; send() runs it
replies = await chat.send("What are the main adverse events?")
replies["bob/llama-3"].text ; replies.text (single model) ; chat.spent
```

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| Open | `hub.chat(models, sources=, via=, limit=)` | `Chat` | `models`: one path, a list, or `Endpoint`s. With `sources`, every message searches first. |
| From results | `results.chat(models, include=)` | `Chat` | Fixed passages from the view. |
| Pre-flight | `await chat.preflight()`, `chat.rows`, `chat.pending` | | Price per message and balance per model. |
| Send | `await chat.send(prompt, max_tokens=300)` | `Replies` | One `Reply` per active model; a short model is a skipped reply with its `TopUp`, never an exception. |
| Models in the room | `chat.add(model, brief=True)`, `chat.remove(model)`, `chat.active`, `chat.lead` | `Chat` | `remove` on an absent model raises `InvalidState`. |
| Context | `chat.context`, `chat.history`, `chat.view` | `Context`, `list[Message]`, `Results \| None` | `Context` has `source_tokens`, `history_tokens`, `tokens`, `turns`, `counts`. |
| Change passages | `chat.use(view, include=None)`, `chat.filter(**)`, `chat.only(*)`, `chat.drop(*)`, `chat.top(k)` | `Chat` | Turns kept. |
| Forget turns | `chat.reset()` | `Chat` | View and pre-flights stay. |
| Branch | `chat.fork()` | `Chat` | Independent copy with the transcript so far. The narrowing verbs mutate, so this is how you compare two views over one conversation. |
| Money | `chat.spent`, `chat.spent_by(path)`, `replies.cost`, `reply.cost` | `dict[str, Money]` | |
| Top up | `await chat.top_up(model=None, bundle=)` | `Invoice` | `model` optional when one is short. |
| Turn | `chat.turn`, `chat.last`, `replies.turn`, `replies.context` | | |
| Serialise | `chat.to_dict()`, `replies.to_dict()` | | |

`Chat` mutates in place: it is a room, not a value. This is the one deliberate exception to principle 7, because a
conversation is a stateful thing a user holds across cells. Consequences, each handled:

- The narrowing verbs return the same room, so `a = chat.only("x"); b = chat.only("y")` leaves one room narrowed to
  `y`. Branch with `chat.fork()`.
- Sends on one room are serialised by an internal lock; `asyncio.gather(chat.send(a), chat.send(b))` runs them in
  order and never interleaves the transcript.
- `Replies` and `Reply` are frozen snapshots taken at send time. `chat.reset()` later does not change what an earlier
  turn reports as its `context`.
- A chat opened from `results` keeps that view. After `fresh = await results.retry()` the room still sees the old rows
  until `chat.use(fresh)`. This is the price of immutable results and is stated in the reference.

`Reply` and `Replies` lose their `top_up` method; they expose `.pending`, and each `TopUp` has `.buy(bundle)`.

### 4.8 Aggregator (optional; route and fan-out location open)

The Aggregator takes everything a search or chat gathered and returns one reranked, cited answer. Where the fan-out
happens is not decided (open decision A). The SDK surface below is the same under both options; only what travels in
the request differs.

| Functionality | Syntax | Returns | Notes |
|---|---|---|---|
| Answer over results you already hold | `await results.aggregate(model, prompt=None)` | `Answer` | Sends the view's documents. Works under both options; under option 1 it is the "documents supplied, skip retrieval" form. |
| Answer over sources, one request | `await hub.aggregate(query, sources=, model=, limit=5, filters=None)` | `Answer` | Option 1 only: the Aggregator fans out. Pre-flight runs in the client first so held sources are never sent. |
| Waiting on you | `answer.pending`, `await answer.resume()` | `list[TopUp \| Charge]`, `Answer` | Option 1: the Aggregator returns the per-Space 402/403 envelopes and a `job_id`; the same `TopUp`/`Charge` rows appear; pay, then resume the job. Empty under option 2. |
| Chat through it | `hub.chat(models, sources=, via=Via.AGGREGATOR)` | `Chat` | Each `send` posts query, sources or documents, and history. Pending is surfaced on `Replies.pending`. |
| Where it lives | `Options(aggregator_url=...)` | | Defaults to `{hub_url}/aggregator/api/v1`. |

`Answer`: `text`, `model`, `citations: dict[int, str]`, `reranked: list[tuple[str, Document]]`, `usage`, `cost: Money`,
`per_source: list[SourceResult]` (option 1 returns the raw per-Space bodies so decision 1's transparency holds),
`pending`, `job_id`, `raw`.

Trade-off recorded for the Aggregator discussion:

| | Option 1: fan-out in the Aggregator | Option 2: fan-out in the client, documents to the Aggregator |
|---|---|---|
| Aggregator work | Payment forwarding and a resumable job on top of the fan-out it already does | A new route that accepts documents and skips retrieval |
| Payment consent | Round-trips through the Aggregator: envelopes + `job_id` out, pay, resume | Settled before the Aggregator is called |
| Pre-flight | Client runs it first; the Aggregator must honour the client's send list or repeat the holds | Unchanged |
| Tokens | Client mints per-Space satellite tokens and sends them with the request, as today | Client only |
| Chatbot integrations | One request per turn | Two steps per turn |
| Transparency (decision 1) | Only if the Aggregator returns per-Space bodies | Holds by construction |
| Aggregator state | Job store for resume | Stateless |

The route is unbuilt either way. Missing route raises `AggregatorError`; there is no row to attach it to.

---

## 5. Models and enums

All models are pydantic v2, frozen, with `model_dump()` for JSON. Enums are `str` enums so they compare to their
wire value. Fields match the server names unless noted.

| Model | Fields | Replaces |
|---|---|---|
| `Endpoint` | `name, slug, type: EndpointType, owner_username, description, version, tags, stars_count, policies: list[Policy], connect: list[Connection], readme, health: Health, filterable: list[str]`; properties `path, url, pricing` | same, typed |
| `Policy` | `type: PolicyType, config, version, enabled, description`; `is_payment` | `type: str` |
| `Pricing` | `rail: Rail, price: Money, unit: PriceUnit, wallet_id, wallet_owner, bundles: list[Bundle], payment_url, credits_url, invoices_url`; `paid, prepaid, label` | `bundles: tuple[dict]` |
| `Bundle` | `id, name, amount: Money, credits` | dict |
| `Money` | `amount: Decimal, currency: str`; `__add__` only within one currency | `float` + `currency` pairs |
| `Wallet` | `key, owner, rail, currency, balance: Money \| None, endpoints, bundles, payment_url, credits_url` | same |
| `Invoice` | `id, wallet_key, bundle, amount, status: InvoiceStatus, checkout_url, created_at`; `wait_paid()` | dict |
| `TopUp` | `endpoint, wallet, needed: Money \| None, waiting: list[str], invoice: Invoice \| None`; `buy(bundle)` | same, plus `buy` |
| `Charge` | `endpoint, amount: Money, www_authenticate` (redacted in repr) | same |
| `ChargeEntry` | `source, policy, status, amount: Money, raw` | `list[dict]` on `charges` |
| `Document` | `document_id, content, similarity_score, metadata` | same |
| `Message` | `role: Role, content` | `dict[str, str]` |
| `Identity` | `username, email, auth: AuthMethod, hub_wallet_balance: Money, budget` | `auth: str` |
| `Budget` | `limit: Money, spent: Money`; `remaining` | same |
| `RateLimit` | `limit, remaining, reset_seconds` | buried in `raw` |
| `PlanRow` | `endpoint, estimate: Money, verdict: Verdict, send, hold_reason: Reason \| None, wallet, warnings, note` | `SearchRow`, `verdict: str` |
| `FilterSplit` | `remote: dict, local: dict` | tuple |
| `Context`, `Answer`, `Reply`, `Replies` | as in the mock, typed | |

Enums: `EndpointType {DATA_SOURCE, MODEL, MODEL_DATA_SOURCE}`, `Rail {FREE, STRIPE, XENDIT, CLUSTER, MPP}`,
`PolicyType {STRIPE, XENDIT, CLUSTER, MPP, ACCESS, RATE_LIMIT, PII_FILTER}`, `PriceUnit {REQUEST, DOCUMENT}`,
`Outcome`, `Reason`, `Verdict`, `ReturnKind`, `Include {REFERENCES, SUMMARIES, BOTH}`, `Via {DIRECT, AGGREGATOR}`,
`AuthMethod {PASSWORD, GOOGLE, TOKEN, GUEST}`, `Role {USER, ASSISTANT, SYSTEM}`, `Health {HEALTHY, UNHEALTHY, UNKNOWN}`,
`InvoiceStatus {PENDING, PAID, EXPIRED, FAILED}`.

Every function that accepts an enum also accepts its string value, so `type="model"` keeps working and the IDE still
offers the enum.

---

## 6. Errors

```
SyftHubError                      base; every raise in the package is a subclass
├── ConfigurationError            bad URL, missing token, invalid Options          (before any request)
├── ValidationError               bad argument: unknown path form, limit < 1, bad filter suffix
├── AuthError                     401 that re-minting did not fix; .who = "hub" | "space"
│   └── NotLoggedIn               an action needs a signed-in user
├── HubError                      Hub returned 4xx/5xx with no row to carry it; .status .method .url .body .request_id
│   ├── NotFound                  endpoint, wallet or collective does not exist
│   └── HubUnavailable            connection refused / 5xx after retries
├── SpaceError                    a Space call outside a search row failed (balance, invoice); same attributes + .path
│   └── InvoiceError              invoice creation refused
├── AggregatorError               route missing or failed
├── BudgetExceeded                .needed .remaining (Money); raised by approve() and execute(ignore_budget=False) only
│                                 when the user asks to pay, never by pre-flight
└── InvalidState                  the action does not apply now; message says what to do   (was RunNotReady)
```

Rules:

- A Space's answer to a search or chat message never raises. It becomes a row.
- Rate limits during a search are retried inside the transport when `reset_seconds` is at or under
  `Retry.rate_limit_wait`; otherwise the row is `REJECTED / RATE_LIMITED` with `rate_limit` filled in.
- Executing a plan with nothing to send returns an empty `Results` with `note` set. `NothingToRun` is dropped.
- Messages are specific and actionable: what failed, on which endpoint, what to call next. No bare built-in exceptions.
- 401 and 403 are never conflated: 401 is `AuthError` or reason `AUTH`; 403 is a `REJECTED` row with the policy reason.

---

## 7. Transport and resilience  (`syfthub._transport`)

```python
Options(
    timeout=Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
    retries=Retry(max_attempts=3, initial=0.5, multiplier=1.5, jitter=0.5, max_elapsed=30.0,
                  on_status=(500, 502, 503, 504), on_network=True, rate_limit_wait=10.0),
    circuit_breaker=CircuitBreaker(failures=3, cooldown=60.0),
    concurrency=8,
    http_client=None,                 # an httpx.AsyncClient; injected for tests and proxies
    aggregator_url=None,
    user_agent_suffix=None,           # appended to "syfthub-python/<version> python/<v> httpx/<v>"
    max_items=1000,                   # auto-pagination cap for list()
)
```

| Concern | Behaviour |
|---|---|
| Connections | One `httpx.AsyncClient` with keep-alive; pool limits scale with `concurrency`. HTTP/2 when the server negotiates it. |
| Retries | Exponential backoff with full jitter on network errors and the listed 5xx. Never on 4xx except the rate-limit case above. Idempotent calls only; a search POST is treated as idempotent because Spaces bill on success. |
| Circuit breaker | Per Space host. After `failures` consecutive failures the host is open for `cooldown`; rows become `FAILED / UNREACHABLE` without a request; one probe after cooldown. Breaker state is visible as a pre-flight warning. |
| Tokens | `TokenCache` keyed by (owner, resource). Refresh at 80% of lifetime. One re-mint on 401. Guest tokens when anonymous. `satellite_id` sent where the multi-host contract requires it. |
| Pagination | `list()` follows pages until `max_items`; `pages()` exposes them. |
| Metadata | `User-Agent` on every request. Rate-limit data from headers or `details.reset_seconds` surfaced on `SourceResult.rate_limit`. Metadata never changes behaviour. |
| Logging | `logging.getLogger("syfthub")`. INFO: one line per fan-out. DEBUG: request and response lines with bearer tokens, `X-Payment` and `WWW-Authenticate` redacted. Nothing logged by default. |
| Observability | Optional OpenTelemetry spans per request when the `opentelemetry-api` package is importable; one span per fan-out with child spans per Space. |
| Concurrency | `asyncio.Semaphore(concurrency)` around Space calls. |

---

## 8. Sync twin and notebook layer

- The async package is the source. `syfthub/_sync/` is generated with `unasync` at build time; `syfthub.Hub` and every
  sync class are re-exported from `syfthub`. Tests run against both.
- In Jupyter the async face works directly with top-level `await`. The sync face is for scripts and REPLs.
- `syfthub.notebook` registers `_repr_html_` on `EndpointList`, `Endpoint`, `WalletList`, `SearchPlan`, `Results`,
  `SourceResult`, `Chat`, `Replies`, `Reply`, `Context`, `Invoice`. Widgets render `pending` with buttons that call
  `buy`, `retry` and `approve`. Importing the core never imports IPython or ipywidgets.

---

## 9. Serialisation and adapters

- `to_dict()` / `from_dict()` on `Results`, `Replies`, `Chat`, `EndpointList`. JSON-safe; `Money` serialises as
  `{"amount": "1.25", "currency": "USD"}`; enums as their string values.
- `syfthub.adapters.langchain.SyftHubRetriever(hub, sources, limit)` and a LlamaIndex equivalent wrap
  `hub.search(...).execute()` and emit framework documents with `path` and `similarity_score` in metadata.

---

## 10. Build, test, distribute

| Topic | Decision |
|---|---|
| Low-level clients | Generated from the Hub and Space OpenAPI specs into `syfthub._api`, async, regenerated in CI; the hand-written layer calls only these. Hand-written code is never overwritten by generation. |
| Contract tests | Run in both servers' CI against the generated clients and a recorded set of envelopes (402, 403 reasons, invoices). The SDK pins `MIN_HUB_VERSION` and `MIN_SPACE_VERSION` and warns once per session when a server is older. |
| Testing extra | `syfthub.testing.MockTransport` serves the fakes through `Options(http_client=...)`, so users unit-test integrations offline. |
| Type checking | mypy strict and pyright on the public package; `py.typed` shipped. |
| Versioning | Semver. Deprecated names stay for at least two minor versions with a `DeprecationWarning` naming the replacement. `CHANGELOG.md` in Keep a Changelog format. |
| Distribution | PyPI as `syfthub`; extras `notebook`, `testing`, `langchain`, `llamaindex`, `otel`. Python 3.11+. |
| Docs | Getting started with a time estimate; how-to guides (headless top-up in CI, chatbot integration, several models); explanation pages (payment model, pre-flight, filters); generated reference grouped by namespace with a runnable example per member, executed in CI; Markdown twin of every page and `llms.txt`. |
| Repo | Separate `syft-sdk` repo (design log decision 18) with README quick start, contribution guide stating which files are generated, coverage and lint badges. |

---

## 11. Mock to design: rename table

| Mock | Design | Why |
|---|---|---|
| `syfthub.connect(url, interactive=)` | `syfthub.AsyncHub(url, token=, options=)` / `syfthub.Hub(...)` | Construction is the class; env defaults; no UI flag in the core |
| `hub.login(username=, password=)`, `hub.login.google()`, `hub.login.token()` | `hub.auth.login(...)`, `login_with_google()`, `login_with_token()` | Callable object with methods is not idiomatic; auth gets a namespace. `hub.login(username=, password=)` and `hub.login(token=)` stay as the one alias |
| `hub.whoami()` | `hub.me`, `await hub.auth.whoami()` | |
| `hub.browse(...)` | `await hub.endpoints.list(...)` | Verb plus object; list for collections |
| `hub.find(text)` | `await hub.endpoints.search(text)` | Collided with `hub.search` |
| `hub.get(path)` | `await hub.endpoints.get(path)` | Had no object |
| `Selection` | `EndpointList` | Says what it holds |
| `hub.wallets(eps)`, `hub.wallet(x)`, `hub.balance(x)` | `hub.wallets.list()`, `.get(key)`, `.for_endpoint(path)`, `.balance(path)` | No argument sniffing |
| `Wallet.top_up(bundle) -> dict` | `await wallet.top_up(bundle) -> Invoice` | One return type per action |
| `Search`, `SearchRow` | `SearchPlan`, `PlanRow` | Not confusable with `Results` |
| `search.execute()` runs pre-flight on compose | `plan.preflight()` awaited; `execute()` runs it if needed | Compose is free and sync |
| `results.proceed()` | `results.retry(ignore_budget=True)`, `plan.execute(ignore_budget=True)` | Three go-ahead verbs became two |
| `results.returns` | `results.kind: ReturnKind` | Read as a verb |
| `Outcome.SUCCESS / SKIPPED` | `RETURNED / HELD / REJECTED / FAILED / PAYMENT_REQUIRED` | Who stopped the call is visible |
| `SkipReason` | `Reason` | Shared by held, rejected and failed rows |
| `verdict: str` | `Verdict` enum | IDE catches typos |
| `RunNotReady`, `NothingToRun` | `InvalidState`; empty results with a note | |
| `ValueError`, `RuntimeError`, `KeyError` raises | `InvoiceError`, `AggregatorError`, `InvalidState` | Everything under `SyftHubError` |
| `top_up` on `Reply`, `Replies` | `.pending[i].buy(bundle)` | Smaller surface |
| `interactive=True` widgets | `syfthub[notebook]` extra, auto-registered | Light core |
| `history: list[dict]` | `list[Message]` | Typed |
| `float` + `currency` | `Money` | No cross-currency sums by accident |

Kept as is: `filter / only / drop / top`, `+`, `retry`, `approve`, `skip`, `pending`, `top_up`, `ask`, `aggregate`,
`chat`, `send`, `add`, `remove`, `reset`, `use`, `context`, `spent`, `spent_by`, `charges`, `cost`, `raw`.

---

## 12. Decisions taken on 2026-10-07, and what is still open

| # | Question | Decision |
|---|---|---|
| 1 | `Chat` mutable while `Results` immutable | Yes. Consequences handled with `fork()`, serialised sends and snapshot `Replies` (section 4.7). |
| 2 | Default sources when `sources` is omitted | Free endpoints, picked by the Hub's semantic listing search for the query, capped at `max_sources`. Paid endpoints never implicit. |
| 3 | Budget scope | Per session. `hub.set_budget` and `hub.budget`. |
| 4 | Headless prepaid top-up | `wallet.top_up(bundle)` returns an `Invoice`; `await invoice.wait_paid(timeout, poll)` polls the balance route. |
| 5 | `retry` vs `resume` | `retry`. |
| 6 | `Money` amounts | `Decimal`, parsed once from the server's floats. |
| 7 | Models | pydantic v2, frozen. |
| 8 | Streaming rows from `execute()` | Out of scope for v2. No name reserved. |
| 9 | MPP with no pricing tier | Accept the 403 as reason `BLOCKED`. |
| 10 | Top-level `login` | One alias, `hub.login(username=, password=)` / `hub.login(token=)`. No other top-level aliases. |
| 11 | `Options` scope | One object, applied to the whole client: Hub, every Space, the Aggregator. |

Open:

- **A. Aggregator fan-out location.** Option 1 (Aggregator fans out, forwards payments, resumable job) is the current
  lean; option 2 (client fans out, documents to the Aggregator) is the SDK author's recommendation for v2 because it
  needs no job store and keeps pre-flight in one place. The SDK surface in section 4.8 is the same under both. Decide
  with the Aggregator team; also whether the route takes billing receipts with the documents.
