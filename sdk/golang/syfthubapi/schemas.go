package syfthubapi

import (
	"encoding/json"
	"time"
)

// EndpointType represents the type of endpoint.
type EndpointType string

const (
	EndpointTypeDataSource EndpointType = "data_source"
	EndpointTypeModel      EndpointType = "model"
)

// String returns the string representation of the endpoint type.
func (t EndpointType) String() string {
	return string(t)
}

// Document represents a retrieved document from a data source.
type Document struct {
	// DocumentID is the unique identifier for the document.
	DocumentID string `json:"document_id"`

	// Content is the document content.
	Content string `json:"content"`

	// Metadata contains arbitrary document metadata.
	Metadata map[string]any `json:"metadata,omitempty"`

	// SimilarityScore is the relevance score (0-1).
	SimilarityScore float64 `json:"similarity_score,omitempty"`
}

// Message represents a chat message.
type Message struct {
	// Role is the message role: "system", "user", or "assistant".
	Role string `json:"role"`

	// Content is the message content.
	Content string `json:"content"`
}

// UserContext contains verified user identity information.
type UserContext struct {
	// Sub is the user's unique identifier (subject).
	Sub string `json:"sub"`

	// Email is the user's email address.
	Email string `json:"email"`

	// Username is the user's username.
	Username string `json:"username"`

	// Role is the user's role (e.g., "admin", "user", "guest").
	Role string `json:"role"`
}

// RequestContext carries request metadata through the processing chain.
type RequestContext struct {
	// User contains the verified user identity.
	User *UserContext

	// Input holds the original input (query string or []Message).
	Input any

	// Output holds the handler result (set after execution).
	Output any

	// Metadata contains arbitrary context data.
	Metadata map[string]any

	// StartTime is when the request started processing.
	StartTime time.Time

	// EndpointSlug is the slug of the endpoint being invoked.
	EndpointSlug string

	// EndpointType is the type of the endpoint.
	EndpointType EndpointType

	// PolicyResult contains the result of policy evaluation (set by executor).
	PolicyResult *PolicyResultOutput
}

// NewRequestContext creates a new RequestContext with initialized fields.
func NewRequestContext() *RequestContext {
	return &RequestContext{
		Metadata:  make(map[string]any),
		StartTime: time.Now(),
	}
}

// SetMetadata sets a metadata value.
func (rc *RequestContext) SetMetadata(key string, value any) {
	if rc.Metadata == nil {
		rc.Metadata = make(map[string]any)
	}
	rc.Metadata[key] = value
}

// GetMetadata retrieves a metadata value.
func (rc *RequestContext) GetMetadata(key string) (any, bool) {
	if rc.Metadata == nil {
		return nil, false
	}
	v, ok := rc.Metadata[key]
	return v, ok
}

// DataSourceQueryRequest is the request body for data source queries.
// The aggregator sends messages as a plain query string, not an array.
type DataSourceQueryRequest struct {
	// Messages is the search query string (sent directly by aggregator).
	Messages string `json:"messages"`

	// SimilarityThreshold is the minimum similarity score (0-1).
	SimilarityThreshold float64 `json:"similarity_threshold,omitempty"`

	// Limit is the maximum number of results.
	Limit int `json:"limit,omitempty"`

	// IncludeMetadata indicates whether to include document metadata.
	IncludeMetadata bool `json:"include_metadata,omitempty"`
}

// GetQuery returns the query string.
func (r *DataSourceQueryRequest) GetQuery() string {
	return r.Messages
}

// DataSourceReferences wraps the documents array in the response.
// The aggregator expects: {"references": {"documents": [...]}}
type DataSourceReferences struct {
	// Documents contains the retrieved documents.
	Documents []Document `json:"documents"`
}

// DataSourceQueryResponse is the response from a data source query.
type DataSourceQueryResponse struct {
	// References contains the retrieved documents wrapped in a documents array.
	References DataSourceReferences `json:"references"`
}

// ModelQueryRequest is the request body for model queries.
type ModelQueryRequest struct {
	// Messages is the conversation history.
	Messages []Message `json:"messages"`

	// MaxTokens is the maximum tokens to generate.
	MaxTokens int `json:"max_tokens,omitempty"`

	// Temperature controls randomness (0-2).
	Temperature float64 `json:"temperature,omitempty"`

	// StopSequences are strings that stop generation.
	StopSequences []string `json:"stop_sequences,omitempty"`
}

// ModelQueryResponse is the response from a model query.
type ModelQueryResponse struct {
	// Summary contains the model's response.
	Summary ModelSummary `json:"summary"`
}

// ModelSummaryMessage contains the message content in a model summary.
type ModelSummaryMessage struct {
	// Content is the assistant's message text.
	Content string `json:"content"`
}

// ModelSummary contains the assistant's response.
// Format matches aggregator expectations: summary.message.content
type ModelSummary struct {
	// Message contains the response content.
	Message ModelSummaryMessage `json:"message"`

	// Usage contains token usage statistics (optional).
	Usage *ModelUsage `json:"usage,omitempty"`
}

