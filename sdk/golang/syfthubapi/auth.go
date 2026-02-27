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

// AuthClient handles authentication with SyftHub backend.
type AuthClient struct {
	httpClient *http.Client
	baseURL    string
	apiKey     string
	logger     Logger
}

// NewAuthClient creates a new authentication client.
func NewAuthClient(baseURL, apiKey string, logger Logger) *AuthClient {
	return &AuthClient{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		baseURL: baseURL,
		apiKey:  apiKey,
		logger:  logger,
	}
}

// VerifyToken verifies a satellite token and returns the user context.
func (c *AuthClient) VerifyToken(ctx context.Context, token string) (*UserContext, error) {
	if token == "" {
		return nil, &AuthenticationError{Message: "missing token"}
	}

	reqBody := VerifyTokenRequest{Token: token}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to marshal request",
			Cause:   err,
		}
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/api/v1/verify", bytes.NewReader(body))
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to create request",
			Cause:   err,
		}
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.apiKey)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to verify token",
			Cause:   err,
		}
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to read response",
			Cause:   err,
		}
	}

	if resp.StatusCode != http.StatusOK {
		return nil, &AuthenticationError{
			Message: fmt.Sprintf("token verification failed: %s", string(respBody)),
		}
	}

	var verifyResp VerifyTokenResponse
	if err := json.Unmarshal(respBody, &verifyResp); err != nil {
		return nil, &AuthenticationError{
			Message: "failed to parse response",
			Cause:   err,
		}
	}

	if !verifyResp.Valid {
		msg := verifyResp.Error
		if verifyResp.Message != "" {
			msg = verifyResp.Message
		}
		return nil, &AuthenticationError{
			Message: msg,
		}
	}

	userCtx := verifyResp.ToUserContext()
	if userCtx == nil {
		return nil, &AuthenticationError{
			Message: "token valid but user context missing",
		}
	}

	return userCtx, nil
}

// GetMe retrieves the current user information.
func (c *AuthClient) GetMe(ctx context.Context) (*UserContext, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", c.baseURL+"/api/v1/auth/me", nil)
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to create request",
			Cause:   err,
		}
	}

	req.Header.Set("Authorization", "Bearer "+c.apiKey)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to get user info",
			Cause:   err,
		}
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, &AuthenticationError{
			Message: fmt.Sprintf("authentication failed: %s", string(body)),
		}
	}

	var user UserContext
	if err := json.NewDecoder(resp.Body).Decode(&user); err != nil {
		return nil, &AuthenticationError{
			Message: "failed to parse response",
			Cause:   err,
		}
	}

	return &user, nil
}

