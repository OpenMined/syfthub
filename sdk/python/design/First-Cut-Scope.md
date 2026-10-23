# SDK v2 First Cut Scope

Oct 8, 2026 · @Shubham

The first cut is a headless, search-only Python SDK built on what Syft Space serves today: SyftHub login, source discovery with policies and prices, wallets with balance and top-up, and compose → pre-flight → execute over any set of sources. A Hub endpoint is a source in the SDK: some answer with document chunks, some with a model's reply, and search treats them alike.&#32;

**Later: **Metadata filters, chat, the Aggregator and the notebook skin wait for a later cut.

## In and out

Everything in the first cut maps onto a route Syft Space or SyftHub serves today. The one exception is the Action model in pre-flight, which is pure client logic over Hub metadata and wallet balances.

| Area | In the first cut | Deferred |
| --- | --- | --- |
| Login | `login(username, password)`, `login(token)`, `SYFTHUB_TOKEN` env, `hub.me` | Google login (browser flow does not suit headless) |
| Sources | `list(owner=, type=, free=, tag=)`, `get`, fuzzy `matching`, `filter(...)` on a list you hold; `source.policies`, `source.pricing` | Collectives as a source alias |
| Wallets | `list`, `for_source`, `balance`, `refresh`, `top_up(bundle)` → `Invoice` | Managed-wallet admin |
| Search | plain query, `sources=[...]`, `limit`, `similarity_threshold`, `include_metadata`; model sources accepted alongside document sources | `plan.filter(**metadata)`: Spaces do not support it yet |
| Pre-flight | iterable `Preflight` with `actions`, per-source rows, estimate per wallet, session budget; skip as the one decision; execute(strict=True); to\_dict and from\_dict for resuming | Health probes; any use of the Hub's `health_status` |
| Execute | one POST per Space in parallel, retries, per-Space circuit breaker, `Results` | Streaming |
| Payments | prepaid invoice with `checkout_url`, `status`, `refresh`, `wait_paid`; MPP 402 paid inside `execute()` while within budget, else a row with an action | Paying an MPP charge before the Space asks (no route) |
| Errors | exception hierarchy for faults that stop the call; per-source failures as rows |  |
| Delivery | async API plus a sync twin (a runtime wrapper over it), `logging`, `to_dict`/`from_dict` for queues and caches | `syfthub.notebook` HTML and widgets |
| Chat |  | `hub.chat`, `results.chat`, `results.ask` |
| Aggregator |  | both forms; needs the new route |

Model sources: when a source of type `MODEL` is in `sources`, its `summary` comes back as one `Document` on that row with `score=None`, because a reply is not a similarity match. `results.documents` lists scored chunks by score and then the unscored summaries after them; `top(k)` trims the scored chunks only and always keeps the summaries. `results.chunks` is the scored subset, `results.answers` the summaries alone.

## The API on one screen

Five nouns and one verb. Low-level clients, token caching, retries and pagination sit behind them and never surface unless `Options` is passed.

```python
import syfthub

async with syfthub.AsyncHub(budget=2.00) as hub:  # url/token from SYFTHUB_URL / SYFTHUB_TOKEN
    await hub.login(username="alice", password="...")  # or login(token=...); hub.me afterwards

    # Sources: list, narrow, view (a Hub endpoint is a source here)
    sources = await hub.sources.list()  # all pages followed -> SourceList
    bobs = await hub.sources.list(owner="bob")  # one owner's sources
    picks = sources.matching("clinical trials").filter(type="data_source")
    src = await hub.sources.get("erin/trials")  # Source
    src.policies  # [Policy]: type, config, enabled
    src.pricing  # Pricing | None: price, unit, currency, wallet, bundles, mode

    # Wallets: what I share against, balances, top-up
    wallets = await hub.wallets.list()  # [Wallet]: owner, rail, currency, balance, sources
    w = await hub.wallets.for_source("erin/trials")
    await w.refresh()  # one balance call; w.balance is Money
    invoice = await w.top_up("starter")  # Invoice: checkout_url, amount, status

    # Search: compose (sync, free) -> pre-flight -> execute
    plan = hub.search(
        "adverse events in phase III",
        sources=[
            "erin/trials",
            "carol/papers",
            "bob/llama-3",
        ],  # paths, Source objects or a SourceList
        limit=5,
        similarity_threshold=0.6,
        include_metadata=True,
    )
    pre = await plan.preflight()  # Preflight: iterable, nothing sent
    for action in pre.actions:  # TopUp | OverBudget | AccessDenied | CircuitOpen
        ...  # hand to the app's user, or decide in code
    plan = plan.skip("carol/papers")  # the one decision; returns a new plan
    results = await plan.execute()  # pre-flight again, send what is allowed, hold the rest
    results = await plan.execute(strict=True)  # or: raise ActionRequired unless every row is ready

    # Resume in another process: rebuild from the query, or reload a dict the app kept
    plan = syfthub.SearchPlan.from_dict(hub, plan.to_dict())

    # Results: rows not exceptions
    results.documents  # [(path, Document)] across sources
    results["erin/trials"].outcome  # RETURNED | HELD | REJECTED | FAILED | PAYMENT_REQUIRED
    results.failed, results.actions  # rows that stopped; actions still open
    results = await results.plan.skip(
        "kim/ledger"
    ).execute()  # the plan behind the results, with its skips
    results.cost, results.to_dict()

with syfthub.Hub() as hub:
    ...  # sync twin: same names, no await
```

