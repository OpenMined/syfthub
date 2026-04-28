# SyftHub SDKs

Official client libraries for talking to SyftHub from your code.

| SDK | Language | Path | Install |
|-----|----------|------|---------|
| Python | 3.10+ | [`sdk/python`](python) | `pip install syfthub-sdk` |
| TypeScript | Node 18+ / browsers | [`sdk/typescript`](typescript) | `npm install @syfthub/sdk` |
| Go (hub client) | 1.21+ | [`sdk/golang/syfthub`](golang) | `go get github.com/openmined/syfthub/sdk/golang` |
| Go (endpoint SDK) | 1.21+ | [`sdk/golang/syfthubapi`](golang/syfthubapi) | `go get github.com/openmined/syfthub/sdk/golang/syfthubapi` |

All SDKs cover the same core surface — auth, browsing, endpoint management, and RAG chat — adapted to each language's conventions.

## A taste

```python
# Python
from syfthub_sdk import SyftHubClient

client = SyftHubClient(base_url="https://hub.syft.com")
client.auth.login(email="alice@example.com", password="...")
for ep in client.hub.browse():
    print(ep.name)
```

```typescript
// TypeScript
import { SyftHubClient } from '@syfthub/sdk';

const client = new SyftHubClient({ baseUrl: 'https://hub.syft.com' });
await client.auth.login({ email: 'alice@example.com', password: '...' });
for await (const ep of client.hub.browse()) console.log(ep.name);
```

```go
// Go
client, _ := syfthub.NewClient()
client.Auth.Login(ctx, "alice", "...")
iter := client.Hub.Browse(ctx)
for iter.Next(ctx) { fmt.Println(iter.Value().Name) }
```

## Documentation

Each SDK has its own README with a fuller walkthrough:

- [Python SDK](python/README.md) · [guide](../docs/guides/python-sdk.md)
- [TypeScript SDK](typescript/README.md) · [guide](../docs/guides/typescript-sdk.md)
- [Go SDK](golang/README.md)
- [Go endpoint SDK](golang/syfthubapi/README.md)

## License

[Apache 2.0](../LICENSE)