// ModelUsage contains token usage statistics.
type ModelUsage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

// TunnelEndpointInfo contains endpoint identification in tunnel messages.
type TunnelEndpointInfo struct {
	Slug string `json:"slug"`
	Type string `json:"type"`
}

// TunnelRequest is the request format for tunnel mode communication.
// Matches Python syfthub-api TunnelRequest schema.
type TunnelRequest struct {
	// Protocol is the protocol version identifier (e.g., "syfthub-tunnel/v1").
	Protocol string `json:"protocol"`

	// Type is the message type discriminator ("endpoint_request").
	Type string `json:"type"`

	// CorrelationID is a unique ID for matching request to response.
	CorrelationID string `json:"correlation_id"`

	// ReplyTo is the subject to send the response to.
	ReplyTo string `json:"reply_to"`

	// Endpoint contains target endpoint information.
	Endpoint TunnelEndpointInfo `json:"endpoint"`

	// Payload contains the actual request data.
	Payload json.RawMessage `json:"payload"`

	// TimeoutMs is the request timeout in milliseconds.
	TimeoutMs int `json:"timeout_ms"`

	// SatelliteToken is the JWT for user verification.
	SatelliteToken string `json:"satellite_token,omitempty"`

	// Timestamp is when the request was created (internal use).
	Timestamp time.Time `json:"-"`
}

// RequestID returns the correlation ID (for backward compatibility).
func (r *TunnelRequest) RequestID() string {
	return r.CorrelationID
}

// EndpointSlug returns the endpoint slug from the nested endpoint info.
func (r *TunnelRequest) EndpointSlug() string {
	return r.Endpoint.Slug
}

// EndpointType returns the endpoint type from the nested endpoint info.
func (r *TunnelRequest) EndpointType() EndpointType {
	return EndpointType(r.Endpoint.Type)
}

// TunnelResponse is the response format for tunnel mode communication.
// Matches Python syfthub-api TunnelResponse schema.
type TunnelResponse struct {
	// Protocol is the protocol version identifier.
	Protocol string `json:"protocol"`

	// Type is the message type discriminator ("endpoint_response").
	Type string `json:"type"`

	// CorrelationID matches the request's correlation_id.
	CorrelationID string `json:"correlation_id"`

	// Status is "success" or "error".
	Status string `json:"status"`

	// EndpointSlug is the endpoint that processed the request.
	EndpointSlug string `json:"endpoint_slug"`

	// Payload contains the response data (if success).
	Payload json.RawMessage `json:"payload,omitempty"`

	// Error contains error details (if error).
	Error *TunnelError `json:"error,omitempty"`

	// Timing contains timing information.
	Timing *TunnelTiming `json:"timing,omitempty"`
}

// TunnelError contains error information for tunnel responses.
type TunnelError struct {
	// Code is the error code.
	Code TunnelErrorCode `json:"code"`

	// Message is a human-readable error message.
	Message string `json:"message"`

	// Details contains additional error context.
	Details map[string]any `json:"details,omitempty"`
}

// TunnelTiming contains timing information for tunnel requests.
type TunnelTiming struct {
	// ReceivedAt is when the request was received.
	ReceivedAt time.Time `json:"received_at"`

	// ProcessedAt is when processing completed.
	ProcessedAt time.Time `json:"processed_at"`

	// DurationMs is the processing duration in milliseconds.
	DurationMs int64 `json:"duration_ms"`
}

// TunnelErrorCode represents error codes for tunnel communication.
type TunnelErrorCode string

const (
	TunnelErrorCodeAuthFailed        TunnelErrorCode = "AUTH_FAILED"
	TunnelErrorCodeEndpointNotFound  TunnelErrorCode = "ENDPOINT_NOT_FOUND"
	TunnelErrorCodePolicyDenied      TunnelErrorCode = "POLICY_DENIED"
	TunnelErrorCodeExecutionFailed   TunnelErrorCode = "EXECUTION_FAILED"
	TunnelErrorCodeTimeout           TunnelErrorCode = "TIMEOUT"
	TunnelErrorCodeInvalidRequest    TunnelErrorCode = "INVALID_REQUEST"
	TunnelErrorCodeInternalError     TunnelErrorCode = "INTERNAL_ERROR"
	TunnelErrorCodeEndpointDisabled  TunnelErrorCode = "ENDPOINT_DISABLED"
	TunnelErrorCodeRateLimitExceeded TunnelErrorCode = "RATE_LIMIT_EXCEEDED"
)

// EndpointInfo contains metadata about a registered endpoint.
type EndpointInfo struct {
	// Slug is the endpoint identifier.
	Slug string `json:"slug"`

	// Name is the display name.
	Name string `json:"name"`

	// Description is a brief description.
	Description string `json:"description"`

	// Type is the endpoint type.
	Type EndpointType `json:"type"`

	// Enabled indicates if the endpoint is active (internal use, not sent to server).
	Enabled bool `json:"-"`

	// Version is the endpoint version.
	Version string `json:"version,omitempty"`

	// Visibility is the endpoint visibility (public, private, internal).
	Visibility string `json:"visibility,omitempty"`

	// Readme is the markdown documentation.
	Readme string `json:"readme,omitempty"`

	// Connect contains connection information.
	Connect []ConnectionInfo `json:"connect,omitempty"`

	// Policies contains serialized policy configurations.
	Policies []map[string]any `json:"policies,omitempty"`
}

