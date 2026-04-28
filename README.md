<div align="center">

# SyftHub

**The home for AI/ML endpoints.**

Discover, share, and run AI models and data sources — like GitHub, but for endpoints.

[![CI](https://github.com/IonesioJunior/syfthub/actions/workflows/ci.yml/badge.svg)](https://github.com/IonesioJunior/syfthub/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

[Documentation](docs/index.md) · [Python SDK](sdk/python) · [TypeScript SDK](sdk/typescript) · [Go SDK](sdk/golang) · [Contributing](CONTRIBUTING.md)

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
- **First-class SDKs** for Python, TypeScript, and Go, plus a CLI.

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

## Using the SDKs

```python
# Python
from syfthub_sdk import SyftHubClient

client = SyftHubClient(base_url="https://hub.syft.com")
client.auth.login(email="alice@example.com", password="...")

for endpoint in client.hub.browse():
    print(endpoint.name)
```

```typescript
// TypeScript
import { SyftHubClient } from '@syfthub/sdk';

const client = new SyftHubClient({ baseUrl: 'https://hub.syft.com' });
await client.auth.login({ email: 'alice@example.com', password: '...' });

for await (const endpoint of client.hub.browse()) {
  console.log(endpoint.name);
}
```

See the [SDK guides](sdk/README.md) for the full reference.

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
├── sdk/               official SDKs (python, typescript, go)
├── cli/               command-line client
├── deploy/            deployment configs
└── docs/              documentation
```

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). For release process and versioning, see [RELEASING.md](RELEASING.md).

## License

[Apache 2.0](LICENSE)
