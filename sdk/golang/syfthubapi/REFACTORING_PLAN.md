# SyftHub Go SDK Refactoring Plan

## Overview

This plan addresses all identified architectural issues and implements P0, P1, and P2 recommendations from the SDK evaluation.

**Estimated Total Effort**: 8-10 hours
**Risk Level**: Medium (significant refactoring with proper safety measures)

---

## Phase 0: Preparation (Before Any Changes)

### 0.1 Create Test Foundation
Before refactoring, create basic tests to ensure behavior preservation.

**Test Files to Create**:
| File | Coverage |
|------|----------|
| `config_test.go` | LoadFromEnv, Validate, IsTunnelMode, DeriveNATSWebSocketURL |
| `endpoint_test.go` | Builders, registry, invocation |
| `api_test.go` | Request handling, policy execution |
| `auth_test.go` | Auth and sync clients with mock HTTP |
| `middleware_test.go` | Middleware chain behavior |

### 0.2 Safety Rules
- Each commit leaves code in working state
- Use Strangler Fig pattern: add new code alongside old, switch, remove old
- Run tests after each step
- Use `go test -race` to detect race conditions

---

## Phase 1: P0 Critical Security Fixes

### Step 1: Fix Token Verification (CRITICAL)

**Problem**: `api.go:565-580` returns hardcoded user for ANY non-empty token, bypassing all authentication.

**Files Changed**: `api.go`

**Changes**:

1. Add `authClient` field to `SyftAPI` struct:
```go
type SyftAPI struct {
    // ... existing fields
    authClient *AuthClient  // NEW
}
```

2. Initialize in `New()`:
```go
func New(opts ...Option) *SyftAPI {
    // ... existing setup
    slogLogger := NewSlogLogger(logger)
    authClient := NewAuthClient(config.SyftHubURL, config.APIKey, slogLogger)

    return &SyftAPI{
        // ... existing fields
        authClient: authClient,
    }
}
```

3. Replace `verifyToken` implementation:
```go
func (api *SyftAPI) verifyToken(ctx context.Context, token string) (*UserContext, error) {
    if api.authClient == nil {
        return nil, &AuthenticationError{Message: "auth client not initialized"}
    }
    return api.authClient.VerifyToken(ctx, token)
}
```

**Risk**: Medium - Changes authentication behavior
**Test**: Verify with real backend or mock AuthClient

---

### Step 2: Fix Race Condition in Policy Execution

**Problem**: `runPreExecutePolicies` and `runPostExecutePolicies` read `globalPolicies` without holding a lock while `AddPolicy` writes with a lock.

**Files Changed**: `api.go`

**Changes**:

1. Update `runPreExecutePolicies` (line 583):
```go
func (api *SyftAPI) runPreExecutePolicies(ctx context.Context, reqCtx *RequestContext, endpoint *Endpoint) error {
    // Copy reference under read lock
    api.mu.RLock()
    policies := api.globalPolicies
    api.mu.RUnlock()

    // Run global policies first
    for _, p := range policies {
        if err := p.PreExecute(ctx, reqCtx); err != nil {
            return &PolicyDeniedError{
                Policy:   p.Name(),
                Reason:   err.Error(),
                User:     reqCtx.User.Username,
                Endpoint: endpoint.Slug,
            }
        }
    }

    // Endpoint policies don't need lock (immutable after registration)
    for _, p := range endpoint.policies {
        // ... existing logic
    }

    return nil
}
```

2. Update `runPostExecutePolicies` (line 612) similarly.

**Risk**: Low - Adds safety without changing behavior
**Test**: Run with `go test -race ./...`

---

## Phase 2: P1 Correctness Fixes

### Step 3: Replace panic() with Error Return

**Problem**: `DeriveNATSWebSocketURL` panics on invalid input instead of returning error.

**Files Changed**: `config.go`, `auth.go`

**Changes in config.go**:

