package syfthubapi

import (
	"context"
	"fmt"
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

	// dataSourceHandler is the handler for data source endpoints.
	dataSourceHandler DataSourceHandler

	// modelHandler is the handler for model endpoints.
	modelHandler ModelHandler

	// agentHandler is the handler for agent endpoints.
	agentHandler AgentHandler

	// isFileBasedEndpoint indicates if this is from file mode.
	isFileBased bool

	// executor is the subprocess executor (for file-based endpoints).
	executor Executor

	// policyExecutor runs policy checks without executing the handler.
	// Used by agent endpoints where the handler lifecycle differs from model/data_source.
	policyExecutor Executor
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

// SetExecutor sets the executor for file-based endpoints.
// This also marks the endpoint as file-based.
func (e *Endpoint) SetExecutor(exec Executor) {
	e.executor = exec
	e.isFileBased = true
}

// SetAgentHandler sets the agent handler for file-based agent endpoints.
// This also marks the endpoint as file-based.
func (e *Endpoint) SetAgentHandler(handler AgentHandler) {
	e.agentHandler = handler
	e.isFileBased = true
}

// SetPolicyExecutor sets a dedicated policy-check executor.
// Used by agent endpoints that need policy enforcement but don't use the
// standard SubprocessExecutor for their handler lifecycle.
func (e *Endpoint) SetPolicyExecutor(exec Executor) {
	e.policyExecutor = exec
}

// CheckPolicies runs policy evaluation without executing the endpoint handler.
// Returns nil PolicyResultOutput if no policy executor is configured (no policies).
func (e *Endpoint) CheckPolicies(ctx context.Context, reqCtx *RequestContext) (*PolicyResultOutput, error) {
	if e.policyExecutor == nil {
		return nil, nil
	}

	input := &ExecutorInput{
		Type:     string(e.Type),
		Messages: []Message{{Role: "user", Content: "policy_check"}},
	}
	if reqCtx != nil {
		userID := ""
		if reqCtx.User != nil {
			userID = reqCtx.User.Username
		}
		input.Context = &ExecutionContext{
			UserID:       userID,
			EndpointSlug: e.Slug,
			EndpointType: string(e.Type),
			Metadata:     reqCtx.Metadata,
		}
		input.TransactionToken = reqCtx.TransactionToken
	}

	output, err := e.policyExecutor.Execute(ctx, input)
	if err != nil {
		return nil, fmt.Errorf("policy check failed: %w", err)
	}

	return output.PolicyResult, nil
}

// IsFileBased returns whether this endpoint is file-based.
func (e *Endpoint) IsFileBased() bool {
	return e.isFileBased
}

// InvokeDataSource invokes a data source handler.
func (e *Endpoint) InvokeDataSource(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
	if e.Type != EndpointTypeDataSource {
		return nil, &ExecutionError{
			Endpoint: e.Slug,
			Message:  "endpoint is not a data source",
		}
	}

	if e.isFileBased && e.executor != nil {
		return e.executeDataSourceViaSubprocess(ctx, query, reqCtx)
	}

	if e.dataSourceHandler == nil {
		return nil, &ExecutionError{
			Endpoint: e.Slug,
			Message:  "no handler registered",
		}
	}

	return e.dataSourceHandler(ctx, query, reqCtx)
}

// InvokeModel invokes a model handler.
func (e *Endpoint) InvokeModel(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
	if e.Type != EndpointTypeModel {
		return "", &ExecutionError{
			Endpoint: e.Slug,
			Message:  "endpoint is not a model",
		}
	}

	if e.isFileBased && e.executor != nil {
		return e.executeModelViaSubprocess(ctx, messages, reqCtx)
	}

	if e.modelHandler == nil {
		return "", &ExecutionError{
			Endpoint: e.Slug,
			Message:  "no handler registered",
		}
	}

	return e.modelHandler(ctx, messages, reqCtx)
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
	if e.agentHandler == nil {
		return nil, &ExecutionError{
			Endpoint: e.Slug,
			Message:  "no agent handler registered",
		}
	}
	return e.agentHandler, nil
}

// executeDataSourceViaSubprocess executes via subprocess.
func (e *Endpoint) executeDataSourceViaSubprocess(ctx context.Context, query string, reqCtx *RequestContext) ([]Document, error) {
	input := &ExecutorInput{
		Type:  "data_source",
		Query: query,
	}
	if reqCtx != nil {
		userID := ""
		if reqCtx.User != nil {
			userID = reqCtx.User.Username
		}
		input.Context = &ExecutionContext{
			UserID:       userID,
			EndpointSlug: e.Slug,
			EndpointType: string(e.Type),
			Metadata:     reqCtx.Metadata,
		}
		// Pass transaction token for billing policies
		input.TransactionToken = reqCtx.TransactionToken
	}

	output, err := e.executor.Execute(ctx, input)
	if err != nil {
		return nil, &ExecutionError{
			Endpoint: e.Slug,
			Message:  "subprocess execution failed",
			Cause:    err,
		}
	}

	// Capture policy result in request context for logging
	if reqCtx != nil && output.PolicyResult != nil {
		reqCtx.PolicyResult = output.PolicyResult
	}

	if !output.Success {
		return nil, &ExecutionError{
			Endpoint:  e.Slug,
			Message:   output.Error,
			ErrorType: output.ErrorType,
		}
	}

	// Parse result as []Document
	var docs []Document
	if err := unmarshalJSON(output.Result, &docs); err != nil {
		return nil, &ExecutionError{
			Endpoint: e.Slug,
			Message:  "failed to parse handler result",
			Cause:    err,
		}
	}

	return docs, nil
}

// executeModelViaSubprocess executes via subprocess.
func (e *Endpoint) executeModelViaSubprocess(ctx context.Context, messages []Message, reqCtx *RequestContext) (string, error) {
	input := &ExecutorInput{
		Type:     "model",
		Messages: messages,
	}
	if reqCtx != nil {
		userID := ""
		if reqCtx.User != nil {
			userID = reqCtx.User.Username
		}
		input.Context = &ExecutionContext{
			UserID:       userID,
			EndpointSlug: e.Slug,
			EndpointType: string(e.Type),
			Metadata:     reqCtx.Metadata,
		}
		// Pass transaction token for billing policies
		input.TransactionToken = reqCtx.TransactionToken
	}

	output, err := e.executor.Execute(ctx, input)
	if err != nil {
		return "", &ExecutionError{
			Endpoint: e.Slug,
			Message:  "subprocess execution failed",
			Cause:    err,
		}
	}

	// Capture policy result in request context for logging
	if reqCtx != nil && output.PolicyResult != nil {
		reqCtx.PolicyResult = output.PolicyResult
	}

	if !output.Success {
		return "", &ExecutionError{
			Endpoint:  e.Slug,
			Message:   output.Error,
			ErrorType: output.ErrorType,
		}
	}

	// Parse result as string
	var result string
	if err := unmarshalJSON(output.Result, &result); err != nil {
		return "", &ExecutionError{
			Endpoint: e.Slug,
			Message:  "failed to parse handler result",
			Cause:    err,
		}
	}

	return result, nil
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
func (r *EndpointRegistry) ReplaceFileBased(endpoints []*Endpoint) {
	r.mu.Lock()
	defer r.mu.Unlock()

	// Remove existing file-based endpoints, closing their executors and handlers
	for slug, ep := range r.endpoints {
		if ep.isFileBased {
			if ep.executor != nil {
				ep.executor.Close()
			}
			if ep.policyExecutor != nil {
				ep.policyExecutor.Close()
			}
			delete(r.endpoints, slug)
		}
	}

	// Add new file-based endpoints
	for _, ep := range endpoints {
		ep.isFileBased = true
		r.endpoints[ep.Slug] = ep
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
// Returns a non-nil error if the builder has a previous error, or if name/description are missing.
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

	b.endpoint.dataSourceHandler = handler
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

	b.endpoint.modelHandler = handler
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
