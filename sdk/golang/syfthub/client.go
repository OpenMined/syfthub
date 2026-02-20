package syfthub

import (
	"context"
	"os"
	"strings"
	"sync"
	"time"
)

// Environment variable names.
const (
	EnvSyftHubURL    = "SYFTHUB_URL"
	EnvAggregatorURL = "SYFTHUB_AGGREGATOR_URL"
	EnvAPIToken      = "SYFTHUB_API_TOKEN"
)

// Default configuration values.
const (
	DefaultTimeout    = 30 * time.Second
	DefaultAggTimeout = 120 * time.Second
	DefaultPageSize   = 20
)

// Client is the main client for interacting with the SyftHub API.
//
// Example usage:
//
//	// Initialize with environment variable
//	// (set SYFTHUB_URL=https://hub.syft.com)
//	client, err := syfthub.NewClient()
//
//	// Or with explicit URL
//	client, err := syfthub.NewClient(syfthub.WithBaseURL("https://hub.syft.com"))
//
//	// Login with username/password
//	user, err := client.Auth.Login(ctx, "john", "secret123")
//
//	// Or use API token (alternative to login)
//	client, err := syfthub.NewClient(
//	    syfthub.WithBaseURL("https://hub.syft.com"),
//	    syfthub.WithAPIToken("syft_pat_xxxxx..."),
//	)
//	// No login needed with API token!
//
//	// Use resources
//	iter := client.MyEndpoints.List(ctx)
//	for iter.Next(ctx) {
//	    fmt.Println(iter.Value().Name)
//	}
//
//	// Context manager for cleanup
//	defer client.Close()
//
//	// Token persistence
//	tokens := client.GetTokens()
//	// ... save tokens to file/db ...
//	// Later:
//	client.SetTokens(tokens)
type Client struct {
	baseURL       string
	aggregatorURL string
	timeout       time.Duration
	http          *httpClient

	// Eagerly-initialized resources
	Auth        *AuthResource
	Users       *UsersResource
	MyEndpoints *MyEndpointsResource
	Hub         *HubResource

	// Lazy-initialized resources
	mu         sync.Mutex
	chat       *ChatResource
	syftai     *SyftAIResource
	accounting *AccountingResource
	apiTokens  *APITokensResource
}

// Option is a function that configures the Client.
type Option func(*Client) error

// WithBaseURL sets the base URL for the SyftHub API.
func WithBaseURL(url string) Option {
	return func(c *Client) error {
		c.baseURL = strings.TrimRight(url, "/")
		return nil
	}
}

// WithTimeout sets the request timeout.
func WithTimeout(timeout time.Duration) Option {
	return func(c *Client) error {
		c.timeout = timeout
		return nil
	}
}

// WithAggregatorURL sets a custom aggregator URL.
func WithAggregatorURL(url string) Option {
	return func(c *Client) error {
		c.aggregatorURL = strings.TrimRight(url, "/")
		return nil
	}
}

// WithAPIToken sets an API token for authentication.
// When provided, the client will be authenticated immediately without needing to call Login().
func WithAPIToken(token string) Option {
	return func(c *Client) error {
		if c.http != nil {
			c.http.SetAPIToken(token)
		}
		return nil
	}
}

// NewClient creates a new SyftHub client.
//
// Options can be passed to customize the client configuration.
// If no base URL is provided, it will be read from the SYFTHUB_URL environment variable.
func NewClient(opts ...Option) (*Client, error) {
	c := &Client{
		timeout: DefaultTimeout,
	}

	// Apply options
	for _, opt := range opts {
		if err := opt(c); err != nil {
			return nil, err
		}
	}

	// Resolve base URL from environment if not set
	if c.baseURL == "" {
		c.baseURL = os.Getenv(EnvSyftHubURL)
	}
	if c.baseURL == "" {
		return nil, &ConfigurationError{
			SyftHubError: newSyftHubError(0, "SyftHub URL not configured. Either pass WithBaseURL option or set "+EnvSyftHubURL+" environment variable"),
		}
	}

	// Resolve aggregator URL (default to {base_url}/aggregator/api/v1)
	if c.aggregatorURL == "" {
		c.aggregatorURL = os.Getenv(EnvAggregatorURL)
	}
	if c.aggregatorURL == "" {
		c.aggregatorURL = c.baseURL + "/aggregator/api/v1"
	}

	// Create HTTP client
	c.http = newHTTPClient(c.baseURL, c.timeout)

	// Check for API token from environment
	if envToken := os.Getenv(EnvAPIToken); envToken != "" {
		c.http.SetAPIToken(envToken)
	}

	// Re-apply WithAPIToken option if it was passed (after http client is created)
	for _, opt := range opts {
		if err := opt(c); err != nil {
			return nil, err
		}
	}

	// Create eagerly-initialized resources
	c.Auth = newAuthResource(c.http)
	c.Users = newUsersResource(c.http)
	c.MyEndpoints = newMyEndpointsResource(c.http)
	c.Hub = newHubResource(c.http)

	return c, nil
}