```go
// DeriveNATSWebSocketURL derives the NATS WebSocket URL from a SyftHub URL.
// Returns error if URL scheme is not http:// or https://.
func DeriveNATSWebSocketURL(syfthubURL string) (string, error) {
    if strings.HasPrefix(syfthubURL, "https://") {
        host := strings.TrimRight(syfthubURL[len("https://"):], "/")
        if !strings.Contains(host, ":") {
            host += ":443"
        }
        return "wss://" + host, nil
    }
    if strings.HasPrefix(syfthubURL, "http://") {
        host := strings.TrimRight(syfthubURL[len("http://"):], "/")
        if !strings.Contains(host, ":") {
            host += ":80"
        }
        return "ws://" + host, nil
    }
    return "", fmt.Errorf("cannot derive NATS URL from %q: must start with http:// or https://", syfthubURL)
}
```

**Changes in auth.go** (line 178):
```go
func (c *AuthClient) GetNATSCredentials(ctx context.Context, username string) (*NATSCredentials, error) {
    // ... existing code

    natsURL, err := DeriveNATSWebSocketURL(c.baseURL)
    if err != nil {
        return nil, &AuthenticationError{
            Message: "failed to derive NATS URL",
            Cause:   err,
        }
    }

    // ... rest of function
}
```

**Risk**: Low - API change but callers updated
**Test**: Unit test with invalid URLs

---

### Step 4: Handle LoadFromEnv Error

**Problem**: Error from `config.LoadFromEnv()` is silently ignored.

**Files Changed**: `api.go`

**Changes** (line 86):
```go
func New(opts ...Option) *SyftAPI {
    config := DefaultConfig()

    // Log warning but don't fail - env vars are optional
    if err := config.LoadFromEnv(); err != nil {
        slog.Warn("failed to load config from environment", "error", err)
    }

    // ... rest of function
}
```

**Risk**: Very low
**Test**: Set invalid env var, check warning logged

---

### Step 5: Add Comprehensive Unit Tests

**New Files**:
- `config_test.go`
- `endpoint_test.go`
- `api_test.go`
- `auth_test.go`
- `middleware_test.go`

Each test file should cover:
- Happy path
- Error cases
- Edge cases
- Concurrency (where applicable)

---

## Phase 3: P2 Design Improvements

### Step 6: Create PolicyExecutor (Extract Class)

**Problem**: SyftAPI is a God Object with too many responsibilities.

**New File**: `policy_executor.go`

```go
package syfthubapi

import (
    "context"
    "log/slog"
    "sync"
)

// PolicyExecutor manages policy evaluation for requests.
type PolicyExecutor struct {
    globalPolicies []Policy
    mu             sync.RWMutex
    logger         *slog.Logger
}

// NewPolicyExecutor creates a new policy executor.
func NewPolicyExecutor(logger *slog.Logger) *PolicyExecutor {
    return &PolicyExecutor{
        logger: logger,
    }
}

// AddGlobalPolicy adds a policy that applies to all endpoints.
func (e *PolicyExecutor) AddGlobalPolicy(p Policy) {
    e.mu.Lock()
    defer e.mu.Unlock()
    e.globalPolicies = append(e.globalPolicies, p)
}

// GlobalPolicies returns a copy of global policies (thread-safe).
func (e *PolicyExecutor) GlobalPolicies() []Policy {
    e.mu.RLock()
    defer e.mu.RUnlock()
    result := make([]Policy, len(e.globalPolicies))
    copy(result, e.globalPolicies)
    return result
}

// RunPreExecute runs pre-execution policies.
func (e *PolicyExecutor) RunPreExecute(ctx context.Context, reqCtx *RequestContext, endpoint *Endpoint) error {
    e.mu.RLock()
    policies := e.globalPolicies
    e.mu.RUnlock()

    // Run global policies first
    for _, p := range policies {
        if err := p.PreExecute(ctx, reqCtx); err != nil {
            return &PolicyDeniedError{
                Policy:   p.Name(),
                Reason:   err.Error(),
                User:     reqCtx.User.Username,
                Endpoint: endpoint.Slug,
            }
        }
    }

    // Run endpoint-specific policies
    for _, p := range endpoint.policies {
        if err := p.PreExecute(ctx, reqCtx); err != nil {
            return &PolicyDeniedError{
                Policy:   p.Name(),
                Reason:   err.Error(),
                User:     reqCtx.User.Username,
                Endpoint: endpoint.Slug,
            }
        }
    }

    return nil
}

// RunPostExecute runs post-execution policies in reverse order.
func (e *PolicyExecutor) RunPostExecute(ctx context.Context, reqCtx *RequestContext, endpoint *Endpoint, result any) error {
    // Run endpoint policies in reverse order
    for i := len(endpoint.policies) - 1; i >= 0; i-- {
        p := endpoint.policies[i]
        if err := p.PostExecute(ctx, reqCtx, result); err != nil {
            return &PolicyDeniedError{
                Policy:   p.Name(),
                Reason:   err.Error(),
                User:     reqCtx.User.Username,
                Endpoint: endpoint.Slug,
            }
        }
    }

    // Run global policies in reverse order
    e.mu.RLock()
    policies := e.globalPolicies
    e.mu.RUnlock()

    for i := len(policies) - 1; i >= 0; i-- {
        p := policies[i]
        if err := p.PostExecute(ctx, reqCtx, result); err != nil {
            return &PolicyDeniedError{
                Policy:   p.Name(),
                Reason:   err.Error(),
                User:     reqCtx.User.Username,
                Endpoint: endpoint.Slug,
            }
        }
    }

    return nil
}
```