// GetNATSCredentials retrieves NATS credentials for tunnel mode.
func (c *AuthClient) GetNATSCredentials(ctx context.Context, username string) (*NATSCredentials, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", c.baseURL+"/api/v1/nats/credentials", nil)
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to create request",
			Cause:   err,
		}
	}

	req.Header.Set("Authorization", "Bearer "+c.apiKey)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to get NATS credentials",
			Cause:   err,
		}
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, &AuthenticationError{
			Message: fmt.Sprintf("failed to get NATS credentials: %s", string(body)),
		}
	}

	// Parse the response which contains nats_auth_token
	var credsResp struct {
		NATSAuthToken string `json:"nats_auth_token"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&credsResp); err != nil {
		return nil, &AuthenticationError{
			Message: "failed to parse response",
			Cause:   err,
		}
	}

	// Derive NATS WebSocket URL from base URL
	natsURL, err := DeriveNATSWebSocketURL(c.baseURL)
	if err != nil {
		return nil, &AuthenticationError{
			Message: "failed to derive NATS URL",
			Cause:   err,
		}
	}

	// Build the subject for this user
	subject := fmt.Sprintf("syfthub.spaces.%s", username)

	return &NATSCredentials{
		URL:     natsURL,
		Token:   credsResp.NATSAuthToken,
		Subject: subject,
	}, nil
}

// RegisterEncryptionPublicKey registers the space's X25519 public key with the hub.
// Called on startup after generating the keypair, before subscribing to NATS.
func (c *AuthClient) RegisterEncryptionPublicKey(ctx context.Context, publicKeyB64 string) error {
	body, err := json.Marshal(map[string]string{
		"encryption_public_key": publicKeyB64,
	})
	if err != nil {
		return &AuthenticationError{
			Message: "failed to marshal key registration request",
			Cause:   err,
		}
	}

	req, err := http.NewRequestWithContext(
		ctx, "PUT",
		c.baseURL+"/api/v1/nats/encryption-key",
		bytes.NewReader(body),
	)
	if err != nil {
		return &AuthenticationError{
			Message: "failed to create request",
			Cause:   err,
		}
	}
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return &AuthenticationError{
			Message: "failed to register encryption key",
			Cause:   err,
		}
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return &AuthenticationError{
			Message: fmt.Sprintf("failed to register encryption key: %s", string(respBody)),
		}
	}

	return nil
}

// SyncClient handles endpoint synchronization with SyftHub backend.
type SyncClient struct {
	httpClient *http.Client
	baseURL    string
	apiKey     string
	logger     Logger
}

// NewSyncClient creates a new sync client.
func NewSyncClient(baseURL, apiKey string, logger Logger) *SyncClient {
	return &SyncClient{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		baseURL: baseURL,
		apiKey:  apiKey,
		logger:  logger,
	}
}

// SyncEndpoints synchronizes endpoints with SyftHub backend.
func (c *SyncClient) SyncEndpoints(ctx context.Context, endpoints []EndpointInfo) (*SyncEndpointsResponse, error) {
	reqBody := SyncEndpointsRequest{Endpoints: endpoints}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, &SyncError{
			Message: "failed to marshal request",
			Cause:   err,
		}
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/api/v1/endpoints/sync", bytes.NewReader(body))
	if err != nil {
		return nil, &SyncError{
			Message: "failed to create request",
			Cause:   err,
		}
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.apiKey)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, &SyncError{
			Message: "failed to sync endpoints",
			Cause:   err,
		}
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, &SyncError{
			Message: "failed to read response",
			Cause:   err,
		}
	}

	if resp.StatusCode != http.StatusOK {
		return nil, &SyncError{
			Message:    fmt.Sprintf("sync failed: %s", string(respBody)),
			StatusCode: resp.StatusCode,
		}
	}

	var syncResp SyncEndpointsResponse
	if err := json.Unmarshal(respBody, &syncResp); err != nil {
		return nil, &SyncError{
			Message: "failed to parse response",
			Cause:   err,
		}
	}

	if c.logger != nil {
		c.logger.Info("endpoints synced",
			"synced", syncResp.Synced,
			"deleted", syncResp.Deleted,
		)
	}

	return &syncResp, nil
}

// UpdateDomain updates the user's space domain.
func (c *SyncClient) UpdateDomain(ctx context.Context, domain string) error {
	reqBody := map[string]string{"domain": domain}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return &SyncError{
			Message: "failed to marshal request",
			Cause:   err,
		}
	}

	req, err := http.NewRequestWithContext(ctx, "PUT", c.baseURL+"/api/v1/users/me", bytes.NewReader(body))
	if err != nil {
		return &SyncError{
			Message: "failed to create request",
			Cause:   err,
		}
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.apiKey)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return &SyncError{
			Message: "failed to update domain",
			Cause:   err,
		}
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return &SyncError{
			Message:    fmt.Sprintf("failed to update domain: %s", string(respBody)),
			StatusCode: resp.StatusCode,
		}
	}

	return nil
}

// APIAuthenticator provides authentication for the SyftAPI.
type APIAuthenticator struct {
	authClient *AuthClient
	syncClient *SyncClient
	config     *Config
	logger     Logger
}

// NewAPIAuthenticator creates a new API authenticator.
func NewAPIAuthenticator(config *Config, logger Logger) *APIAuthenticator {
	return &APIAuthenticator{
		authClient: NewAuthClient(config.SyftHubURL, config.APIKey, logger),
		syncClient: NewSyncClient(config.SyftHubURL, config.APIKey, logger),
		config:     config,
		logger:     logger,
	}
}

// Authenticate authenticates with SyftHub and returns user info.
func (a *APIAuthenticator) Authenticate(ctx context.Context) (*UserContext, error) {
	user, err := a.authClient.GetMe(ctx)
	if err != nil {
		return nil, err
	}

	if a.logger != nil {
		a.logger.Info("authenticated with SyftHub",
			"username", user.Username,
			"email", user.Email,
		)
	}

	return user, nil
}

// SyncEndpoints syncs endpoints with SyftHub.
func (a *APIAuthenticator) SyncEndpoints(ctx context.Context, endpoints []EndpointInfo) error {
	// Update domain first
	if !a.config.IsTunnelMode() {
		if err := a.syncClient.UpdateDomain(ctx, a.config.SpaceURL); err != nil {
			return err
		}
	}

	// Sync endpoints
	_, err := a.syncClient.SyncEndpoints(ctx, endpoints)
	return err
}

// VerifyToken verifies a satellite token.
func (a *APIAuthenticator) VerifyToken(ctx context.Context, token string) (*UserContext, error) {
	return a.authClient.VerifyToken(ctx, token)
}

// GetNATSCredentials gets NATS credentials for tunnel mode.
func (a *APIAuthenticator) GetNATSCredentials(ctx context.Context) (*NATSCredentials, error) {
	username := a.config.GetTunnelUsername()
	return a.authClient.GetNATSCredentials(ctx, username)
}

// RegisterEncryptionPublicKey registers the space's X25519 public key with the hub.
func (a *APIAuthenticator) RegisterEncryptionPublicKey(ctx context.Context, publicKeyB64 string) error {
	return a.authClient.RegisterEncryptionPublicKey(ctx, publicKeyB64)
}
