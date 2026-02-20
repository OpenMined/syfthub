package transport

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func TestNewHTTPTransport(t *testing.T) {
	cfg := &Config{
		Host: "localhost",
		Port: 8080,
	}

	transport, err := NewHTTPTransport(cfg)
	if err != nil {
		t.Fatalf("NewHTTPTransport error: %v", err)
	}

	if transport == nil {
		t.Fatal("transport is nil")
	}
}

func TestHTTPTransportSetRequestHandler(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{Host: "localhost", Port: 8080})

	transport.SetRequestHandler(func(ctx context.Context, req *syfthubapi.TunnelRequest) (*syfthubapi.TunnelResponse, error) {
		return &syfthubapi.TunnelResponse{Status: "success"}, nil
	})

	if transport.handler == nil {
		t.Error("handler should be set")
	}
}

func TestHTTPTransportHandleHealth(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{Host: "localhost", Port: 8080})

	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()

	transport.handleHealth(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d", resp.StatusCode)
	}

	var body map[string]string
	json.NewDecoder(resp.Body).Decode(&body)
	if body["status"] != "healthy" {
		t.Errorf("status = %q", body["status"])
	}
}

func TestHTTPTransportHandleListEndpoints(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{Host: "localhost", Port: 8080})

	req := httptest.NewRequest("GET", "/api/v1/endpoints", nil)
	w := httptest.NewRecorder()

	transport.handleListEndpoints(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d", resp.StatusCode)
	}

	var body map[string]any
	json.NewDecoder(resp.Body).Decode(&body)
	if body["endpoints"] == nil {
		t.Error("endpoints should be present")
	}
}

func TestHTTPTransportExtractBearerToken(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{})

	tests := []struct {
		name     string
		auth     string
		expected string
	}{
		{"valid bearer", "Bearer token123", "token123"},
		{"lowercase bearer", "bearer token456", "token456"},
		{"no auth header", "", ""},
		{"invalid format", "Basic auth", ""},
		{"missing token", "Bearer", ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", "/", nil)
			if tt.auth != "" {
				req.Header.Set("Authorization", tt.auth)
			}

			got := transport.extractBearerToken(req)
			if got != tt.expected {
				t.Errorf("extractBearerToken() = %q, want %q", got, tt.expected)
			}
		})
	}
}

func TestHTTPTransportDetectEndpointType(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{})

	tests := []struct {
		name     string
		body     string
		expected syfthubapi.EndpointType
	}{
		{
			name:     "model with max_tokens",
			body:     `{"messages": [], "max_tokens": 1000}`,
			expected: syfthubapi.EndpointTypeModel,
		},
		{
			name:     "data source with similarity_threshold",
			body:     `{"messages": "query", "similarity_threshold": 0.8}`,
			expected: syfthubapi.EndpointTypeDataSource,
		},
		{
			name:     "ambiguous defaults to model",
			body:     `{"messages": []}`,
			expected: syfthubapi.EndpointTypeModel,
		},
		{
			name:     "invalid json defaults to model",
			body:     `invalid`,
			expected: syfthubapi.EndpointTypeModel,
		},
		{
			name:     "empty body defaults to model",
			body:     `{}`,
			expected: syfthubapi.EndpointTypeModel,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := transport.detectEndpointType([]byte(tt.body))
			if got != tt.expected {
				t.Errorf("detectEndpointType() = %q, want %q", got, tt.expected)
			}
		})
	}
}

