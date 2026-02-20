package syfthubapi

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestNewAuthClient(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	client := NewAuthClient("https://hub.example.com", "test-api-key", NewSlogLogger(logger))

	if client == nil {
		t.Fatal("client is nil")
	}
	if client.baseURL != "https://hub.example.com" {
		t.Errorf("baseURL = %q", client.baseURL)
	}
	if client.apiKey != "test-api-key" {
		t.Errorf("apiKey = %q", client.apiKey)
	}
}

func TestAuthClientVerifyToken(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	t.Run("empty token", func(t *testing.T) {
		client := NewAuthClient("http://localhost", "key", NewSlogLogger(logger))

		_, err := client.VerifyToken(context.Background(), "")
		if err == nil {
			t.Fatal("expected error for empty token")
		}
		if !errors.Is(err, ErrAuthentication) {
			t.Error("should be AuthenticationError")
		}
	})

	t.Run("successful verification", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/verify" {
				t.Errorf("unexpected path: %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("unexpected method: %s", r.Method)
			}
			if r.Header.Get("Authorization") != "Bearer test-key" {
				t.Errorf("unexpected auth header: %s", r.Header.Get("Authorization"))
			}

			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(VerifyTokenResponse{
				Valid:    true,
				Sub:      "user-123",
				Username: "testuser",
				Email:    "test@example.com",
				Role:     "admin",
			})
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		ctx, err := client.VerifyToken(context.Background(), "valid-token")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}

		if ctx.Sub != "user-123" {
			t.Errorf("Sub = %q", ctx.Sub)
		}
		if ctx.Username != "testuser" {
			t.Errorf("Username = %q", ctx.Username)
		}
	})

	t.Run("invalid token", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(VerifyTokenResponse{
				Valid:   false,
				Error:   "token_expired",
				Message: "Token has expired",
			})
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		_, err := client.VerifyToken(context.Background(), "invalid-token")
		if err == nil {
			t.Fatal("expected error for invalid token")
		}
	})

	t.Run("server error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte("server error"))
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		_, err := client.VerifyToken(context.Background(), "token")
		if err == nil {
			t.Fatal("expected error for server error")
		}
	})

	t.Run("invalid response json", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Write([]byte("invalid json"))
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		_, err := client.VerifyToken(context.Background(), "token")
		if err == nil {
			t.Fatal("expected error for invalid json")
		}
	})

	t.Run("valid but no user context", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(VerifyTokenResponse{
				Valid: true,
				// No Sub field
			})
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		_, err := client.VerifyToken(context.Background(), "token")
		if err == nil {
			t.Fatal("expected error for missing user context")
		}
	})
}

func TestAuthClientGetMe(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	t.Run("successful", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/auth/me" {
				t.Errorf("unexpected path: %s", r.URL.Path)
			}
			if r.Method != "GET" {
				t.Errorf("unexpected method: %s", r.Method)
			}

			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(UserContext{
				Sub:      "user-456",
				Username: "me",
				Email:    "me@example.com",
			})
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		user, err := client.GetMe(context.Background())
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}

		if user.Sub != "user-456" {
			t.Errorf("Sub = %q", user.Sub)
		}
	})

	t.Run("unauthorized", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte("unauthorized"))
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		_, err := client.GetMe(context.Background())
		if err == nil {
			t.Fatal("expected error for unauthorized")
		}
	})
}

func TestAuthClientGetNATSCredentials(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	t.Run("successful", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/nats/credentials" {
				t.Errorf("unexpected path: %s", r.URL.Path)
			}

			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]string{
				"nats_auth_token": "nats-token-123",
			})
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		creds, err := client.GetNATSCredentials(context.Background(), "testuser")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}

		if creds.Token != "nats-token-123" {
			t.Errorf("Token = %q", creds.Token)
		}
		if creds.Subject != "syfthub.spaces.testuser" {
			t.Errorf("Subject = %q", creds.Subject)
		}
		// URL should be derived from server URL (http -> ws)
		if creds.URL == "" {
			t.Error("URL should not be empty")
		}
	})

	t.Run("server error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		client := NewAuthClient(server.URL, "test-key", NewSlogLogger(logger))
		_, err := client.GetNATSCredentials(context.Background(), "user")
		if err == nil {
			t.Fatal("expected error")
		}
	})
}

func TestNewSyncClient(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	client := NewSyncClient("https://hub.example.com", "test-key", NewSlogLogger(logger))

	if client == nil {
		t.Fatal("client is nil")
	}
	if client.baseURL != "https://hub.example.com" {
		t.Errorf("baseURL = %q", client.baseURL)
	}
}

func TestSyncClientSyncEndpoints(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	t.Run("successful sync", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/endpoints/sync" {
				t.Errorf("unexpected path: %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("unexpected method: %s", r.Method)
			}

			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(SyncEndpointsResponse{
				Synced:  2,
				Deleted: 1,
			})
		}))
		defer server.Close()

		client := NewSyncClient(server.URL, "test-key", NewSlogLogger(logger))
		endpoints := []EndpointInfo{
			{Slug: "ep1", Name: "Endpoint 1", Type: EndpointTypeModel},
			{Slug: "ep2", Name: "Endpoint 2", Type: EndpointTypeDataSource},
		}

		resp, err := client.SyncEndpoints(context.Background(), endpoints)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}

		if resp.Synced != 2 {
			t.Errorf("Synced = %d", resp.Synced)
		}
		if resp.Deleted != 1 {
			t.Errorf("Deleted = %d", resp.Deleted)
		}
	})

	t.Run("server error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte("service unavailable"))
		}))
		defer server.Close()

		client := NewSyncClient(server.URL, "test-key", NewSlogLogger(logger))
		_, err := client.SyncEndpoints(context.Background(), nil)
		if err == nil {
			t.Fatal("expected error")
		}

		var syncErr *SyncError
		if !errors.As(err, &syncErr) {
			t.Error("should be SyncError")
		}
		if syncErr.StatusCode != http.StatusServiceUnavailable {
			t.Errorf("StatusCode = %d", syncErr.StatusCode)
		}
	})
}