// Chat returns the ChatResource for RAG-augmented conversations.
// The resource is lazily initialized on first access.
func (c *Client) Chat() *ChatResource {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.chat == nil {
		c.chat = newChatResource(c.Hub, c.Auth, c.aggregatorURL, c.timeout)
	}
	return c.chat
}

// SyftAI returns the SyftAIResource for direct SyftAI-Space queries.
// The resource is lazily initialized on first access.
func (c *Client) SyftAI() *SyftAIResource {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.syftai == nil {
		c.syftai = newSyftAIResource(c.http)
	}
	return c.syftai
}

// Accounting returns the AccountingResource for billing operations.
// The resource is lazily initialized on first access.
// Credentials are automatically retrieved from the backend after login.
//
// Returns an error if not authenticated or if accounting is not configured.
func (c *Client) Accounting(ctx context.Context) (*AccountingResource, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.accounting == nil {
		acc, err := c.initAccounting(ctx)
		if err != nil {
			return nil, err
		}
		c.accounting = acc
	}
	return c.accounting, nil
}

// initAccounting initializes the accounting resource by fetching credentials from the backend.
func (c *Client) initAccounting(ctx context.Context) (*AccountingResource, error) {
	if !c.IsAuthenticated() {
		return nil, newAuthenticationError("Must be logged in to use accounting. Call client.Auth.Login() first.")
	}

	// Fetch credentials from backend
	creds, err := c.Users.GetAccountingCredentials(ctx)
	if err != nil {
		return nil, err
	}

	if creds.URL == nil || *creds.URL == "" {
		return nil, &ConfigurationError{
			SyftHubError: newSyftHubError(0, "No accounting service configured for this user. Contact your administrator to set up accounting."),
		}
	}

	if creds.Password == nil || *creds.Password == "" {
		return nil, &ConfigurationError{
			SyftHubError: newSyftHubError(0, "Accounting password not available. This may indicate an issue with your account setup."),
		}
	}

	return newAccountingResource(*creds.URL, creds.Email, *creds.Password, c.timeout), nil
}

// APITokens returns the APITokensResource for managing API tokens.
// The resource is lazily initialized on first access.
func (c *Client) APITokens() *APITokensResource {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.apiTokens == nil {
		c.apiTokens = newAPITokensResource(c.http)
	}
	return c.apiTokens
}

// IsAuthenticated returns true if the client has authentication (JWT or API token).
func (c *Client) IsAuthenticated() bool {
	return c.http.IsAuthenticated()
}

// IsUsingAPIToken returns true if the client is using API token authentication.
func (c *Client) IsUsingAPIToken() bool {
	return c.http.IsUsingAPIToken()
}

// GetTokens returns the current authentication tokens for persistence.
// Returns nil if not authenticated with JWT tokens.
func (c *Client) GetTokens() *AuthTokens {
	return c.http.GetTokens()
}

// SetTokens sets authentication tokens (e.g., from a saved session).
func (c *Client) SetTokens(tokens *AuthTokens) {
	c.http.SetTokens(tokens)
}

// Close closes the client and releases resources.
func (c *Client) Close() {
	c.http.Close()
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.accounting != nil {
		c.accounting.Close()
	}
}

// BaseURL returns the configured base URL.
func (c *Client) BaseURL() string {
	return c.baseURL
}

// AggregatorURL returns the configured aggregator URL.
func (c *Client) AggregatorURL() string {
	return c.aggregatorURL
}

// -------------------------------------------------------------------------
// Auth method aliases for convenience
// -------------------------------------------------------------------------

// Register registers a new user. Alias for client.Auth.Register().
func (c *Client) Register(ctx context.Context, req *RegisterRequest) (*User, error) {
	return c.Auth.Register(ctx, req)
}

// Login logs in with username and password. Alias for client.Auth.Login().
func (c *Client) Login(ctx context.Context, username, password string) (*User, error) {
	return c.Auth.Login(ctx, username, password)
}

// Logout logs out and invalidates tokens. Alias for client.Auth.Logout().
func (c *Client) Logout(ctx context.Context) error {
	return c.Auth.Logout(ctx)
}

// Me returns the current authenticated user. Alias for client.Auth.Me().
func (c *Client) Me(ctx context.Context) (*User, error) {
	return c.Auth.Me(ctx)
}

// Refresh manually refreshes the access token. Alias for client.Auth.Refresh().
func (c *Client) Refresh(ctx context.Context) error {
	return c.Auth.Refresh(ctx)
}

// ChangePassword changes the current user's password. Alias for client.Auth.ChangePassword().
func (c *Client) ChangePassword(ctx context.Context, currentPassword, newPassword string) error {
	return c.Auth.ChangePassword(ctx, currentPassword, newPassword)
}