// ConnectionInfo represents how to connect to an endpoint.
type ConnectionInfo struct {
	Type   string         `json:"type"`
	Config map[string]any `json:"config"`
}

// SyncEndpointsRequest is the request to sync endpoints with SyftHub.
type SyncEndpointsRequest struct {
	// Endpoints is the list of endpoints to sync.
	Endpoints []EndpointInfo `json:"endpoints"`
}

// SyncEndpointsResponse is the response from syncing endpoints.
type SyncEndpointsResponse struct {
	// Synced is the number of endpoints synced.
	Synced int `json:"synced"`

	// Deleted is the number of endpoints deleted.
	Deleted int `json:"deleted"`
}

// VerifyTokenRequest is the request to verify a satellite token.
type VerifyTokenRequest struct {
	// Token is the satellite token to verify.
	Token string `json:"token"`
}

// VerifyTokenResponse is the response from token verification.
// Backend returns user fields at the top level, not nested under "user".
type VerifyTokenResponse struct {
	// Valid indicates if the token is valid.
	Valid bool `json:"valid"`

	// User fields (returned at top level by backend)
	Sub      string `json:"sub,omitempty"`
	Email    string `json:"email,omitempty"`
	Username string `json:"username,omitempty"`
	Role     string `json:"role,omitempty"`

	// Token metadata
	Aud string `json:"aud,omitempty"`
	Exp int64  `json:"exp,omitempty"`
	Iat int64  `json:"iat,omitempty"`

	// Error fields (for invalid tokens)
	Error   string `json:"error,omitempty"`
	Message string `json:"message,omitempty"`
}

// ToUserContext converts the response to a UserContext.
func (r *VerifyTokenResponse) ToUserContext() *UserContext {
	if !r.Valid || r.Sub == "" {
		return nil
	}
	return &UserContext{
		Sub:      r.Sub,
		Email:    r.Email,
		Username: r.Username,
		Role:     r.Role,
	}
}

// HeartbeatRequest is the request to send a heartbeat.
type HeartbeatRequest struct {
	// TTLSeconds is the requested TTL.
	TTLSeconds int `json:"ttl_seconds"`
}

// HeartbeatResponse is the response from a heartbeat request.
type HeartbeatResponse struct {
	// EffectiveTTLSeconds is the actual TTL applied.
	EffectiveTTLSeconds int `json:"effective_ttl_seconds"`

	// ExpiresAt is when the heartbeat expires.
	ExpiresAt time.Time `json:"expires_at"`
}

// ExecutorInput is the input format for subprocess execution.
// This matches the Python policy_manager.runner.schema.RunnerInput.
type ExecutorInput struct {
	// Type is the endpoint type ("model" or "data_source").
	Type string `json:"type"`

	// Query is the query string (for data sources).
	Query string `json:"query,omitempty"`

	// Messages is the message list (for models).
	Messages []Message `json:"messages,omitempty"`

	// Context contains execution context with user and endpoint info.
	Context *ExecutionContext `json:"context,omitempty"`

	// Policies contains policy configurations to enforce.
	Policies []PolicyConfig `json:"policies,omitempty"`

	// Store contains store configuration for stateful policies.
	Store *StoreConfig `json:"store,omitempty"`

	// HandlerPath is the absolute path to the handler (runner.py).
	HandlerPath string `json:"handler_path,omitempty"`

	// WorkDir is the working directory for the handler.
	WorkDir string `json:"work_dir,omitempty"`

	// MaxTokens is the max tokens for model responses (legacy, not used by runner).
	MaxTokens int `json:"max_tokens,omitempty"`

	// Temperature is the sampling temperature (legacy, not used by runner).
	Temperature float64 `json:"temperature,omitempty"`
}

// ExecutorOutput is the output format from subprocess execution.
// This matches the Python policy_manager.runner.schema.RunnerOutput.
type ExecutorOutput struct {
	// Success indicates if execution succeeded.
	Success bool `json:"success"`

	// Result contains the handler result.
	Result json.RawMessage `json:"result,omitempty"`

	// Error contains error message if failed.
	Error string `json:"error,omitempty"`

	// ErrorType contains the error type name.
	ErrorType string `json:"error_type,omitempty"`

	// PolicyResult contains detailed policy evaluation result.
	PolicyResult *PolicyResultOutput `json:"policy_result,omitempty"`
}

// NATSCredentials contains NATS connection credentials.
type NATSCredentials struct {
	// URL is the NATS server URL.
	URL string `json:"url"`

	// Token is the authentication token.
	Token string `json:"token"`

	// Subject is the subscription subject.
	Subject string `json:"subject"`
}
