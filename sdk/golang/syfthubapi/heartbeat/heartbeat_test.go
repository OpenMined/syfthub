package heartbeat

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestNewManager(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	cfg := &Config{
		BaseURL:            "https://hub.example.com",
		APIKey:             "test-key",
		SpaceURL:           "https://space.example.com",
		TTLSeconds:         300,
		IntervalMultiplier: 0.8,
		Logger:             logger,
		MaxRetries:         5,
		BaseRetryDelay:     10 * time.Second,
	}

	manager := NewManager(cfg)

	if manager == nil {
		t.Fatal("manager is nil")
	}
	if manager.baseURL != "https://hub.example.com" {
		t.Errorf("baseURL = %q", manager.baseURL)
	}
	if manager.apiKey != "test-key" {
		t.Errorf("apiKey = %q", manager.apiKey)
	}
	if manager.spaceURL != "https://space.example.com" {
		t.Errorf("spaceURL = %q", manager.spaceURL)
	}
	if manager.ttl != 300*time.Second {
		t.Errorf("ttl = %v", manager.ttl)
	}
	if manager.interval != 240*time.Second { // 300 * 0.8
		t.Errorf("interval = %v", manager.interval)
	}
	if manager.maxRetries != 5 {
		t.Errorf("maxRetries = %d", manager.maxRetries)
	}
}

func TestNewManagerDefaults(t *testing.T) {
	cfg := &Config{
		BaseURL:            "https://hub.example.com",
		APIKey:             "test-key",
		SpaceURL:           "https://space.example.com",
		TTLSeconds:         100,
		IntervalMultiplier: 0.5,
		// No logger, max retries, or retry delay set
	}

	manager := NewManager(cfg)

	if manager.maxRetries != 3 {
		t.Errorf("default maxRetries = %d, want 3", manager.maxRetries)
	}
	if manager.baseRetryDelay != 5*time.Second {
		t.Errorf("default baseRetryDelay = %v, want 5s", manager.baseRetryDelay)
	}
}

func TestManagerIsRunning(t *testing.T) {
	cfg := &Config{
		BaseURL:            "http://localhost",
		APIKey:             "key",
		SpaceURL:           "http://space",
		TTLSeconds:         60,
		IntervalMultiplier: 0.8,
	}

	manager := NewManager(cfg)

	if manager.IsRunning() {
		t.Error("should not be running initially")
	}
}

func TestManagerStartStop(t *testing.T) {
	heartbeatCount := int32(0)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&heartbeatCount, 1)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(HeartbeatResponse{
			Status:     "ok",
			TTLSeconds: 60,
			Domain:     "test.example.com",
		})
	}))
	defer server.Close()

	cfg := &Config{
		BaseURL:            server.URL,
		APIKey:             "test-key",
		SpaceURL:           "https://space.example.com",
		TTLSeconds:         60,
		IntervalMultiplier: 0.8,
	}

	manager := NewManager(cfg)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start in goroutine
	done := make(chan error, 1)
	go func() {
		done <- manager.Start(ctx)
	}()

	// Wait for initial heartbeat
	time.Sleep(100 * time.Millisecond)

	if !manager.IsRunning() {
		t.Error("should be running after Start")
	}

	// Stop using Stop method to properly reset running flag
	stopCtx, stopCancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer stopCancel()

	if err := manager.Stop(stopCtx); err != nil {
		t.Errorf("Stop error: %v", err)
	}

	// Wait for stop
	select {
	case <-done:
		// Expected
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for manager to stop")
	}

	if manager.IsRunning() {
		t.Error("should not be running after Stop")
	}

	// At least one heartbeat should have been sent
	if atomic.LoadInt32(&heartbeatCount) < 1 {
		t.Error("at least one heartbeat should have been sent")
	}
}

func TestManagerStopMethod(t *testing.T) {
	// Use a real test server to avoid connection issues
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(HeartbeatResponse{
			Status:     "ok",
			TTLSeconds: 60,
		})
	}))
	defer server.Close()

	cfg := &Config{
		BaseURL:            server.URL,
		APIKey:             "test-key",
		SpaceURL:           "https://space.example.com",
		TTLSeconds:         60,
		IntervalMultiplier: 0.8,
	}

	manager := NewManager(cfg)

	ctx := context.Background()

	// Start in goroutine
	done := make(chan error, 1)
	go func() {
		done <- manager.Start(ctx)
	}()

	// Wait for initial heartbeat to complete
	time.Sleep(200 * time.Millisecond)

	// Stop using Stop method
	stopCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err := manager.Stop(stopCtx)
	if err != nil {
		t.Errorf("Stop error: %v", err)
	}

	// Wait for goroutine
	select {
	case <-done:
		// Expected
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for manager goroutine")
	}
}

func TestManagerStopWhenNotRunning(t *testing.T) {
	cfg := &Config{
		BaseURL:            "http://localhost",
		APIKey:             "key",
		SpaceURL:           "http://space",
		TTLSeconds:         60,
		IntervalMultiplier: 0.8,
	}

	manager := NewManager(cfg)

	// Stop without starting should not error
	err := manager.Stop(context.Background())
	if err != nil {
		t.Errorf("Stop when not running should not error: %v", err)
	}
}

