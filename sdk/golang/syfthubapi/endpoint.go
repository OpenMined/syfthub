package syfthubapi

import (
	"context"
	"log/slog"
	"regexp"
	"sync"
)

// Slug validation regex: 1-64 chars, lowercase alphanumeric with hyphens/underscores.
var slugRegex = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,63}$`)

// DataSourceHandler is the function signature for data source endpoints.
type DataSourceHandler func(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error)

// ModelHandler is the function signature for model endpoints.
type ModelHandler func(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error)

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

	// invoker encapsulates all type-specific and mode-specific execution logic.
	invoker EndpointInvoker

	// isFileBased indicates if this is from file mode (for registry lifecycle management).
	isFileBased bool
}

// Executor interface for executing endpoint handlers.
type Executor interface {
	Execute(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error)
	Close() error
}

// Info returns the endpoint information for sync.
func (e *Endpoint) Info() EndpointInfo {
	return EndpointInfo{
		Slug:        e.Slug,
		Name:        e.Name,
		Description: e.Description,
		Type:        e.Type,
		Enabled:     e.Enabled,
		Version:     e.Version,
		Readme:      e.Readme,
	}
}

// SetInvoker sets the endpoint's invoker directly.
func (e *Endpoint) SetInvoker(inv EndpointInvoker) {
	e.invoker = inv
}

// Invoker returns the endpoint's invoker.
func (e *Endpoint) Invoker() EndpointInvoker {
	return e.invoker
}

// EndpointHandlerConfig holds the configuration for wiring an endpoint's handler.
// This replaces the separate SetExecutor/SetAgentHandler/SetPolicyExecutor methods
// with a single unified wiring point.
type EndpointHandlerConfig struct {
	Executor       Executor     // for model/data_source (subprocess/container)
	AgentHandler   AgentHandler // for agents
	PolicyExecutor Executor     // for agent policy checks
	Logger         *slog.Logger // for agent invoker logging
}

// SetHandler wires the endpoint's invoker from the given config.
// The endpoint type determines which fields are used.
func (e *Endpoint) SetHandler(cfg EndpointHandlerConfig) {
	e.isFileBased = true
	switch e.Type {
	case EndpointTypeAgent:
		e.invoker = &AgentOneShotInvoker{
			codec:          ModelCodec{},
			handler:        cfg.AgentHandler,
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
		return nil, &ExecutionError{Endpoint: e.Slug, Message: typeErrMsg}
	}
	if e.invoker == nil {
		return nil, &ExecutionError{Endpoint: e.Slug, Message: "no handler registered"}
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
		return nil, &ExecutionError{Endpoint: e.Slug, Message: "unexpected result type from invoker"}
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
		return "", &ExecutionError{Endpoint: e.Slug, Message: "unexpected result type from invoker"}
	}
	return s, nil
}

// GetAgentHandler returns the agent handler for this endpoint.
// Returns an error if the endpoint is not an agent type or has no handler.
func (e *Endpoint) GetAgentHandler() (AgentHandler, error) {
	if e.Type != EndpointTypeAgent {
		return nil, &ExecutionError{
			Endpoint: e.Slug,
			Message:  "endpoint is not an agent",
		}
	}
	if inv, ok := e.invoker.(*AgentOneShotInvoker); ok && inv.handler != nil {
		return inv.handler, nil
	}
	return nil, &ExecutionError{
		Endpoint: e.Slug,
		Message:  "no agent handler registered",
	}
}

// CheckPolicies runs policy evaluation without executing the endpoint handler.
// Returns nil PolicyResultOutput if no policy executor is configured.
func (e *Endpoint) CheckPolicies(ctx context.Context, reqCtx *RequestContext) (*PolicyResultOutput, error) {
	if inv, ok := e.invoker.(*AgentOneShotInvoker); ok && inv.policyExecutor != nil {
		return inv.checkPolicies(ctx, reqCtx)
	}
	return nil, nil
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
		return &EndpointRegistrationError{
			Slug:    endpoint.Slug,
			Field:   "slug",
			Message: "endpoint already registered",
		}
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

// baseEndpointBuilder holds the fields and logic shared by all endpoint builders.
type baseEndpointBuilder struct {
	api      *SyftAPI
	endpoint *Endpoint
	err      error
}

// setName validates and sets the endpoint display name.
func (b *baseEndpointBuilder) setName(name string) {
	if b.err != nil {
		return
	}
	if name == "" {
		b.err = &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "name",
			Message: "name is required",
		}
		return
	}
	b.endpoint.Name = name
}

// setDescription validates and sets the endpoint description.
func (b *baseEndpointBuilder) setDescription(description string) {
	if b.err != nil {
		return
	}
	if description == "" {
		b.err = &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "description",
			Message: "description is required",
		}
		return
	}
	b.endpoint.Description = description
}

// setVersion sets the endpoint version.
func (b *baseEndpointBuilder) setVersion(version string) {
	if b.err != nil {
		return
	}
	b.endpoint.Version = version
}

// setEnabled sets whether the endpoint is enabled.
func (b *baseEndpointBuilder) setEnabled(enabled bool) {
	if b.err != nil {
		return
	}
	b.endpoint.Enabled = enabled
}

// validateForRegistration checks common preconditions before registering an endpoint.
func (b *baseEndpointBuilder) validateForRegistration() error {
	if b.err != nil {
		return b.err
	}
	if b.endpoint.Name == "" {
		return &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "name",
			Message: "name is required",
		}
	}
	if b.endpoint.Description == "" {
		return &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "description",
			Message: "description is required",
		}
	}
	return nil
}

// DataSourceBuilder builds data source endpoints using the builder pattern.
type DataSourceBuilder struct {
	baseEndpointBuilder
}

// Name sets the endpoint display name.
func (b *DataSourceBuilder) Name(name string) *DataSourceBuilder {
	b.setName(name)
	return b
}

// Description sets the endpoint description.
func (b *DataSourceBuilder) Description(description string) *DataSourceBuilder {
	b.setDescription(description)
	return b
}

// Version sets the endpoint version.
func (b *DataSourceBuilder) Version(version string) *DataSourceBuilder {
	b.setVersion(version)
	return b
}

// Enabled sets whether the endpoint is enabled.
func (b *DataSourceBuilder) Enabled(enabled bool) *DataSourceBuilder {
	b.setEnabled(enabled)
	return b
}

// Handler sets the data source handler and registers the endpoint.
func (b *DataSourceBuilder) Handler(handler DataSourceHandler) error {
	if err := b.validateForRegistration(); err != nil {
		return err
	}
	if handler == nil {
		return &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "handler",
			Message: "handler is required",
		}
	}

	b.endpoint.invoker = &UnifiedInvoker{
		codec:  DataSourceCodec{},
		slug:   b.endpoint.Slug,
		epType: EndpointTypeDataSource,
		handler: func(ctx context.Context, input any, reqCtx *RequestContext) (any, error) {
			return handler(ctx, input.(string), reqCtx)
		},
	}
	return b.api.registerEndpoint(b.endpoint)
}

// ModelBuilder builds model endpoints using the builder pattern.
type ModelBuilder struct {
	baseEndpointBuilder
}

// Name sets the endpoint display name.
func (b *ModelBuilder) Name(name string) *ModelBuilder {
	b.setName(name)
	return b
}

// Description sets the endpoint description.
func (b *ModelBuilder) Description(description string) *ModelBuilder {
	b.setDescription(description)
	return b
}

// Version sets the endpoint version.
func (b *ModelBuilder) Version(version string) *ModelBuilder {
	b.setVersion(version)
	return b
}

// Enabled sets whether the endpoint is enabled.
func (b *ModelBuilder) Enabled(enabled bool) *ModelBuilder {
	b.setEnabled(enabled)
	return b
}

// Handler sets the model handler and registers the endpoint.
func (b *ModelBuilder) Handler(handler ModelHandler) error {
	if err := b.validateForRegistration(); err != nil {
		return err
	}
	if handler == nil {
		return &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "handler",
			Message: "handler is required",
		}
	}

	b.endpoint.invoker = &UnifiedInvoker{
		codec:  ModelCodec{},
		slug:   b.endpoint.Slug,
		epType: EndpointTypeModel,
		handler: func(ctx context.Context, input any, reqCtx *RequestContext) (any, error) {
			return handler(ctx, input.([]Message), reqCtx)
		},
	}
	return b.api.registerEndpoint(b.endpoint)
}

// validateSlug validates an endpoint slug.
func validateSlug(slug string) error {
	if slug == "" {
		return &EndpointRegistrationError{
			Slug:    slug,
			Field:   "slug",
			Message: "slug is required",
		}
	}
	if !slugRegex.MatchString(slug) {
		return &EndpointRegistrationError{
			Slug:    slug,
			Field:   "slug",
			Message: "slug must be 1-64 lowercase alphanumeric characters with hyphens or underscores",
		}
	}
	return nil
}

// Ensure invokers implement the interface at compile time.
var (
	_ EndpointInvoker = (*UnifiedInvoker)(nil)
	_ EndpointInvoker = (*AgentOneShotInvoker)(nil)
)