func TestSyncClientUpdateDomain(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	t.Run("successful update", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/me" {
				t.Errorf("unexpected path: %s", r.URL.Path)
			}
			if r.Method != "PUT" {
				t.Errorf("unexpected method: %s", r.Method)
			}

			w.WriteHeader(http.StatusOK)
		}))
		defer server.Close()

		client := NewSyncClient(server.URL, "test-key", NewSlogLogger(logger))
		err := client.UpdateDomain(context.Background(), "https://myspace.example.com")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("server error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("invalid domain"))
		}))
		defer server.Close()

		client := NewSyncClient(server.URL, "test-key", NewSlogLogger(logger))
		err := client.UpdateDomain(context.Background(), "invalid")
		if err == nil {
			t.Fatal("expected error")
		}
	})
}

func TestNewAPIAuthenticator(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	cfg := &Config{
		SyftHubURL: "https://hub.example.com",
		APIKey:     "test-key",
		SpaceURL:   "https://space.example.com",
	}

	auth := NewAPIAuthenticator(cfg, NewSlogLogger(logger))

	if auth == nil {
		t.Fatal("authenticator is nil")
	}
	if auth.authClient == nil {
		t.Error("authClient is nil")
	}
	if auth.syncClient == nil {
		t.Error("syncClient is nil")
	}
}

func TestAPIAuthenticatorAuthenticate(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(UserContext{
			Sub:      "user-123",
			Username: "authuser",
		})
	}))
	defer server.Close()

	cfg := &Config{
		SyftHubURL: server.URL,
		APIKey:     "test-key",
		SpaceURL:   "https://space.example.com",
	}

	auth := NewAPIAuthenticator(cfg, NewSlogLogger(logger))
	user, err := auth.Authenticate(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if user.Username != "authuser" {
		t.Errorf("Username = %q", user.Username)
	}
}

func TestAPIAuthenticatorSyncEndpoints(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	t.Run("non-tunnel mode updates domain first", func(t *testing.T) {
		domainUpdated := false
		endpointsSynced := false

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			switch r.URL.Path {
			case "/api/v1/users/me":
				domainUpdated = true
				w.WriteHeader(http.StatusOK)
			case "/api/v1/endpoints/sync":
				endpointsSynced = true
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(SyncEndpointsResponse{Synced: 1})
			}
		}))
		defer server.Close()

		cfg := &Config{
			SyftHubURL: server.URL,
			APIKey:     "test-key",
			SpaceURL:   "https://space.example.com", // Non-tunnel mode
		}

		auth := NewAPIAuthenticator(cfg, NewSlogLogger(logger))
		err := auth.SyncEndpoints(context.Background(), []EndpointInfo{
			{Slug: "ep1"},
		})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}

		if !domainUpdated {
			t.Error("domain should be updated in non-tunnel mode")
		}
		if !endpointsSynced {
			t.Error("endpoints should be synced")
		}
	})

	t.Run("tunnel mode skips domain update", func(t *testing.T) {
		domainUpdated := false

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			switch r.URL.Path {
			case "/api/v1/users/me":
				domainUpdated = true
				w.WriteHeader(http.StatusOK)
			case "/api/v1/endpoints/sync":
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(SyncEndpointsResponse{Synced: 1})
			}
		}))
		defer server.Close()

		cfg := &Config{
			SyftHubURL: server.URL,
			APIKey:     "test-key",
			SpaceURL:   "tunneling:testuser", // Tunnel mode
		}

		auth := NewAPIAuthenticator(cfg, NewSlogLogger(logger))
		err := auth.SyncEndpoints(context.Background(), nil)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}

		if domainUpdated {
			t.Error("domain should NOT be updated in tunnel mode")
		}
	})
}

func TestAPIAuthenticatorVerifyToken(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(VerifyTokenResponse{
			Valid:    true,
			Sub:      "user-123",
			Username: "verified",
		})
	}))
	defer server.Close()

	cfg := &Config{
		SyftHubURL: server.URL,
		APIKey:     "test-key",
		SpaceURL:   "https://space.example.com",
	}

	auth := NewAPIAuthenticator(cfg, NewSlogLogger(logger))
	user, err := auth.VerifyToken(context.Background(), "token")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if user.Username != "verified" {
		t.Errorf("Username = %q", user.Username)
	}
}

func TestAPIAuthenticatorGetNATSCredentials(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{
			"nats_auth_token": "nats-token",
		})
	}))
	defer server.Close()

	cfg := &Config{
		SyftHubURL: server.URL,
		APIKey:     "test-key",
		SpaceURL:   "tunneling:mytunneluser",
	}

	auth := NewAPIAuthenticator(cfg, NewSlogLogger(logger))
	creds, err := auth.GetNATSCredentials(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if creds.Subject != "syfthub.spaces.mytunneluser" {
		t.Errorf("Subject = %q", creds.Subject)
	}
}