func TestHTTPTransportErrorCodeToHTTPStatus(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{})

	tests := []struct {
		code     syfthubapi.TunnelErrorCode
		expected int
	}{
		{syfthubapi.TunnelErrorCodeAuthFailed, http.StatusUnauthorized},
		{syfthubapi.TunnelErrorCodeEndpointNotFound, http.StatusNotFound},
		{syfthubapi.TunnelErrorCodePolicyDenied, http.StatusForbidden},
		{syfthubapi.TunnelErrorCodeExecutionFailed, http.StatusInternalServerError},
		{syfthubapi.TunnelErrorCodeTimeout, http.StatusGatewayTimeout},
		{syfthubapi.TunnelErrorCodeInvalidRequest, http.StatusBadRequest},
		{syfthubapi.TunnelErrorCodeEndpointDisabled, http.StatusServiceUnavailable},
		{syfthubapi.TunnelErrorCodeRateLimitExceeded, http.StatusTooManyRequests},
		{syfthubapi.TunnelErrorCodeInternalError, http.StatusInternalServerError},
		{"UNKNOWN", http.StatusInternalServerError},
	}

	for _, tt := range tests {
		t.Run(string(tt.code), func(t *testing.T) {
			got := transport.errorCodeToHTTPStatus(tt.code)
			if got != tt.expected {
				t.Errorf("errorCodeToHTTPStatus(%q) = %d, want %d", tt.code, got, tt.expected)
			}
		})
	}
}

func TestHTTPTransportWriteError(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{})

	w := httptest.NewRecorder()
	transport.writeError(w, http.StatusBadRequest, "test error")

	resp := w.Result()
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("status = %d", resp.StatusCode)
	}

	var body map[string]string
	json.NewDecoder(resp.Body).Decode(&body)
	if body["error"] != "test error" {
		t.Errorf("error = %q", body["error"])
	}
}

func TestHTTPTransportWriteResponse(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{})

	t.Run("success response", func(t *testing.T) {
		w := httptest.NewRecorder()
		resp := &syfthubapi.TunnelResponse{
			Status:  "success",
			Payload: json.RawMessage(`{"result": "data"}`),
		}

		transport.writeResponse(w, resp)

		result := w.Result()
		if result.StatusCode != http.StatusOK {
			t.Errorf("status = %d", result.StatusCode)
		}

		body, _ := io.ReadAll(result.Body)
		if string(body) != `{"result": "data"}` {
			t.Errorf("body = %q", string(body))
		}
	})

	t.Run("error response", func(t *testing.T) {
		w := httptest.NewRecorder()
		resp := &syfthubapi.TunnelResponse{
			Status: "error",
			Error: &syfthubapi.TunnelError{
				Code:    syfthubapi.TunnelErrorCodeAuthFailed,
				Message: "auth failed",
				Details: map[string]any{"reason": "expired"},
			},
		}

		transport.writeResponse(w, resp)

		result := w.Result()
		if result.StatusCode != http.StatusUnauthorized {
			t.Errorf("status = %d", result.StatusCode)
		}
	})
}

func TestHTTPTransportHandleQueryNoSlug(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{})

	req := httptest.NewRequest("POST", "/api/v1/endpoints//query", bytes.NewReader([]byte(`{}`)))
	w := httptest.NewRecorder()

	transport.handleQuery(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("status = %d, want %d", resp.StatusCode, http.StatusBadRequest)
	}
}

func TestHTTPTransportHandleQueryNoHandler(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{})
	// Don't set handler

	req := httptest.NewRequest("POST", "/api/v1/endpoints/test/query", bytes.NewReader([]byte(`{}`)))
	req.SetPathValue("slug", "test")
	w := httptest.NewRecorder()

	transport.handleQuery(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusInternalServerError {
		t.Errorf("status = %d", resp.StatusCode)
	}
}

func TestHTTPTransportHandleQuerySuccess(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{})

	transport.SetRequestHandler(func(ctx context.Context, req *syfthubapi.TunnelRequest) (*syfthubapi.TunnelResponse, error) {
		if req.Endpoint.Slug != "test-ep" {
			t.Errorf("slug = %q", req.Endpoint.Slug)
		}
		return &syfthubapi.TunnelResponse{
			Status:  "success",
			Payload: json.RawMessage(`{"result": "ok"}`),
		}, nil
	})

	body := `{"messages": [{"role": "user", "content": "hi"}]}`
	req := httptest.NewRequest("POST", "/api/v1/endpoints/test-ep/query", bytes.NewReader([]byte(body)))
	req.Header.Set("Authorization", "Bearer test-token")
	req.SetPathValue("slug", "test-ep")
	w := httptest.NewRecorder()

	transport.handleQuery(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d", resp.StatusCode)
	}
}

