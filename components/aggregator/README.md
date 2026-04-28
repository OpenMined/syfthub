# SyftHub Aggregator

A small, stateless service that turns published endpoints into a chat experience: it pulls relevant context from data sources, hands the prompt to a model, and streams the answer back.

For project-level docs, see the [repository README](../../README.md) and [`docs/`](../../docs/index.md).

## What it does

When you chat with an endpoint on SyftHub, the aggregator:

1. Queries the selected data sources in parallel for relevant documents.
2. Builds a prompt that grounds the model in what was retrieved.
3. Calls the model endpoint and streams tokens back to the caller.

It holds no state — every request carries the connection details it needs, which keeps deployment simple and horizontal scaling cheap.

## Running locally

From the repo root, `make dev` starts the aggregator alongside the rest of the stack at <http://localhost:8080/aggregator>.

To run it on its own:

```bash
cd components/aggregator
uv sync
uv run uvicorn aggregator.main:app --reload --port 8001
```

## Learn more

- [Aggregator architecture](../../docs/architecture/components/aggregator.md)
- [Aggregator API reference](../../docs/api/aggregator.md)
- [RAG architecture explained](../../docs/explanation/rag-architecture.md)