| Object | What it holds | Mutability |
| --- | --- | --- |
| `AsyncHub` / `Hub` | session, token cache, budget, `Options` | one per process |
| `SourceList` | sources from the Hub; `matching`, `filter`, `pick`, `+` | immutable, views return new lists |
| `Source` | Hub metadata plus `policies` and `pricing` read off the payment policy | frozen |
| `Wallet` | owner, type, currency, `balance`, sources it covers; `refresh`, `top_up` | `balance` updates on `refresh` |
| `SearchPlan` | query, sources, options, skips; `preflight`, `skip`, `execute`, `to_dict` | immutable; `skip` returns a new plan |
| `Preflight` | rows, `actions`, `estimate`, `ready` | snapshot; `refresh()` returns a new one |
| `Results` | one `SourceResult` per source; views and actions return new `Results` | immutable |

`similarity_threshold`, `limit` and `include_metadata` travel to the Space in the query body exactly as the current SDK sends them. Nothing else is added to the request.

Field-level definitions of every object, as pydantic models: Schemas

## Pre-flight as data

`await plan.preflight()` returns a `Preflight` that an application can iterate, branch on and serialise. Nothing is sent to a Space. It costs one Hub read per unknown source and one balance call per prepaid wallet.

```python
pre = await plan.preflight()

pre.ready  # True when every source will be sent and no action is open
pre.estimate  # {"USD": Money("0.35")}: max cost per currency, summed per wallet
pre.sending, pre.held  # [PlanRow]
for row in pre:  # PlanRow: source, verdict, estimate, wallet, note
    print(row.source.path, row.verdict)

for action in pre.actions:  # what a person or the app must do before sending
    action.kind  # "top_up" | "over_budget" | "access_denied" | "circuit_open"
    action.affects  # [Source] held by this one action
    action.steps  # [str]: plain-English steps, for a log line or a UI
```

One action per cause, not per source: two sources billed to the same wallet produce one `TopUp` whose `shortfall` covers both.

| Action | Fields | Resolve by |
| --- | --- | --- |
| `TopUp` | `wallet`, `shortfall: Money`, `bundles: [Bundle]`, `suggested: Bundle \| None`, `affects` | `invoice = await action.top_up()` creates a `PENDING` invoice for `suggested`, the smallest bundle that covers `shortfall`; `top_up(bundle)` names one instead. Pay at `invoice.checkout_url`, execute again. Nothing is charged until the user pays. |
| `OverBudget` | `estimate`, `budget`, `affects` | raise the budget with `hub.set_budget(x)` and execute again; or `plan.skip(*paths)` |
| `AccessDenied` | `affects`, `rule` | `plan.skip(*paths)` |
| `CircuitOpen` | `affects`, `reopens_at` | wait, or `plan.skip(*paths)` |

`Verdict` per row: `READY`, `WILL_ASK_TO_PAY` (MPP, sent anyway), `NEEDS_CREDITS`, `OVER_BUDGET`, `ACCESS_DENIED`, `CIRCUIT_OPEN`. No `UNHEALTHY`: the SDK exposes no health flag (2026-10-13, LLD decision 23).

Looking at pre-flight is optional. `plan.execute()` always runs it first, sends the rows it allows, and returns the held rows inside the same `Results` with their reasons and nothing spent on them; `results.actions` carries the same action list pre-flight would have shown. Both paths end in one `Results` object, so an app can write a single handler. For apps that want all or nothing, `execute(strict=True)` raises `ActionRequired`, carrying the actions, before anything is sent if any row is held.

