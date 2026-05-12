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

// MaxJSONBodyBytes is the maximum number of bytes read from a JSON HTTP
// response body. Bodies larger than this are truncated.
const MaxJSONBodyBytes = 1 << 20

// DefaultHTTPTimeout is the default timeout for HTTP clients used by JSON
// helpers in this SDK.
const DefaultHTTPTimeout = 30 * time.Second

// HubAPIError represents an HTTP-level error from the SyftHub backend or any
// other JSON endpoint invoked via DoJSONRequest. It is returned whenever the
// response status code is >= 300.
type HubAPIError struct {
	StatusCode int
	Body       string
}

func (e *HubAPIError) Error() string {
	return fmt.Sprintf("hub API error (status %d): %s", e.StatusCode, e.Body)
}

// DoJSONRequest performs an HTTP request with a JSON body and decodes a JSON
// response. It is the canonical JSON-HTTP helper for this SDK.
//
// Behavior:
//   - If reqBody is non-nil, it is JSON-marshaled and used as the request
//     body, and Content-Type is set to application/json.
//   - Each header from headers is added (via Header.Add) to the request.
//   - The response body is read up to MaxJSONBodyBytes.
//   - If the response status is >= 300, a *HubAPIError is returned containing
//     the status code and the (possibly truncated) body.
//   - If respBody is non-nil and the request succeeded, the body is
//     JSON-unmarshaled into it.
//
// If client is nil, http.DefaultClient is used.
func DoJSONRequest(ctx context.Context, client *http.Client, method, url string, headers http.Header, reqBody, respBody any) error {
	var body io.Reader
	if reqBody != nil {
		data, err := json.Marshal(reqBody)
		if err != nil {
			return fmt.Errorf("marshal request: %w", err)
		}
		body = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}

	if reqBody != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	for k, vs := range headers {
		for _, v := range vs {
			req.Header.Add(k, v)
		}
	}

	if client == nil {
		client = http.DefaultClient
	}

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, MaxJSONBodyBytes))
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
