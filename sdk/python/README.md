# SyftHub Python SDK

[![PyPI](https://img.shields.io/pypi/v/syfthub-sdk.svg)](https://pypi.org/project/syfthub-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/syfthub-sdk.svg)](https://pypi.org/project/syfthub-sdk/)

`syfthub` is the Python client for [SyftHub](https://syfthub.org). Log in once, pick the sources
you want to search, see what each one will cost and need before anything is sent, then run the
search. Queries go straight from your process to each publisher's Space; the Hub is only consulted
for the catalogue, the per-Space tokens and, for metered sources, the payment credential.

## Documentation

The full guide is at
**[docs/python/guides/sdk.md](https://github.com/OpenMined/syfthub/blob/main/docs/python/guides/sdk.md)**:
sources, pre-flight, decisions, wallets, budgets, snapshots, options and errors.

Runnable examples, including a notebook and a chat app with SyftHub as retrieval, are in
[examples/](https://github.com/OpenMined/syfthub/tree/main/sdk/python/examples).

## Installation

```bash
pip install --pre syfthub-sdk            # pre-release until the first stable 2.x tag
pip install --pre 'syfthub-sdk[http2]'   # with HTTP/2, for Options(http2=True)
```

Requires Python 3.11 or newer.

## Quick start

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

The sync twin is the same API without `await`:

```python
with syfthub.Hub(token="...") as hub:
    results = hub.search("adverse events in phase 3", ["erin/trials"]).execute()
```

## Testing your app

`syfthub.testing.FakeHub` stands in for a Hub and its Spaces, with no extra dependency. See
[Testing your app](https://github.com/OpenMined/syfthub/blob/main/docs/python/guides/sdk.md#testing-your-app)
in the guide.

## Development

```bash
uv sync --all-extras
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/unit
uv run python scripts/gen_sync_stub.py   # after changing a public async method or what it returns
```

`src/syfthub/_sync.pyi` and `src/syfthub/sync.py` are generated from the async package. A unit
test fails until they are regenerated.

## License

Apache 2.0. See [LICENSE](https://github.com/OpenMined/syfthub/blob/main/LICENSE).
