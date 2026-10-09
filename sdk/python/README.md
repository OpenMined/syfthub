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

## Development

```bash
uv sync --all-extras
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/unit
```
