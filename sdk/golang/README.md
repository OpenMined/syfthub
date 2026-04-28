# SyftHub Go SDK

The official Go client for [SyftHub](https://github.com/IonesioJunior/syfthub) — discover endpoints, publish your own, and run RAG chats from a Go program.

## Install

```bash
go get github.com/openmined/syfthub/sdk/golang
```

## Quick start

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/openmined/syfthub/sdk/golang/syfthub"
)

func main() {
    client, err := syfthub.NewClient()
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()

    ctx := context.Background()
    if _, err := client.Auth.Login(ctx, "alice", "..."); err != nil {
        log.Fatal(err)
    }

    // RAG chat
    resp, err := client.Chat().Complete(ctx, &syfthub.ChatRequest{
        Prompt:      "What is machine learning?",
        Model:       "alice/gpt-model",
        DataSources: []string{"bob/ml-docs"},
    })
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println(resp.Response)
}
```

The SDK covers auth, hub discovery (browse / search / trending / star), endpoint management, RAG chat (streaming + non-streaming), API tokens, and accounting. Every list operation returns a `PageIterator[T]` for lazy pagination.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SYFTHUB_URL` | SyftHub API URL | `https://hub.syft.com` |
| `SYFTHUB_AGGREGATOR_URL` | Aggregator URL | auto-discovered |
| `SYFTHUB_API_TOKEN` | API token for authentication | — |

Or pass functional options to `NewClient(...)` — `WithBaseURL`, `WithTimeout`, `WithAPIToken`, `WithAggregatorURL`.

## Examples

Runnable examples live in [`examples/`](examples/):

```bash
cd examples/demo
go run . -username alice -password ... \
    -model "bob/gpt-model" -data-sources "carol/docs" \
    -prompt "What is machine learning?"
```

## Building Spaces

To build a SyftHub Space (an endpoint server) in Go, see [`syfthubapi`](syfthubapi/README.md) — the companion SDK for endpoint authors.

## License

[Apache 2.0](../../LICENSE)
