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
is set (see [Options](client.md#options)).

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

## Guides

One page per thing you do with the SDK. Read them in order the first time; after that each one
stands on its own.

| Page | What it covers |
|---|---|
| [Client](client.md) | `AsyncHub` and the sync `Hub`, environment variables, login, `Options`, logging |
| [Sources](sources.md) | Browsing the catalogue, `Source` and `SourceList`, what a source publishes |
| [Searching](search.md) | Composing a plan, pre-flight verdicts, decisions, executing, retrying, saving and resuming |
| [Filtering by metadata](filters.md) | The `F` builder, `source.where`, the published filter schema, what is refused and where |
| [Money](money.md) | Session budget per currency, prepaid wallets and top-ups, metered sources |
| [Errors](errors.md) | What raises, what lands in a row, and the outcome and reason codes |
| [Testing your app](testing.md) | `FakeHub`: an in-memory Hub and Spaces for your tests |
| [API reference](reference.md) | Every public name, one line each; `help()` has the rest |

## Examples

Runnable programs in [`sdk/python/examples/`](../../../sdk/python/examples/README.md): a notebook
that walks the SDK against a real Hub, a chat app with SyftHub as retrieval (async, sync, and with
metadata filters), and a profiler that reports where the time goes.