---

### Step 7: Create RequestProcessor (Extract Class)

**New File**: `processor.go`

```go
package syfthubapi

import (
    "context"
    "encoding/json"
    "fmt"
    "log/slog"
    "time"
)

// RequestProcessor handles the execution of endpoint requests.
type RequestProcessor struct {
    registry       *EndpointRegistry
    policyExecutor *PolicyExecutor
    authClient     *AuthClient
    logger         *slog.Logger
}

// ProcessorConfig holds configuration for RequestProcessor.
type ProcessorConfig struct {
    Registry       *EndpointRegistry
    PolicyExecutor *PolicyExecutor
    AuthClient     *AuthClient
    Logger         *slog.Logger
}

// NewRequestProcessor creates a new request processor.
func NewRequestProcessor(cfg *ProcessorConfig) *RequestProcessor {
    return &RequestProcessor{
        registry:       cfg.Registry,
        policyExecutor: cfg.PolicyExecutor,
        authClient:     cfg.AuthClient,
        logger:         cfg.Logger,
    }
}

// Process handles an incoming tunnel request.
func (p *RequestProcessor) Process(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
    startTime := time.Now()

    p.logger.Debug("processing request",
        "correlation_id", req.CorrelationID,
        "endpoint", req.Endpoint.Slug,
        "endpoint_type", req.Endpoint.Type,
    )

    // Create request context
    reqCtx := NewRequestContext()
    reqCtx.EndpointSlug = req.Endpoint.Slug
    reqCtx.EndpointType = EndpointType(req.Endpoint.Type)

    // Verify token
    userCtx, err := p.authClient.VerifyToken(ctx, req.SatelliteToken)
    if err != nil {
        return p.errorResponse(req, TunnelErrorCodeAuthFailed, err.Error()), nil
    }
    reqCtx.User = userCtx

    // Get endpoint
    endpoint, ok := p.registry.Get(req.Endpoint.Slug)
    if !ok {
        return p.errorResponse(req, TunnelErrorCodeEndpointNotFound,
            fmt.Sprintf("endpoint not found: %s", req.Endpoint.Slug)), nil
    }

    if !endpoint.Enabled {
        return p.errorResponse(req, TunnelErrorCodeEndpointDisabled,
            fmt.Sprintf("endpoint disabled: %s", req.Endpoint.Slug)), nil
    }

    // Run pre-execution policies
    if err := p.policyExecutor.RunPreExecute(ctx, reqCtx, endpoint); err != nil {
        return p.errorResponse(req, TunnelErrorCodePolicyDenied, err.Error()), nil
    }

    // Execute handler using invoker pattern
    result, err := p.invokeEndpoint(ctx, req, endpoint, reqCtx)
    if err != nil {
        return p.errorResponse(req, TunnelErrorCodeExecutionFailed, err.Error()), nil
    }

    // Run post-execution policies
    reqCtx.Output = result
    if err := p.policyExecutor.RunPostExecute(ctx, reqCtx, endpoint, result); err != nil {
        return p.errorResponse(req, TunnelErrorCodePolicyDenied, err.Error()), nil
    }

    // Serialize response
    payload, err := json.Marshal(result)
    if err != nil {
        return p.errorResponse(req, TunnelErrorCodeInternalError,
            fmt.Sprintf("failed to serialize response: %v", err)), nil
    }

    processedAt := time.Now()
    return &TunnelResponse{
        Protocol:      "syfthub-tunnel/v1",
        Type:          "endpoint_response",
        CorrelationID: req.CorrelationID,
        Status:        "success",
        EndpointSlug:  req.Endpoint.Slug,
        Payload:       payload,
        Timing: &TunnelTiming{
            ReceivedAt:  startTime,
            ProcessedAt: processedAt,
            DurationMs:  processedAt.Sub(startTime).Milliseconds(),
        },
    }, nil
}

// invokeEndpoint executes the endpoint handler based on type.
func (p *RequestProcessor) invokeEndpoint(ctx context.Context, req *TunnelRequest, endpoint *Endpoint, reqCtx *RequestContext) (any, error) {
    endpointType := EndpointType(req.Endpoint.Type)

    switch endpointType {
    case EndpointTypeDataSource:
        var dsReq DataSourceQueryRequest
        if err := json.Unmarshal(req.Payload, &dsReq); err != nil {
            return nil, fmt.Errorf("invalid request payload: %w", err)
        }
        reqCtx.Input = dsReq.GetQuery()
        docs, err := endpoint.InvokeDataSource(ctx, dsReq.GetQuery(), reqCtx)
        if err != nil {
            return nil, err
        }
        return DataSourceQueryResponse{
            References: DataSourceReferences{Documents: docs},
        }, nil

    case EndpointTypeModel:
        var modelReq ModelQueryRequest
        if err := json.Unmarshal(req.Payload, &modelReq); err != nil {
            return nil, fmt.Errorf("invalid request payload: %w", err)
        }
        reqCtx.Input = modelReq.Messages
        response, err := endpoint.InvokeModel(ctx, modelReq.Messages, reqCtx)
        if err != nil {
            return nil, err
        }
        return ModelQueryResponse{
            Summary: ModelSummary{
                Message: ModelSummaryMessage{Content: response},
            },
        }, nil

    default:
        return nil, fmt.Errorf("unknown endpoint type: %s", req.Endpoint.Type)
    }
}

// errorResponse creates an error tunnel response.
func (p *RequestProcessor) errorResponse(req *TunnelRequest, code TunnelErrorCode, message string) *TunnelResponse {
    p.logger.Debug("returning error response",
        "correlation_id", req.CorrelationID,
        "code", code,
        "message", message,
    )
    return &TunnelResponse{
        Protocol:      "syfthub-tunnel/v1",
        Type:          "endpoint_response",
        CorrelationID: req.CorrelationID,
        Status:        "error",
        EndpointSlug:  req.Endpoint.Slug,
        Error: &TunnelError{
            Code:    code,
            Message: message,
        },
    }
}
```

