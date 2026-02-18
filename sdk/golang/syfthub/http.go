package syfthub

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// HTTPDoer is an interface for making HTTP requests (for testing).
type HTTPDoer interface {
	Do(req *http.Request) (*http.Response, error)
}

// httpClient is the internal HTTP client with automatic token management.
type httpClient struct {
	baseURL string
	timeout time.Duration
	client  HTTPDoer

	// Token storage (protected by mutex)
	mu           sync.RWMutex
	accessToken  string
	refreshToken string
	apiToken     string
}

// newHTTPClient creates a new HTTP client.
func newHTTPClient(baseURL string, timeout time.Duration) *httpClient {
	return &httpClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		timeout: timeout,
		client: &http.Client{
			Timeout: timeout,
		},
	}
}

// newHTTPClientWithDoer creates a new HTTP client with a custom HTTPDoer (for testing).
func newHTTPClientWithDoer(baseURL string, timeout time.Duration, doer HTTPDoer) *httpClient {
	return &httpClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		timeout: timeout,
		client:  doer,
	}
}

// Close closes the HTTP client.
func (h *httpClient) Close() {
	// http.Client doesn't need explicit closing, but if we have custom transport
	// we might need to close it. For now, this is a no-op.
}

// IsAuthenticated checks if client has tokens set.
func (h *httpClient) IsAuthenticated() bool {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return h.accessToken != "" || h.apiToken != ""
}

// IsUsingAPIToken checks if client is using API token authentication.
func (h *httpClient) IsUsingAPIToken() bool {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return h.apiToken != ""
}

// SetTokens sets JWT authentication tokens.
func (h *httpClient) SetTokens(tokens *AuthTokens) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.accessToken = tokens.AccessToken
	h.refreshToken = tokens.RefreshToken
	h.apiToken = "" // Clear API token when using JWT
}

// SetAPIToken sets API token for authentication.
func (h *httpClient) SetAPIToken(token string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.apiToken = token
	h.accessToken = "" // Clear JWT tokens when using API token
	h.refreshToken = ""
}

// GetTokens returns current JWT authentication tokens.
func (h *httpClient) GetTokens() *AuthTokens {
	h.mu.RLock()
	defer h.mu.RUnlock()
	if h.accessToken != "" && h.refreshToken != "" {
		return &AuthTokens{
			AccessToken:  h.accessToken,
			RefreshToken: h.refreshToken,
			TokenType:    "bearer",
		}
	}
	return nil
}

// ClearTokens clears all authentication tokens.
func (h *httpClient) ClearTokens() {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.accessToken = ""
	h.refreshToken = ""
	h.apiToken = ""
}

// getBearerToken returns the current bearer token (API token takes precedence).
func (h *httpClient) getBearerToken() string {
	h.mu.RLock()
	defer h.mu.RUnlock()
	if h.apiToken != "" {
		return h.apiToken
	}
	return h.accessToken
}

// requestOptions contains options for making HTTP requests.
type requestOptions struct {
	includeAuth bool
	retryOn401  bool
	formData    url.Values
	query       url.Values
}

// RequestOption is a function that modifies request options.
type RequestOption func(*requestOptions)

// WithoutAuth disables authentication for the request.
func WithoutAuth() RequestOption {
	return func(o *requestOptions) {
		o.includeAuth = false
	}
}

// WithNoRetry disables 401 retry for the request.
func WithNoRetry() RequestOption {
	return func(o *requestOptions) {
		o.retryOn401 = false
	}
}

// WithFormData sets form data for the request.
func WithFormData(data url.Values) RequestOption {
	return func(o *requestOptions) {
		o.formData = data
	}
}

// WithQuery sets query parameters for the request.
func WithQuery(params url.Values) RequestOption {
	return func(o *requestOptions) {
		o.query = params
	}
}

