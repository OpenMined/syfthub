package cmd

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"testing"
	"time"
)

func TestGenerateState(t *testing.T) {
	state, err := generateState()
	if err != nil {
		t.Fatalf("generateState() error: %v", err)
	}

	// Should be 32 hex characters (16 bytes encoded as hex)
	if len(state) != 32 {
		t.Errorf("state length = %d, want 32", len(state))
	}

	// Should be valid hex
	for _, c := range state {
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
			t.Errorf("state contains non-hex character: %c", c)
			break
		}
	}

	// Two calls should produce different states
	state2, err := generateState()
	if err != nil {
		t.Fatalf("second generateState() error: %v", err)
	}
	if state == state2 {
		t.Error("two generateState() calls produced identical values")
	}
}

func TestSendResult_NonBlocking(t *testing.T) {
	ch := make(chan browserAuthResult, 1)

	// First send should succeed
	sendResult(ch, browserAuthResult{token: "first"})

	// Second send should not block (dropped because channel is full)
	done := make(chan struct{})
	go func() {
		sendResult(ch, browserAuthResult{token: "second"})
		close(done)
	}()

	select {
	case <-done:
		// Good, didn't block
	case <-time.After(1 * time.Second):
		t.Fatal("sendResult blocked on full channel")
	}

	// Verify first result is still in the channel
	result := <-ch
	if result.token != "first" {
		t.Errorf("token = %q, want %q", result.token, "first")
	}
}

func TestSendResult_Error(t *testing.T) {
	ch := make(chan browserAuthResult, 1)
	sendResult(ch, browserAuthResult{err: fmt.Errorf("test error")})

	result := <-ch
	if result.err == nil {
		t.Fatal("expected error, got nil")
	}
	if result.err.Error() != "test error" {
		t.Errorf("error = %q, want %q", result.err.Error(), "test error")
	}
}

