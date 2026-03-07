package handlers

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

// HTTPHandler handles type=http steps.
// Makes safe, constrained HTTP requests for API validation,
// data fetching, and webhook registration.
type HTTPHandler struct {
	client *http.Client
}

// NewHTTPHandler creates an HTTPHandler with a shared HTTP client.
func NewHTTPHandler() *HTTPHandler {
	return &HTTPHandler{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

var allowedMethods = map[string]bool{
	"GET":    true,
	"POST":   true,
	"PUT":    true,
	"DELETE": true,
}

func (h *HTTPHandler) Validate(step *nodeops.SetupStep) error {
	if step.HTTP == nil {
		return fmt.Errorf("http config is required for type 'http'")
	}
	if step.HTTP.Method == "" {
		return fmt.Errorf("http.method is required")
	}
	if !allowedMethods[strings.ToUpper(step.HTTP.Method)] {
		return fmt.Errorf("http.method must be GET, POST, PUT, or DELETE (got '%s')", step.HTTP.Method)
	}
	if step.HTTP.URL == "" {
		return fmt.Errorf("http.url is required")
	}
	return nil
}

func (h *HTTPHandler) Execute(step *nodeops.SetupStep, ctx *setupflow.SetupContext) (*setupflow.StepResult, error) {
	cfg := step.HTTP

	// Determine timeout
	timeout := 30 * time.Second
	if cfg.TimeoutSecs > 0 {
		if cfg.TimeoutSecs > 120 {
			cfg.TimeoutSecs = 120 // Max 120s
		}
		timeout = time.Duration(cfg.TimeoutSecs) * time.Second
	}

	// Build request URL with query params
	reqURL := cfg.URL
	if len(cfg.Query) > 0 {
		u, err := url.Parse(reqURL)
		if err != nil {
			return nil, fmt.Errorf("invalid URL: %w", err)
		}
		q := u.Query()
		for k, v := range cfg.Query {
			q.Set(k, v)
		}
		u.RawQuery = q.Encode()
		reqURL = u.String()
	}

	// Build body
	var bodyReader io.Reader
	if cfg.JSON != nil {
		jsonBytes, err := json.Marshal(cfg.JSON)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal JSON body: %w", err)
		}
		bodyReader = strings.NewReader(string(jsonBytes))
	} else if cfg.Body != "" {
		bodyReader = strings.NewReader(cfg.Body)
	}

	// Create request
	req, err := http.NewRequest(strings.ToUpper(cfg.Method), reqURL, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	// Set headers
	if cfg.JSON != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	for k, v := range cfg.Headers {
		req.Header.Set(k, v)
	}

	// Execute with timeout
	client := &http.Client{Timeout: timeout}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("HTTP request failed: %w", err)
	}
	defer resp.Body.Close()

	// Read response body (up to 1MB)
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	// Check status
	if cfg.ExpectStatus > 0 {
		if resp.StatusCode != cfg.ExpectStatus {
			return nil, fmt.Errorf("expected status %d, got %d: %s", cfg.ExpectStatus, resp.StatusCode, string(body))
		}
	} else {
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
		}
	}

	// Build result
	result := &setupflow.StepResult{
		Value: string(body),
		Metadata: map[string]string{
			"status_code": strconv.Itoa(resp.StatusCode),
		},
	}

	// Try to parse as JSON
	if json.Valid(body) {
		result.Response = json.RawMessage(body)
	}

	return result, nil
}
