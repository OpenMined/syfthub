# SyftHub TypeScript SDK

The official TypeScript client for [SyftHub](https://github.com/IonesioJunior/syfthub) — works in Node 18+ and modern browsers.

## Install

```bash
npm install @syfthub/sdk
# or
yarn add @syfthub/sdk
# or
pnpm add @syfthub/sdk
```

## Quick start

```typescript
import { SyftHubClient } from '@syfthub/sdk';

const client = new SyftHubClient({ baseUrl: 'https://hub.syft.com' });

// Sign in
await client.auth.login({ email: 'alice@example.com', password: '...' });

// Browse the hub
for await (const endpoint of client.hub.browse()) {
  console.log(`${endpoint.ownerUsername}/${endpoint.slug} — ${endpoint.name}`);
}

// Publish your own
const endpoint = await client.myEndpoints.create({
  name: 'My Cool API',
  type: EndpointType.MODEL,
  visibility: Visibility.PUBLIC,
  description: 'A really cool API',
});

// Star something you like
await client.hub.star('alice/cool-api');
```

The SDK is fully typed, supports `for await` lazy pagination on every list, persists tokens via `client.getTokens()` / `client.setTokens(...)`, and exposes typed errors (`AuthenticationError`, `NotFoundError`, `ValidationError`, …) for graceful handling.

## Documentation

- [TypeScript SDK guide](../../docs/guides/typescript-sdk.md) — full walkthrough with examples.
- [Backend API reference](../../docs/api/backend.md) — every endpoint the SDK calls.

## Configuration

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | SyftHub API base URL |

## License

[Apache 2.0](../../LICENSE)