func TestStartBrowserAuthFlow_ReceivesToken(t *testing.T) {
	ctx := context.Background()

	resultCh := make(chan struct {
		token string
		err   error
	}, 1)

	var setupURL string
	ready := make(chan struct{})

	go func() {
		tok, flowErr := startBrowserAuthFlow(ctx, "https://hub.example.com", func(url string) {
			setupURL = url
			close(ready)
		})
		resultCh <- struct {
			token string
			err   error
		}{tok, flowErr}
	}()

	// Wait for server to be ready
	select {
	case <-ready:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for server to start")
	}

	// Extract port and state from setupURL
	// Format: https://hub.example.com/cli-setup?port=PORT&state=STATE
	parts := strings.Split(setupURL, "?")
	if len(parts) != 2 {
		t.Fatalf("unexpected setupURL format: %s", setupURL)
	}

	params := strings.Split(parts[1], "&")
	var port, state string
	for _, p := range params {
		kv := strings.SplitN(p, "=", 2)
		if len(kv) == 2 {
			switch kv[0] {
			case "port":
				port = kv[1]
			case "state":
				state = kv[1]
			}
		}
	}

	if port == "" || state == "" {
		t.Fatalf("could not extract port/state from URL: %s", setupURL)
	}

	// Simulate browser callback
	callbackResp, httpErr := http.Get(fmt.Sprintf("http://127.0.0.1:%s/cli/done?state=%s&token=mytoken123", port, state))
	if httpErr != nil {
		t.Fatalf("callback request failed: %v", httpErr)
	}
	callbackResp.Body.Close()

	if callbackResp.StatusCode != http.StatusOK {
		t.Errorf("callback status = %d, want 200", callbackResp.StatusCode)
	}

	// Verify token was received
	select {
	case result := <-resultCh:
		if result.err != nil {
			t.Fatalf("startBrowserAuthFlow error: %v", result.err)
		}
		if result.token != "mytoken123" {
			t.Errorf("token = %q, want %q", result.token, "mytoken123")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for flow result")
	}
}

func TestStartBrowserAuthFlow_StateMismatch(t *testing.T) {
	ctx := context.Background()

	resultCh := make(chan struct {
		token string
		err   error
	}, 1)

	var setupURL string
	ready := make(chan struct{})

	go func() {
		tok, flowErr := startBrowserAuthFlow(ctx, "https://hub.example.com", func(url string) {
			setupURL = url
			close(ready)
		})
		resultCh <- struct {
			token string
			err   error
		}{tok, flowErr}
	}()

	select {
	case <-ready:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for server to start")
	}

	// Extract port from URL
	port := extractParam(t, setupURL, "port")

	// Send callback with wrong state
	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%s/cli/done?state=wrongstate&token=mytoken", port))
	if err != nil {
		t.Fatalf("callback request failed: %v", err)
	}
	resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400 for state mismatch, got %d", resp.StatusCode)
	}

	// The flow should return an error
	select {
	case result := <-resultCh:
		if result.err == nil {
			t.Fatal("expected error for state mismatch, got nil")
		}
		if !strings.Contains(result.err.Error(), "state mismatch") {
			t.Errorf("error = %q, expected to contain 'state mismatch'", result.err.Error())
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for flow result")
	}
}

func TestStartBrowserAuthFlow_MissingToken(t *testing.T) {
	ctx := context.Background()

	resultCh := make(chan struct {
		token string
		err   error
	}, 1)

	var setupURL string
	ready := make(chan struct{})

	go func() {
		tok, flowErr := startBrowserAuthFlow(ctx, "https://hub.example.com", func(url string) {
			setupURL = url
			close(ready)
		})
		resultCh <- struct {
			token string
			err   error
		}{tok, flowErr}
	}()

	select {
	case <-ready:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for server to start")
	}

	port := extractParam(t, setupURL, "port")
	state := extractParam(t, setupURL, "state")

	// Send callback with correct state but empty token
	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%s/cli/done?state=%s&token=", port, state))
	if err != nil {
		t.Fatalf("callback request failed: %v", err)
	}
	resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400 for missing token, got %d", resp.StatusCode)
	}

	select {
	case result := <-resultCh:
		if result.err == nil {
			t.Fatal("expected error for missing token, got nil")
		}
		if !strings.Contains(result.err.Error(), "empty token") {
			t.Errorf("error = %q, expected to contain 'empty token'", result.err.Error())
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for flow result")
	}
}

func TestStartBrowserAuthFlow_ContextCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())

	resultCh := make(chan struct {
		token string
		err   error
	}, 1)

	ready := make(chan struct{})

	go func() {
		tok, flowErr := startBrowserAuthFlow(ctx, "https://hub.example.com", func(_ string) {
			close(ready)
		})
		resultCh <- struct {
			token string
			err   error
		}{tok, flowErr}
	}()

	select {
	case <-ready:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for server to start")
	}

	// Cancel the context
	cancel()

	select {
	case result := <-resultCh:
		if result.err == nil {
			t.Fatal("expected context cancellation error, got nil")
		}
		if result.err != context.Canceled {
			t.Errorf("error = %v, want context.Canceled", result.err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for cancellation")
	}
}

func TestStartBrowserAuthFlow_Timeout(t *testing.T) {
	// Use a context with a very short deadline to simulate timeout.
	// Note: the actual auth timeout is 5 minutes, but context cancellation
	// is checked first, so we use context timeout instead.
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	resultCh := make(chan struct {
		token string
		err   error
	}, 1)

	ready := make(chan struct{})

	go func() {
		tok, flowErr := startBrowserAuthFlow(ctx, "https://hub.example.com", func(_ string) {
			close(ready)
		})
		resultCh <- struct {
			token string
			err   error
		}{tok, flowErr}
	}()

	select {
	case <-ready:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for server to start")
	}

	// Don't hit the callback — let context timeout expire
	select {
	case result := <-resultCh:
		if result.err == nil {
			t.Fatal("expected timeout error, got nil")
		}
		// Could be context.DeadlineExceeded
		if result.err != context.DeadlineExceeded {
			t.Errorf("error = %v, want context.DeadlineExceeded", result.err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for flow timeout")
	}
}

func TestStartBrowserAuthFlow_MethodNotAllowed(t *testing.T) {
	ctx := context.Background()

	var setupURL string
	ready := make(chan struct{})

	// Start in background — we'll cancel via context later
	cancelCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	go func() {
		startBrowserAuthFlow(cancelCtx, "https://hub.example.com", func(url string) {
			setupURL = url
			close(ready)
		})
	}()

	select {
	case <-ready:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for server to start")
	}

	port := extractParam(t, setupURL, "port")

	// POST should be rejected
	resp, err := http.Post(fmt.Sprintf("http://127.0.0.1:%s/cli/done", port), "text/plain", nil)
	if err != nil {
		t.Fatalf("POST request failed: %v", err)
	}
	resp.Body.Close()

	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("expected 405 for POST, got %d", resp.StatusCode)
	}

	cancel()
}

// extractParam extracts a query parameter from a URL string.
func extractParam(t *testing.T, rawURL, key string) string {
	t.Helper()
	parts := strings.Split(rawURL, "?")
	if len(parts) != 2 {
		t.Fatalf("unexpected URL format: %s", rawURL)
	}
	for _, p := range strings.Split(parts[1], "&") {
		kv := strings.SplitN(p, "=", 2)
		if len(kv) == 2 && kv[0] == key {
			return kv[1]
		}
	}
	t.Fatalf("parameter %q not found in URL: %s", key, rawURL)
	return ""
}
