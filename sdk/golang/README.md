# SyftHub Go SDK

Official Go SDK for SyftHub - a platform for RAG-powered AI endpoints.

## Installation

```bash
go get github.com/openmined/syfthub/sdk/golang
```

## Quick Start

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/openmined/syfthub/sdk/golang/syfthub"
)

func main() {
    // Create client (reads SYFTHUB_URL from environment)
    client, err := syfthub.NewClient()
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()

    ctx := context.Background()

    // Login
    user, err := client.Auth.Login(ctx, "username", "password")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Logged in as: %s\n", user.Username)

    // RAG Chat Query
    chat := client.Chat()
    response, err := chat.Complete(ctx, &syfthub.ChatRequest{
        Prompt:      "What is machine learning?",
        Model:       "alice/gpt-model",
        DataSources: []string{"bob/ml-docs", "carol/tutorials"},
    })
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println(response.Response)
}
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SYFTHUB_URL` | SyftHub API URL | `https://hub.syft.com` |
| `SYFTHUB_AGGREGATOR_URL` | Aggregator service URL | Auto-discovered |
| `SYFTHUB_API_TOKEN` | API token for authentication | - |

### Client Options

```go
client, err := syfthub.NewClient(
    syfthub.WithBaseURL("https://hub.syft.com"),
    syfthub.WithTimeout(30 * time.Second),
    syfthub.WithAggregatorURL("https://aggregator.syft.com"),
    syfthub.WithAPIToken("your-api-token"),
)
```

## Authentication

### Username/Password Login

```go
user, err := client.Auth.Login(ctx, "username", "password")
```

### API Token Authentication

```go
// Via environment variable
os.Setenv("SYFTHUB_API_TOKEN", "your-api-token")
client, _ := syfthub.NewClient()

// Or via option
client, _ := syfthub.NewClient(syfthub.WithAPIToken("your-api-token"))
```

### Register New User

```go
user, err := client.Auth.Register(ctx, &syfthub.RegisterRequest{
    Username: "newuser",
    Email:    "user@example.com",
    Password: "securepassword",
    FullName: "New User",
})
```

## Chat (RAG Queries)

### Complete (Non-Streaming)

```go
chat := client.Chat()

response, err := chat.Complete(ctx, &syfthub.ChatRequest{
    Prompt:      "Explain neural networks",
    Model:       "owner/model-slug",
    DataSources: []string{"owner1/docs", "owner2/kb"},
    TopK:        5,
    MaxTokens:   1024,
    Temperature: 0.7,
})

fmt.Println(response.Response)
fmt.Printf("Retrieval: %dms, Generation: %dms\n",
    response.Metadata.RetrievalTimeMs,
    response.Metadata.GenerationTimeMs)
```

### Streaming

```go
events, errChan := chat.Stream(ctx, &syfthub.ChatRequest{
    Prompt: "What is Python?",
    Model:  "owner/model",
})

for event := range events {
    switch e := event.(type) {
    case *syfthub.TokenEvent:
        fmt.Print(e.Content)
    case *syfthub.RetrievalCompleteEvent:
        fmt.Printf("[Retrieved %d docs]\n", e.TotalDocuments)
    case *syfthub.DoneEvent:
        fmt.Println("\nComplete!")
    case *syfthub.ErrorEvent:
        fmt.Printf("Error: %s\n", e.Message)
    }
}

if err := <-errChan; err != nil {
    log.Fatal(err)
}
```

### Available Models and Data Sources

```go
// Get available models
models, err := chat.GetAvailableModels(ctx)
for _, m := range models {
    fmt.Printf("%s/%s: %s\n", m.OwnerUsername, m.Slug, m.Name)
}

// Get available data sources
sources, err := chat.GetAvailableDataSources(ctx)
```

## Hub Discovery

### Browse Public Endpoints

```go
iter := client.Hub.Browse(ctx, syfthub.WithPageSize(20))
for iter.Next(ctx) {
    ep := iter.Value()
    fmt.Printf("%s/%s: %s\n", ep.OwnerUsername, ep.Slug, ep.Name)
}
if err := iter.Err(); err != nil {
    log.Fatal(err)
}
```

### Search Endpoints

```go
results, err := client.Hub.Search(ctx, "machine learning",
    syfthub.WithTopK(10),
    syfthub.WithMinScore(0.5),
)
for _, r := range results {
    fmt.Printf("[%.2f] %s\n", r.RelevanceScore, r.Name)
}
```

### Trending Endpoints

```go
iter := client.Hub.Trending(ctx, syfthub.WithMinStars(10))
for iter.Next(ctx) {
    ep := iter.Value()
    fmt.Printf("%s - %d stars\n", ep.Name, ep.StarsCount)
}
```

### Star/Unstar

```go
err := client.Hub.Star(ctx, "owner/endpoint")
err = client.Hub.Unstar(ctx, "owner/endpoint")

starred, err := client.Hub.IsStarred(ctx, "owner/endpoint")
```

## Endpoint Management

### List My Endpoints

```go
iter := client.MyEndpoints.List(ctx,
    syfthub.WithVisibility(syfthub.VisibilityPublic),
)
for iter.Next(ctx) {
    ep := iter.Value()
    fmt.Println(ep.Name)
}
```

### Create Endpoint

```go
endpoint, err := client.MyEndpoints.Create(ctx, &syfthub.CreateEndpointRequest{
    Name:        "My API",
    Type:        syfthub.EndpointTypeModel,
    Visibility:  syfthub.VisibilityPublic,
    Description: "A cool AI model",
    Readme:      "# My API\n\nDocumentation here.",
})
```

### Update/Delete

