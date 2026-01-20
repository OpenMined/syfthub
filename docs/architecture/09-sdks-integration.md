# SyftHub SDKs Integration Guide

> Comprehensive documentation for the Python and TypeScript SDKs - dual implementations with identical APIs for seamless SyftHub integration.

## Table of Contents

- [Overview](#overview)
- [Design Philosophy](#design-philosophy)
- [Installation](#installation)
- [Client Initialization](#client-initialization)
- [Authentication](#authentication)
- [Resources](#resources)
  - [Auth Resource](#auth-resource)
  - [Users Resource](#users-resource)
  - [Hub Resource](#hub-resource)
  - [MyEndpoints Resource](#myendpoints-resource)
  - [Chat Resource](#chat-resource)
  - [Accounting Resource](#accounting-resource)
  - [SyftAI Resource](#syftai-resource)
- [Streaming](#streaming)
- [Pagination](#pagination)
- [Error Handling](#error-handling)
- [Type Definitions](#type-definitions)
- [Advanced Patterns](#advanced-patterns)
- [Best Practices](#best-practices)

---

## Overview

SyftHub provides official SDKs in two languages:

| SDK | Package | Runtime Requirements |
|-----|---------|---------------------|
| **Python** | `syfthub-sdk` | Python 3.10+ |
| **TypeScript** | `@syfthub/sdk` | Node.js 18+ / Modern browsers |

Both SDKs share:
- **Identical API surface** - Same resource names, method names, and parameters
- **Resource-based architecture** - Organized around API resources (auth, hub, endpoints, etc.)
- **Automatic token management** - Handles refresh tokens transparently
- **Type safety** - Full type definitions (Pydantic models / TypeScript interfaces)
- **Streaming support** - Server-Sent Events for chat operations

---

## Design Philosophy

### Resource-Based Architecture

The SDKs follow a resource-oriented design where each API domain is encapsulated in a dedicated resource class:

```
SyftHubClient
    ├── auth          # Authentication operations
    ├── users         # User profile management
    ├── hub           # Browse public endpoints
    ├── myEndpoints   # Manage your endpoints (CRUD)
    ├── chat          # RAG-augmented conversations
    ├── accounting    # Billing and transactions
    └── syftai        # Direct SyftAI-Space queries
```

### Naming Conventions

| Concept | Python | TypeScript |
|---------|--------|------------|
| Resource access | `client.my_endpoints` | `client.myEndpoints` |
| Method names | `snake_case` | `camelCase` |
| Model fields | `snake_case` | `camelCase` |
| Enums | `EndpointType.MODEL` | `EndpointType.MODEL` |

---

## Installation

### Python

```bash
# Using pip
pip install syfthub-sdk

# Using poetry
poetry add syfthub-sdk

# Using uv
uv add syfthub-sdk
```

**Requirements:**
- Python 3.10 or higher
- Dependencies: `httpx`, `pydantic>=2.0`

### TypeScript

```bash
# Using npm
npm install @syfthub/sdk

# Using yarn
yarn add @syfthub/sdk

# Using pnpm
pnpm add @syfthub/sdk
```

**Requirements:**
- Node.js 18+ (for native fetch) or modern browser
- No external dependencies required

---

## Client Initialization

### Basic Initialization

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk import SyftHubClient

# With explicit URL
client = SyftHubClient(
    base_url="https://hub.syft.com"
)

# Using environment variable
# Set SYFTHUB_URL=https://hub.syft.com
client = SyftHubClient()
```

</td>
<td>

```typescript
import { SyftHubClient } from '@syfthub/sdk';

// With explicit URL
const client = new SyftHubClient({
  baseUrl: 'https://hub.syft.com'
});

// Using environment variable
// Set SYFTHUB_URL=https://hub.syft.com
const client = new SyftHubClient();
```

</td>
</tr>
</table>

### Configuration Options

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
client = SyftHubClient(
    # Required (or from SYFTHUB_URL env)
    base_url="https://hub.syft.com",

    # Request timeout in seconds (default: 30)
    timeout=60.0,

    # Aggregator URL (default: {base_url}/aggregator/api/v1)
    # Or from SYFTHUB_AGGREGATOR_URL env
    aggregator_url="https://agg.syft.com/api/v1",

    # Accounting service credentials (optional)
    # Or from SYFTHUB_ACCOUNTING_* env vars
    accounting_url="https://accounting.syft.com",
    accounting_email="user@example.com",
    accounting_password="secret",
)
```

</td>
<td>

```typescript
const client = new SyftHubClient({
  // Required (or from SYFTHUB_URL env)
  baseUrl: 'https://hub.syft.com',

  // Request timeout in ms (default: 30000)
  timeout: 60000,

  // Aggregator URL (default: {baseUrl}/aggregator/api/v1)
  // Or from SYFTHUB_AGGREGATOR_URL env
  aggregatorUrl: 'https://agg.syft.com/api/v1',

  // Accounting service credentials (optional)
  // Or from SYFTHUB_ACCOUNTING_* env vars
  accountingUrl: 'https://accounting.syft.com',
  accountingEmail: 'user@example.com',
  accountingPassword: 'secret',
});
```

</td>
</tr>
</table>

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SYFTHUB_URL` | Base URL for SyftHub API | Yes (if not passed to constructor) |
| `SYFTHUB_AGGREGATOR_URL` | Aggregator service URL | No (defaults to `{base_url}/aggregator/api/v1`) |
| `SYFTHUB_ACCOUNTING_URL` | Accounting service URL | No (required for accounting operations) |
| `SYFTHUB_ACCOUNTING_EMAIL` | Accounting auth email | No (required for accounting operations) |
| `SYFTHUB_ACCOUNTING_PASSWORD` | Accounting auth password | No (required for accounting operations) |

### Context Manager / Cleanup

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Using context manager (recommended)
with SyftHubClient() as client:
    client.auth.login(
        username="alice",
        password="secret123"
    )
    # Client is automatically closed

# Manual cleanup
client = SyftHubClient()
try:
    # ... use client
finally:
    client.close()
```

</td>
<td>

```typescript
// Manual cleanup (optional)
const client = new SyftHubClient();
try {
  await client.auth.login('alice', 'secret123');
  // ... use client
} finally {
  client.close();
}

// Note: close() is currently a no-op in TypeScript
// but may be used for connection pooling in future
```

</td>
</tr>
</table>

---

## Authentication

### Login

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Login with credentials
user = client.auth.login(
    username="alice",  # or email
    password="secret123"
)
print(f"Logged in as {user.username}")

# Shorthand method on client
user = client.login(
    username="alice",
    password="secret123"
)
```

</td>
<td>

```typescript
// Login with credentials
const user = await client.auth.login(
  'alice',  // or email
  'secret123'
);
console.log(`Logged in as ${user.username}`);
```

</td>
</tr>
</table>

### Registration

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
user = client.auth.register(
    username="alice",
    email="alice@example.com",
    password="SecurePass123!",
    full_name="Alice Smith",
    # Optional: set accounting password
    accounting_password="custom_password",
)

# Shorthand method on client
user = client.register(
    username="alice",
    email="alice@example.com",
    password="SecurePass123!",
    full_name="Alice Smith",
)
```

</td>
<td>

```typescript
const user = await client.auth.register({
  username: 'alice',
  email: 'alice@example.com',
  password: 'SecurePass123!',
  fullName: 'Alice Smith',
  // Optional: set accounting password
  accountingPassword: 'custom_password',
});
```

</td>
</tr>
</table>

### Token Management

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Check authentication status
if client.is_authenticated:
    print("Client is authenticated")

# Get tokens for persistence
tokens = client.get_tokens()
if tokens:
    # Save to file/database
    save_tokens(tokens.access_token,
                tokens.refresh_token)

# Restore tokens later
from syfthub_sdk.models import AuthTokens
client.set_tokens(AuthTokens(
    access_token=saved_access,
    refresh_token=saved_refresh,
))

# Manually refresh token
client.auth.refresh()
# Or shorthand:
client.refresh()
```

</td>
<td>

```typescript
// Check authentication status
if (client.isAuthenticated) {
  console.log('Client is authenticated');
}

// Get tokens for persistence
const tokens = client.getTokens();
if (tokens) {
  // Save to localStorage/database
  localStorage.setItem('tokens',
    JSON.stringify(tokens));
}

// Restore tokens later
const saved = JSON.parse(
  localStorage.getItem('tokens')!
);
client.setTokens(saved);

// Manually refresh token
await client.auth.refresh();
```

</td>
</tr>
</table>

### Logout

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
client.auth.logout()
# Or shorthand:
client.logout()
```

</td>
<td>

```typescript
await client.auth.logout();
```

</td>
</tr>
</table>

### Change Password

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
client.auth.change_password(
    current_password="old_secret",
    new_password="new_secret123",
)
# Or shorthand:
client.change_password(
    current_password="old_secret",
    new_password="new_secret123",
)
```

</td>
<td>

```typescript
await client.auth.changePassword(
  'old_secret',
  'new_secret123'
);
```

</td>
</tr>
</table>

### Get Current User

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
me = client.auth.me()
# Or shorthand:
me = client.me()

print(f"ID: {me.id}")
print(f"Username: {me.username}")
print(f"Email: {me.email}")
print(f"Full Name: {me.full_name}")
print(f"Role: {me.role}")
```

</td>
<td>

```typescript
const me = await client.auth.me();

console.log(`ID: ${me.id}`);
console.log(`Username: ${me.username}`);
console.log(`Email: ${me.email}`);
console.log(`Full Name: ${me.fullName}`);
console.log(`Role: ${me.role}`);
```

</td>
</tr>
</table>

### Satellite Tokens

Satellite tokens are short-lived RS256-signed JWTs for authenticating with federated SyftAI-Space instances.

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Get token for a specific audience
response = client.auth.get_satellite_token("alice")
print(f"Token expires in {response.expires_in}s")
token = response.target_token

# Get tokens for multiple audiences
tokens = client.auth.get_satellite_tokens(
    ["alice", "bob", "carol"]
)
for aud, token in tokens.items():
    print(f"{aud}: {token[:20]}...")
```

</td>
<td>

```typescript
// Get token for a specific audience
const response = await client.auth.getSatelliteToken('alice');
console.log(`Token expires in ${response.expiresIn}s`);
const token = response.targetToken;

// Get tokens for multiple audiences
const tokens = await client.auth.getSatelliteTokens(
  ['alice', 'bob', 'carol']
);
for (const [aud, token] of tokens) {
  console.log(`${aud}: ${token.slice(0, 20)}...`);
}
```

</td>
</tr>
</table>

---

## Resources

### Auth Resource

The Auth resource handles authentication, session management, and token operations.

| Method | Description |
|--------|-------------|
| `register()` | Create new user account |
| `login()` | Authenticate with credentials |
| `logout()` | End session and invalidate tokens |
| `me()` | Get current authenticated user |
| `refresh()` | Manually refresh access token |
| `change_password()` | Change current user's password |
| `get_satellite_token()` | Get RS256 token for federated service |
| `get_satellite_tokens()` | Get tokens for multiple audiences (parallel) |
| `get_transaction_tokens()` | Get billing authorization tokens |

### Users Resource

The Users resource handles profile management and availability checks.

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Update profile
user = client.users.update(
    username="new_username",
    email="new@example.com",
    full_name="Alice Smith",
    avatar_url="https://example.com/avatar.jpg",
    domain="api.alice.com",
)

# Check username availability
if client.users.check_username("newname"):
    print("Username is available!")

# Check email availability
if client.users.check_email("new@example.com"):
    print("Email is available!")

# Get accounting credentials
creds = client.users.get_accounting_credentials()
if creds.url and creds.password:
    print(f"Accounting URL: {creds.url}")
```

</td>
<td>

```typescript
// Update profile
const user = await client.users.update({
  username: 'new_username',
  email: 'new@example.com',
  fullName: 'Alice Smith',
  avatarUrl: 'https://example.com/avatar.jpg',
  domain: 'api.alice.com',
});

// Check username availability
if (await client.users.checkUsername('newname')) {
  console.log('Username is available!');
}

// Check email availability
if (await client.users.checkEmail('new@example.com')) {
  console.log('Email is available!');
}

// Get accounting credentials
const creds = await client.users.getAccountingCredentials();
if (creds.url && creds.password) {
  console.log(`Accounting URL: ${creds.url}`);
}
```

</td>
</tr>
</table>

### Hub Resource

The Hub resource provides read-only access to public endpoints for discovery.

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Browse all public endpoints
for endpoint in client.hub.browse():
    print(f"{endpoint.path}: {endpoint.name}")
    print(f"  Type: {endpoint.type}")
    print(f"  Stars: {endpoint.stars_count}")

# Get trending endpoints
for endpoint in client.hub.trending(min_stars=10):
    print(f"{endpoint.name} - {endpoint.stars_count} stars")

# Get a specific endpoint
endpoint = client.hub.get("alice/cool-api")
print(f"Name: {endpoint.name}")
print(f"README: {endpoint.readme[:100]}...")

# Star an endpoint (requires auth)
client.hub.star("alice/cool-api")

# Check if starred
if client.hub.is_starred("alice/cool-api"):
    print("You've starred this!")

# Unstar an endpoint
client.hub.unstar("alice/cool-api")
```

</td>
<td>

```typescript
// Browse all public endpoints
for await (const endpoint of client.hub.browse()) {
  console.log(`${endpoint.ownerUsername}/${endpoint.slug}: ${endpoint.name}`);
  console.log(`  Type: ${endpoint.type}`);
  console.log(`  Stars: ${endpoint.starsCount}`);
}

// Get trending endpoints
for await (const endpoint of client.hub.trending({ minStars: 10 })) {
  console.log(`${endpoint.name} - ${endpoint.starsCount} stars`);
}

// Get a specific endpoint
const endpoint = await client.hub.get('alice/cool-api');
console.log(`Name: ${endpoint.name}`);
console.log(`README: ${endpoint.readme.slice(0, 100)}...`);

// Star an endpoint (requires auth)
await client.hub.star('alice/cool-api');

// Check if starred
if (await client.hub.isStarred('alice/cool-api')) {
  console.log("You've starred this!");
}

// Unstar an endpoint
await client.hub.unstar('alice/cool-api');
```

</td>
</tr>
</table>

### MyEndpoints Resource

The MyEndpoints resource provides CRUD operations for managing your own endpoints.

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk.models import (
    EndpointType,
    Visibility,
    Connection,
    Policy,
)

# List your endpoints
for endpoint in client.my_endpoints.list():
    print(f"{endpoint.name} ({endpoint.visibility})")

# List with filter
for endpoint in client.my_endpoints.list(
    visibility=Visibility.PUBLIC
):
    print(endpoint.name)

# Create an endpoint
endpoint = client.my_endpoints.create(
    name="My Model",
    type=EndpointType.MODEL,  # or "model"
    visibility=Visibility.PUBLIC,  # or "public"
    description="A powerful ML model",
    slug="my-model",  # optional, auto-generated
    version="1.0.0",
    readme="# My Model\n\nThis model does...",
    tags=["machine-learning", "nlp"],
    connect=[
        Connection(
            type="http",
            enabled=True,
            description="Main endpoint",
            config={"url": "https://api.example.com"},
        )
    ],
    policies=[
        Policy(
            type="rate_limit",
            enabled=True,
            config={"requests_per_minute": 60},
        )
    ],
)
print(f"Created: {endpoint.slug}")

# Get an endpoint
endpoint = client.my_endpoints.get("alice/my-model")

# Update an endpoint
updated = client.my_endpoints.update(
    "alice/my-model",
    description="Updated description",
    version="1.1.0",
    tags=["ml", "updated"],
)

# Delete an endpoint
client.my_endpoints.delete("alice/my-model")
```

</td>
<td>

```typescript
import { EndpointType, Visibility } from '@syfthub/sdk';

// List your endpoints
for await (const endpoint of client.myEndpoints.list()) {
  console.log(`${endpoint.name} (${endpoint.visibility})`);
}

// List with filter
for await (const endpoint of client.myEndpoints.list({
  visibility: Visibility.PUBLIC
})) {
  console.log(endpoint.name);
}

// Create an endpoint
const endpoint = await client.myEndpoints.create({
  name: 'My Model',
  type: EndpointType.MODEL,  // or 'model'
  visibility: Visibility.PUBLIC,  // or 'public'
  description: 'A powerful ML model',
  slug: 'my-model',  // optional, auto-generated
  version: '1.0.0',
  readme: '# My Model\n\nThis model does...',
  tags: ['machine-learning', 'nlp'],
  connect: [
    {
      type: 'http',
      enabled: true,
      description: 'Main endpoint',
      config: { url: 'https://api.example.com' },
    }
  ],
  policies: [
    {
      type: 'rate_limit',
      enabled: true,
      config: { requests_per_minute: 60 },
    }
  ],
});
console.log(`Created: ${endpoint.slug}`);

// Get an endpoint
const ep = await client.myEndpoints.get('alice/my-model');

// Update an endpoint
const updated = await client.myEndpoints.update('alice/my-model', {
  description: 'Updated description',
  version: '1.1.0',
  tags: ['ml', 'updated'],
});

// Delete an endpoint
await client.myEndpoints.delete('alice/my-model');
```

</td>
</tr>
</table>

### Chat Resource

The Chat resource provides RAG-augmented conversations via the Aggregator service.

#### Chat Completion

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Simple chat completion
response = client.chat.complete(
    prompt="What is machine learning?",
    model="alice/gpt-model",
    data_sources=["bob/ml-docs", "carol/tutorials"],
    # Optional parameters
    top_k=5,           # Documents per source
    max_tokens=1024,   # Max response tokens
    temperature=0.7,   # Generation temperature
    similarity_threshold=0.5,  # Min doc similarity
)

# Access response
print(response.response)

# Access sources (dict: title -> DocumentSource)
for title, source in response.sources.items():
    print(f"Source: {title}")
    print(f"  Endpoint: {source.slug}")
    print(f"  Content: {source.content[:100]}...")

# Access retrieval metadata
for info in response.retrieval_info:
    print(f"{info.path}: {info.documents_retrieved} docs")
    print(f"  Status: {info.status}")

# Access timing metadata
print(f"Retrieval: {response.metadata.retrieval_time_ms}ms")
print(f"Generation: {response.metadata.generation_time_ms}ms")
print(f"Total: {response.metadata.total_time_ms}ms")

# Access token usage (if available)
if response.usage:
    print(f"Tokens: {response.usage.total_tokens}")
```

</td>
<td>

```typescript
// Simple chat completion
const response = await client.chat.complete({
  prompt: 'What is machine learning?',
  model: 'alice/gpt-model',
  dataSources: ['bob/ml-docs', 'carol/tutorials'],
  // Optional parameters
  topK: 5,           // Documents per source
  maxTokens: 1024,   // Max response tokens
  temperature: 0.7,  // Generation temperature
  similarityThreshold: 0.5,  // Min doc similarity
});

// Access response
console.log(response.response);

// Access sources (Record: title -> DocumentSource)
for (const [title, source] of Object.entries(response.sources)) {
  console.log(`Source: ${title}`);
  console.log(`  Endpoint: ${source.slug}`);
  console.log(`  Content: ${source.content.slice(0, 100)}...`);
}

// Access retrieval metadata
for (const info of response.retrievalInfo) {
  console.log(`${info.path}: ${info.documentsRetrieved} docs`);
  console.log(`  Status: ${info.status}`);
}

// Access timing metadata
console.log(`Retrieval: ${response.metadata.retrievalTimeMs}ms`);
console.log(`Generation: ${response.metadata.generationTimeMs}ms`);
console.log(`Total: ${response.metadata.totalTimeMs}ms`);

// Access token usage (if available)
if (response.usage) {
  console.log(`Tokens: ${response.usage.totalTokens}`);
}
```

</td>
</tr>
</table>

#### Chat Streaming

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Streaming chat
for event in client.chat.stream(
    prompt="Explain neural networks",
    model="alice/gpt-model",
    data_sources=["bob/ml-docs"],
):
    if event.type == "retrieval_start":
        print(f"Retrieving from {event.source_count} sources...")

    elif event.type == "source_complete":
        print(f"  {event.path}: {event.documents_retrieved} docs")

    elif event.type == "retrieval_complete":
        print(f"Retrieval done: {event.total_documents} docs in {event.time_ms}ms")

    elif event.type == "generation_start":
        print("Generating response...")

    elif event.type == "token":
        print(event.content, end="", flush=True)

    elif event.type == "done":
        print(f"\n\nCompleted in {event.metadata.total_time_ms}ms")
        print(f"Sources used: {len(event.sources)}")

    elif event.type == "error":
        print(f"Error: {event.message}")
```

</td>
<td>

```typescript
// Streaming chat
for await (const event of client.chat.stream({
  prompt: 'Explain neural networks',
  model: 'alice/gpt-model',
  dataSources: ['bob/ml-docs'],
})) {
  if (event.type === 'retrieval_start') {
    console.log(`Retrieving from ${event.sourceCount} sources...`);

  } else if (event.type === 'source_complete') {
    console.log(`  ${event.path}: ${event.documentsRetrieved} docs`);

  } else if (event.type === 'retrieval_complete') {
    console.log(`Retrieval done: ${event.totalDocuments} docs in ${event.timeMs}ms`);

  } else if (event.type === 'generation_start') {
    console.log('Generating response...');

  } else if (event.type === 'token') {
    process.stdout.write(event.content);

  } else if (event.type === 'done') {
    console.log(`\n\nCompleted in ${event.metadata.totalTimeMs}ms`);
    console.log(`Sources used: ${Object.keys(event.sources).length}`);

  } else if (event.type === 'error') {
    console.log(`Error: ${event.message}`);
  }
}
```

</td>
</tr>
</table>

#### Discover Available Endpoints

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Get available models
for model in client.chat.get_available_models(limit=10):
    print(f"Model: {model.owner_username}/{model.slug}")
    print(f"  Name: {model.name}")

# Get available data sources
for source in client.chat.get_available_data_sources(limit=10):
    print(f"Data: {source.owner_username}/{source.slug}")
    print(f"  Name: {source.name}")
```

</td>
<td>

```typescript
// Get available models
const models = await client.chat.getAvailableModels(10);
for (const model of models) {
  console.log(`Model: ${model.ownerUsername}/${model.slug}`);
  console.log(`  Name: ${model.name}`);
}

// Get available data sources
const sources = await client.chat.getAvailableDataSources(10);
for (const source of sources) {
  console.log(`Data: ${source.ownerUsername}/${source.slug}`);
  console.log(`  Name: ${source.name}`);
}
```

</td>
</tr>
</table>

### Accounting Resource

The Accounting resource connects to the external billing service using Basic auth (separate from SyftHub's JWT auth).

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Get user balance and info
user = client.accounting.get_user()
print(f"Balance: {user.balance}")
print(f"Organization: {user.organization}")

# List transactions
for tx in client.accounting.get_transactions():
    print(f"{tx.created_at}: {tx.amount}")
    print(f"  From: {tx.sender_email}")
    print(f"  To: {tx.recipient_email}")
    print(f"  Status: {tx.status}")

# Get specific transaction
tx = client.accounting.get_transaction("tx_123")

# Create a transaction (PENDING status)
tx = client.accounting.create_transaction(
    recipient_email="bob@example.com",
    amount=10.0,
    app_name="syftai-space",  # optional context
    app_ep_path="alice/model",  # optional context
)

# Confirm transaction (transfers funds)
tx = client.accounting.confirm_transaction(tx.id)

# Or cancel transaction (no transfer)
tx = client.accounting.cancel_transaction(tx.id)

# Update accounting password
client.accounting.update_password(
    current_password="old_pass",
    new_password="new_pass",
)

# Update organization
client.accounting.update_organization("OpenMined")

# Delegated transactions (pre-authorized)
# Step 1: Sender creates token
token = client.accounting.create_transaction_token(
    recipient_email="service@example.com"
)

# Step 2: Recipient creates transaction using token
tx = client.accounting.create_delegated_transaction(
    sender_email="alice@example.com",
    amount=5.0,
    token=token,
)

# Step 3: Recipient confirms
tx = client.accounting.confirm_transaction(tx.id)
```

</td>
<td>

```typescript
// Get user balance and info
const user = await client.accounting.getUser();
console.log(`Balance: ${user.balance}`);
console.log(`Organization: ${user.organization}`);

// List transactions
for await (const tx of client.accounting.getTransactions()) {
  console.log(`${tx.createdAt}: ${tx.amount}`);
  console.log(`  From: ${tx.senderEmail}`);
  console.log(`  To: ${tx.recipientEmail}`);
  console.log(`  Status: ${tx.status}`);
}

// Get specific transaction
const tx = await client.accounting.getTransaction('tx_123');

// Create a transaction (PENDING status)
let transaction = await client.accounting.createTransaction({
  recipientEmail: 'bob@example.com',
  amount: 10.0,
  appName: 'syftai-space',  // optional context
  appEpPath: 'alice/model',  // optional context
});

// Confirm transaction (transfers funds)
transaction = await client.accounting.confirmTransaction(transaction.id);

// Or cancel transaction (no transfer)
transaction = await client.accounting.cancelTransaction(transaction.id);

// Update accounting password
await client.accounting.updatePassword('old_pass', 'new_pass');

// Update organization
await client.accounting.updateOrganization('OpenMined');

// Delegated transactions (pre-authorized)
// Step 1: Sender creates token
const token = await client.accounting.createTransactionToken(
  'service@example.com'
);

// Step 2: Recipient creates transaction using token
const delegatedTx = await client.accounting.createDelegatedTransaction(
  'alice@example.com',
  5.0,
  token
);

// Step 3: Recipient confirms
await client.accounting.confirmTransaction(delegatedTx.id);
```

</td>
</tr>
</table>

### SyftAI Resource

The SyftAI resource provides direct access to SyftAI-Space endpoints without the Aggregator. Use this for custom RAG pipelines.

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk.models import EndpointRef, Message

# Query a data source directly
docs = client.syftai.query_data_source(
    endpoint=EndpointRef(
        url="http://syftai:8080",
        slug="docs",
        owner_username="alice",
    ),
    query="What is Python?",
    user_email="bob@example.com",
    top_k=5,
)
for doc in docs:
    print(f"Score: {doc.score}")
    print(f"Content: {doc.content[:100]}...")

# Query a model directly
response = client.syftai.query_model(
    endpoint=EndpointRef(
        url="http://syftai:8080",
        slug="gpt-model",
        owner_username="alice",
    ),
    messages=[
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Hello!"),
    ],
    user_email="bob@example.com",
    max_tokens=256,
    temperature=0.7,
)
print(response)
```

</td>
<td>

```typescript
// Query a data source directly
const docs = await client.syftai.queryDataSource({
  endpoint: {
    url: 'http://syftai:8080',
    slug: 'docs',
    ownerUsername: 'alice',
  },
  query: 'What is Python?',
  userEmail: 'bob@example.com',
  topK: 5,
});
for (const doc of docs) {
  console.log(`Score: ${doc.score}`);
  console.log(`Content: ${doc.content.slice(0, 100)}...`);
}

// Query a model directly
const response = await client.syftai.queryModel({
  endpoint: {
    url: 'http://syftai:8080',
    slug: 'gpt-model',
    ownerUsername: 'alice',
  },
  messages: [
    { role: 'system', content: 'You are helpful.' },
    { role: 'user', content: 'Hello!' },
  ],
  userEmail: 'bob@example.com',
  maxTokens: 256,
  temperature: 0.7,
});
console.log(response);
```

</td>
</tr>
</table>

---

## Streaming

### Stream Event Types

Chat streaming uses Server-Sent Events (SSE) with the following event types:

| Event Type | Description | Fields |
|------------|-------------|--------|
| `retrieval_start` | Retrieval phase begins | `source_count` / `sourceCount` |
| `source_complete` | Single source finished | `path`, `status`, `documents_retrieved` |
| `retrieval_complete` | All retrieval done | `total_documents`, `time_ms` |
| `generation_start` | Model generation begins | (none) |
| `token` | Token from model | `content` |
| `done` | Generation complete | `sources`, `retrieval_info`, `metadata`, `usage` |
| `error` | Error occurred | `message` |

### Handling All Event Types

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk.chat import (
    RetrievalStartEvent,
    SourceCompleteEvent,
    RetrievalCompleteEvent,
    GenerationStartEvent,
    TokenEvent,
    DoneEvent,
    ErrorEvent,
)

full_response = ""
for event in client.chat.stream(...):
    match event:
        case RetrievalStartEvent():
            print(f"Starting retrieval from {event.source_count} sources")
        case SourceCompleteEvent():
            print(f"Source {event.path}: {event.status}")
        case RetrievalCompleteEvent():
            print(f"Retrieved {event.total_documents} documents")
        case GenerationStartEvent():
            print("Starting generation...")
        case TokenEvent():
            full_response += event.content
            print(event.content, end="")
        case DoneEvent():
            print(f"\nDone! Timing: {event.metadata}")
        case ErrorEvent():
            raise Exception(f"Stream error: {event.message}")
```

</td>
<td>

```typescript
import type { ChatStreamEvent } from '@syfthub/sdk';

let fullResponse = '';
for await (const event of client.chat.stream({...})) {
  switch (event.type) {
    case 'retrieval_start':
      console.log(`Starting retrieval from ${event.sourceCount} sources`);
      break;
    case 'source_complete':
      console.log(`Source ${event.path}: ${event.status}`);
      break;
    case 'retrieval_complete':
      console.log(`Retrieved ${event.totalDocuments} documents`);
      break;
    case 'generation_start':
      console.log('Starting generation...');
      break;
    case 'token':
      fullResponse += event.content;
      process.stdout.write(event.content);
      break;
    case 'done':
      console.log(`\nDone! Timing: ${JSON.stringify(event.metadata)}`);
      break;
    case 'error':
      throw new Error(`Stream error: ${event.message}`);
  }
}
```

</td>
</tr>
</table>

---

## Pagination

Both SDKs provide lazy pagination via `PageIterator` for list operations.

### Iterating All Items

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Iterate through all items (lazy loading)
for endpoint in client.hub.browse():
    print(endpoint.name)

# Custom page size
for endpoint in client.hub.browse(page_size=50):
    print(endpoint.name)
```

</td>
<td>

```typescript
// Iterate through all items (lazy loading)
for await (const endpoint of client.hub.browse()) {
  console.log(endpoint.name);
}

// Custom page size
for await (const endpoint of client.hub.browse({ pageSize: 50 })) {
  console.log(endpoint.name);
}
```

</td>
</tr>
</table>

### Get First Page Only

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Get first page only (default 20 items)
first_page = client.hub.browse().first_page()
for endpoint in first_page:
    print(endpoint.name)
```

</td>
<td>

```typescript
// Get first page only (default 20 items)
const firstPage = await client.hub.browse().firstPage();
for (const endpoint of firstPage) {
  console.log(endpoint.name);
}
```

</td>
</tr>
</table>

### Get All Items at Once

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Get all items (may be slow for large lists)
all_endpoints = client.hub.browse().all()
print(f"Total: {len(all_endpoints)}")
```

</td>
<td>

```typescript
// Get all items (may be slow for large lists)
const allEndpoints = await client.hub.browse().all();
console.log(`Total: ${allEndpoints.length}`);
```

</td>
</tr>
</table>

---

## Error Handling

### Exception Hierarchy

```
SyftHubError (base)
    ├── AuthenticationError     # 401 - Invalid credentials/token
    ├── AuthorizationError      # 403 - Permission denied
    ├── NotFoundError           # 404 - Resource not found
    ├── ValidationError         # 422 - Invalid request data
    ├── APIError                # Other HTTP errors
    ├── NetworkError            # Connection/timeout errors
    ├── ConfigurationError      # Invalid SDK configuration
    ├── UserAlreadyExistsError  # 409 - Duplicate user
    ├── ChatError (base for chat errors)
    │   ├── AggregatorError     # Aggregator service error
    │   ├── RetrievalError      # Data source retrieval failed
    │   ├── GenerationError     # Model generation failed
    │   └── EndpointResolutionError  # Cannot resolve endpoint
    └── Accounting Errors
        ├── AccountingAccountExistsError    # Email exists in accounting
        ├── InvalidAccountingPasswordError  # Wrong accounting password
        └── AccountingServiceUnavailableError  # Accounting service down
```

### Handling Errors

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk.exceptions import (
    SyftHubError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
    NetworkError,
    UserAlreadyExistsError,
    AccountingAccountExistsError,
    AggregatorError,
)

try:
    user = client.auth.login(
        username="alice",
        password="wrong"
    )
except AuthenticationError as e:
    print(f"Login failed: {e.message}")

except AuthorizationError as e:
    print(f"Access denied: {e.message}")

except NotFoundError as e:
    print(f"Not found: {e.message}")

except ValidationError as e:
    print(f"Validation error: {e.message}")
    # Access field-level errors
    for field, errors in e.errors.items():
        print(f"  {field}: {errors}")

except NetworkError as e:
    print(f"Network error: {e.message}")
    print(f"Cause: {e.cause}")

except SyftHubError as e:
    print(f"API error [{e.status_code}]: {e.message}")

# Registration error handling
try:
    client.auth.register(...)
except UserAlreadyExistsError as e:
    print(f"User exists: {e.field} is taken")
except AccountingAccountExistsError as e:
    # Need to provide existing accounting password
    password = input("Enter your accounting password: ")
    client.auth.register(..., accounting_password=password)
```

</td>
<td>

```typescript
import {
  SyftHubError,
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  ValidationError,
  NetworkError,
  UserAlreadyExistsError,
  AccountingAccountExistsError,
  AggregatorError,
} from '@syfthub/sdk';

try {
  const user = await client.auth.login('alice', 'wrong');
} catch (error) {
  if (error instanceof AuthenticationError) {
    console.log(`Login failed: ${error.message}`);

  } else if (error instanceof AuthorizationError) {
    console.log(`Access denied: ${error.message}`);

  } else if (error instanceof NotFoundError) {
    console.log(`Not found: ${error.message}`);

  } else if (error instanceof ValidationError) {
    console.log(`Validation error: ${error.message}`);
    // Access field-level errors
    if (error.errors) {
      for (const [field, msgs] of Object.entries(error.errors)) {
        console.log(`  ${field}: ${msgs.join(', ')}`);
      }
    }

  } else if (error instanceof NetworkError) {
    console.log(`Network error: ${error.message}`);
    console.log(`Cause: ${error.cause?.message}`);

  } else if (error instanceof SyftHubError) {
    console.log(`API error: ${error.message}`);
  }
}

// Registration error handling
try {
  await client.auth.register({...});
} catch (error) {
  if (error instanceof UserAlreadyExistsError) {
    console.log(`User exists: ${error.field} is taken`);
  } else if (error instanceof AccountingAccountExistsError) {
    // Need to provide existing accounting password
    const password = await promptUser('Enter your accounting password:');
    await client.auth.register({...accountingPassword: password});
  }
}
```

</td>
</tr>
</table>

---

## Type Definitions

### Enums

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk.models import (
    # Visibility levels
    Visibility,  # PUBLIC, PRIVATE, INTERNAL

    # Endpoint types
    EndpointType,  # MODEL, DATA_SOURCE

    # User roles
    UserRole,  # ADMIN, USER, GUEST

    # Organization roles
    OrganizationRole,  # OWNER, ADMIN, MEMBER

    # Transaction status
    TransactionStatus,  # PENDING, COMPLETED, CANCELLED

    # Source query status
    SourceStatus,  # SUCCESS, ERROR, TIMEOUT

    # Transaction creator type
    CreatorType,  # SYSTEM, SENDER, RECIPIENT
)
```

</td>
<td>

```typescript
import {
  // Visibility levels
  Visibility,  // PUBLIC, PRIVATE, INTERNAL

  // Endpoint types
  EndpointType,  // MODEL, DATA_SOURCE

  // User roles
  UserRole,  // ADMIN, USER, GUEST

  // Organization roles
  OrganizationRole,  // OWNER, ADMIN, MEMBER

  // Transaction status
  TransactionStatus,  // PENDING, COMPLETED, CANCELLED

  // Transaction creator type
  CreatorType,  // SYSTEM, SENDER, RECIPIENT
} from '@syfthub/sdk';
```

</td>
</tr>
</table>

### Core Models

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk.models import (
    # User models
    User,
    AuthTokens,
    SatelliteTokenResponse,
    AccountingCredentials,

    # Endpoint models
    Endpoint,       # Full (your endpoints)
    EndpointPublic, # Public (hub browsing)
    Policy,
    Connection,

    # Chat models
    EndpointRef,
    ChatResponse,
    ChatMetadata,
    TokenUsage,
    SourceInfo,
    DocumentSource,
    Document,
    Message,

    # Accounting models
    AccountingUser,
    Transaction,
)
```

</td>
<td>

```typescript
import type {
  // User types
  User,
  AuthTokens,
  UserRegisterInput,
  UserUpdateInput,
  AccountingCredentials,

  // Endpoint types
  Endpoint,       // Full (your endpoints)
  EndpointPublic, // Public (hub browsing)
  Policy,
  Connection,
  EndpointCreateInput,
  EndpointUpdateInput,

  // Chat types
  EndpointRef,
  ChatResponse,
  ChatMetadata,
  ChatOptions,
  TokenUsage,
  SourceInfo,
  DocumentSource,
  Document,
  Message,
  ChatStreamEvent,

  // Accounting types
  AccountingUser,
  Transaction,
  CreateTransactionInput,
} from '@syfthub/sdk';
```

</td>
</tr>
</table>

---

## Advanced Patterns

### Custom HTTP Client Options

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# The SDK uses httpx internally
# Custom timeout per operation
client = SyftHubClient(
    base_url="https://hub.syft.com",
    timeout=60.0,  # 60 seconds for all requests
)

# For chat operations, the internal
# aggregator client uses 120s timeout
# (LLM generation can be slow)
```

</td>
<td>

```typescript
// The SDK uses native fetch
// Custom timeout per operation
const client = new SyftHubClient({
  baseUrl: 'https://hub.syft.com',
  timeout: 60000,  // 60 seconds for all requests
});

// For chat streaming with abort signal
const controller = new AbortController();
setTimeout(() => controller.abort(), 30000);

for await (const event of client.chat.stream({
  prompt: '...',
  model: '...',
  signal: controller.signal,
})) {
  // Handle events
}
```

</td>
</tr>
</table>

### Working with Endpoint Paths

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Endpoint paths follow GitHub-style format
# Format: "owner_username/slug"

# Get endpoint by path
endpoint = client.hub.get("alice/my-model")
print(f"Path: {endpoint.path}")  # alice/my-model

# Use path in operations
client.hub.star("alice/my-model")
client.my_endpoints.update("alice/my-model", name="New Name")

# Use in chat
response = client.chat.complete(
    prompt="Hello",
    model="alice/gpt-model",
    data_sources=["bob/docs", "carol/tutorials"],
)
```

</td>
<td>

```typescript
// Endpoint paths follow GitHub-style format
// Format: "owner_username/slug"

// Get endpoint by path
const endpoint = await client.hub.get('alice/my-model');
console.log(`Path: ${endpoint.ownerUsername}/${endpoint.slug}`);

// Use path in operations
await client.hub.star('alice/my-model');
await client.myEndpoints.update('alice/my-model', { name: 'New Name' });

// Use in chat
const response = await client.chat.complete({
  prompt: 'Hello',
  model: 'alice/gpt-model',
  dataSources: ['bob/docs', 'carol/tutorials'],
});
```

</td>
</tr>
</table>

### Building Custom RAG Pipelines

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk.models import EndpointRef, Message

# Custom RAG: retrieve then generate separately
# Step 1: Get satellite tokens
owners = ["alice", "bob"]
tokens = client.auth.get_satellite_tokens(owners)

# Step 2: Resolve endpoints
data_ep = client.hub.get("bob/docs")
model_ep = client.hub.get("alice/gpt")

# Step 3: Query data source
docs = client.syftai.query_data_source(
    endpoint=EndpointRef(
        url=data_ep.connect[0].config["url"],
        slug=data_ep.slug,
        owner_username=data_ep.owner_username,
    ),
    query="What is Python?",
    user_email="user@example.com",
    satellite_token=tokens.get("bob"),
)

# Step 4: Build custom prompt
context = "\n\n".join([d.content for d in docs])
messages = [
    Message(role="system", content=f"Context:\n{context}"),
    Message(role="user", content="Based on the context, explain Python."),
]

# Step 5: Query model
response = client.syftai.query_model(
    endpoint=EndpointRef(
        url=model_ep.connect[0].config["url"],
        slug=model_ep.slug,
        owner_username=model_ep.owner_username,
    ),
    messages=messages,
    user_email="user@example.com",
    satellite_token=tokens.get("alice"),
)
```

</td>
<td>

```typescript
// Custom RAG: retrieve then generate separately
// Step 1: Get satellite tokens
const owners = ['alice', 'bob'];
const tokens = await client.auth.getSatelliteTokens(owners);

// Step 2: Resolve endpoints
const dataEp = await client.hub.get('bob/docs');
const modelEp = await client.hub.get('alice/gpt');

// Step 3: Query data source
const docs = await client.syftai.queryDataSource({
  endpoint: {
    url: dataEp.connect[0].config['url'] as string,
    slug: dataEp.slug,
    ownerUsername: dataEp.ownerUsername,
  },
  query: 'What is Python?',
  userEmail: 'user@example.com',
  satelliteToken: tokens.get('bob'),
});

// Step 4: Build custom prompt
const context = docs.map(d => d.content).join('\n\n');
const messages = [
  { role: 'system', content: `Context:\n${context}` },
  { role: 'user', content: 'Based on the context, explain Python.' },
];

// Step 5: Query model
const response = await client.syftai.queryModel({
  endpoint: {
    url: modelEp.connect[0].config['url'] as string,
    slug: modelEp.slug,
    ownerUsername: modelEp.ownerUsername,
  },
  messages,
  userEmail: 'user@example.com',
  satelliteToken: tokens.get('alice'),
});
```

</td>
</tr>
</table>

---

## Best Practices

### 1. Use Environment Variables for Configuration

```bash
# .env file
SYFTHUB_URL=https://hub.syft.com
SYFTHUB_ACCOUNTING_URL=https://accounting.syft.com
SYFTHUB_ACCOUNTING_EMAIL=user@example.com
SYFTHUB_ACCOUNTING_PASSWORD=secret
```

### 2. Handle Token Persistence

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
import json
from pathlib import Path

TOKEN_FILE = Path.home() / ".syfthub_tokens.json"

def save_session(client):
    tokens = client.get_tokens()
    if tokens:
        TOKEN_FILE.write_text(json.dumps({
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
        }))

def restore_session(client):
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text())
        from syfthub_sdk.models import AuthTokens
        client.set_tokens(AuthTokens(**data))
        return True
    return False

# Usage
client = SyftHubClient()
if not restore_session(client):
    client.login(username="alice", password="secret")
    save_session(client)
```

</td>
<td>

```typescript
const TOKEN_KEY = 'syfthub_tokens';

function saveSession(client: SyftHubClient) {
  const tokens = client.getTokens();
  if (tokens) {
    localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
  }
}

function restoreSession(client: SyftHubClient): boolean {
  const saved = localStorage.getItem(TOKEN_KEY);
  if (saved) {
    client.setTokens(JSON.parse(saved));
    return true;
  }
  return false;
}

// Usage
const client = new SyftHubClient();
if (!restoreSession(client)) {
  await client.auth.login('alice', 'secret');
  saveSession(client);
}
```

</td>
</tr>
</table>

### 3. Implement Retry Logic for Network Errors

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
from syfthub_sdk.exceptions import NetworkError
import time

def with_retry(func, max_retries=3, delay=1.0):
    for attempt in range(max_retries):
        try:
            return func()
        except NetworkError as e:
            if attempt == max_retries - 1:
                raise
            print(f"Retry {attempt + 1}/{max_retries}: {e}")
            time.sleep(delay * (2 ** attempt))

# Usage
result = with_retry(
    lambda: client.chat.complete(
        prompt="Hello",
        model="alice/gpt"
    )
)
```

</td>
<td>

```typescript
import { NetworkError } from '@syfthub/sdk';

async function withRetry<T>(
  fn: () => Promise<T>,
  maxRetries = 3,
  delay = 1000
): Promise<T> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (!(error instanceof NetworkError)) throw error;
      if (attempt === maxRetries - 1) throw error;
      console.log(`Retry ${attempt + 1}/${maxRetries}: ${error.message}`);
      await new Promise(r => setTimeout(r, delay * (2 ** attempt)));
    }
  }
  throw new Error('Unreachable');
}

// Usage
const result = await withRetry(() =>
  client.chat.complete({
    prompt: 'Hello',
    model: 'alice/gpt',
  })
);
```

</td>
</tr>
</table>

### 4. Use Streaming for Long-Running Chat Operations

For better UX, prefer streaming over complete() for chat:

```python
# Python - Stream with progress
for event in client.chat.stream(prompt="...", model="..."):
    if event.type == "token":
        print(event.content, end="", flush=True)
```

```typescript
// TypeScript - Stream with UI updates
for await (const event of client.chat.stream({...})) {
  if (event.type === 'token') {
    updateUI(event.content);
  }
}
```

### 5. Check Configuration Before Using Optional Resources

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
</tr>
<tr>
<td>

```python
# Check if accounting is configured
if client.accounting.is_configured:
    user = client.accounting.get_user()
else:
    print("Accounting not configured")
```

</td>
<td>

```typescript
// Check if accounting is configured
if (client.isAccountingConfigured) {
  const user = await client.accounting.getUser();
} else {
  console.log('Accounting not configured');
}
```

</td>
</tr>
</table>

---

## Related Documentation

- [01-system-architecture.md](./01-system-architecture.md) - System overview
- [03-api-reference.md](./03-api-reference.md) - REST API documentation
- [04-authentication-security.md](./04-authentication-security.md) - Auth & security details

---

## SDK Source Code

- Python SDK: `/sdk/python/src/syfthub_sdk/`
- TypeScript SDK: `/sdk/typescript/src/`
