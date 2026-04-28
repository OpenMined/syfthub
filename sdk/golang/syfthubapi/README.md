# SyftHub API — Go SDK for endpoint authors

A Go framework for building SyftHub Spaces — the servers that host the actual model and data-source endpoints. Think of it as FastAPI for SyftHub.

If you want to **call** SyftHub from Go, you want [`syfthub`](../README.md) instead.

## Install

```bash
go get github.com/openmined/syfthub/sdk/golang/syfthubapi
```

## Hello, endpoint

```go
package main

import (
    "context"
    "log"

    "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func main() {
    app := syfthubapi.New()

    app.DataSource("papers").
        Name("Research Papers").
        Description("Search through research papers").
        Handler(func(ctx context.Context, query string, req *syfthubapi.RequestContext) ([]syfthubapi.Document, error) {
            return []syfthubapi.Document{
                {DocumentID: "1", Content: "...", SimilarityScore: 0.95},
            }, nil
        })

    app.Model("chat").
        Name("Chat Assistant").
        Handler(func(ctx context.Context, messages []syfthubapi.Message, req *syfthubapi.RequestContext) (string, error) {
            return "Hello! How can I help?", nil
        })

    if err := app.Run(context.Background()); err != nil {
        log.Fatal(err)
    }
}
```

That's a complete Space — registered with SyftHub, ready to receive RAG requests.

## What's in the box

- **Declarative endpoints** for both data sources and models.
- **HTTP and NATS tunneling** transports — same code, different deploy.
- **File-based endpoints** with hot reload, so non-Go authors can ship endpoints from a folder of YAML + Python.
- **Policy framework** — rate limits, access control, time windows, plus composable `AllOf` / `AnyOf` / `Not`.
- **Middleware**, lifecycle hooks, and JWT verification against the SyftHub backend.

## Configuration

Set via env vars or functional options on `New(...)`:

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | SyftHub backend URL (required) |
| `SYFTHUB_API_KEY` | API token (PAT) (required) |
| `SPACE_URL` | `http://...` for direct HTTP, or `tunneling:username` for NATS |
| `SERVER_PORT` | HTTP port (default `8000`) |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `HEARTBEAT_ENABLED` | default `true` |
| `ENDPOINTS_PATH` | path to file-based endpoints |

## Examples

Runnable examples live in [`../examples/`](../examples/) — start with `file_based/endpoints/sample-model`.

## License

[Apache 2.0](../../../LICENSE)