```go
endpoint, err := client.MyEndpoints.Update(ctx, "owner/slug",
    &syfthub.UpdateEndpointRequest{
        Description: ptr("Updated description"),
    },
)

err = client.MyEndpoints.Delete(ctx, "owner/slug")
```

## User Management

### Update Profile

```go
user, err := client.Users.Update(ctx, &syfthub.UpdateUserRequest{
    FullName: ptr("John Doe"),
})
```

### Check Username/Email Availability

```go
available, err := client.Users.CheckUsername(ctx, "newusername")
available, err = client.Users.CheckEmail(ctx, "new@example.com")
```

### Aggregator Configurations

```go
// List aggregators
aggregators, err := client.Users.Aggregators.List(ctx)

// Create aggregator
agg, err := client.Users.Aggregators.Create(ctx,
    "My Aggregator",
    "https://my-aggregator.example.com",
)

// Set as default
agg, err = client.Users.Aggregators.SetDefault(ctx, agg.ID)

// Delete
err = client.Users.Aggregators.Delete(ctx, agg.ID)
```

## API Tokens

```go
tokens := client.APITokens()

// Create token (SAVE THE TOKEN - only shown once!)
result, err := tokens.Create(ctx, &syfthub.CreateAPITokenRequest{
    Name:   "CI/CD Pipeline",
    Scopes: []syfthub.APITokenScope{syfthub.APITokenScopeWrite},
})
fmt.Println("Token:", result.Token) // Save this!

// List tokens
response, err := tokens.List(ctx)
for _, t := range response.Tokens {
    fmt.Printf("%s: %s\n", t.Name, t.TokenPrefix)
}

// Revoke
err = tokens.Revoke(ctx, tokenID)
```

## Accounting (Billing)

```go
// Get accounting resource (auto-fetches credentials from backend)
accounting, err := client.Accounting(ctx)

// Check balance
user, err := accounting.GetUser(ctx)
fmt.Printf("Balance: %.2f credits\n", user.Balance)

// List transactions
iter := accounting.GetTransactions(ctx)
for iter.Next(ctx) {
    tx := iter.Value()
    fmt.Printf("%s: %.2f (%s -> %s)\n",
        tx.Status, tx.Amount, tx.SenderEmail, tx.RecipientEmail)
}

// Create transaction
tx, err := accounting.CreateTransaction(ctx, &syfthub.CreateTransactionRequest{
    RecipientEmail: "recipient@example.com",
    Amount:         10.0,
})

// Confirm transaction
tx, err = accounting.ConfirmTransaction(ctx, tx.ID)
```

## Direct SyftAI Queries

For custom RAG pipelines, use the low-level SyftAI resource:

```go
syftai := client.SyftAI()

// Query data source directly
docs, err := syftai.QueryDataSource(ctx, &syfthub.QueryDataSourceRequest{
    Endpoint:  syfthub.EndpointRef{URL: "http://syftai:8080", Slug: "docs"},
    Query:     "What is Python?",
    UserEmail: "user@example.com",
    TopK:      10,
})

// Query model directly
response, err := syftai.QueryModel(ctx, &syfthub.QueryModelRequest{
    Endpoint: syfthub.EndpointRef{URL: "http://syftai:8080", Slug: "gpt"},
    Messages: []syfthub.Message{
        {Role: "system", Content: "You are helpful."},
        {Role: "user", Content: "Hello!"},
    },
    UserEmail: "user@example.com",
})

// Stream model response
chunks, errChan := syftai.QueryModelStream(ctx, &syfthub.QueryModelRequest{...})
for chunk := range chunks {
    fmt.Print(chunk)
}
```

## Pagination

All list operations return a `PageIterator[T]` for lazy pagination:

```go
iter := client.Hub.Browse(ctx)

// Iterate through all items
for iter.Next(ctx) {
    item := iter.Value()
    // ...
}
if err := iter.Err(); err != nil {
    log.Fatal(err)
}

// Or get all items at once
all, err := iter.All(ctx)

// Or get first N items
first5, err := iter.Take(ctx, 5)

// Or get first page only
firstPage, err := iter.FirstPage(ctx)

// Or use callback
err := iter.ForEach(ctx, func(item T) bool {
    fmt.Println(item)
    return true // continue iteration
})
```

## Error Handling

All errors implement the `SyftHubError` interface:

```go
response, err := chat.Complete(ctx, req)
if err != nil {
    var authErr *syfthub.AuthenticationError
    var notFound *syfthub.NotFoundError
    var epErr *syfthub.EndpointResolutionError

    switch {
    case errors.As(err, &authErr):
        fmt.Println("Authentication failed:", authErr.Message)
    case errors.As(err, &notFound):
        fmt.Println("Not found:", notFound.Message)
    case errors.As(err, &epErr):
        fmt.Printf("Could not resolve endpoint '%s': %s\n",
            epErr.EndpointPath, epErr.Message)
    default:
        fmt.Println("Error:", err)
    }
}
```

### Error Types

| Error | Description |
|-------|-------------|
| `AuthenticationError` | Invalid credentials or expired token |
| `AuthorizationError` | Insufficient permissions |
| `NotFoundError` | Resource not found |
| `ValidationError` | Invalid request data |
| `NetworkError` | Connection failed |
| `ConfigurationError` | Missing or invalid configuration |
| `ChatError` | Chat/RAG operation failed |
| `AggregatorError` | Aggregator service error |
| `EndpointResolutionError` | Could not resolve endpoint path |
| `RetrievalError` | Document retrieval failed |
| `GenerationError` | Model generation failed |

## Examples

See the [examples](examples/) directory for complete working examples:

```bash
cd examples/demo
go run . -username alice -password secret123 \
    -model "bob/gpt-model" \
    -data-sources "carol/docs" \
    -prompt "What is machine learning?"
```

## License

Apache 2.0