Budget is per `AsyncHub` session and per currency, because publishers bill in their own currencies and the SDK never converts money: `AsyncHub(budget=2.00)` caps USD only, `AsyncHub(budget={"USD": 2.00, "IDR": 50000})` caps both, and `hub.set_budget(...)` replaces the caps. There is no budget until one is set, and a currency with no cap is not budgeted. `hub.spent` accumulates every charge the session paid, per currency, across searches. Decided 2026-10-12.

### Decisions and resuming

Actions fall into two groups, and the SDK treats them differently.

- **Facts the SDK observes.** Paying an invoice, adding credits, a Space coming back. The app tells the SDK nothing. The next `execute()` runs pre-flight again, reads the balances, and the row passes. There is no "I paid" call.
- **Decisions the SDK must apply.** There is one: `plan.skip(*paths)`, which marks those rows `HELD by_user` and returns a new plan. There is no force. A row held for `no_credits`, `access_denied` or `circuit_open` would only be refused by the Space if sent, so the SDK never offers to send it; a row held for `over_budget` is released by raising the budget, the one knob, and executing again.

A plan is a pure function of its query, sources, options and decisions. Everything else, prices, access and balances, is read fresh at pre-flight. So the SDK holds no state between a pause and a resume, and the app has two equivalent ways back: rebuild the plan from the query and the decisions its user sent back, or reload a snapshot it chose to keep. `to_dict()` is a convenience, not a requirement:

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

The app owns persistence: where the dict goes, what key it sits under, and when a saved plan is abandoned. The SDK stamps `version` and `created_at` so a stale snapshot is re-priced rather than trusted. The dict is authority to spend money, so it should be written server-side and never round-tripped through a browser. `results.plan` returns the plan behind a `Results`, carrying its decisions, so retrying after a restart is the same call as executing after one.

## Payments

A payment is a user action that happens outside the process, so the SDK models it as a durable object with a status the app can poll, persist and resume from. Two families exist on Syft Space today.

**Prepaid (stripe, xendit, managed wallet).** One verb creates an invoice: `wallet.top_up(bundle)` on a wallet, or `action.top_up(bundle=None)` on a `TopUp` action, which defaults to `action.suggested`. Both call the Space's invoice route and return a `PENDING` `Invoice`; prepaid rails sell fixed bundles only, so the SDK never sizes a purchase, it only points at the smallest bundle that covers the shortfall. Nothing is charged until the user pays at `checkout_url`.

```python
invoice = await action.top_up()  # the suggested bundle; or top_up("starter")
invoice.id, invoice.checkout_url, invoice.amount, invoice.wallet_key
invoice.status  # PENDING | PAID | EXPIRED | FAILED
await invoice.refresh()  # GET invoices_url (my invoices), match by id; balance as fallback
await invoice.wait_paid(timeout=600, poll=5)  # headless: polls until PAID or raises PaymentTimeout
invoice.to_dict() / await hub.wallets.invoice(
    wallet_key, invoice_id
)  # persist, then pick up in another process
```

| Status | Meaning | App should |
| --- | --- | --- |
| `PENDING` | invoice created, checkout not completed | show `checkout_url`, store `invoice.id`, poll or `wait_paid` |
| `PAID` | provider webhook landed, balance rose | `plan.execute()` or `results.retry()` |
| `EXPIRED` | checkout link lapsed | `action.top_up(...)` again |
| `FAILED` | provider declined | surface to the user; do not retry automatically |

**MPP (experimental, not a priority in this cut).** No charge exists before the Space answers 402, so pre-flight can only flag `WILL_ASK_TO_PAY`. During `execute()` the SDK pays each 402 challenge through the Hub wallet route and re-sends with `X-Payment`, as long as the charge fits the remaining session budget. The app sees a normal `RETURNED` row with `charge` filled in and `hub.spent` updated. A charge that would cross the budget stops: the row comes back `PAYMENT_REQUIRED` with a `Charge` and an `OverBudget` action, and the app raises the budget and executes again, or skips the source. The budget is the one knob. With no budget set, MPP charges are paid as the Spaces ask. The Hub wallet itself is topped up outside the SDK; if it cannot cover a challenge, the row is `PAYMENT_REQUIRED` with `error` from the Hub and steps that say to top up in the SyftHub UI. The pay call carries a client-generated `Idempotency-Key`, stored in the snapshot, so a crash between paying and re-sending cannot charge twice once the Hub honours the header.

Balances are never trusted from cache for a decision: pre-flight always refreshes the prepaid wallets it needs, and `wallet.balance` carries `refreshed_at`.

## Errors

The rule: a fault that stops the whole call raises; a fault that stops one source becomes a row. An app catches `syfthub.SyftHubError` once and reads `results.failed` for the rest.

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