// Request makes an HTTP request and returns the response body.
func (h *httpClient) Request(ctx context.Context, method, path string, body interface{}, opts ...RequestOption) ([]byte, error) {
	// Apply default options
	options := &requestOptions{
		includeAuth: true,
		retryOn401:  true,
	}
	for _, opt := range opts {
		opt(options)
	}

	// Build URL
	reqURL := h.baseURL + path
	if options.query != nil {
		reqURL += "?" + options.query.Encode()
	}

	// Build request body
	var bodyReader io.Reader
	var contentType string

	if options.formData != nil {
		bodyReader = strings.NewReader(options.formData.Encode())
		contentType = "application/x-www-form-urlencoded"
	} else if body != nil {
		bodyBytes, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		bodyReader = bytes.NewReader(bodyBytes)
		contentType = "application/json"
	}

	// Create request
	req, err := http.NewRequestWithContext(ctx, method, reqURL, bodyReader)
	if err != nil {
		return nil, newNetworkError(fmt.Errorf("failed to create request: %w", err))
	}

	// Set headers
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	req.Header.Set("Accept", "application/json")

	if options.includeAuth {
		if token := h.getBearerToken(); token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
	}

	// Make request
	resp, err := h.client.Do(req)
	if err != nil {
		return nil, newNetworkError(err)
	}
	defer resp.Body.Close()

	// Read response body
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, newNetworkError(fmt.Errorf("failed to read response body: %w", err))
	}

	// Handle 401 with token refresh
	if resp.StatusCode == 401 && options.retryOn401 && options.includeAuth && h.attemptRefresh(ctx) {
		// Retry with new token
		return h.Request(ctx, method, path, body, append(opts, WithNoRetry())...)
	}

	// Handle errors
	if resp.StatusCode >= 400 {
		return nil, h.handleError(resp.StatusCode, respBody)
	}

	// Return body (or empty for 204)
	if resp.StatusCode == 204 {
		return []byte("{}"), nil
	}

	return respBody, nil
}

