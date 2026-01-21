# SyftHub SDK

Python SDK for interacting with the SyftHub API programmatically.

## Installation

```bash
# Using pip
pip install syfthub-sdk

# Using uv
uv add syfthub-sdk

# From source
cd sdk
uv sync
```

## Quick Start

```python
from syfthub_sdk import SyftHubClient

# Initialize client
client = SyftHubClient(base_url="https://hub.syft.com")

# Register a new user
user = client.auth.register(
    username="john",
    email="john@example.com",
    password="secret123",
    full_name="John Doe"
)

# Login
user = client.auth.login(username="john", password="secret123")
print(f"Logged in as {user.username}")

# Get current user
me = client.auth.me()
```

## Managing Your Endpoints

```python
# List your endpoints (with lazy pagination)
for endpoint in client.my_endpoints.list():
    print(f"{endpoint.name} ({endpoint.visibility})")

# Get just the first page
first_page = client.my_endpoints.list().first_page()

# Create an endpoint
endpoint = client.my_endpoints.create(
    name="My Cool API",
    visibility="public",
    description="A really cool API",
    readme="# My API\n\nThis is my API documentation."
)
print(f"Created: {endpoint.slug}")

# Update an endpoint
endpoint = client.my_endpoints.update(
    endpoint_id=endpoint.id,
    description="Updated description"
)

# Delete an endpoint
client.my_endpoints.delete(endpoint_id=endpoint.id)
```

## Browsing the Hub

```python
# Browse public endpoints
for endpoint in client.hub.browse():
    print(f"{endpoint.path}: {endpoint.name}")

# Get trending endpoints
for endpoint in client.hub.trending(min_stars=10):
    print(f"{endpoint.name} - {endpoint.stars_count} stars")

# Get a specific endpoint by path
endpoint = client.hub.get("alice/cool-api")
print(endpoint.readme)

# Star/unstar endpoints (requires auth)
client.hub.star("alice/cool-api")
client.hub.unstar("alice/cool-api")

# Check if you've starred an endpoint
if client.hub.is_starred("alice/cool-api"):
    print("You've starred this!")
```

## User Profile

```python
# Update profile
user = client.users.update(
    full_name="John D.",
    avatar_url="https://example.com/avatar.png"
)

# Check username availability
if client.users.check_username("newusername"):
    print("Username is available!")

# Change password
client.auth.change_password(
    current_password="old123",
    new_password="new456"
)
```

## Accounting

```python
# Get account balance
balance = client.accounting.balance()
print(f"Credits: {balance.credits} {balance.currency}")

# List transactions
for tx in client.accounting.transactions():
    print(f"{tx.created_at}: {tx.amount} - {tx.description}")
```

## Token Persistence

```python
# Get tokens for saving
tokens = client.get_tokens()
if tokens:
    # Save to file, database, etc.
    save_tokens(tokens.access_token, tokens.refresh_token)

# Later, restore session
from syfthub_sdk import AuthTokens

tokens = AuthTokens(
    access_token=load_access_token(),
    refresh_token=load_refresh_token()
)
client.set_tokens(tokens)
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | SyftHub API base URL |

## Error Handling

```python
from syfthub_sdk import (
    SyftHubError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
    ConfigurationError,
)

try:
    client.auth.login(username="john", password="wrong")
except AuthenticationError as e:
    print(f"Login failed: {e}")
except SyftHubError as e:
    print(f"API error [{e.status_code}]: {e.message}")
```

## Context Manager

```python
with SyftHubClient(base_url="https://hub.syft.com") as client:
    client.auth.login(username="john", password="secret123")
    # ... do work ...
# Client is automatically closed
```

## Pagination

All list methods return a `PageIterator` for lazy pagination:

```python
# Iterate through all items (fetches pages as needed)
for endpoint in client.my_endpoints.list():
    print(endpoint.name)

# Get just the first page
first_page = client.my_endpoints.list().first_page()

# Get all items as a list
all_items = client.my_endpoints.list().all()

# Get first N items
top_10 = client.my_endpoints.list().take(10)
```

## License

MIT
