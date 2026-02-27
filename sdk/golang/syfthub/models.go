package syfthub

import (
	"time"
)

// =============================================================================
// Enums
// =============================================================================

// Visibility represents endpoint visibility levels.
type Visibility string

const (
	VisibilityPublic   Visibility = "public"
	VisibilityPrivate  Visibility = "private"
	VisibilityInternal Visibility = "internal"
)

// EndpointType represents the type of endpoint.
type EndpointType string

const (
	EndpointTypeModel           EndpointType = "model"
	EndpointTypeDataSource      EndpointType = "data_source"
	EndpointTypeModelDataSource EndpointType = "model_data_source"
)

// UserRole represents user role levels.
type UserRole string

const (
	UserRoleAdmin UserRole = "admin"
	UserRoleUser  UserRole = "user"
	UserRoleGuest UserRole = "guest"
)

// OrganizationRole represents role within an organization.
type OrganizationRole string

const (
	OrganizationRoleOwner  OrganizationRole = "owner"
	OrganizationRoleAdmin  OrganizationRole = "admin"
	OrganizationRoleMember OrganizationRole = "member"
)

// TransactionStatus represents transaction status in the accounting service.
type TransactionStatus string

const (
	TransactionStatusPending   TransactionStatus = "pending"
	TransactionStatusCompleted TransactionStatus = "completed"
	TransactionStatusCancelled TransactionStatus = "cancelled"
)

// CreatorType represents who created or resolved a transaction.
type CreatorType string

const (
	CreatorTypeSystem    CreatorType = "system"
	CreatorTypeSender    CreatorType = "sender"
	CreatorTypeRecipient CreatorType = "recipient"
)

// SourceStatus represents the status of a data source query.
type SourceStatus string

const (
	SourceStatusSuccess SourceStatus = "success"
	SourceStatusError   SourceStatus = "error"
	SourceStatusTimeout SourceStatus = "timeout"
)

// APITokenScope represents API token permission scopes.
type APITokenScope string

const (
	APITokenScopeRead  APITokenScope = "read"
	APITokenScopeWrite APITokenScope = "write"
	APITokenScopeFull  APITokenScope = "full"
)

// =============================================================================
// User Models
// =============================================================================

// User represents a user returned from the API.
type User struct {
	ID            int        `json:"id"`
	Username      string     `json:"username"`
	Email         string     `json:"email"`
	FullName      string     `json:"full_name"`
	AvatarURL     *string    `json:"avatar_url,omitempty"`
	Role          UserRole   `json:"role"`
	IsActive      bool       `json:"is_active"`
	CreatedAt     time.Time  `json:"created_at"`
	UpdatedAt     *time.Time `json:"updated_at,omitempty"`
	Domain        *string    `json:"domain,omitempty"`
	AggregatorURL *string    `json:"aggregator_url,omitempty"`
}

// AuthTokens represents authentication tokens.
type AuthTokens struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
}

// SatelliteTokenResponse represents the response from satellite token endpoint.
type SatelliteTokenResponse struct {
	TargetToken string `json:"target_token"`
	ExpiresIn   int    `json:"expires_in"`
}

// PeerTokenResponse represents the response from peer token endpoint.
type PeerTokenResponse struct {
	PeerToken   string `json:"peer_token"`
	PeerChannel string `json:"peer_channel"`
	ExpiresIn   int    `json:"expires_in"`
	NatsURL     string `json:"nats_url"`
}

// =============================================================================
// Endpoint Models
// =============================================================================

// Policy represents policy configuration for endpoints.
type Policy struct {
	Type        string                 `json:"type"`
	Version     string                 `json:"version"`
	Enabled     bool                   `json:"enabled"`
	Description string                 `json:"description"`
	Config      map[string]interface{} `json:"config"`
}

// Connection represents connection configuration for endpoints.
type Connection struct {
	Type        string                 `json:"type"`
	Enabled     bool                   `json:"enabled"`
	Description string                 `json:"description"`
	Config      map[string]interface{} `json:"config"`
}

