# SyftHub SDKs

Official SDKs for interacting with the SyftHub API.

## Available SDKs

| SDK | Language | Directory | Status |
|-----|----------|-----------|--------|
| [Python SDK](./python/) | Python 3.10+ | `sdk/python/` | Stable |
| [TypeScript SDK](./typescript/) | TypeScript/Node.js 18+ | `sdk/typescript/` | Stable |

## Quick Comparison

### Installation

**Python:**
```bash
pip install syfthub-sdk
# or
uv add syfthub-sdk
```

**TypeScript:**
```bash
npm install @syfthub/sdk
# or
yarn add @syfthub/sdk
```

### Basic Usage

**Python:**
```python
from syfthub_sdk import SyftHubClient

client = SyftHubClient(base_url="https://hub.syft.com")
user = await client.auth.login("alice", "password")

for endpoint in client.hub.browse():
    print(endpoint.name)
```

**TypeScript:**
```typescript
import { SyftHubClient } from '@syfthub/sdk';

const client = new SyftHubClient({ baseUrl: 'https://hub.syft.com' });
const user = await client.auth.login('alice', 'password');

for await (const endpoint of client.hub.browse()) {
  console.log(endpoint.name);
}
```

## API Parity

Both SDKs provide the same functionality with identical APIs (adjusted for language conventions):

| Feature | Python | TypeScript |
|---------|--------|------------|
| Auth | `client.auth.*` | `client.auth.*` |
| My Endpoints | `client.my_endpoints.*` | `client.myEndpoints.*` |
| Hub | `client.hub.*` | `client.hub.*` |
| Users | `client.users.*` | `client.users.*` |
| Accounting | `client.accounting.*` | `client.accounting.*` |

### Naming Conventions

| Python (snake_case) | TypeScript (camelCase) |
|---------------------|------------------------|
| `my_endpoints` | `myEndpoints` |
| `full_name` | `fullName` |
| `get_tokens()` | `getTokens()` |
| `is_authenticated` | `isAuthenticated` |

### Iteration

**Python:**
```python
for endpoint in client.hub.browse():
    print(endpoint.name)
```

**TypeScript:**
```typescript
for await (const endpoint of client.hub.browse()) {
  console.log(endpoint.name);
}
```

## Environment Variables

Both SDKs support the same environment variables:

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | SyftHub API base URL |
| `SYFTHUB_ACCOUNTING_URL` | Accounting service URL (optional) |
| `SYFTHUB_ACCOUNTING_EMAIL` | Accounting auth email (optional) |
| `SYFTHUB_ACCOUNTING_PASSWORD` | Accounting auth password (optional) |

## Development

### Python SDK

```bash
cd sdk/python
uv sync
uv run pytest
```

### TypeScript SDK

```bash
cd sdk/typescript
npm install
npm run build
npm test
```

## License

MIT
