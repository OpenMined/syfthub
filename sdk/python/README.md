# SyftHub Python SDK

`syfthub` is the Python client for [SyftHub](https://syfthub.org): log in once, pick the sources you
want to search, see what each one will cost and need before anything is sent, then run the search.

This is **v2**. It replaces the earlier `syfthub_sdk` package under the same distribution name,
`syfthub-sdk`. The 0.x line stays on PyPI for existing pins.

## Status

First cut, under construction: headless and search-only. Chat, metadata filters and the Aggregator
come in later cuts.

## Install

```bash
pip install syfthub-sdk
```

## Quick start

```python
import syfthub

async with syfthub.AsyncHub(token="...", budget=1.00) as hub:      # or SYFTHUB_TOKEN
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

`syfthub.testing.FakeHub` stands in for a Hub and its Spaces in your own tests, with no extra
dependency. See `examples/` for the reference chat app and `tests/unit/test_testing.py` for the fake.

## Development

```bash
uv sync --all-extras
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/unit
```
