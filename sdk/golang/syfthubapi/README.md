# SyftHub API - Go SDK

A Go framework for building SyftHub Spaces with a FastAPI-like interface. This is a 1:1 feature-complete port of the Python `syfthub-api` package.

## Features

- **Declarative endpoint registration** via builder pattern
- **Two execution modes**: HTTP direct and NATS tunneling
- **File-based endpoint configuration** with hot-reload
- **Policy enforcement framework** (pre/post execution hooks)
- **Heartbeat mechanism** for availability signaling
- **JWT token verification** via SyftHub backend
- **Middleware support** for request/response processing
- **Python subprocess execution** for file-based endpoints

## Installation

```bash
go get github.com/openmined/syfthub/sdk/golang/syfthubapi
```

## Quick Start

### Basic HTTP Server

```go
package main

import (
    "context"
    "log"

    "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func main() {
    app := syfthubapi.New()

    // Register a data source endpoint
    app.DataSource("papers").
        Name("Research Papers").
        Description("Search through research papers").
        Handler(func(ctx context.Context, query string, reqCtx *syfthubapi.RequestContext) ([]syfthubapi.Document, error) {
            return []syfthubapi.Document{
                {DocumentID: "1", Content: "...", SimilarityScore: 0.95},
            }, nil
        })

    // Register a model endpoint
    app.Model("chat").
        Name("Chat Assistant").
        Description("An AI chat assistant").
        Handler(func(ctx context.Context, messages []syfthubapi.Message, reqCtx *syfthubapi.RequestContext) (string, error) {
            return "Hello! How can I help?", nil
        })

    // Run the server
    if err := app.Run(context.Background()); err != nil {
        log.Fatal(err)
    }
}
```

### Configuration

Configuration is loaded from environment variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `SYFTHUB_URL` | SyftHub backend URL | Yes |
| `SYFTHUB_API_KEY` | API token (PAT) for authentication | Yes |
| `SPACE_URL` | Public URL or `tunneling:username` | Yes |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | No |
| `SERVER_HOST` | HTTP server bind address | No |
| `SERVER_PORT` | HTTP server port (default: 8000) | No |
| `HEARTBEAT_ENABLED` | Enable heartbeat (default: true) | No |
| `HEARTBEAT_TTL_SECONDS` | Heartbeat TTL (default: 300) | No |
| `ENDPOINTS_PATH` | Path to file-based endpoints | No |
| `WATCH_ENABLED` | Enable hot-reload (default: true) | No |

Or use functional options:

```go
app := syfthubapi.New(
    syfthubapi.WithSyftHubURL("https://syfthub.example.com"),
    syfthubapi.WithAPIKey("syft_pat_xxx"),
    syfthubapi.WithSpaceURL("http://localhost:8001"),
    syfthubapi.WithLogLevel("DEBUG"),
    syfthubapi.WithServerPort(8001),
    syfthubapi.WithHeartbeatEnabled(true),
    syfthubapi.WithEndpointsPath("./endpoints"),
)
```

## Endpoint Types

### Data Source

Data sources return documents based on a search query:

```go
app.DataSource("slug").
    Name("Display Name").
    Description("Brief description").
    Version("1.0.0").
    Handler(func(ctx context.Context, query string, reqCtx *syfthubapi.RequestContext) ([]syfthubapi.Document, error) {
        // Return relevant documents
        return []syfthubapi.Document{...}, nil
    })
```

### Model

Models process messages and return a response:

```go
app.Model("slug").
    Name("Display Name").
    Description("Brief description").
    Version("1.0.0").
    Handler(func(ctx context.Context, messages []syfthubapi.Message, reqCtx *syfthubapi.RequestContext) (string, error) {
        // Process messages and return response
        return "response", nil
    })
```

## Execution Modes

### HTTP Mode (Default)

Set `SPACE_URL` to an HTTP URL:

```bash
export SPACE_URL=http://localhost:8001
```

The server listens directly on the specified host and port.

### Tunnel Mode

Set `SPACE_URL` to use NATS tunneling:

```bash
export SPACE_URL=tunneling:my-username
```

The server connects to NATS and receives requests via pub/sub.

## File-Based Endpoints

Endpoints can be defined via directory structure:

```
endpoints/
├── my-model/
│   ├── README.md        # YAML frontmatter + docs
│   ├── runner.py        # Python handler
│   ├── .env             # Environment variables
│   ├── pyproject.toml   # Dependencies
│   └── policy/
│       └── rate_limit.yaml
```