func TestManagerDoubleStart(t *testing.T) {
	cfg := &Config{
		BaseURL:            "http://localhost:9999",
		APIKey:             "key",
		SpaceURL:           "http://space",
		TTLSeconds:         60,
		IntervalMultiplier: 0.8,
	}

	manager := NewManager(cfg)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// First start
	go manager.Start(ctx)
	time.Sleep(50 * time.Millisecond)

	// Second start should error
	err := manager.Start(ctx)
	if err == nil {
		t.Error("double start should error")
	}
}

func TestManagerSendHeartbeat(t *testing.T) {
	t.Run("successful heartbeat", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/me/heartbeat" {
				t.Errorf("unexpected path: %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("unexpected method: %s", r.Method)
			}
			if r.Header.Get("Authorization") != "Bearer test-key" {
				t.Errorf("unexpected auth: %s", r.Header.Get("Authorization"))
			}

			var req HeartbeatRequest
			json.NewDecoder(r.Body).Decode(&req)
			if req.URL != "https://space.example.com" {
				t.Errorf("request URL = %q", req.URL)
			}

			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(HeartbeatResponse{
				Status:     "ok",
				TTLSeconds: 300,
				Domain:     "space.example.com",
			})
		}))
		defer server.Close()

		cfg := &Config{
			BaseURL:            server.URL,
			APIKey:             "test-key",
			SpaceURL:           "https://space.example.com",
			TTLSeconds:         300,
			IntervalMultiplier: 0.8,
		}

		manager := NewManager(cfg)
		resp, err := manager.sendHeartbeat(context.Background())
		if err != nil {
			t.Fatalf("sendHeartbeat error: %v", err)
		}

		if resp.TTLSeconds != 300 {
			t.Errorf("TTLSeconds = %d", resp.TTLSeconds)
		}
	})

	t.Run("server error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte("server error"))
		}))
		defer server.Close()

		cfg := &Config{
			BaseURL:            server.URL,
			APIKey:             "test-key",
			SpaceURL:           "https://space.example.com",
			TTLSeconds:         300,
			IntervalMultiplier: 0.8,
		}

		manager := NewManager(cfg)
		_, err := manager.sendHeartbeat(context.Background())
		if err == nil {
			t.Error("expected error for server error")
		}
	})
}

func TestManagerSendHeartbeatWithRetry(t *testing.T) {
	t.Run("succeeds on retry", func(t *testing.T) {
		attempts := int32(0)

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			count := atomic.AddInt32(&attempts, 1)
			if count < 2 {
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(HeartbeatResponse{Status: "ok", TTLSeconds: 60})
		}))
		defer server.Close()

		cfg := &Config{
			BaseURL:            server.URL,
			APIKey:             "test-key",
			SpaceURL:           "https://space.example.com",
			TTLSeconds:         60,
			IntervalMultiplier: 0.8,
			MaxRetries:         3,
			BaseRetryDelay:     10 * time.Millisecond, // Fast for testing
		}

		manager := NewManager(cfg)
		err := manager.sendHeartbeatWithRetry(context.Background())
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}

		if atomic.LoadInt32(&attempts) < 2 {
			t.Error("should have retried")
		}
	})

	t.Run("fails after max retries", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		cfg := &Config{
			BaseURL:            server.URL,
			APIKey:             "test-key",
			SpaceURL:           "https://space.example.com",
			TTLSeconds:         60,
			IntervalMultiplier: 0.8,
			MaxRetries:         2,
			BaseRetryDelay:     10 * time.Millisecond,
		}

		manager := NewManager(cfg)
		err := manager.sendHeartbeatWithRetry(context.Background())
		if err == nil {
			t.Error("expected error after max retries")
		}
	})

	t.Run("respects context cancellation", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		cfg := &Config{
			BaseURL:            server.URL,
			APIKey:             "test-key",
			SpaceURL:           "https://space.example.com",
			TTLSeconds:         60,
			IntervalMultiplier: 0.8,
			MaxRetries:         10,
			BaseRetryDelay:     1 * time.Second,
		}

		manager := NewManager(cfg)

		ctx, cancel := context.WithCancel(context.Background())
		cancel() // Cancel immediately

		err := manager.sendHeartbeatWithRetry(ctx)
		if err == nil {
			t.Error("expected error for cancelled context")
		}
	})
}

func TestHeartbeatRequestJSON(t *testing.T) {
	req := HeartbeatRequest{
		URL:        "https://space.example.com",
		TTLSeconds: 300,
	}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded HeartbeatRequest
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.URL != req.URL {
		t.Errorf("URL = %q", decoded.URL)
	}
	if decoded.TTLSeconds != req.TTLSeconds {
		t.Errorf("TTLSeconds = %d", decoded.TTLSeconds)
	}
}

func TestHeartbeatResponseJSON(t *testing.T) {
	resp := HeartbeatResponse{
		Status:     "ok",
		ReceivedAt: time.Now(),
		ExpiresAt:  time.Now().Add(5 * time.Minute),
		Domain:     "space.example.com",
		TTLSeconds: 300,
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}

	var decoded HeartbeatResponse
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}

	if decoded.Status != resp.Status {
		t.Errorf("Status = %q", decoded.Status)
	}
	if decoded.Domain != resp.Domain {
		t.Errorf("Domain = %q", decoded.Domain)
	}
	if decoded.TTLSeconds != resp.TTLSeconds {
		t.Errorf("TTLSeconds = %d", decoded.TTLSeconds)
	}
}
