package syfthubapi

import (
	"context"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
	"sync"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// Slug validation regex: 1-64 chars, lowercase alphanumeric with hyphens/underscores.
var slugRegex = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,63}$`)

// Endpoint represents a registered endpoint.
type Endpoint struct {
	// Slug is the unique endpoint identifier.
	Slug string

	// Name is the display name.
	Name string

	// Description is a brief description.
	Description string

	// Type is the endpoint type.
	Type EndpointType

	// Enabled indicates if the endpoint is active.
	Enabled bool

	// Version is the endpoint version.
	Version string

	// Readme is the markdown documentation (body after frontmatter).
	Readme string

	// AcceptsAttachments opts an agent endpoint into receiving inbound file
	// attachments from the caller. Default false. See
	// docs/architecture/attachments.md.
	AcceptsAttachments bool

	// invoker encapsulates all type-specific and mode-specific execution logic.
	invoker EndpointInvoker

	// isFileBased indicates if this is from file mode (for registry lifecycle management).
	isFileBased bool

	// policyConfigs holds the loaded policy configurations for this endpoint
	// (typically read from policies.yaml by the file-mode loader). They are
	// surfaced verbatim (after secret sanitization) via Info().Policies so
	// that hub clients and gateways can discover requirements such as a
	// transaction policy without invoking the endpoint.
	policyConfigs []nodeops.Policy
}

// Executor interface for executing endpoint handlers.
type Executor interface {
	Execute(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error)
	Close() error
}

// Info returns the endpoint information for sync.
//
// The Policies slice contains a sanitized projection of e.policyConfigs:
// secret material is stripped via sanitizePolicyConfig before the data
// leaves the runtime. When no policies are loaded, Policies is left nil so
// that the JSON omitempty tag drops the field on the wire.
func (e *Endpoint) Info() EndpointInfo {
	info := EndpointInfo{
		Slug:        e.Slug,
		Name:        e.Name,
		Description: e.Description,
		Type:        e.Type,
		Enabled:     e.Enabled,
		Version:     e.Version,
		Readme:      e.Readme,
	}
	if len(e.policyConfigs) > 0 {
		info.Policies = make([]map[string]any, 0, len(e.policyConfigs))
		for _, p := range e.policyConfigs {
			info.Policies = append(info.Policies, map[string]any{
				"name":   p.Name,
				"type":   p.Type,
				"config": sanitizePolicyConfig(p.Type, p.Config),
			})
		}
	}
	return info
}

// SetPolicyConfigs records the policy configurations associated with this
// endpoint. The file-mode loader calls this after parsing policies.yaml so
// that Info() can surface the policy metadata to hub clients.
func (e *Endpoint) SetPolicyConfigs(cfgs []nodeops.Policy) {
	e.policyConfigs = cfgs
}

// sanitizePolicyConfig returns a copy of cfg with secret material removed so
// that the result is safe to ship over the wire via Info().
//
// Keys are passed through verbatim except those that are clearly private:
//   - keys beginning with "_" (private-by-convention)
//   - keys whose name (lower-cased) contains "secret", "password",
//     "private_key", "signing_key", "auth_token", or "api_key".
//
// The check intentionally targets the substrings above rather than any
// occurrence of "key" so that benign fields like "chain_id", "recipient" or
// generic identifier fields are preserved.
//
// When adding a new policy type that contains secret material, prefer storing
// only a reference (e.g. a key id) in the config rather than the secret
// itself, so this generic filter remains sufficient.
func sanitizePolicyConfig(_ string, cfg map[string]any) map[string]any {
	if cfg == nil {
		return map[string]any{}
	}

	out := make(map[string]any, len(cfg))
	for k, v := range cfg {
		if strings.HasPrefix(k, "_") {
			continue
		}
		if isSensitivePolicyKey(k) {
			continue
		}
		out[k] = v
	}
	return out
}

// sensitivePolicyKeyNeedles are case-insensitive substrings that mark a
// policy-config key as holding secret material.
var sensitivePolicyKeyNeedles = []string{
	"secret",
	"password",
	"private_key",
	"signing_key",
	"auth_token",
	"api_key",
}

// isSensitivePolicyKey reports whether a config key name looks like it holds
// secret material. The match is case-insensitive substring based.
func isSensitivePolicyKey(name string) bool {
	lower := strings.ToLower(name)
	for _, needle := range sensitivePolicyKeyNeedles {
		if strings.Contains(lower, needle) {
			return true
		}
	}
	return false
}

// EndpointHandlerConfig holds the configuration for wiring an endpoint's handler.
// This replaces the separate SetExecutor/SetAgentHandler/SetPolicyExecutor methods
// with a single unified wiring point.
type EndpointHandlerConfig struct {
	Executor       Executor     // for model/data_source (subprocess/container)
	AgentHandler   AgentHandler // for agents
	PolicyExecutor Executor     // for agent policy checks
	Logger         *slog.Logger // for agent invoker logging

	// RoutingRecorder, when non-nil and the endpoint is an agent endpoint
	// with policies, is wired into the AgentExecutor so each pending policy
	// notice that carries a manual_review handle is captured for later
	// resolution delivery. nil-safe for non-agent endpoints and for agents
	// without policies — neither path needs it.
	RoutingRecorder manualreview.RoutingRecorder
}

// SetHandler wires the endpoint's invoker from the given config.
// The endpoint type determines which fields are used.
func (e *Endpoint) SetHandler(cfg EndpointHandlerConfig) {
	e.isFileBased = true
	switch e.Type {
	case EndpointTypeAgent:
		// Weave per-turn policy enforcement into the agent handler. Both the
		// one-shot (AgentOneShotInvoker) and persistent (AgentSessionManager)
		// paths run this handler, so each inherits pre/post policy without
		// path-specific code.
		handler := cfg.AgentHandler
		if cfg.PolicyExecutor != nil {
			handler = NewAgentExecutorWithConfig(handler, cfg.PolicyExecutor, e.Slug, AgentExecutorConfig{
				Logger:          cfg.Logger,
				RoutingRecorder: cfg.RoutingRecorder,
			}).Handler()
		}
		e.invoker = &AgentOneShotInvoker{
			codec:          ModelCodec{},
			handler:        handler,
			policyExecutor: cfg.PolicyExecutor,
			slug:           e.Slug,
			logger:         cfg.Logger,
		}
	case EndpointTypeDataSource:
		e.invoker = &UnifiedInvoker{codec: DataSourceCodec{}, executor: cfg.Executor, slug: e.Slug, epType: e.Type}
	case EndpointTypeModel, EndpointTypeModelDataSource:
		e.invoker = &UnifiedInvoker{codec: ModelCodec{}, executor: cfg.Executor, slug: e.Slug, epType: e.Type}
	}
}

// IsFileBased returns whether this endpoint is file-based.
func (e *Endpoint) IsFileBased() bool {
	return e.isFileBased
}

// invokeGuarded checks the endpoint type and invokes the registered invoker.
// typeErrMsg is the message used when the endpoint type doesn't match expectedType.
func (e *Endpoint) invokeGuarded(ctx context.Context, expectedType EndpointType, typeErrMsg string, input any, reqCtx *RequestContext) (any, error) {
	if e.Type != expectedType {
		return nil, fmt.Errorf("endpoint %q: %s", e.Slug, typeErrMsg)
	}
	if e.invoker == nil {
		return nil, errNoHandler(e.Slug)
	}
	return e.invoker.Invoke(ctx, input, reqCtx)
}

// InvokeDataSource invokes a data source handler.
func (e *Endpoint) InvokeDataSource(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
	result, err := e.invokeGuarded(ctx, EndpointTypeDataSource, "endpoint is not a data source", query, reqCtx)
	if err != nil {
		return nil, err
	}
	docs, ok := result.([]Document)
	if !ok {
		return nil, fmt.Errorf("endpoint %q: unexpected result type from invoker", e.Slug)
	}
	return docs, nil
}

// InvokeModel invokes a model handler.
func (e *Endpoint) InvokeModel(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
	result, err := e.invokeGuarded(ctx, EndpointTypeModel, "endpoint is not a model", messages, reqCtx)
	if err != nil {
		return "", err
	}
	s, ok := result.(string)
	if !ok {
		return "", fmt.Errorf("endpoint %q: unexpected result type from invoker", e.Slug)
	}
	return s, nil
}

// GetAgentHandler returns the agent handler for this endpoint.
// Returns an error if the endpoint is not an agent type or has no handler.
func (e *Endpoint) GetAgentHandler() (AgentHandler, error) {
	if e.Type != EndpointTypeAgent {
		return nil, fmt.Errorf("endpoint %q: endpoint is not an agent", e.Slug)
	}
	if inv, ok := e.invoker.(*AgentOneShotInvoker); ok && inv.handler != nil {
		return inv.handler, nil
	}
	return nil, fmt.Errorf("endpoint %q: no agent handler registered", e.Slug)
}

// EndpointRegistry manages registered endpoints.
type EndpointRegistry struct {
	endpoints map[string]*Endpoint
	mu        sync.RWMutex
}

// NewEndpointRegistry creates a new endpoint registry.
func NewEndpointRegistry() *EndpointRegistry {
	return &EndpointRegistry{
		endpoints: make(map[string]*Endpoint),
	}
}

// Register adds an endpoint to the registry.
func (r *EndpointRegistry) Register(endpoint *Endpoint) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, exists := r.endpoints[endpoint.Slug]; exists {
		return fmt.Errorf("endpoint %q: already registered", endpoint.Slug)
	}

	r.endpoints[endpoint.Slug] = endpoint
	return nil
}

// Get retrieves an endpoint by slug.
func (r *EndpointRegistry) Get(slug string) (*Endpoint, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	ep, ok := r.endpoints[slug]
	return ep, ok
}

// List returns all registered endpoints.
func (r *EndpointRegistry) List() []*Endpoint {
	r.mu.RLock()
	defer r.mu.RUnlock()

	endpoints := make([]*Endpoint, 0, len(r.endpoints))
	for _, ep := range r.endpoints {
		endpoints = append(endpoints, ep)
	}
	return endpoints
}

// Remove removes an endpoint by slug.
func (r *EndpointRegistry) Remove(slug string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, exists := r.endpoints[slug]; exists {
		delete(r.endpoints, slug)
		return true
	}
	return false
}

// Clear removes all endpoints.
func (r *EndpointRegistry) Clear() {
	r.mu.Lock()
	defer r.mu.Unlock()

	r.endpoints = make(map[string]*Endpoint)
}

// ReplaceFileBased replaces all file-based endpoints atomically.
// Stale invokers (those not reused by the incoming list) are closed after the
// lock is released to avoid blocking concurrent reads while subprocess cleanup runs.
func (r *EndpointRegistry) ReplaceFileBased(endpoints []*Endpoint) {
	// Collect invoker instances from the incoming list so we skip closing
	// invokers that are being reused (e.g. during selective reload where
	// only some endpoints are recreated and the rest keep their invokers).
	reused := make(map[EndpointInvoker]struct{})
	for _, ep := range endpoints {
		if ep.invoker != nil {
			reused[ep.invoker] = struct{}{}
		}
	}

	var stale []EndpointInvoker

	r.mu.Lock()
	for slug, ep := range r.endpoints {
		if ep.isFileBased {
			if ep.invoker != nil {
				if _, ok := reused[ep.invoker]; !ok {
					stale = append(stale, ep.invoker)
				}
			}
			delete(r.endpoints, slug)
		}
	}
	for _, ep := range endpoints {
		ep.isFileBased = true
		r.endpoints[ep.Slug] = ep
	}
	r.mu.Unlock()

	// Close stale invokers outside the lock so blocking subprocess shutdown
	// does not delay concurrent registry reads.
	for _, inv := range stale {
		inv.Close()
	}
}

// SetEnabled updates the enabled status of an endpoint without recreating it.
// Returns true if the endpoint was found and updated, false otherwise.
// This is an O(1) operation that avoids expensive executor recreation.
func (r *EndpointRegistry) SetEnabled(slug string, enabled bool) bool {
	r.mu.Lock()
	defer r.mu.Unlock()

	if ep, ok := r.endpoints[slug]; ok {
		ep.Enabled = enabled
		return true
	}
	return false
}

// validateSlug validates an endpoint slug.
func validateSlug(slug string) error {
	if slug == "" {
		return fmt.Errorf("endpoint slug is required")
	}
	if !slugRegex.MatchString(slug) {
		return fmt.Errorf("endpoint slug %q must be 1-64 lowercase alphanumeric characters with hyphens or underscores", slug)
	}
	return nil
}

// Ensure invokers implement the interface at compile time.
var (
	_ EndpointInvoker = (*UnifiedInvoker)(nil)
	_ EndpointInvoker = (*AgentOneShotInvoker)(nil)
)