// Endpoint represents the full endpoint model (for user's own endpoints).
type Endpoint struct {
	ID             int          `json:"id"`
	UserID         *int         `json:"user_id,omitempty"`
	OrganizationID *int         `json:"organization_id,omitempty"`
	Name           string       `json:"name"`
	Slug           string       `json:"slug"`
	Description    string       `json:"description"`
	Type           EndpointType `json:"type"`
	Visibility     Visibility   `json:"visibility"`
	IsActive       bool         `json:"is_active"`
	Contributors   []int        `json:"contributors"`
	Version        string       `json:"version"`
	Readme         string       `json:"readme"`
	Tags           []string     `json:"tags"`
	StarsCount     int          `json:"stars_count"`
	Policies       []Policy     `json:"policies"`
	Connect        []Connection `json:"connect"`
	CreatedAt      time.Time    `json:"created_at"`
	UpdatedAt      time.Time    `json:"updated_at"`
}

// OwnerType returns "user" or "organization" based on ownership.
func (e *Endpoint) OwnerType() string {
	if e.UserID != nil {
		return "user"
	}
	return "organization"
}

// EndpointPublic represents the public endpoint model (for hub browsing).
type EndpointPublic struct {
	Name              string       `json:"name"`
	Slug              string       `json:"slug"`
	Description       string       `json:"description"`
	Type              EndpointType `json:"type"`
	OwnerUsername     string       `json:"owner_username"`
	ContributorsCount int          `json:"contributors_count"`
	Version           string       `json:"version"`
	Readme            string       `json:"readme"`
	Tags              []string     `json:"tags"`
	StarsCount        int          `json:"stars_count"`
	Policies          []Policy     `json:"policies"`
	Connect           []Connection `json:"connect"`
	CreatedAt         time.Time    `json:"created_at"`
	UpdatedAt         time.Time    `json:"updated_at"`
}

// Path returns the GitHub-style path (owner/slug).
func (e *EndpointPublic) Path() string {
	return e.OwnerUsername + "/" + e.Slug
}

// EndpointSearchResult represents a search result with relevance score.
type EndpointSearchResult struct {
	Name              string       `json:"name"`
	Slug              string       `json:"slug"`
	Description       string       `json:"description"`
	Type              EndpointType `json:"type"`
	OwnerUsername     string       `json:"owner_username"`
	ContributorsCount int          `json:"contributors_count"`
	Version           string       `json:"version"`
	Readme            string       `json:"readme"`
	Tags              []string     `json:"tags"`
	StarsCount        int          `json:"stars_count"`
	Policies          []Policy     `json:"policies"`
	Connect           []Connection `json:"connect"`
	CreatedAt         time.Time    `json:"created_at"`
	UpdatedAt         time.Time    `json:"updated_at"`
	RelevanceScore    float64      `json:"relevance_score"`
}

// Path returns the GitHub-style path (owner/slug).
func (e *EndpointSearchResult) Path() string {
	return e.OwnerUsername + "/" + e.Slug
}

// EndpointSearchResponse represents the response from endpoint search API.
type EndpointSearchResponse struct {
	Results []EndpointSearchResult `json:"results"`
	Total   int                    `json:"total"`
	Query   string                 `json:"query"`
}

// OwnerSummary represents a summary of an owner's endpoints for directory listing.
// This is a lightweight response for listing owners without fetching full endpoint data.
type OwnerSummary struct {
	Username        string `json:"username"`
	EndpointCount   int    `json:"endpoint_count"`
	ModelCount      int    `json:"model_count"`
	DataSourceCount int    `json:"data_source_count"`
}

// OwnersListResponse represents the response from the owners list API.
type OwnersListResponse struct {
	Owners     []OwnerSummary `json:"owners"`
	TotalCount int            `json:"total_count"`
}

// =============================================================================
// Accounting Models
// =============================================================================

// AccountingUser represents a user from the accounting service.
type AccountingUser struct {
	ID           string  `json:"id"`
	Email        string  `json:"email"`
	Balance      float64 `json:"balance"`
	Organization *string `json:"organization,omitempty"`
}

