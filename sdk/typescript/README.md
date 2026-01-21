# SyftHub TypeScript SDK

TypeScript SDK for interacting with the SyftHub API programmatically.

## Installation

```bash
# Using npm
npm install @syfthub/sdk

# Using yarn
yarn add @syfthub/sdk

# Using pnpm
pnpm add @syfthub/sdk
```

## Quick Start

```typescript
import { SyftHubClient } from '@syfthub/sdk';

// Initialize client
const client = new SyftHubClient({ baseUrl: 'https://hub.syft.com' });

// Register a new user
const user = await client.auth.register({
  username: 'john',
  email: 'john@example.com',
  password: 'secret123',
  fullName: 'John Doe',
});

// Login
const loggedIn = await client.auth.login('john', 'secret123');
console.log(`Logged in as ${loggedIn.username}`);

// Get current user
const me = await client.auth.me();
```

## Managing Your Endpoints

```typescript
import { EndpointType, Visibility } from '@syfthub/sdk';

// List your endpoints (with lazy pagination)
for await (const endpoint of client.myEndpoints.list()) {
  console.log(`${endpoint.name} (${endpoint.visibility})`);
}

// Get just the first page
const firstPage = await client.myEndpoints.list().firstPage();

// Create an endpoint
const endpoint = await client.myEndpoints.create({
  name: 'My Cool API',
  type: EndpointType.MODEL,
  visibility: Visibility.PUBLIC,
  description: 'A really cool API',
  readme: '# My API\n\nThis is my API documentation.',
});
console.log(`Created: ${endpoint.slug}`);

// Update an endpoint
const updated = await client.myEndpoints.update('john/my-cool-api', {
  description: 'Updated description',
});

// Delete an endpoint
await client.myEndpoints.delete('john/my-cool-api');
```

## Browsing the Hub

```typescript
// Browse public endpoints
for await (const endpoint of client.hub.browse()) {
  console.log(`${endpoint.ownerUsername}/${endpoint.slug}: ${endpoint.name}`);
}

// Get trending endpoints
for await (const endpoint of client.hub.trending({ minStars: 10 })) {
  console.log(`${endpoint.name} - ${endpoint.starsCount} stars`);
}

// Get a specific endpoint by path
const endpoint = await client.hub.get('alice/cool-api');
console.log(endpoint.readme);

// Star/unstar endpoints (requires auth)
await client.hub.star('alice/cool-api');
await client.hub.unstar('alice/cool-api');

// Check if you've starred an endpoint
if (await client.hub.isStarred('alice/cool-api')) {
  console.log("You've starred this!");
}
```

## User Profile

```typescript
// Update profile
const user = await client.users.update({
  fullName: 'John D.',
  avatarUrl: 'https://example.com/avatar.png',
});

// Check username availability
if (await client.users.checkUsername('newusername')) {
  console.log('Username is available!');
}

// Change password
await client.auth.changePassword('old123', 'new456');
```

## Accounting

```typescript
// Get account balance
const balance = await client.accounting.balance();
console.log(`Credits: ${balance.credits} ${balance.currency}`);

// List transactions
for await (const tx of client.accounting.transactions()) {
  console.log(`${tx.createdAt}: ${tx.amount} - ${tx.description}`);
}
```

## Token Persistence

```typescript
// Get tokens for saving
const tokens = client.getTokens();
if (tokens) {
  // Save to localStorage, database, etc.
  localStorage.setItem('syfthub_tokens', JSON.stringify(tokens));
}

// Later, restore session
const saved = localStorage.getItem('syfthub_tokens');
if (saved) {
  const tokens = JSON.parse(saved);
  client.setTokens(tokens);
}

// Check if authenticated
if (client.isAuthenticated) {
  console.log('Session restored!');
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | SyftHub API base URL |

## Error Handling

```typescript
import {
  SyftHubError,
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  ValidationError,
  NetworkError,
} from '@syfthub/sdk';

try {
  await client.auth.login('john', 'wrong');
} catch (error) {
  if (error instanceof AuthenticationError) {
    console.log(`Login failed: ${error.message}`);
  } else if (error instanceof NotFoundError) {
    console.log('User not found');
  } else if (error instanceof ValidationError) {
    console.log(`Validation error: ${error.message}`);
    console.log('Field errors:', error.errors);
  } else if (error instanceof NetworkError) {
    console.log(`Network error: ${error.message}`);
  } else if (error instanceof SyftHubError) {
    console.log(`API error: ${error.message}`);
  }
}
```

## Pagination

All list methods return a `PageIterator` for lazy async pagination:

```typescript
// Iterate through all items (fetches pages as needed)
for await (const endpoint of client.myEndpoints.list()) {
  console.log(endpoint.name);
}

// Get just the first page
const firstPage = await client.myEndpoints.list().firstPage();

// Get all items as an array (loads all into memory)
const allItems = await client.myEndpoints.list().all();

// Get first N items
const top10 = await client.myEndpoints.list().take(10);
```

## TypeScript Support

This SDK is written in TypeScript and provides full type safety:

```typescript
import {
  // Client
  SyftHubClient,
  SyftHubClientOptions,

  // Enums
  Visibility,
  EndpointType,
  UserRole,

  // Types
  User,
  Endpoint,
  EndpointPublic,
  Policy,
  Connection,
  AuthTokens,

  // Input types
  UserRegisterInput,
  EndpointCreateInput,
  EndpointUpdateInput,

  // Errors
  SyftHubError,
  AuthenticationError,
  ValidationError,

  // Utilities
  PageIterator,
  getEndpointPublicPath,
} from '@syfthub/sdk';

// All types are properly inferred
const endpoint: Endpoint = await client.myEndpoints.create({
  name: 'My API',
  type: EndpointType.MODEL,
});
```

## Comparison with Python SDK

| Python | TypeScript |
|--------|------------|
| `client.auth.login(username, password)` | `client.auth.login(username, password)` |
| `client.my_endpoints.list()` | `client.myEndpoints.list()` |
| `for ep in client.hub.browse()` | `for await (const ep of client.hub.browse())` |
| `client.get_tokens()` | `client.getTokens()` |
| `client.set_tokens(tokens)` | `client.setTokens(tokens)` |
| `client.is_authenticated` | `client.isAuthenticated` |

The TypeScript SDK follows JavaScript/TypeScript conventions (camelCase) while providing the same functionality as the Python SDK.

## Requirements

- Node.js 18+ (for native `fetch` support)
- Or any modern browser

## License

MIT
