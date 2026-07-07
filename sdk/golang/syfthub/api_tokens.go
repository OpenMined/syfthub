package syfthub

import (
	"context"
	"fmt"
	"net/url"
	"strconv"
	"time"
)

// APITokensResource handles API token management.
//
// API tokens provide an alternative to username/password authentication.
// They are ideal for CI/CD pipelines, scripts, and programmatic access.
//
// Example usage:
//
//	// Create a new token
//	result, err := client.APITokens().Create(ctx, &CreateAPITokenRequest{
//	    Name:   "CI/CD Pipeline",
//	    Scopes: []APITokenScope{APITokenScopeWrite},
//	})
//	fmt.Println("Save this token:", result.Token)
//
//	// List all tokens
//	response, err := client.APITokens().List(ctx)
//	for _, token := range response.Tokens {
//	    fmt.Println(token.Name, token.LastUsedAt)
//	}
//
//	// Revoke a token
//	err = client.APITokens().Revoke(ctx, tokenID)
type APITokensResource struct {
	http *httpClient
}

// newAPITokensResource creates a new APITokensResource.
func newAPITokensResource(http *httpClient) *APITokensResource {
	return &APITokensResource{http: http}
}

// CreateAPITokenRequest contains parameters for creating an API token.
type CreateAPITokenRequest struct {
	// Name is a descriptive name for the token (e.g., "CI/CD Pipeline")
	Name string

	// Scopes are permission scopes (default: ["full"]).
	// Options: "read", "write", "full"
	Scopes []APITokenScope

	// ExpiresAt is an optional expiration date
	ExpiresAt *time.Time
}

// Create creates a new API token.
//
// IMPORTANT: The returned token is only shown ONCE!
// Make sure to save it immediately - it cannot be retrieved later.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - ValidationError: If input is invalid
func (a *APITokensResource) Create(ctx context.Context, req *CreateAPITokenRequest) (*APITokenCreateResponse, error) {
	payload := map[string]interface{}{
		"name": req.Name,
	}

	if req.Scopes != nil {
		scopes := make([]string, len(req.Scopes))
		for i, s := range req.Scopes {
			scopes[i] = string(s)
		}
		payload["scopes"] = scopes
	}

	if req.ExpiresAt != nil {
		payload["expires_at"] = req.ExpiresAt.Format(time.RFC3339)
	}

	var response APITokenCreateResponse
	err := a.http.Post(ctx, "/api/v1/auth/tokens", payload, &response)
	if err != nil {
		return nil, err
	}
	return &response, nil
}

// ListAPITokensOption configures the List operation.
type ListAPITokensOption func(*listAPITokensOptions)

type listAPITokensOptions struct {
	includeInactive bool
	skip            int
	limit           int
}

// WithIncludeInactive includes revoked tokens in the list.
func WithIncludeInactive() ListAPITokensOption {
	return func(o *listAPITokensOptions) {
		o.includeInactive = true
	}
}

// WithTokensSkip sets the number of tokens to skip (for pagination).
func WithTokensSkip(skip int) ListAPITokensOption {
	return func(o *listAPITokensOptions) {
		o.skip = skip
	}
}

// WithTokensLimit sets the maximum number of tokens to return.
func WithTokensLimit(limit int) ListAPITokensOption {
	return func(o *listAPITokensOptions) {
		o.limit = limit
	}
}

// List returns all API tokens for the current user.
//
// By default, only active tokens are returned.
// Note: The full token value is never returned - only the prefix.
//
// Errors:
//   - AuthenticationError: If not authenticated
func (a *APITokensResource) List(ctx context.Context, opts ...ListAPITokensOption) (*APITokenListResponse, error) {
	options := &listAPITokensOptions{
		skip:  0,
		limit: 100,
	}
	for _, opt := range opts {
		opt(options)
	}

	query := url.Values{}
	query.Set("skip", strconv.Itoa(options.skip))
	query.Set("limit", strconv.Itoa(options.limit))
	if options.includeInactive {
		query.Set("include_inactive", "true")
	}

	var response APITokenListResponse
	err := a.http.Get(ctx, "/api/v1/auth/tokens", &response, WithQuery(query))
	if err != nil {
		return nil, err
	}
	return &response, nil
}

// Get returns a single API token by ID.
//
// Note: The full token value is never returned - only the prefix.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If token not found
func (a *APITokensResource) Get(ctx context.Context, tokenID int) (*APIToken, error) {
	var token APIToken
	err := a.http.Get(ctx, fmt.Sprintf("/api/v1/auth/tokens/%d", tokenID), &token)
	if err != nil {
		return nil, err
	}
	return &token, nil
}

// Update updates an API token's name.
//
// Only the name can be updated. Scopes and expiration cannot be
// changed after creation.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If token not found
//   - ValidationError: If input is invalid
func (a *APITokensResource) Update(ctx context.Context, tokenID int, name string) (*APIToken, error) {
	var token APIToken
	err := a.http.Patch(ctx, fmt.Sprintf("/api/v1/auth/tokens/%d", tokenID), map[string]string{"name": name}, &token)
	if err != nil {
		return nil, err
	}
	return &token, nil
}

// Revoke revokes an API token.
//
// The token becomes immediately unusable. This action cannot be undone.
//
// Errors:
//   - AuthenticationError: If not authenticated
//   - NotFoundError: If token not found
func (a *APITokensResource) Revoke(ctx context.Context, tokenID int) error {
	return a.http.Delete(ctx, fmt.Sprintf("/api/v1/auth/tokens/%d", tokenID))
}
