# Python SDK Guide

## Installation

```bash
pip install syfthub-sdk
# or
uv add syfthub-sdk
```

**Version:** 0.1.1 | **Requires:** Python >= 3.10

## Client Setup

```python
from syfthub import SyftHubClient

client = SyftHubClient(
    base_url="http://localhost:8080",
    timeout=30.0,
    aggregator_url="http://localhost:8080",
    api_token="syft_pat_...",  # optional, for PAT-based auth
)
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | Base URL of the hub |
| `SYFTHUB_AGGREGATOR_URL` | Aggregator service URL |
| `SYFTHUB_API_TOKEN` | Personal access token |

## Authentication

```python
# Login with credentials
client.login("username", "password")

# Register a new account
client.register("username", "user@example.com", "password", "Full Name")

# Get current user
user = client.me()

# Refresh tokens
client.refresh()

# Change password
client.change_password("old_password", "new_password")

# Logout
client.logout()
```

### Token Persistence

Save and restore tokens across sessions:

```python
tokens = client.get_tokens()
# Store tokens externally...

# Later, restore them:
client.set_tokens(tokens)
```

## Resources

| Resource | Access |
|----------|--------|
| Auth | `client.login()`, `client.register()`, etc. |
| Users | `client.users` |
| My Endpoints | `client.my_endpoints` |
| Hub (Browse) | `client.hub` |
| Chat (RAG) | `client.chat` |
| SyftAI | `client.syftai` |
| API Tokens | `client.api_tokens` |
| Accounting | `client.accounting` |

## Endpoints

```python
# Create
endpoint = client.my_endpoints.create({
    "name": "My Model",
    "type": "model",
    "visibility": "public",
    "description": "A text generation model",
})

# List your endpoints
endpoints = client.my_endpoints.list()

# Get one by slug
endpoint = client.my_endpoints.get("my-model")

# Update
client.my_endpoints.update("my-model", {"description": "Updated description"})

# Delete
client.my_endpoints.delete("my-model")
```

## Browse and Search

```python
# Browse public endpoints
results = client.hub.browse()

# Trending endpoints
trending = client.hub.trending()

# Search
results = client.hub.search("text generation")
```

## Chat (RAG Queries)

```python
response = client.chat(
    prompt="What models are available for text generation?",
    model="owner/model-slug",
    data_sources=["owner/data-source-slug"],
)
```

## API Tokens

```python
# Create a personal access token
token = client.api_tokens.create({"name": "CI token"})

# List tokens
tokens = client.api_tokens.list()

# Revoke a token
client.api_tokens.revoke(token_id)
```

## Accounting

```python
balance = client.accounting.balance()
transactions = client.accounting.transactions()
```

## Cleanup

Always close the client when done to release HTTP connections:

```python
client.close()
```

Or use it as a context manager if supported by your version.
