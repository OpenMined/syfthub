# Searching

[← Python SDK guide](README.md)

A search is a plan you compose, check, adjust and then run. Nothing leaves your process until
`execute`.

## Composing a plan

```python
plan = hub.search(
    "adverse events in phase 3",
    ["erin/trials", "carol/papers"],   # paths, Source objects, a SourceList, or source.where(...)
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

To narrow one source by document metadata, pass `source.where(...)` in place of its path; see
[Filtering by metadata](filters.md).

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

The checks run in the order skip, reachability, access, circuit, pricing, credits, budget, and a
source held by an earlier check is never contacted by a later one. Credits are checked per wallet:
if several sources share one wallet that is short, all of them are held and one `TopUp` carries the
combined shortfall. Budget is checked in plan order and per currency: the first row that would
cross its currency's cap and every paid row in that currency after it are held. A currency with no
cap is not budgeted.

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

row = results["erin/trials"]
row.metadata_fields    # the metadata keys this response declared, from the Space itself
row.chunks[0].metadata # the dict on each Document: those keys, and only those; read with .get
row.chunks[0].image_urls  # metadata["image_urls"] made absolute against the Space's origin
```

Requests fan out in parallel, bounded by `Options.concurrency`, one request per source. A 401 from
a Space re-mints that Space's token once and retries. Timeouts and connection errors retry per
`Options.retry`; a 5xx is retried once (`Retry.server_errors`), since a server that answered is
unlikely to answer differently a moment later and a fan-out hides nothing by waiting.

Per-source trouble never raises. Each `SourceResult` has an `Outcome` and, when it did not return,
a `Reason`; the codes are listed in [Errors](errors.md#per-source-outcomes).

## Retrying and views

`results.retry()` re-sends only the retryable rows, with the same filters, and merges the fresh
rows in. `only`, `drop` and `top(k)` return views for presentation; `a + b` merges two results
over the same plan.

## Saving and resuming

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