---

### Step 8: Update SyftAPI to Use Extracted Components

**File Changed**: `api.go`

**Updated struct**:
```go
type SyftAPI struct {
    config           *Config
    logger           *slog.Logger
    registry         *EndpointRegistry
    transport        Transport
    heartbeatManager HeartbeatManager
    fileProvider     FileProvider

    // Extracted components
    processor      *RequestProcessor
    policyExecutor *PolicyExecutor
    authClient     *AuthClient
    syncClient     *SyncClient

    // Lifecycle
    middleware    []Middleware
    startupHooks  []LifecycleHook
    shutdownHooks []LifecycleHook
    shutdownCh    chan struct{}
    shutdownWg    sync.WaitGroup

    mu sync.RWMutex  // For middleware/hooks only
}
```

**Updated New()**:
```go
func New(opts ...Option) *SyftAPI {
    config := DefaultConfig()
    if err := config.LoadFromEnv(); err != nil {
        slog.Warn("failed to load config from environment", "error", err)
    }

    for _, opt := range opts {
        opt(config)
    }

    logger := setupLogger(config.LogLevel)
    slogLogger := NewSlogLogger(logger)

    registry := NewEndpointRegistry()
    authClient := NewAuthClient(config.SyftHubURL, config.APIKey, slogLogger)
    syncClient := NewSyncClient(config.SyftHubURL, config.APIKey, slogLogger)
    policyExecutor := NewPolicyExecutor(logger)

    processor := NewRequestProcessor(&ProcessorConfig{
        Registry:       registry,
        PolicyExecutor: policyExecutor,
        AuthClient:     authClient,
        Logger:         logger,
    })

    return &SyftAPI{
        config:         config,
        logger:         logger,
        registry:       registry,
        authClient:     authClient,
        syncClient:     syncClient,
        policyExecutor: policyExecutor,
        processor:      processor,
        shutdownCh:     make(chan struct{}),
    }
}
```

