# Python SDK Guide

`syfthub` is the Python client for SyftHub. You log in once, pick the sources you want to search,
see what each one will cost and need before anything is sent, then run the search. Every query goes
straight from your process to the publisher's Space; the Hub is only consulted for the catalogue,
the per-Space access tokens and, for metered sources, the payment credential.

Requires Python 3.11 or newer.

## Installation

```bash
pip install --pre syfthub-sdk      # 2.x is a pre-release until the first stable tag
# or
uv add --prerelease allow syfthub-sdk
```

`pip install --pre 'syfthub-sdk[http2]'` adds HTTP/2 support, used when `Options(http2=True)`
is set (see [Options](#options)).

## The shape of a search

```python
import syfthub

async with syfthub.AsyncHub(token="...") as hub:    # or set SYFTHUB_TOKEN
    plan = hub.search("adverse events in phase 3", ["erin/trials", "carol/papers"])
    pre = await plan.preflight()            # rows + actions; nothing sent, nothing spent
    for action in pre.actions:              # TopUp, OverBudget, AccessDenied, CircuitOpen
        plan = plan.skip(*action.paths)     # the one decision verb
    results = await plan.execute()          # one POST per Space, in parallel
    for path, doc in results.documents:     # best-scored chunks across sources
        print(path, doc.score, doc.content[:80])
```

Four steps, always in this order:

1. **Compose.** `hub.search(...)` returns a `SearchPlan`. Nothing is sent.
2. **Pre-flight.** `plan.preflight()` reads the catalogue and wallet balances and returns one row
   per source with a verdict, plus the actions that would unblock the held rows.
3. **Decide.** Skip sources, top up a wallet, raise a cap, or do nothing. The plan is a frozen
   value; `skip` returns a new one.
4. **Execute.** `plan.execute()` sends every row that pre-flight said it would send and returns
   `Results`, one row per source whether it succeeded or not.

You can call `execute()` without a pre-flight. It runs the same checks internally and holds the same
rows; pre-flight exists so the app can show the user what is about to happen.

## Client setup

```python
import syfthub

hub = syfthub.AsyncHub(
    "https://syfthub.org",      # or SYFTHUB_URL; defaults to the public Hub
    token="syft_pat_...",       # or SYFTHUB_TOKEN
    budget=1.00,                # optional; a session cap per currency (see Session budget)
    options=syfthub.Options(),  # timeouts, retries, circuit breaker, concurrency
)
```

Use `async with syfthub.AsyncHub(...) as hub:` or call `await hub.aclose()` to release the HTTP
client. No request is made until the first call.

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | Hub URL. Defaults to the public Hub. |
| `SYFTHUB_TOKEN` | Bearer token: a personal access token or a login access token. |

### Sync twin

`syfthub.Hub` is the same API without `await`. It runs an `AsyncHub` on a private thread and blocks
the caller, so it works in plain scripts and inside a notebook that already has a running loop.

```python
with syfthub.Hub(token="...") as hub:
    results = hub.search("adverse events in phase 3", ["erin/trials"]).execute()
```

Every object it hands out behaves like its async counterpart: `isinstance` and `match` see the real
classes, and `wallet.refresh()` updates the wallet in place. Only `type(obj)` reveals the proxy, so
prefer `obj.kind` or `isinstance` when you need the class. Two guards: a sync call from the
private loop's own thread raises `RuntimeError` instead of deadlocking, and so does any call after
`close()`. `hub.async_hub` exposes the underlying `AsyncHub` for mixed code.

Type checkers and IDEs see the sync API with full types: `hub.search(...).preflight()` is a
`Preflight`, not a coroutine, and completions work. To annotate your own sync code, take the
names from `syfthub.sync`; at runtime they are the real classes, under a type checker they are
the sync faces.

```python
from syfthub import sync

def review(pre: sync.Preflight) -> sync.SearchPlan: ...
```

## Authentication

```python
await hub.login("username", "password")       # password login
await hub.login(token="syft_pat_...")          # or swap the token in later

hub.authenticated                              # True once a token is held
hub.me                                         # Identity | None, cached from the last login
identity = await hub.auth.whoami()             # GET /auth/me
```

Access tokens obtained by password login are refreshed automatically on a 401. Personal access
tokens are used as given. The SDK never stores credentials on disk.

## Sources

A source is a published endpoint, addressed as `owner/slug`. The catalogue lives on the Hub.

```python
listing = await hub.sources.list()                      # every public source, all pages
mine = await hub.sources.list(owner="erin")             # server-side filters: owner, type, matching
free = await hub.sources.list(free=True, tag="hr")      # local filters: free, tag
hits = await hub.sources.search("parental leave")       # the Hub's keyword search, top_k=10

source = await hub.sources.get("erin/trials")           # SourceNotFound if it does not exist
source.type            # SourceType.DOCUMENTS | MODEL | BOTH
source.pricing         # Pricing | None: rail, price, unit, currency, bundles
source.free            # True when there is no payment policy
source.reachable       # False when the publisher has not connected a Space
source.access(email)   # Access(allowed, rule) from the access policy, predicted client-side
```

`SourceList` is a tuple-like view: `listing.paths`, `listing["erin/trials"]`, `listing[0]`, and
the chainable `filter(type=, owner=, free=, tag=)`, `accessible(viewer)`, `matching(text)` and
`pick(*paths)`. `accessible` takes an email or `hub.me` and keeps the sources whose access policy
admits that viewer, so `listing.filter(free=True).accessible(hub.me)` is what you may search for
nothing. A `SourceList` can be passed straight to `hub.search`.

Every `list`, `get` and `search` call reads the Hub now. `hub.sources.cached(path)` is the only
lookup that does not: it returns what the last read said, for a minute, without a request.

`list` and `search` return what the Hub lists. The Hub delists a source whose Space has stopped
reporting, so a listed source has a live publisher. The SDK exposes no health flag: the Hub's
`health_status` is the Space's own check of the backend behind an endpoint, which the Hub already
acts on, and it says nothing about whether a query will succeed. It stays in `source.raw` if you
want to read it.

## Composing a plan

```python
plan = hub.search(
    "adverse events in phase 3",
    ["erin/trials", "carol/papers"],   # paths, Source objects, or a SourceList
    limit=5,                           # documents per source
    similarity_threshold=0.5,          # 0..1
    include_metadata=True,
)
```

Without `sources`, the plan covers every free document source in the catalogue that your account
may use; paid sources are only ever searched when you name them. `max_sources` puts a ceiling on
that automatic pick and never trims a list you pass. For the Hub's keyword ranking instead, pass
its result in: `hub.search(q, await hub.sources.search(q))`. `plan.explicit` tells the two apart
and `plan.active` lists the paths that are not skipped.

## Pre-flight

```python
pre = await plan.preflight()

pre.ready          # True when no row is held
pre.sending        # rows that execute() will send
pre.held           # rows it will not
pre.estimate       # {"USD": Money(...)}: the worst case across sending rows
pre.actions        # one action per cause, not per source
pre["erin/trials"].verdict
```

Each `PlanRow` carries the `Source`, a `Verdict`, an `estimate`, the `wallet` it would draw from and
a `note`.

| Verdict | Sends | Meaning |
|---|---|---|
| `READY` | yes | Free, or prepaid with enough credits, within the cap for its currency. |
| `WILL_ASK_TO_PAY` | yes | Metered (MPP). The Space will challenge and the SDK pays on the way, within the cap for its currency. |
| `NEEDS_CREDITS` | no | The prepaid wallet cannot cover the estimate. |
| `OVER_BUDGET` | no | The cap for the estimate's currency cannot cover it. |
| `ACCESS_DENIED` | no | Your email does not match the source's access policy. |
| `CIRCUIT_OPEN` | no | The Space's host is down or failing and is cooling down. |
| `UNREACHABLE` | no | The publisher has not connected a Space, or its wallet host did not answer the balance read. |
| `SKIPPED` | no | You skipped it. |

The checks run in the order skip, reachability, access, circuit, pricing, credits, budget,
and a source held by an earlier check is never contacted by a later one. Credits are checked per wallet: if several sources share one wallet
that is short, all of them are held and one `TopUp` carries the combined shortfall. Budget is
checked in plan order and per currency: the first row that would cross its currency's cap and every
paid row in that currency after it are held. A currency with no cap is not budgeted.

## Decisions

There are three ways to change what happens next.

```python
plan = plan.skip("carol/papers")                   # drop sources; returns a new plan
hub.set_budget({"USD": 5.00})                      # raise a cap, or clear them all with None
results = await plan.execute(strict=True)          # raise ActionRequired instead of sending partially
```

`pre.actions` is the list to act on. One action per cause:

| Action | Fields | What resolves it |
|---|---|---|
| `TopUp` | `wallet`, `shortfall`, `bundles`, `suggested` | `await action.top_up()` returns an `Invoice`; the user pays it. |
| `OverBudget` | `estimate`, `budget` | One per currency that crossed. `hub.set_budget({...})` or skip. |
| `AccessDenied` | `rule` | Ask the publisher, or skip. |
| `CircuitOpen` | `reopens_at` | Wait, or skip. |

Every action has `affects` (the sources), `paths` and `steps` (plain-English instructions).

```python
match action:
    case syfthub.TopUp():
        invoice = await action.top_up()           # the suggested bundle
    case syfthub.OverBudget() | syfthub.AccessDenied() | syfthub.CircuitOpen():
        plan = plan.skip(*action.paths)
```

## Executing

```python
results = await plan.execute()

results.chunks         # ((path, Document), ...) scored passages across sources, best first
results.answers        # {path: summary} from model sources
results.documents      # chunks first, then the unscored summaries as Documents
results.kind           # ReturnKind.REFERENCES | SUMMARIES | BOTH | NOTHING
results.ok             # rows that returned
results.failed         # rows that did not
results.held           # rows pre-flight held
results.retryable      # rows worth re-sending: timeouts, 5xx, rate limits, a host that was cooling down
results.cost           # {"USD": Money(...)} actually charged
results.actions        # TopUp actions raised by a 402 at execute time
results["erin/trials"] # one SourceResult
```

Requests fan out in parallel, bounded by `Options.concurrency`, one request per source. A 401 from
a Space re-mints that Space's token once and retries. Timeouts and connection errors retry per
`Options.retry`; a 5xx is retried once (`Retry.server_errors`), since a server that answered is
unlikely to answer differently a moment later and a fan-out hides nothing by waiting.

`SourceResult` has an `Outcome` and, when it did not return, a `Reason`:

| Outcome | Meaning |
|---|---|
| `RETURNED` | The Space answered. `documents`, `summary`, `cost`, `charges`. |
| `HELD` | Not sent: `reason` is the pre-flight verdict (`NO_CREDITS`, `OVER_BUDGET`, `ACCESS_DENIED`, `CIRCUIT_OPEN`, `BY_USER`, `UNREACHABLE`). |
| `REJECTED` | The Space refused: `RATE_LIMITED` (with `rate_limit.reset_seconds`), `ACCESS_DENIED`, `NO_PRICING_TIER`, `BLOCKED`, `NOT_PUBLISHED`, `AUTH`. |
| `FAILED` | Transport or server trouble: `TIMEOUT`, `SERVER_ERROR`, `UNREACHABLE`, `NOT_FOUND`. |
| `PAYMENT_REQUIRED` | A 402 the SDK could not settle: `topup` or `charge` says why. |

`results.retry()` re-sends only the retryable rows and merges the fresh rows in. `only`, `drop`
and `top(k)` return views for presentation.

## Money

### Session budget

A budget belongs to the session, not to a plan: it caps what every search on this `hub` may spend
together. There is no budget until you set one. Because publishers bill in their own currencies
and the SDK never converts money, a budget is one cap per currency, and a currency with no cap is
not budgeted at all.

```python
hub = syfthub.AsyncHub(budget=1.00)                         # shorthand for {"USD": 1.00}
hub = syfthub.AsyncHub(budget={"USD": 1.00, "IDR": 50000})  # one cap per currency
hub = syfthub.AsyncHub(budget=syfthub.Money.of(5, "EUR"))   # a cap in another currency
```

A number or string caps USD. A `Money` caps its own currency. A mapping caps several currencies
at once; its values may be numbers or `Money`, and a `Money` whose currency differs from its key
raises `ConfigurationError`.

The caps can change at any point in the session. Spend is kept across changes and only a new
`hub` starts from zero.

```python
hub.set_budget({"USD": 2.00})   # replace the caps; what was spent stays
hub.set_budget(None)            # no caps; spend is still recorded

hub.budget.limits               # {"USD": Money(2.00)}
hub.budget.remaining            # per capped currency: cap minus spend
hub.budget.remaining_in("USD")  # one currency; None when it has no cap
hub.spent                       # {"USD": Money(...), "IDR": Money(...)}: every charge, capped or not
```

Pre-flight judges each currency on its own, in plan order: the first paid row whose estimate would
cross its currency's cap, and every paid row in that currency after it, are held behind one
`OverBudget` action per crossed currency. A row billed in a currency with no cap is sent, and its
note says so. Execute records what each Space actually charged, per currency, whether or not that
currency is capped; a metered (MPP) charge counts as soon as it is paid.

### Prepaid wallets

Publishers who bill by prepaid credits (Stripe, Xendit, a managed wallet) expose a wallet per
publisher, rail and currency. Balances and top-ups go straight to the publisher's Space.

```python
wallets = await hub.wallets.list()                       # across the sources seen this session
wallet = await hub.wallets.for_source("erin/trials")      # Wallet | None
await wallet.refresh()                                   # balance, refreshed_at
wallet.bundles, wallet.suggest(shortfall)                # Bundle(name, amount, credits)

invoice = await wallet.top_up("starter")                 # Invoice: id, amount, status, checkout_url
await invoice.refresh()                                  # or
await invoice.wait_paid(timeout=600, poll=5)             # PaymentTimeout if it does not settle
await wallet.invoices()                                  # history
```

A `TopUp` action wraps the same calls: `await action.top_up()` picks the suggested bundle. Nothing
is charged until the user completes the checkout; then pre-flight passes.

`wallet.id` is the publisher's wallet id and the key that groups sources on one wallet; `wallet.key`
is the readable `owner/rail/currency` label. A policy that publishes only its URLs gets the UUID
from them as its id. `list()` and `for_source()` read every balance they return, in parallel, and
stamp `refreshed_at`. Those reads go straight to each wallet's host and are not retried, so a
dead Space costs one connect timeout, a slow one at most `Timeout.lookup` seconds, and leaves `balance=None`; `wallet.refresh()` keeps the
retry policy. `hub.wallets.get(key)`
is a lookup of a wallet already seen, with no request, so its balance is as of `refreshed_at`.

### Metered sources (MPP)

Sources on the `mpp` rail are charged per request through the Machine Payments Protocol. The Space
answers with a 402 challenge; the SDK asks the Hub to sign a credential with the wallet you created
on the Hub, retries with it, and records the charge in `results.cost` and `hub.spent`. Pre-flight
shows these rows as `WILL_ASK_TO_PAY` and counts their price against the cap for their currency.

The Hub wallet itself is created and funded on the Hub, not through the SDK. Without one, or when
it cannot cover the charge, the row comes back `PAYMENT_REQUIRED` with the Hub's code in `error`
(`WALLET_NOT_CONFIGURED`, `INSUFFICIENT_BALANCE`, ...) and `charge` holding the challenge.

## Snapshots and resuming

Plans, invoices and results are plain data and round-trip through dicts, so an app can hand a
top-up to the user, save the job, and pick it up later or in another process.

```python
saved = {"plan": plan.to_dict(), "invoice": invoice.to_dict()}

plan = syfthub.SearchPlan.from_dict(hub, saved["plan"])
invoice = syfthub.Invoice.from_dict(hub, saved["invoice"])
if (await invoice.refresh()).paid:
    results = await plan.execute()
```

A snapshot written by an incompatible SDK version raises `StaleSnapshot`. On the sync twin use
`hub.load(syfthub.SearchPlan, saved["plan"])`.

## Options

```python
syfthub.Options(
    timeout=syfthub.Timeout(connect=5.0, read=30.0, total=60.0, lookup=5.0),
    retry=syfthub.Retry(attempts=3, server_errors=1, backoff=0.5, max_backoff=8.0),
    http2=False,                # opt in with `pip install 'syfthub-sdk[http2]'`: see below
    circuit_breaker=syfthub.CircuitBreaker(failures=5, cooldown=30.0),
    concurrency=8,          # parallel requests across Spaces
    max_items=1000,         # catalogue pages are read up to this many sources
    user_agent=None,
    http_client=None,       # your own httpx.AsyncClient, for proxies or tests
)
```

`Timeout.lookup` is the read timeout for the balance reads behind `wallets.list` and pre-flight,
which wait on many wallet hosts at once; one slow host then delays them by at most that, and shows
as `balance=None`. Everything you ask of one host, `refresh`, a top-up, an invoice poll, the query,
keeps `read`. Idle connections stay in the pool for a minute, so a Hub call that follows a slow
fan-out does not pay a new handshake.

The circuit breaker is per Space host. A connection failure, which is a timeout, a refused
connection or a DNS error, opens it at once, since the host is down; a 5xx counts toward
`failures`. An open host is held for `cooldown` seconds, and the next execute sends one probe first
and holds the rest if it fails. Rows held this way are `retryable`, so `results.retry()` after the
cooldown re-sends them.

`http2=True` asks every host for HTTP/2, so concurrent requests to one host share a connection
instead of each opening its own, which from far away costs two round trips of TCP and TLS. It
needs `pip install 'syfthub-sdk[http2]'`, and it is decided per host: the Hub and the station
negotiate it, a Space served by bare uvicorn or over plain HTTP stays on HTTP/1.1, and nothing
breaks either way. It helps when the SDK fans out to one host, such as the Space tokens behind
`wallets.list` or several sources on one Space; a single query gains nothing.

## Errors

All errors derive from `syfthub.SyftHubError`.

| Error | When |
|---|---|
| `ConfigurationError` | Bad URL, token and password both given, invalid `Options`. |
| `ValidationError` | Also a `ValueError`: blank query, threshold out of range, malformed path, no bundle covers a shortfall. |
| `AuthError` | Login refused, or the token expired and could not be renewed. |
| `HubUnreachable` | The Hub itself cannot be reached after retries. |
| `SourceNotFound` | `hub.sources.get` on an unknown path. |
| `ActionRequired` | `execute(strict=True)` with pending actions; carries `.actions`. |
| `PaymentFailed` | A wallet, top-up or invoice call was refused; `.code` carries the Hub's code when there is one. At execute time an MPP refusal lands in the row instead. |
| `PaymentTimeout` | `invoice.wait_paid` ran out of time. |
| `StaleSnapshot` | A dict from an incompatible SDK version. |

Per-source trouble at execute time never raises; it lands in the `SourceResult` row.

## Testing your app

`syfthub.testing` ships an in-memory Hub and Spaces over `httpx.MockTransport`, with no extra
dependency, so your tests exercise the real SDK end to end.

```python
from syfthub.testing import FakeHub

fake = FakeHub()
fake.add_source("alice", "notes", description="parental leave policy")
fake.add_source("erin", "trials", price=0.05)                 # prepaid, 0.05 USD per request
fake.add_source("kim", "metered", mpp_price=0.02)             # MPP
fake.space("alice").reply("notes", documents=[{"content": "16 weeks", "score": 0.8}])
fake.space("erin").reply("trials", documents=[{"content": "phase 3", "score": 0.7}], cost=0.05)

async with fake.hub(budget=1.0) as hub:
    plan = hub.search("leave", ["alice/notes", "erin/trials"])
    pre = await plan.preflight()                     # erin/trials: NEEDS_CREDITS
    invoice = await pre.actions[0].top_up()
    fake.space("erin").pay(invoice.id)               # simulate the checkout
    results = await plan.execute()

fake.calls                                           # every request, secrets redacted
```

`FakeSpace.reject(slug, outcome="rate_limited", ...)` scripts refusals, `FakeHub.users` enforces
login, and `FakeHub.mpp_error` makes the Hub's pay route fail with a given code. The sync twin works
against the fake too: `syfthub.Hub(fake.url, token="t", options=fake.options())`.

## Logging

The SDK logs to `logging.getLogger("syfthub")`: one INFO line per execute and one DEBUG line per
request with secrets redacted. A `NullHandler` is installed, so a quiet app sees nothing.

## Examples

In `sdk/python/examples/`:

- `quickstart.ipynb` walks the SDK cell by cell against a real Hub: browse, compose, pre-flight,
  resolve what blocks, execute, retry, wallets, budget, snapshots and what the SDK sent. It reads
  `SYFTHUB_TOKEN` and pays nothing unless you flip its `PAY` switch.
- `openai_chat.py` and `openai_chat_sync.py` are the reference chat app: pre-flight, hand a top-up
  back to the user with a saved plan, resume after payment, answer with OpenAI from the retrieved
  context.
- `profile_hub.py` reports where the time goes: every request split into connection setup, the
  wait for the server and the body read, and every SDK operation split into time on the wire
  versus time in this process, per operation, per route and per source.