// attemptRefresh attempts to refresh the access token.
func (h *httpClient) attemptRefresh(ctx context.Context) bool {
	h.mu.RLock()
	apiToken := h.apiToken
	refreshToken := h.refreshToken
	h.mu.RUnlock()

	// API tokens don't support refresh
	if apiToken != "" {
		return false
	}

	if refreshToken == "" {
		return false
	}

	// Make refresh request
	reqBody, _ := json.Marshal(map[string]string{
		"refresh_token": refreshToken,
	})

	req, err := http.NewRequestWithContext(ctx, "POST", h.baseURL+"/api/v1/auth/refresh", bytes.NewReader(reqBody))
	if err != nil {
		return false
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := h.client.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return false
	}

	var result struct {
		AccessToken  string `json:"access_token"`
		RefreshToken string `json:"refresh_token"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false
	}

	h.mu.Lock()
	h.accessToken = result.AccessToken
	h.refreshToken = result.RefreshToken
	h.mu.Unlock()

	return true
}

// handleError converts HTTP errors to SDK errors.
func (h *httpClient) handleError(statusCode int, body []byte) error {
	// Try to parse error detail
	var detail map[string]interface{}
	var message string
	var errorCode string

	if err := json.Unmarshal(body, &detail); err == nil {
		// Try to extract message from nested detail
		if innerDetail, ok := detail["detail"].(map[string]interface{}); ok {
			if msg, ok := innerDetail["message"].(string); ok {
				message = msg
			}
			if code, ok := innerDetail["code"].(string); ok {
				errorCode = code
			}
		} else if detailStr, ok := detail["detail"].(string); ok {
			message = detailStr
		} else if msg, ok := detail["message"].(string); ok {
			message = msg
		}
	}

	if message == "" {
		message = string(body)
	}

	// Check for accounting-specific errors
	if errorCode != "" {
		switch errorCode {
		case "ACCOUNTING_ACCOUNT_EXISTS":
			return &AccountingAccountExistsError{
				SyftHubError: newSyftHubError(statusCode, message),
			}
		case "INVALID_ACCOUNTING_PASSWORD":
			return &InvalidAccountingPasswordError{
				SyftHubError: newSyftHubError(statusCode, message),
			}
		case "ACCOUNTING_SERVICE_UNAVAILABLE":
			return &AccountingServiceUnavailableError{
				SyftHubError: newSyftHubError(statusCode, message),
			}
		}
	}

	// Standard error handling
	switch statusCode {
	case 401:
		return newAuthenticationError(message)
	case 403:
		return newAuthorizationError(message)
	case 404:
		return newNotFoundError(message)
	case 422:
		// Try to extract validation errors
		var validationErrors map[string][]string
		if detailMap, ok := detail["detail"].(map[string]interface{}); ok {
			if errorsMap, ok := detailMap["errors"].(map[string]interface{}); ok {
				validationErrors = make(map[string][]string)
				for k, v := range errorsMap {
					if arr, ok := v.([]interface{}); ok {
						for _, item := range arr {
							if str, ok := item.(string); ok {
								validationErrors[k] = append(validationErrors[k], str)
							}
						}
					}
				}
			}
		}
		return newValidationError(message, validationErrors)
	default:
		return newAPIError(statusCode, message)
	}
}

// Get makes a GET request.
func (h *httpClient) Get(ctx context.Context, path string, result interface{}, opts ...RequestOption) error {
	body, err := h.Request(ctx, "GET", path, nil, opts...)
	if err != nil {
		return err
	}
	if result != nil {
		return json.Unmarshal(body, result)
	}
	return nil
}

// Post makes a POST request.
func (h *httpClient) Post(ctx context.Context, path string, body, result interface{}, opts ...RequestOption) error {
	respBody, err := h.Request(ctx, "POST", path, body, opts...)
	if err != nil {
		return err
	}
	if result != nil {
		return json.Unmarshal(respBody, result)
	}
	return nil
}

// Put makes a PUT request.
func (h *httpClient) Put(ctx context.Context, path string, body, result interface{}, opts ...RequestOption) error {
	respBody, err := h.Request(ctx, "PUT", path, body, opts...)
	if err != nil {
		return err
	}
	if result != nil {
		return json.Unmarshal(respBody, result)
	}
	return nil
}

// Patch makes a PATCH request.
func (h *httpClient) Patch(ctx context.Context, path string, body, result interface{}, opts ...RequestOption) error {
	respBody, err := h.Request(ctx, "PATCH", path, body, opts...)
	if err != nil {
		return err
	}
	if result != nil {
		return json.Unmarshal(respBody, result)
	}
	return nil
}

// Delete makes a DELETE request.
func (h *httpClient) Delete(ctx context.Context, path string, opts ...RequestOption) error {
	_, err := h.Request(ctx, "DELETE", path, nil, opts...)
	return err
}

// GetRaw makes a GET request and returns the raw response body.
func (h *httpClient) GetRaw(ctx context.Context, path string, opts ...RequestOption) ([]byte, error) {
	return h.Request(ctx, "GET", path, nil, opts...)
}

// PostRaw makes a POST request and returns the raw response body.
func (h *httpClient) PostRaw(ctx context.Context, path string, body interface{}, opts ...RequestOption) ([]byte, error) {
	return h.Request(ctx, "POST", path, body, opts...)
}

// StreamRequest makes a streaming HTTP request and returns the response for reading.
// The caller is responsible for closing the response body.
func (h *httpClient) StreamRequest(ctx context.Context, method, path string, body interface{}, opts ...RequestOption) (*http.Response, error) {
	// Apply default options
	options := &requestOptions{
		includeAuth: true,
		retryOn401:  false, // Streaming requests don't retry
	}
	for _, opt := range opts {
		opt(options)
	}

	// Build URL
	reqURL := h.baseURL + path
	if options.query != nil {
		reqURL += "?" + options.query.Encode()
	}

	// Build request body
	var bodyReader io.Reader
	if body != nil {
		bodyBytes, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		bodyReader = bytes.NewReader(bodyBytes)
	}

	// Create request
	req, err := http.NewRequestWithContext(ctx, method, reqURL, bodyReader)
	if err != nil {
		return nil, newNetworkError(fmt.Errorf("failed to create request: %w", err))
	}

	// Set headers
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	if options.includeAuth {
		if token := h.getBearerToken(); token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
	}

	// Make request
	resp, err := h.client.Do(req)
	if err != nil {
		return nil, newNetworkError(err)
	}

	// Handle errors (but don't close body - let caller handle it)
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		return nil, h.handleError(resp.StatusCode, body)
	}

	return resp, nil
}

// basicAuthHTTPClient wraps httpClient with Basic authentication for accounting service.
type basicAuthHTTPClient struct {
	*httpClient
	username string
	password string
}

// newBasicAuthHTTPClient creates a new HTTP client with Basic authentication.
func newBasicAuthHTTPClient(baseURL string, timeout time.Duration, username, password string) *basicAuthHTTPClient {
	return &basicAuthHTTPClient{
		httpClient: newHTTPClient(baseURL, timeout),
		username:   username,
		password:   password,
	}
}

// Request makes an HTTP request with Basic authentication.
func (h *basicAuthHTTPClient) Request(ctx context.Context, method, path string, body interface{}, opts ...RequestOption) ([]byte, error) {
	// Apply default options
	options := &requestOptions{
		includeAuth: true,
		retryOn401:  false, // No token refresh for Basic auth
	}
	for _, opt := range opts {
		opt(options)
	}

	// Build URL
	reqURL := h.baseURL + path
	if options.query != nil {
		reqURL += "?" + options.query.Encode()
	}

	// Build request body
	var bodyReader io.Reader
	if body != nil {
		bodyBytes, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		bodyReader = bytes.NewReader(bodyBytes)
	}

	// Create request
	req, err := http.NewRequestWithContext(ctx, method, reqURL, bodyReader)
	if err != nil {
		return nil, newNetworkError(fmt.Errorf("failed to create request: %w", err))
	}

	// Set headers
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	if options.includeAuth {
		req.SetBasicAuth(h.username, h.password)
	}

	// Make request
	resp, err := h.client.Do(req)
	if err != nil {
		return nil, newNetworkError(err)
	}
	defer resp.Body.Close()

	// Read response body
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, newNetworkError(fmt.Errorf("failed to read response body: %w", err))
	}

	// Handle errors
	if resp.StatusCode >= 400 {
		return nil, h.handleError(resp.StatusCode, respBody)
	}

	return respBody, nil
}

// Get makes a GET request with Basic authentication.
func (h *basicAuthHTTPClient) Get(ctx context.Context, path string, result interface{}, opts ...RequestOption) error {
	body, err := h.Request(ctx, "GET", path, nil, opts...)
	if err != nil {
		return err
	}
	if result != nil {
		return json.Unmarshal(body, result)
	}
	return nil
}

// Post makes a POST request with Basic authentication.
func (h *basicAuthHTTPClient) Post(ctx context.Context, path string, body, result interface{}, opts ...RequestOption) error {
	respBody, err := h.Request(ctx, "POST", path, body, opts...)
	if err != nil {
		return err
	}
	if result != nil {
		return json.Unmarshal(respBody, result)
	}
	return nil
}

// Patch makes a PATCH request with Basic authentication.
func (h *basicAuthHTTPClient) Patch(ctx context.Context, path string, body, result interface{}, opts ...RequestOption) error {
	respBody, err := h.Request(ctx, "PATCH", path, body, opts...)
	if err != nil {
		return err
	}
	if result != nil {
		return json.Unmarshal(respBody, result)
	}
	return nil
}