func TestHTTPTransportStop(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{Host: "localhost", Port: 0})

	// Stop without server should not error
	err := transport.Stop(context.Background())
	if err != nil {
		t.Errorf("Stop error: %v", err)
	}
}

func TestHTTPTransportStartStop(t *testing.T) {
	transport, _ := NewHTTPTransport(&Config{Host: "127.0.0.1", Port: 0})

	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan error, 1)
	go func() {
		done <- transport.Start(ctx)
	}()

	// Give server time to start
	time.Sleep(50 * time.Millisecond)

	// Cancel context to stop
	cancel()

	select {
	case err := <-done:
		// Expected nil or context cancelled
		if err != nil && err != context.Canceled {
			t.Errorf("unexpected error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for Start to return")
	}

	// Stop should work
	err := transport.Stop(context.Background())
	if err != nil {
		t.Errorf("Stop error: %v", err)
	}
}

// Transport interface tests

func TestTransportInterface(t *testing.T) {
	// Verify HTTPTransport implements Transport interface
	var _ Transport = (*HTTPTransport)(nil)
}

// Transport package functions

func TestIsTunnelMode(t *testing.T) {
	tests := []struct {
		url      string
		expected bool
	}{
		{"tunneling:user", true},
		{"tunneling:", true},
		{"https://space.example.com", false},
		{"http://localhost", false},
		{"", false},
	}

	for _, tt := range tests {
		t.Run(tt.url, func(t *testing.T) {
			got := IsTunnelMode(tt.url)
			if got != tt.expected {
				t.Errorf("IsTunnelMode(%q) = %v, want %v", tt.url, got, tt.expected)
			}
		})
	}
}

func TestGetTunnelUsername(t *testing.T) {
	tests := []struct {
		url      string
		expected string
	}{
		{"tunneling:testuser", "testuser"},
		{"tunneling:", ""},
		{"https://space.example.com", ""},
		{"", ""},
	}

	for _, tt := range tests {
		t.Run(tt.url, func(t *testing.T) {
			got := GetTunnelUsername(tt.url)
			if got != tt.expected {
				t.Errorf("GetTunnelUsername(%q) = %q, want %q", tt.url, got, tt.expected)
			}
		})
	}
}

func TestNew(t *testing.T) {
	t.Run("creates HTTP transport for non-tunnel", func(t *testing.T) {
		cfg := &Config{
			SpaceURL: "https://space.example.com",
			Host:     "localhost",
			Port:     8080,
		}

		transport, err := New(cfg)
		if err != nil {
			t.Fatalf("New error: %v", err)
		}

		// Should be HTTPTransport
		_, ok := transport.(*HTTPTransport)
		if !ok {
			t.Error("expected HTTPTransport for non-tunnel URL")
		}
	})
}

// Benchmark tests

func BenchmarkExtractBearerToken(b *testing.B) {
	transport, _ := NewHTTPTransport(&Config{})
	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer test-token-12345")

	for i := 0; i < b.N; i++ {
		transport.extractBearerToken(req)
	}
}

func BenchmarkDetectEndpointType(b *testing.B) {
	transport, _ := NewHTTPTransport(&Config{})
	body := []byte(`{"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1000}`)

	for i := 0; i < b.N; i++ {
		transport.detectEndpointType(body)
	}
}

func TestNewHTTPTransportWithLogger(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	cfg := &Config{
		Host:   "localhost",
		Port:   8080,
		Logger: &syfthubapi.SlogLogger{Logger: logger},
	}

	transport, err := NewHTTPTransport(cfg)
	if err != nil {
		t.Fatalf("NewHTTPTransport error: %v", err)
	}

	if transport == nil {
		t.Fatal("transport is nil")
	}
}
