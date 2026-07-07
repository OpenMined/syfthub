# TypeScript SDK Guide

## Installation

```bash
npm install @syfthub/sdk
```

**Version:** 0.1.1 | **Requires:** Node >= 18.0.0

## Client Setup

```typescript
import { SyftHubClient } from "@syfthub/sdk";

const client = new SyftHubClient({
  baseUrl: "http://localhost:8080",
  timeout: 30000,
  aggregatorUrl: "http://localhost:8080",
  apiToken: "syft_pat_...", // optional, for PAT-based auth
});
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | Base URL of the hub |
| `SYFTHUB_API_TOKEN` | Personal access token |

## Authentication

```typescript
// Login
await client.auth.login({ email: "user@example.com", password: "password" });

// Check auth state
if (client.isAuthenticated) {
  // ...
}

// Get and restore tokens
const tokens = client.getTokens();
client.setTokens(tokens);
```

## Resources

| Resource | Access |
|----------|--------|
| Auth | `client.auth` |
| Users | `client.users` |
| My Endpoints | `client.myEndpoints` |
| Hub (Browse) | `client.hub` |
| Chat (RAG) | `client.chat` |
| SyftAI | `client.syftai` |
| API Tokens | `client.apiTokens` |
| Accounting | `client.accounting` (lazy-init, see below) |

Resources are available immediately after constructing the client, except for `accounting` which requires explicit initialization.

## Endpoints

```typescript
// Create
const endpoint = await client.myEndpoints.create({
  name: "My Model",
  type: "model",
  visibility: "public",
  description: "A text generation model",
});

// List your endpoints
const endpoints = await client.myEndpoints.list();

// Get one by slug
const ep = await client.myEndpoints.get("my-model");

// Update
await client.myEndpoints.update("my-model", { description: "Updated" });

// Delete
await client.myEndpoints.delete("my-model");
```

## Browse and Search

```typescript
// Browse public endpoints
const results = await client.hub.browse();

// Trending endpoints
const trending = await client.hub.trending();

// Search
const results = await client.hub.search("text generation");
```

## Chat (RAG Queries)

```typescript
const response = await client.chat({
  prompt: "What models are available for text generation?",
  model: "owner/model-slug",
  dataSources: ["owner/data-source-slug"],
});
```

## Accounting

Accounting requires explicit initialization before use:

```typescript
await client.initAccounting();

const balance = await client.accounting.balance();
const transactions = await client.accounting.transactions();
```

## API Tokens

```typescript
// Create a personal access token
const token = await client.apiTokens.create({ name: "CI token" });

// List tokens
const tokens = await client.apiTokens.list();

// Revoke a token
await client.apiTokens.revoke(tokenId);
```

## Cleanup

Close the client to release resources when done:

```typescript
client.close();
```
