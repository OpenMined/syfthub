# Publishing Endpoints

## Concepts

An endpoint represents an AI model or data source registered on SyftHub. Every endpoint is addressed as `/{owner}/{slug}` and has a type of `model`, `data_source`, or `model_data_source`.

## Creating an Endpoint

### Via API

```
POST /api/v1/endpoints
```

```json
{
  "name": "My Model",
  "type": "model",
  "visibility": "public",
  "description": "A text generation model",
  "tags": ["nlp", "text-generation"],
  "connect": "https://my-model.example.com/v1",
  "slug": "my-model"
}
```

### Via Python SDK

```python
from syfthub import SyftHubClient

client = SyftHubClient(base_url="http://localhost:8080")
client.login("username", "password")

endpoint = client.my_endpoints.create({
    "name": "My Model",
    "type": "model",
    "visibility": "public",
    "description": "A text generation model",
})
```

### Via TypeScript SDK

```typescript
import { SyftHubClient } from "@syfthub/sdk";

const client = new SyftHubClient({ baseUrl: "http://localhost:8080" });
await client.auth.login({ email: "user@example.com", password: "password" });

const endpoint = await client.myEndpoints.create({
  name: "My Model",
  type: "model",
  visibility: "public",
  description: "A text generation model",
});
```

### Via CLI

```bash
# Use the API directly if the CLI does not have a dedicated add command
curl -X POST http://localhost:8080/api/v1/endpoints \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My Model","type":"model","visibility":"public"}'
```

## Visibility Options

| Visibility | Who can access |
|------------|---------------|
| `PUBLIC` | Anyone, including unauthenticated users |
| `INTERNAL` | Any authenticated user |
| `PRIVATE` | Owner or organization members only (returns 404 to others, not 403) |

## Health Reporting

Report endpoint health so the hub can display live status:

```
POST /api/v1/endpoints/health
```

```json
{
  "endpoints": [
    {
      "slug": "my-model",
      "status": "online",
      "url": "https://my-model.example.com/v1",
      "ttl_seconds": 60
    }
  ]
}
```

The health monitor re-evaluates reported health every 30 seconds: once a
report's TTL has expired the endpoint stops counting as healthy, and after
enough consecutive failures it is deactivated. The monitor does not call
endpoint URLs itself — status is what the owner reports.

## Benchmark Reporting

Report the results of your own benchmark run against your own endpoint —
alongside health status, but for output quality rather than reachability:

```
POST /api/v1/endpoints/quality
```

The badge needs two figures: the headline (answer accuracy, or for a
search-only endpoint, how often it found the right material) and the share of
unanswerable questions it answered anyway. `reliable` says whether the
benchmark vouches for the figures at all; a card it does not vouch for is
still shown, but muted rather than colored.

Unlike health, a card has no TTL: it stands until replaced or withdrawn with
`DELETE /api/v1/endpoints/quality/{slug}`. The marketplace shows nothing for
an endpoint that has never been measured.

See the [API reference](../api/backend.md) for the full request/response shape.

## Endpoint Sync

To replace all of your endpoints in one call (destructive — removes endpoints not in the list):

```
POST /api/v1/endpoints/sync
```

```json
{
  "endpoints": [
    {
      "name": "My Model",
      "type": "model",
      "visibility": "public",
      "connect": "https://my-model.example.com/v1",
      "slug": "my-model"
    }
  ]
}
```

This is useful for CI/CD pipelines that declaratively manage endpoints.
