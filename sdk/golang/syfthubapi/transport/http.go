package transport

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// HTTPTransport implements Transport for direct HTTP mode.
type HTTPTransport struct {
	server  *http.Server
	handler RequestHandler
	config  *Config
	logger  *slog.Logger
}

// NewHTTPTransport creates a new HTTP transport.
func NewHTTPTransport(cfg *Config) (*HTTPTransport, error) {
	logger := slog.Default()
	if cfg.Logger != nil {
		if l, ok := cfg.Logger.(*slog.Logger); ok {
			logger = l
		}
	}

	return &HTTPTransport{
		config: cfg,
		logger: logger,
	}, nil
}

// Start begins the HTTP server.
func (t *HTTPTransport) Start(ctx context.Context) error {
	mux := http.NewServeMux()

	// Health check endpoint
	mux.HandleFunc("GET /health", t.handleHealth)

	// API v1 endpoints
	mux.HandleFunc("POST /api/v1/endpoints/{slug}/query", t.handleQuery)

	// List endpoints
	mux.HandleFunc("GET /api/v1/endpoints", t.handleListEndpoints)

	addr := fmt.Sprintf("%s:%d", t.config.Host, t.config.Port)
	t.server = &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 120 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	t.logger.Info("starting HTTP server", "addr", addr)

	// Start server in goroutine
	errCh := make(chan error, 1)
	go func() {
		if err := t.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errCh <- err
		}
		close(errCh)
	}()

	// Wait for context cancellation or error
	select {
	case <-ctx.Done():
		return nil
	case err := <-errCh:
		return &syfthubapi.TransportError{
			Transport: "http",
			Message:   "server error",
			Cause:     err,
		}
	}
}

// Stop gracefully shuts down the HTTP server.
func (t *HTTPTransport) Stop(ctx context.Context) error {
	if t.server == nil {
		return nil
	}

	t.logger.Info("stopping HTTP server")
	return t.server.Shutdown(ctx)
}

// SetRequestHandler sets the request handler.
func (t *HTTPTransport) SetRequestHandler(handler RequestHandler) {
	t.handler = handler
}

// handleHealth handles health check requests.
func (t *HTTPTransport) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
}

// handleQuery handles endpoint query requests.
func (t *HTTPTransport) handleQuery(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	if slug == "" {
		t.writeError(w, http.StatusBadRequest, "missing endpoint slug")
		return
	}

	// Extract bearer token
	token := t.extractBearerToken(r)

	// Read request body
	body, err := io.ReadAll(r.Body)
	if err != nil {
		t.writeError(w, http.StatusBadRequest, "failed to read request body")
		return
	}
	defer r.Body.Close()

	// Determine endpoint type from request body
	endpointType := t.detectEndpointType(body)

	// Build tunnel request (matching Python syfthub-api format)
	tunnelReq := &syfthubapi.TunnelRequest{
		Protocol:      "syfthub-tunnel/v1",
		Type:          "endpoint_request",
		CorrelationID: fmt.Sprintf("%d", time.Now().UnixNano()),
		Endpoint: syfthubapi.TunnelEndpointInfo{
			Slug: slug,
			Type: string(endpointType),
		},
		Payload:        body,
		SatelliteToken: token,
		TimeoutMs:      30000,
	}

	// Call handler
	if t.handler == nil {
		t.writeError(w, http.StatusInternalServerError, "no handler configured")
		return
	}

	resp, err := t.handler(r.Context(), tunnelReq)
	if err != nil {
		t.logger.Error("handler error", "error", err)
		t.writeError(w, http.StatusInternalServerError, "internal server error")
		return
	}

	// Write response
	t.writeResponse(w, resp)
}

// handleListEndpoints handles listing available endpoints.
func (t *HTTPTransport) handleListEndpoints(w http.ResponseWriter, r *http.Request) {
	// This would typically query the registry, but we don't have direct access here
	// Return empty list for now - actual implementation would need registry access
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]any{"endpoints": []any{}})
}

// extractBearerToken extracts the bearer token from the Authorization header.
func (t *HTTPTransport) extractBearerToken(r *http.Request) string {
	auth := r.Header.Get("Authorization")
	if auth == "" {
		return ""
	}

	parts := strings.SplitN(auth, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
		return ""
	}

	return parts[1]
}

// detectEndpointType tries to detect the endpoint type from the request body.
func (t *HTTPTransport) detectEndpointType(body []byte) syfthubapi.EndpointType {
	// Try to parse and detect type based on fields present
	var req map[string]any
	if err := json.Unmarshal(body, &req); err != nil {
		return syfthubapi.EndpointTypeModel // Default to model
	}

	// If messages is present with role/content structure, likely model
	// If query or similarity_threshold, likely data_source
	if _, hasMessages := req["messages"]; hasMessages {
		// Could be either - need to check endpoint registry
		// For now, check for model-specific fields
		if _, hasMaxTokens := req["max_tokens"]; hasMaxTokens {
			return syfthubapi.EndpointTypeModel
		}
		if _, hasThreshold := req["similarity_threshold"]; hasThreshold {
			return syfthubapi.EndpointTypeDataSource
		}
	}

	// Default to model
	return syfthubapi.EndpointTypeModel
}

// writeError writes an error response.
func (t *HTTPTransport) writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]string{"error": message})
}

// writeResponse writes a tunnel response as HTTP response.
func (t *HTTPTransport) writeResponse(w http.ResponseWriter, resp *syfthubapi.TunnelResponse) {
	w.Header().Set("Content-Type", "application/json")

	if resp.Status == "error" && resp.Error != nil {
		status := t.errorCodeToHTTPStatus(resp.Error.Code)
		w.WriteHeader(status)
		json.NewEncoder(w).Encode(map[string]any{
			"error":   resp.Error.Message,
			"code":    resp.Error.Code,
			"details": resp.Error.Details,
		})
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write(resp.Payload)
}

// errorCodeToHTTPStatus maps tunnel error codes to HTTP status codes.
func (t *HTTPTransport) errorCodeToHTTPStatus(code syfthubapi.TunnelErrorCode) int {
	switch code {
	case syfthubapi.TunnelErrorCodeAuthFailed:
		return http.StatusUnauthorized
	case syfthubapi.TunnelErrorCodeEndpointNotFound:
		return http.StatusNotFound
	case syfthubapi.TunnelErrorCodePolicyDenied:
		return http.StatusForbidden
	case syfthubapi.TunnelErrorCodeExecutionFailed:
		return http.StatusInternalServerError
	case syfthubapi.TunnelErrorCodeTimeout:
		return http.StatusGatewayTimeout
	case syfthubapi.TunnelErrorCodeInvalidRequest:
		return http.StatusBadRequest
	case syfthubapi.TunnelErrorCodeEndpointDisabled:
		return http.StatusServiceUnavailable
	case syfthubapi.TunnelErrorCodeRateLimitExceeded:
		return http.StatusTooManyRequests
	default:
		return http.StatusInternalServerError
	}
}

// Ensure HTTPTransport implements Transport.
var _ Transport = (*HTTPTransport)(nil)
