package syfthubapi

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// HubAPIError represents an HTTP-level error from the SyftHub backend.
type HubAPIError struct {
	StatusCode int
	Body       string
}

func (e *HubAPIError) Error() string {
	return fmt.Sprintf("hub API error (status %d): %s", e.StatusCode, e.Body)
}

// HubClient handles all communication with the SyftHub backend.
// It provides a single HTTP client for auth, sync, and NATS credential operations.
type HubClient struct {
	httpClient *http.Client
	baseURL    string
	apiKey     string
	logger     Logger
}

// NewHubClient creates a new hub client.
func NewHubClient(baseURL, apiKey string, logger Logger) *HubClient {
	return &HubClient{
		httpClient: &http.Client{Timeout: 30 * time.Second},
		baseURL:    baseURL,
		apiKey:     apiKey,
		logger:     logger,
	}
}

// doJSON performs a JSON HTTP request and decodes the response.
func (c *HubClient) doJSON(ctx context.Context, method, path string, reqBody, respBody any) error {
	var body io.Reader
	if reqBody != nil {
		data, err := json.Marshal(reqBody)
		if err != nil {
			return fmt.Errorf("marshal request: %w", err)
		}
		body = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	if reqBody != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode >= 300 {
		return &HubAPIError{StatusCode: resp.StatusCode, Body: string(raw)}
	}

	if respBody != nil {
		if err := json.Unmarshal(raw, respBody); err != nil {
			return fmt.Errorf("parse response: %w", err)
		}
	}
	return nil
}

// VerifyToken verifies a satellite token and returns the user context.
func (c *HubClient) VerifyToken(ctx context.Context, token string) (*UserContext, error) {
	if token == "" {
		return nil, &AuthenticationError{Message: "missing token"}
	}

	var resp VerifyTokenResponse
	if err := c.doJSON(ctx, "POST", "/api/v1/verify", VerifyTokenRequest{Token: token}, &resp); err != nil {
		return nil, &AuthenticationError{Message: "token verification failed", Cause: err}
	}

	if !resp.Valid {
		msg := resp.Error
		if resp.Message != "" {
			msg = resp.Message
		}
		return nil, &AuthenticationError{Message: msg}
	}

	userCtx := resp.ToUserContext()
	if userCtx == nil {
		return nil, &AuthenticationError{Message: "token valid but user context missing"}
	}

	return userCtx, nil
}

// GetMe retrieves the current user information.
func (c *HubClient) GetMe(ctx context.Context) (*UserContext, error) {
	var user UserContext
	if err := c.doJSON(ctx, "GET", "/api/v1/auth/me", nil, &user); err != nil {
		return nil, &AuthenticationError{Message: "failed to get user info", Cause: err}
	}
	return &user, nil
}

// GetNATSCredentials retrieves NATS credentials for tunnel mode.
func (c *HubClient) GetNATSCredentials(ctx context.Context, username string) (*NATSCredentials, error) {
	var credsResp struct {
		NATSAuthToken string `json:"nats_auth_token"`
	}
	if err := c.doJSON(ctx, "GET", "/api/v1/nats/credentials", nil, &credsResp); err != nil {
		return nil, &AuthenticationError{Message: "failed to get NATS credentials", Cause: err}
	}

	natsURL, err := DeriveNATSWebSocketURL(c.baseURL)
	if err != nil {
		return nil, &AuthenticationError{Message: "failed to derive NATS URL", Cause: err}
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
		return &AuthenticationError{Message: "failed to register encryption key", Cause: err}
	}
	return nil
}

// SyncEndpoints synchronizes endpoints with SyftHub backend.
func (c *HubClient) SyncEndpoints(ctx context.Context, endpoints []EndpointInfo) (*SyncEndpointsResponse, error) {
	var resp SyncEndpointsResponse
	if err := c.doJSON(ctx, "POST", "/api/v1/endpoints/sync", SyncEndpointsRequest{Endpoints: endpoints}, &resp); err != nil {
		if apiErr, ok := err.(*HubAPIError); ok {
			return nil, &SyncError{Message: fmt.Sprintf("sync failed: %s", apiErr.Body), StatusCode: apiErr.StatusCode}
		}
		return nil, &SyncError{Message: "sync failed", Cause: err}
	}

	if c.logger != nil {
		c.logger.Info("endpoints synced", "synced", resp.Synced, "deleted", resp.Deleted)
	}
	return &resp, nil
}

// UpdateDomain updates the user's space domain.
func (c *HubClient) UpdateDomain(ctx context.Context, domain string) error {
	if err := c.doJSON(ctx, "PUT", "/api/v1/users/me", map[string]string{"domain": domain}, nil); err != nil {
		if apiErr, ok := err.(*HubAPIError); ok {
			return &SyncError{Message: fmt.Sprintf("failed to update domain: %s", apiErr.Body), StatusCode: apiErr.StatusCode}
		}
		return &SyncError{Message: "failed to update domain", Cause: err}
	}
	return nil
}
