<div align="center">

<img src="components/frontend/public/favicon/openmined-icon.svg" alt="OpenMined" width="120" />

# SyftHub

**The home for AI/ML endpoints.**

Discover, share, and run AI models and data sources — like GitHub, but for endpoints.

[![CI](https://github.com/IonesioJunior/syfthub/actions/workflows/ci.yml/badge.svg)](https://github.com/IonesioJunior/syfthub/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

[Documentation](docs/index.md) · [Python SDK](sdk/python) · [Contributing](CONTRIBUTING.md)

</div>

---

## What is SyftHub?

SyftHub is a registry and discovery platform for AI/ML endpoints. Publish a model or a data source, point friends or teammates at it, and let anyone build on top of it — through a web UI, an SDK, or a chat interface backed by retrieval-augmented generation.

If you've ever wished there were a single place to find the model your team's been talking about, share your own, or wire one into a chat app without standing up new infrastructure — that's what SyftHub is for.

## Highlights

- **Browse and discover** public models and data sources, sorted by popularity and freshness.
- **Publish your own** with public, internal, or private visibility, full markdown READMEs, and versioning.
- **Chat with endpoints** — built-in RAG aggregator orchestrates retrieval and generation across endpoints.
- **Collaborate in organizations** with role-based access for teams.
- **Federated identity** — SyftHub issues short-lived signed tokens so satellite services can verify users without phoning home.
- **A Python SDK** that searches sources, shows what each one costs and needs before anything is sent, and pays metered sources on the way.

## Quick Start

Clone, copy the env template, and run:

```bash
git clone https://github.com/IonesioJunior/syfthub.git
cd syfthub
cp .env.example .env
make dev
```

The full stack starts behind nginx at <http://localhost:8080>. API docs live at <http://localhost:8080/docs>.

To stop everything: `make stop`.

## Using the Python SDK

```python
# Python (syfthub-sdk 2.x: pip install --pre syfthub-sdk)
import syfthub

with syfthub.Hub(token="syft_pat_...", budget=1.00) as hub:   # optional cap, per currency
    for source in hub.sources.list():
        print(source.path, source.pricing)

    plan = hub.search("adverse events in phase 3", ["erin/trials", "carol/papers"])
    pre = plan.preflight()                 # what each source costs and needs; nothing sent
    results = plan.skip(*(row.path for row in pre.held)).execute()
    for path, doc in results.documents:
        print(path, doc.score, doc.content[:80])
```

See the [Python SDK guide](docs/python/guides/sdk.md) for the full reference.

The TypeScript SDK, the Go SDK and the `syft` CLI are retired. Their last state is kept on the
[`legacy-sdks`](https://github.com/OpenMined/syfthub/tree/legacy-sdks) branch, and the published
packages (`@syfthub/sdk` 0.3.1 on npm, `syfthub-sdk` 0.3.1 on PyPI) stay available for existing
users. The TypeScript client now lives in `components/frontend/sdk` as part of the web app.

## Documentation

Full docs live in [`docs/`](docs/index.md):

- [Architecture overview](docs/architecture/overview.md) — services, data flow, tokens.
- [Local setup](docs/guides/local-setup.md) — clone to running.
- [Publishing endpoints](docs/guides/publishing-endpoints.md) — share your first model.
- [API reference](docs/api/backend.md) — backend, aggregator, MCP.
- [Runbooks](docs/runbooks/deploy.md) — deploy, rollback, incident response.

## Project layout

```
syfthub/
├── components/        services (backend, frontend, aggregator, mcp)
├── sdk/               the Python SDK
├── deploy/            deployment configs
└── docs/              documentation
```

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). For release process and versioning, see [RELEASING.md](RELEASING.md).

## License

[Apache 2.0](LICENSE)