**Delegate methods**:
```go
func (api *SyftAPI) AddPolicy(policy Policy) {
    api.policyExecutor.AddGlobalPolicy(policy)
}

func (api *SyftAPI) handleRequest(ctx context.Context, req *TunnelRequest) (*TunnelResponse, error) {
    return api.processor.Process(ctx, req)
}
```

---

### Step 9: Remove Duplicate Policy Interface

**File Changed**: `policy/policy.go`

**Changes**:
```go
package policy

import (
    "context"
    "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// Policy is an alias for the canonical Policy interface in syfthubapi.
type Policy = syfthubapi.Policy

// Compile-time interface checks
var (
    _ syfthubapi.Policy = (*BasePolicy)(nil)
    _ syfthubapi.Policy = (*CompositePolicy)(nil)
    _ syfthubapi.Policy = (*NotPolicy)(nil)
)

// ... rest of file unchanged
```

---

### Step 10: Delete WorkerPoolExecutor (YAGNI)

**File Changed**: `filemode/executor.go`

**Delete lines 228-330** (WorkerPoolExecutor and related types).

**Update CreateExecutor**:
```go
func CreateExecutor(cfg *ExecutorConfig, runtime *RuntimeConfig) (syfthubapi.Executor, error) {
    venvPython := filepath.Join(cfg.WorkDir, ".venv", "bin", "python")
    if _, err := os.Stat(venvPython); err == nil {
        cfg.PythonPath = venvPython
    }

    if runtime.Mode != "" && runtime.Mode != "subprocess" {
        cfg.Logger.Warn("unsupported runtime mode, using subprocess", "mode", runtime.Mode)
    }

    return NewSubprocessExecutor(cfg)
}
```

---

## Dependency Graph

```
Step 1 (auth fix)      ─┐
Step 2 (race fix)      ─┼─→ Step 6 (PolicyExecutor) ─→ Step 7 (RequestProcessor) ─┬→ Step 9 (invokers)
Step 3 (panic fix)     ─┘                                                          └→ Step 10 (inject sync)
Step 4 (env error)     ─→ independent
Step 5 (tests)         ─→ continuous
Step 8 (Policy iface)  ─→ independent
```

**Critical Path**: Steps 1, 2 → Step 6 → Step 7 → Steps 9, 10

---

## Testing Strategy

After each step:
1. Run `go build ./...` - Compile check
2. Run `go test ./...` - Unit tests
3. Run `go test -race ./...` - Race detection
4. Manual test with example app

---

## Rollback Plan

Each step is a separate commit. If issues arise:
1. `git revert <commit>` for the problematic step
2. Fix the issue
3. Re-apply

---

## Success Criteria

- [ ] All tests pass
- [ ] No race conditions detected
- [ ] Token verification uses real AuthClient
- [ ] SyftAPI struct has ≤10 fields
- [ ] No panics in normal code paths
- [ ] All P0/P1/P2 issues resolved