// Transaction represents a transaction record from the accounting service.
type Transaction struct {
	ID             string            `json:"id"`
	SenderEmail    string            `json:"senderEmail"`
	RecipientEmail string            `json:"recipientEmail"`
	Amount         float64           `json:"amount"`
	Status         TransactionStatus `json:"status"`
	CreatedBy      CreatorType       `json:"createdBy"`
	ResolvedBy     *CreatorType      `json:"resolvedBy,omitempty"`
	CreatedAt      time.Time         `json:"createdAt"`
	ResolvedAt     *time.Time        `json:"resolvedAt,omitempty"`
	AppName        *string           `json:"appName,omitempty"`
	AppEpPath      *string           `json:"appEpPath,omitempty"`
}

// IsPending checks if transaction is still pending.
func (t *Transaction) IsPending() bool {
	return t.Status == TransactionStatusPending
}

// IsCompleted checks if transaction was completed.
func (t *Transaction) IsCompleted() bool {
	return t.Status == TransactionStatusCompleted
}

// IsCancelled checks if transaction was cancelled.
func (t *Transaction) IsCancelled() bool {
	return t.Status == TransactionStatusCancelled
}

// AccountingCredentials represents credentials for the accounting service.
type AccountingCredentials struct {
	URL      *string `json:"url,omitempty"`
	Email    string  `json:"email"`
	Password *string `json:"password,omitempty"`
}

// =============================================================================
// Chat Models
// =============================================================================

// EndpointRef represents a reference to a SyftAI-Space endpoint.
type EndpointRef struct {
	URL           string  `json:"url"`
	Slug          string  `json:"slug"`
	Name          string  `json:"name,omitempty"`
	TenantName    *string `json:"tenant_name,omitempty"`
	OwnerUsername *string `json:"owner_username,omitempty"`
}

// Document represents a document retrieved from a data source.
type Document struct {
	Content  string                 `json:"content"`
	Score    float64                `json:"score"`
	Metadata map[string]interface{} `json:"metadata"`
}

// SourceInfo represents information about a data source retrieval.
type SourceInfo struct {
	Path               string       `json:"path"`
	DocumentsRetrieved int          `json:"documents_retrieved"`
	Status             SourceStatus `json:"status"`
	ErrorMessage       *string      `json:"error_message,omitempty"`
}

// DocumentSource represents a document source entry.
type DocumentSource struct {
	Slug    string `json:"slug"`
	Content string `json:"content"`
}

// ChatMetadata represents timing metadata for chat response.
type ChatMetadata struct {
	RetrievalTimeMs  int `json:"retrieval_time_ms"`
	GenerationTimeMs int `json:"generation_time_ms"`
	TotalTimeMs      int `json:"total_time_ms"`
}

// TokenUsage represents token usage information from model generation.
type TokenUsage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

// ChatResponse represents the response from a chat completion request.
type ChatResponse struct {
	Response      string                    `json:"response"`
	Sources       map[string]DocumentSource `json:"sources"`
	RetrievalInfo []SourceInfo              `json:"retrieval_info"`
	Metadata      ChatMetadata              `json:"metadata"`
	Usage         *TokenUsage               `json:"usage,omitempty"`
}

// Message represents a chat message for model queries.
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// =============================================================================
// API Token Models
// =============================================================================

