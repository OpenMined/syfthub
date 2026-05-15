package syfthubapi

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
)

// HubClient handles all communication with the SyftHub backend.
// It provides a single HTTP client for auth, sync, and NATS credential operations.
type HubClient struct {
	httpClient *http.Client
	baseURL    string
	apiKey     string
	logger     *slog.Logger
}

// NewHubClient creates a new hub client.
func NewHubClient(baseURL, apiKey string, logger *slog.Logger) *HubClient {
	return &HubClient{
		httpClient: &http.Client{Timeout: DefaultHTTPTimeout},
		baseURL:    baseURL,
		apiKey:     apiKey,
		logger:     logger,
	}
}

// doJSON performs a JSON HTTP request to the hub with the bearer-token
// Authorization header attached.
func (c *HubClient) doJSON(ctx context.Context, method, path string, reqBody, respBody any) error {
	headers := http.Header{}
	headers.Set("Authorization", "Bearer "+c.apiKey)
	return DoJSONRequest(ctx, c.httpClient, method, c.baseURL+path, headers, reqBody, respBody)
}

// VerifyToken verifies a satellite token and returns the user context.
func (c *HubClient) VerifyToken(ctx context.Context, token string) (*UserContext, error) {
	if token == "" {
		return nil, fmt.Errorf("authentication: missing token")
	}

	var resp VerifyTokenResponse
	if err := c.doJSON(ctx, "POST", "/api/v1/verify", VerifyTokenRequest{Token: token}, &resp); err != nil {
		return nil, fmt.Errorf("authentication: token verification failed: %w", err)
	}

	if !resp.Valid {
		msg := resp.Error
		if resp.Message != "" {
			msg = resp.Message
		}
		return nil, fmt.Errorf("authentication: %s", msg)
	}

	userCtx := resp.ToUserContext()
	if userCtx == nil {
		return nil, fmt.Errorf("authentication: token valid but user context missing")
	}

	return userCtx, nil
}

// GetMe retrieves the current user information.
func (c *HubClient) GetMe(ctx context.Context) (*UserContext, error) {
	var user UserContext
	if err := c.doJSON(ctx, "GET", "/api/v1/auth/me", nil, &user); err != nil {
		return nil, fmt.Errorf("authentication: failed to get user info: %w", err)
	}
	return &user, nil
}

// GetNATSCredentials retrieves NATS credentials for tunnel mode.
func (c *HubClient) GetNATSCredentials(ctx context.Context, username string) (*NATSCredentials, error) {
	var credsResp struct {
		NATSAuthToken string `json:"nats_auth_token"`
	}
	if err := c.doJSON(ctx, "GET", "/api/v1/nats/credentials", nil, &credsResp); err != nil {
		return nil, fmt.Errorf("authentication: failed to get NATS credentials: %w", err)
	}

	natsURL, err := DeriveNATSWebSocketURL(c.baseURL)
	if err != nil {
		return nil, fmt.Errorf("authentication: failed to derive NATS URL: %w", err)
	}

	return &NATSCredentials{
		URL:     natsURL,
		Token:   credsResp.NATSAuthToken,
		Subject: fmt.Sprintf("syfthub.spaces.%s", username),
	}, nil
}

// RegisterEncryptionPublicKey registers the space's X25519 public key with the hub.
func (c *HubClient) RegisterEncryptionPublicKey(ctx context.Context, publicKeyB64 string) error {
	if err := c.doJSON(ctx, "PUT", "/api/v1/nats/encryption-key", map[string]string{"encryption_public_key": publicKeyB64}, nil); err != nil {
		return fmt.Errorf("authentication: failed to register encryption key: %w", err)
	}
	return nil
}

// SyncEndpoints synchronizes endpoints with SyftHub backend.
func (c *HubClient) SyncEndpoints(ctx context.Context, endpoints []EndpointInfo) (*SyncEndpointsResponse, error) {
	var resp SyncEndpointsResponse
	if err := c.doJSON(ctx, "POST", "/api/v1/endpoints/sync", SyncEndpointsRequest{Endpoints: endpoints}, &resp); err != nil {
		var apiErr *HubAPIError
		if errors.As(err, &apiErr) {
			return nil, fmt.Errorf("sync failed (status %d): %s", apiErr.StatusCode, apiErr.Body)
		}
		return nil, fmt.Errorf("sync failed: %w", err)
	}

	if c.logger != nil {
		c.logger.Info("endpoints synced", "synced", resp.Synced, "deleted", resp.Deleted)
	}
	return &resp, nil
}

// UpdateDomain updates the user's space domain.
func (c *HubClient) UpdateDomain(ctx context.Context, domain string) error {
	if err := c.doJSON(ctx, "PUT", "/api/v1/users/me", map[string]string{"domain": domain}, nil); err != nil {
		var apiErr *HubAPIError
		if errors.As(err, &apiErr) {
			return fmt.Errorf("failed to update domain (status %d): %s", apiErr.StatusCode, apiErr.Body)
		}
		return fmt.Errorf("failed to update domain: %w", err)
	}
	return nil
}
