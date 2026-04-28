# SyftHub Python SDK

The official Python client for [SyftHub](https://github.com/IonesioJunior/syfthub) — browse endpoints, publish your own, and run RAG chats from a script or notebook.

## Install

```bash
pip install syfthub-sdk
# or
uv add syfthub-sdk
```

## Quick start

```python
from syfthub_sdk import SyftHubClient

client = SyftHubClient(base_url="https://hub.syft.com")

# Sign in
client.auth.login(email="alice@example.com", password="...")

# Browse the hub
for endpoint in client.hub.browse():
    print(endpoint.path, "—", endpoint.name)

# Publish your own
endpoint = client.my_endpoints.create(
    name="My Cool API",
    visibility="public",
    description="A really cool API",
)

# Star something you like
client.hub.star("alice/cool-api")
```

The client supports context managers, lazy pagination on every `list()`, token persistence via `client.get_tokens()` / `client.set_tokens(...)`, and typed exceptions (`AuthenticationError`, `NotFoundError`, `ValidationError`, …) for graceful error handling.

## Documentation

- [Python SDK guide](../../docs/guides/python-sdk.md) — full walkthrough with examples.
- [Backend API reference](../../docs/api/backend.md) — every endpoint the SDK calls.

## Configuration

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | SyftHub API base URL |

## License

[Apache 2.0](../../LICENSE)