// APIToken represents API token metadata (without the actual token value).
type APIToken struct {
	ID          int             `json:"id"`
	Name        string          `json:"name"`
	TokenPrefix string          `json:"token_prefix"`
	Scopes      []APITokenScope `json:"scopes"`
	ExpiresAt   *time.Time      `json:"expires_at,omitempty"`
	LastUsedAt  *time.Time      `json:"last_used_at,omitempty"`
	LastUsedIP  *string         `json:"last_used_ip,omitempty"`
	IsActive    bool            `json:"is_active"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

// APITokenCreateResponse represents the response from creating an API token.
// The Token field is only returned ONCE during creation.
type APITokenCreateResponse struct {
	APIToken
	Token string `json:"token"`
}

// APITokenListResponse represents the response from listing API tokens.
type APITokenListResponse struct {
	Tokens []APIToken `json:"tokens"`
	Total  int        `json:"total"`
}

// =============================================================================
// NATS Credentials Models
// =============================================================================

// NatsCredentials represents credentials for connecting to the NATS server.
type NatsCredentials struct {
	NatsAuthToken string `json:"nats_auth_token"`
}

// =============================================================================
// Sync Endpoints Models
// =============================================================================

// SyncEndpointsResponse represents the response from sync endpoints operation.
type SyncEndpointsResponse struct {
	Synced    int        `json:"synced"`
	Deleted   int        `json:"deleted"`
	Endpoints []Endpoint `json:"endpoints"`
}

// =============================================================================
// Heartbeat Models
// =============================================================================

// HeartbeatResponse represents the response from the heartbeat endpoint.
type HeartbeatResponse struct {
	Status     string    `json:"status"`
	ReceivedAt time.Time `json:"received_at"`
	ExpiresAt  time.Time `json:"expires_at"`
	Domain     string    `json:"domain"`
	TTLSeconds int       `json:"ttl_seconds"`
}

// =============================================================================
// User Aggregator Models
// =============================================================================

// UserAggregator represents a user's aggregator configuration.
type UserAggregator struct {
	ID        int       `json:"id"`
	UserID    int       `json:"user_id"`
	Name      string    `json:"name"`
	URL       string    `json:"url"`
	IsDefault bool      `json:"is_default"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// =============================================================================
// Request/Input Models
// =============================================================================

// RegisterRequest represents the input for user registration.
type RegisterRequest struct {
	Username           string  `json:"username"`
	Email              string  `json:"email"`
	Password           string  `json:"password"`
	FullName           string  `json:"full_name"`
	AccountingPassword *string `json:"accounting_password,omitempty"`
}

// CreateEndpointRequest represents the input for creating an endpoint.
type CreateEndpointRequest struct {
	Name        string       `json:"name"`
	Slug        *string      `json:"slug,omitempty"`
	Description string       `json:"description,omitempty"`
	Type        EndpointType `json:"type"`
	Visibility  Visibility   `json:"visibility,omitempty"`
	Readme      string       `json:"readme,omitempty"`
	Tags        []string     `json:"tags,omitempty"`
	Policies    []Policy     `json:"policies,omitempty"`
	Connect     []Connection `json:"connect,omitempty"`
}

// UpdateEndpointRequest represents the input for updating an endpoint.
type UpdateEndpointRequest struct {
	Name        *string      `json:"name,omitempty"`
	Description *string      `json:"description,omitempty"`
	Visibility  *Visibility  `json:"visibility,omitempty"`
	Readme      *string      `json:"readme,omitempty"`
	Tags        []string     `json:"tags,omitempty"`
	Policies    []Policy     `json:"policies,omitempty"`
	Connect     []Connection `json:"connect,omitempty"`
}

// UpdateUserRequest represents the input for updating a user profile.
type UpdateUserRequest struct {
	FullName  *string `json:"full_name,omitempty"`
	AvatarURL *string `json:"avatar_url,omitempty"`
}

// ChatRequest represents the input for a chat completion request.
type ChatRequest struct {
	Prompt      string   `json:"prompt"`
	Model       string   `json:"model"`
	DataSources []string `json:"data_sources,omitempty"`
	TopK        int      `json:"top_k,omitempty"`
	MaxTokens   int      `json:"max_tokens,omitempty"`
	Temperature float64  `json:"temperature,omitempty"`
}

// =============================================================================
// Pagination Response Wrapper
// =============================================================================

// PaginatedResponse represents a paginated API response.
type PaginatedResponse[T any] struct {
	Items      []T `json:"items"`
	Total      int `json:"total"`
	Page       int `json:"page"`
	Size       int `json:"size"`
	TotalPages int `json:"total_pages"`
}

// =============================================================================
// Chat Streaming Events
// =============================================================================

// ChatEventType represents the type of chat streaming event.
type ChatEventType string

const (
	ChatEventTypeRetrievalStart      ChatEventType = "retrieval_start"
	ChatEventTypeSourceComplete      ChatEventType = "source_complete"
	ChatEventTypeRetrievalComplete   ChatEventType = "retrieval_complete"
	ChatEventTypeRerankingStart      ChatEventType = "reranking_start"
	ChatEventTypeRerankingComplete   ChatEventType = "reranking_complete"
	ChatEventTypeGenerationStart     ChatEventType = "generation_start"
	ChatEventTypeGenerationHeartbeat ChatEventType = "generation_heartbeat"
	ChatEventTypeToken               ChatEventType = "token"
	ChatEventTypeDone                ChatEventType = "done"
	ChatEventTypeError               ChatEventType = "error"
)

// ChatEvent is the interface for all chat streaming events.
type ChatEvent interface {
	EventType() ChatEventType
}

// RetrievalStartEvent indicates retrieval has started.
type RetrievalStartEvent struct{}

func (e *RetrievalStartEvent) EventType() ChatEventType { return ChatEventTypeRetrievalStart }

// SourceCompleteEvent indicates a single source query completed.
type SourceCompleteEvent struct {
	Source SourceInfo `json:"source"`
}

func (e *SourceCompleteEvent) EventType() ChatEventType { return ChatEventTypeSourceComplete }

// RetrievalCompleteEvent indicates all retrieval is complete.
type RetrievalCompleteEvent struct {
	Sources []SourceInfo `json:"sources"`
}

func (e *RetrievalCompleteEvent) EventType() ChatEventType { return ChatEventTypeRetrievalComplete }

// GenerationStartEvent indicates model generation has started.
type GenerationStartEvent struct {
	Model string `json:"model"`
}

func (e *GenerationStartEvent) EventType() ChatEventType { return ChatEventTypeGenerationStart }

// GenerationHeartbeatEvent is emitted periodically while waiting for model generation.
type GenerationHeartbeatEvent struct {
	ElapsedMs int `json:"elapsed_ms"`
}

func (e *GenerationHeartbeatEvent) EventType() ChatEventType {
	return ChatEventTypeGenerationHeartbeat
}

// RerankingStartEvent indicates document reranking has started.
type RerankingStartEvent struct {
	Documents int `json:"documents"`
}

func (e *RerankingStartEvent) EventType() ChatEventType { return ChatEventTypeRerankingStart }

// RerankingCompleteEvent indicates document reranking is complete.
type RerankingCompleteEvent struct {
	Documents int `json:"documents"`
	TimeMs    int `json:"time_ms"`
}

func (e *RerankingCompleteEvent) EventType() ChatEventType { return ChatEventTypeRerankingComplete }

// TokenEvent represents a single generated token.
type TokenEvent struct {
	Content string `json:"content"`
}

func (e *TokenEvent) EventType() ChatEventType { return ChatEventTypeToken }

// DoneEvent indicates generation is complete.
type DoneEvent struct {
	Response string                    `json:"response"`
	Metadata ChatMetadata              `json:"metadata"`
	Sources  map[string]DocumentSource `json:"sources"`
	Usage    *TokenUsage               `json:"usage,omitempty"`
}

func (e *DoneEvent) EventType() ChatEventType { return ChatEventTypeDone }

// ErrorEvent indicates an error occurred during streaming.
type ErrorEvent struct {
	Error   string `json:"error"`
	Code    string `json:"code,omitempty"`
	Details string `json:"details,omitempty"`
}

func (e *ErrorEvent) EventType() ChatEventType { return ChatEventTypeError }

// =============================================================================
// Transaction Tokens Models
// =============================================================================

// TransactionTokensRequest represents the request for transaction tokens.
type TransactionTokensRequest struct {
	Usernames []string `json:"usernames"`
}

// TransactionTokensResponse represents the response with transaction tokens.
type TransactionTokensResponse struct {
	Tokens map[string]string `json:"tokens"`
}
