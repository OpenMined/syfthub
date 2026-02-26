package syfthubapi

import (
	"context"
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

	// Policies holds the policy configurations for this endpoint.
	Policies []PolicyConfig

	// dataSourceHandler is the handler for data source endpoints.
	dataSourceHandler DataSourceHandler

	// modelHandler is the handler for model endpoints.
	modelHandler ModelHandler

	// isFileBasedEndpoint indicates if this is from file mode.
	isFileBased bool

	// executor is the subprocess executor (for file-based endpoints).
	executor Executor
}

// Executor interface for executing endpoint handlers.
type Executor interface {
	Execute(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error)
	Close() error
}

// Info returns the endpoint information for sync.
func (e *Endpoint) Info() EndpointInfo {
	var policies []map[string]any
	for _, p := range e.Policies {
		policies = append(policies, map[string]any{
			"type":   p.Type,
			"config": p.Config,
		})
	}
	return EndpointInfo{
		Slug:        e.Slug,
		Name:        e.Name,
		Description: e.Description,
		Type:        e.Type,
		Enabled:     e.Enabled,
		Version:     e.Version,
		Readme:      e.Readme,
		Policies:    policies,
	}
}

// SetExecutor sets the executor for file-based endpoints.
// This also marks the endpoint as file-based.
func (e *Endpoint) SetExecutor(exec Executor) {
	e.executor = exec
	e.isFileBased = true
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

	// Remove existing file-based endpoints
	for slug, ep := range r.endpoints {
		if ep.isFileBased {
			if ep.executor != nil {
				ep.executor.Close()
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

// DataSourceBuilder builds data source endpoints using the builder pattern.
type DataSourceBuilder struct {
	api      *SyftAPI
	endpoint *Endpoint
	err      error
}

// Name sets the endpoint display name.
func (b *DataSourceBuilder) Name(name string) *DataSourceBuilder {
	if b.err != nil {
		return b
	}
	if name == "" {
		b.err = &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "name",
			Message: "name is required",
		}
		return b
	}
	b.endpoint.Name = name
	return b
}

// Description sets the endpoint description.
func (b *DataSourceBuilder) Description(description string) *DataSourceBuilder {
	if b.err != nil {
		return b
	}
	if description == "" {
		b.err = &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "description",
			Message: "description is required",
		}
		return b
	}
	b.endpoint.Description = description
	return b
}

// Version sets the endpoint version.
func (b *DataSourceBuilder) Version(version string) *DataSourceBuilder {
	if b.err != nil {
		return b
	}
	b.endpoint.Version = version
	return b
}

// Enabled sets whether the endpoint is enabled.
func (b *DataSourceBuilder) Enabled(enabled bool) *DataSourceBuilder {
	if b.err != nil {
		return b
	}
	b.endpoint.Enabled = enabled
	return b
}

// Handler sets the data source handler and registers the endpoint.
func (b *DataSourceBuilder) Handler(handler DataSourceHandler) error {
	if b.err != nil {
		return b.err
	}
	if handler == nil {
		return &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "handler",
			Message: "handler is required",
		}
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

	b.endpoint.dataSourceHandler = handler
	return b.api.registerEndpoint(b.endpoint)
}

// ModelBuilder builds model endpoints using the builder pattern.
type ModelBuilder struct {
	api      *SyftAPI
	endpoint *Endpoint
	err      error
}

// Name sets the endpoint display name.
func (b *ModelBuilder) Name(name string) *ModelBuilder {
	if b.err != nil {
		return b
	}
	if name == "" {
		b.err = &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "name",
			Message: "name is required",
		}
		return b
	}
	b.endpoint.Name = name
	return b
}

// Description sets the endpoint description.
func (b *ModelBuilder) Description(description string) *ModelBuilder {
	if b.err != nil {
		return b
	}
	if description == "" {
		b.err = &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "description",
			Message: "description is required",
		}
		return b
	}
	b.endpoint.Description = description
	return b
}

// Version sets the endpoint version.
func (b *ModelBuilder) Version(version string) *ModelBuilder {
	if b.err != nil {
		return b
	}
	b.endpoint.Version = version
	return b
}

// Enabled sets whether the endpoint is enabled.
func (b *ModelBuilder) Enabled(enabled bool) *ModelBuilder {
	if b.err != nil {
		return b
	}
	b.endpoint.Enabled = enabled
	return b
}

// Handler sets the model handler and registers the endpoint.
func (b *ModelBuilder) Handler(handler ModelHandler) error {
	if b.err != nil {
		return b.err
	}
	if handler == nil {
		return &EndpointRegistrationError{
			Slug:    b.endpoint.Slug,
			Field:   "handler",
			Message: "handler is required",
		}
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