Per-source faults are rows on `Results`, never exceptions, so one offline Space does not lose the other four answers.

| Outcome | Who stopped it | `reason` values | Retryable |
| --- | --- | --- | --- |
| `RETURNED` | nobody |  |  |
| `HELD` | pre-flight, nothing spent | `no_credits`, `over_budget`, `access_denied`, `circuit_open`, `by_user` | after the action |
| `REJECTED` | the Space's policy, 403 | `no_credits`, `rate_limited`, `access_denied`, `no_pricing_tier`, `blocked` | `rate_limited`, `no_credits` |
| `FAILED` | transport or server, after retries | `unreachable`, `timeout`, `server_error`, `not_found`, `auth` | all but `not_found` |
| `PAYMENT_REQUIRED` | an MPP Space, 402 |  | raise the budget, then execute again |

Every `SourceResult` keeps `status_code`, `error` (message from the Space's 403 envelope or the transport), `attempts`, `elapsed_ms` and the verbatim `raw` body, so an app can log exactly what happened without the SDK deciding what matters. `results.failed` lists `REJECTED` and `FAILED` rows; `results.ok` lists `RETURNED` ones. A rate limit is never waited out inside the call: the Space's 403 comes back as `REJECTED rate_limited` with `rate_limit.reset_seconds` on the row, retryable, and the app decides when to call `results.retry()`.

Logging goes to `logging.getLogger("syfthub")`: one INFO line per `execute()` with counts and cost, DEBUG per request with `Authorization`, `X-Payment` and `WWW-Authenticate` redacted.

## Example: a chat app on OpenAI with SyftHub as retrieval

The app takes a question, retrieves passages from three SyftHub sources, and passes them to OpenAI as context. Payments are the only part that can pause, so the retrieval step is written as a function that either returns `Results` or returns a `TopUp` the UI must show. Everything else is straight-line code.

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

What the SDK did for the app, without the app asking:

- Minted and cached one satellite token per Space, refreshed it before expiry, and re-minted once on a 401.
- Called the three Spaces in parallel, retried `kim/ledger` once on a 503, and tripped nothing.
- Refreshed the two prepaid wallets, found `erin/trials` short, and returned one `TopUp` instead of sending a request that would have been rejected.
- Paid an MPP charge on `kim/ledger` because it fit the remaining budget, and recorded it in `hub.spent`.
- Turned a `bob/llama-3` summary into a `Document` so the context loop did not need a special case, had a model been in `SOURCES`.

For a web service the `payment_required` dictionary goes back to the client as JSON. The client opens the checkout URL and later calls a second route that runs `resume()`. `store` and `job_id` are the app's own: the SDK hands over plain dicts from `to_dict()` and takes them back with `from_dict()`, and never decides where they live. Because `SearchPlan`, `Invoice` and `Results` all serialise this way, the pause can span processes, a queue, or days.

The sync twin is the same example with `syfthub.Hub`, no `await`, and the OpenAI sync client. Nothing else changes.

## Flow

&#91;embedded content: request path · one decision, one payment loop\]

The only branch is the pre-flight gate. A `TopUp` sends the app around the payment loop and back into pre-flight; every other action is resolved in code by skipping the source or raising the budget. MPP charges are paid inside `execute()` while they fit the budget; one that does not comes back as a row with an action, still on the bottom row.

## Open questions

All resolved on 2026-10-08.

- [x] MPP with no session budget: pay every challenge as asked. The Hub wallet is topped up outside the SDK; an empty one surfaces as a `PAYMENT_REQUIRED` row.
- [x] Invoice status: no invoice-by-id route. The policy publishes `payment_url`, `invoices_url` and `credits_url`; `refresh()` lists and matches by id, balance as fallback. The SDK follows these URLs and never builds one.
- [x] Idempotency key: the SDK sends a client-generated `Idempotency-Key` on the Hub wallet-pay call from day one and stores it in the snapshot; the Hub honours it as a follow-up (a key-to-response table with a 24 h expiry).
- [x] Model sources: the summary `Document` carries `score=None`. Scored chunks first, summaries after; `top(k)` trims chunks only.
- [x] Sync twin: a runtime wrapper over the async client, with a private event loop on a background thread so it also works where a loop is already running. Generated stubs for IDE typing can come later.
- [x] Rate limits: the app decides. No in-call wait; `REJECTED rate_limited` with `reset_seconds`, retryable. `Retry.rate_limit_wait` is gone.
- [x] Wallet id: the policy config carries `wallet_id`; `Wallet.id` reads it and wallets group by it.