### README.md Frontmatter

```yaml
---
slug: my-model
type: model              # or "data_source"
name: My Model
description: Description here
enabled: true
version: "1.0.0"
env:
  required: [API_KEY]
  optional: [DEBUG]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# Documentation
```

### runner.py Handler

```python
def handler(messages: list[dict], context: dict = None) -> str:
    """Handle model requests."""
    return "response"

# For data sources:
def handler(query: str, context: dict = None) -> list[dict]:
    """Handle data source requests."""
    return [{"document_id": "1", "content": "...", "similarity_score": 0.9}]
```

## Policy Framework

### Built-in Policies

```go
import "github.com/openmined/syfthub/sdk/golang/syfthubapi/policy"

// Rate limiting
rateLimit := policy.NewRateLimitPolicy("rate-limit", 100, 3600) // 100 requests per hour

// Access control
accessPolicy := policy.NewAccessGroupPolicy("access",
    []string{"alice", "bob"},  // allowed users
    []string{"admin"},         // allowed roles
    nil,                       // denied users
    nil,                       // denied roles
)

// Time window
timeWindow := policy.NewTimeWindowPolicy("business-hours", 9, 17, nil, nil)

// Add to endpoint
app.Model("premium").
    Policies(rateLimit, accessPolicy).
    Handler(...)
```

### YAML Policy Configuration

```yaml
# policy/rate_limit.yaml
type: rate_limit
name: rate-limit
args:
  max_requests: 100
  window_seconds: 3600
```

### Composite Policies

```go
// All policies must pass
allOf := policy.NewAllOfPolicy("all", policy1, policy2)

// At least one must pass
anyOf := policy.NewAnyOfPolicy("any", policy1, policy2)

// Negate a policy
not := policy.NewNotPolicy("not-admin", adminPolicy)
```

## Middleware

```go
// Built-in middleware
app.Use(syfthubapi.LoggingMiddleware(logger))
app.Use(syfthubapi.RecoveryMiddleware(logger))
app.Use(syfthubapi.TimeoutMiddleware(30 * time.Second))

// Custom middleware
app.Use(func(next syfthubapi.RequestHandler) syfthubapi.RequestHandler {
    return func(ctx context.Context, req *syfthubapi.TunnelRequest) (*syfthubapi.TunnelResponse, error) {
        // Pre-processing
        resp, err := next(ctx, req)
        // Post-processing
        return resp, err
    }
})
```

## Lifecycle Hooks

```go
app.OnStartup(func(ctx context.Context) error {
    // Initialize database connections, etc.
    return nil
})

app.OnShutdown(func(ctx context.Context) error {
    // Clean up resources
    return nil
})
```

## Error Handling

All errors implement `error` and can be checked with `errors.Is()`:

```go
import "errors"

if errors.Is(err, syfthubapi.ErrPolicyDenied) {
    // Handle policy denial
}

if errors.Is(err, syfthubapi.ErrAuthentication) {
    // Handle auth error
}
```

## Package Structure

```
syfthubapi/
├── api.go              # Main SyftAPI struct
├── config.go           # Configuration management
├── endpoint.go         # Endpoint types and builder
├── schemas.go          # Request/Response types
├── errors.go           # Error types
├── middleware.go       # Middleware chain
├── auth.go             # Authentication
├── transport/
│   ├── transport.go    # Transport interface
│   ├── http.go         # HTTP transport
│   └── nats.go         # NATS transport
├── heartbeat/
│   └── heartbeat.go    # Heartbeat manager
├── policy/
│   ├── policy.go       # Policy interface
│   ├── loader.go       # YAML loading
│   └── builtin.go      # Built-in policies
└── filemode/
    ├── provider.go     # File provider
    ├── loader.go       # README parsing
    ├── watcher.go      # File watching
    ├── executor.go     # Subprocess execution
    └── venv.go         # Virtual env management
```

## Comparison with Python SDK

| Feature | Python | Go |
|---------|--------|-----|
| Endpoint registration | `@app.datasource()` decorator | `app.DataSource().Handler()` builder |
| Async handlers | `async def` | Goroutines + context |
| Error handling | Exceptions | Error returns |
| Configuration | Pydantic Settings | Functional options |
| Hot-reload | watchdog | fsnotify |
| Subprocess execution | loky | os/exec |

## License

Apache 2.0
