package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

func TestNewClient(t *testing.T) {
	t.Run("with base URL option", func(t *testing.T) {
		client, err := NewClient(WithBaseURL("https://hub.example.com"))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if client == nil {
			t.Fatal("client should not be nil")
		}
		if client.BaseURL() != "https://hub.example.com" {
			t.Errorf("BaseURL = %q", client.BaseURL())
		}
		client.Close()
	})

	t.Run("trims trailing slash from URL", func(t *testing.T) {
		client, err := NewClient(WithBaseURL("https://hub.example.com/"))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if client.BaseURL() != "https://hub.example.com" {
			t.Errorf("BaseURL = %q", client.BaseURL())
		}
		client.Close()
	})

	t.Run("with timeout option", func(t *testing.T) {
		client, err := NewClient(
			WithBaseURL("https://hub.example.com"),
			WithTimeout(60*time.Second),
		)
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if client.timeout != 60*time.Second {
			t.Errorf("timeout = %v", client.timeout)
		}
		client.Close()
	})

	t.Run("with aggregator URL option", func(t *testing.T) {
		client, err := NewClient(
			WithBaseURL("https://hub.example.com"),
			WithAggregatorURL("https://custom-aggregator.example.com"),
		)
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if client.AggregatorURL() != "https://custom-aggregator.example.com" {
			t.Errorf("AggregatorURL = %q", client.AggregatorURL())
		}
		client.Close()
	})

	t.Run("default aggregator URL", func(t *testing.T) {
		client, err := NewClient(WithBaseURL("https://hub.example.com"))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		expected := "https://hub.example.com/aggregator/api/v1"
		if client.AggregatorURL() != expected {
			t.Errorf("AggregatorURL = %q, want %q", client.AggregatorURL(), expected)
		}
		client.Close()
	})

	t.Run("with API token option", func(t *testing.T) {
		client, err := NewClient(
			WithBaseURL("https://hub.example.com"),
			WithAPIToken("syft_pat_xxxxx"),
		)
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if !client.IsAuthenticated() {
			t.Error("should be authenticated with API token")
		}
		if !client.IsUsingAPIToken() {
			t.Error("should be using API token")
		}
		client.Close()
	})

	t.Run("error without base URL", func(t *testing.T) {
		// Clear environment
		os.Unsetenv(EnvSyftHubURL)

		_, err := NewClient()
		if err == nil {
			t.Fatal("expected error without base URL")
		}
		configErr, ok := err.(*ConfigurationError)
		if !ok {
			t.Fatalf("expected ConfigurationError, got %T", err)
		}
		if configErr.Message == "" {
			t.Error("error message should not be empty")
		}
	})

	t.Run("reads URL from environment", func(t *testing.T) {
		t.Setenv(EnvSyftHubURL, "https://env-hub.example.com")

		client, err := NewClient()
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if client.BaseURL() != "https://env-hub.example.com" {
			t.Errorf("BaseURL = %q", client.BaseURL())
		}
		client.Close()
	})

	t.Run("reads aggregator URL from environment", func(t *testing.T) {
		t.Setenv(EnvSyftHubURL, "https://hub.example.com")
		t.Setenv(EnvAggregatorURL, "https://env-aggregator.example.com")

		client, err := NewClient()
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if client.AggregatorURL() != "https://env-aggregator.example.com" {
			t.Errorf("AggregatorURL = %q", client.AggregatorURL())
		}
		client.Close()
	})

	t.Run("reads API token from environment", func(t *testing.T) {
		t.Setenv(EnvSyftHubURL, "https://hub.example.com")
		t.Setenv(EnvAPIToken, "syft_pat_env_token")

		client, err := NewClient()
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if !client.IsAuthenticated() {
			t.Error("should be authenticated from env token")
		}
		if !client.IsUsingAPIToken() {
			t.Error("should be using API token from env")
		}
		client.Close()
	})

	t.Run("option overrides environment", func(t *testing.T) {
		t.Setenv(EnvSyftHubURL, "https://env-hub.example.com")

		client, err := NewClient(WithBaseURL("https://option-hub.example.com"))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		if client.BaseURL() != "https://option-hub.example.com" {
			t.Errorf("BaseURL = %q, want option-hub", client.BaseURL())
		}
		client.Close()
	})

	t.Run("resources are initialized", func(t *testing.T) {
		client, err := NewClient(WithBaseURL("https://hub.example.com"))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}

		if client.Auth == nil {
			t.Error("Auth should be initialized")
		}
		if client.Users == nil {
			t.Error("Users should be initialized")
		}
		if client.MyEndpoints == nil {
			t.Error("MyEndpoints should be initialized")
		}
		if client.Hub == nil {
			t.Error("Hub should be initialized")
		}
		client.Close()
	})
}

func TestClientAuthentication(t *testing.T) {
	client, err := NewClient(WithBaseURL("https://hub.example.com"))
	if err != nil {
		t.Fatalf("NewClient error: %v", err)
	}
	defer client.Close()

	t.Run("not authenticated initially", func(t *testing.T) {
		if client.IsAuthenticated() {
			t.Error("should not be authenticated initially")
		}
	})

	t.Run("set and get tokens", func(t *testing.T) {
		tokens := &AuthTokens{
			AccessToken:  "access",
			RefreshToken: "refresh",
			TokenType:    "bearer",
		}
		client.SetTokens(tokens)

		if !client.IsAuthenticated() {
			t.Error("should be authenticated after setting tokens")
		}

		retrieved := client.GetTokens()
		if retrieved == nil {
			t.Fatal("GetTokens returned nil")
		}
		if retrieved.AccessToken != "access" {
			t.Errorf("AccessToken = %q", retrieved.AccessToken)
		}
	})
}

func TestClientLazyResources(t *testing.T) {
	client, err := NewClient(WithBaseURL("https://hub.example.com"))
	if err != nil {
		t.Fatalf("NewClient error: %v", err)
	}
	defer client.Close()

	t.Run("Chat resource", func(t *testing.T) {
		chat := client.Chat()
		if chat == nil {
			t.Error("Chat() should not return nil")
		}

		// Second call should return same instance
		chat2 := client.Chat()
		if chat != chat2 {
			t.Error("Chat() should return same instance")
		}
	})

	t.Run("SyftAI resource", func(t *testing.T) {
		syftai := client.SyftAI()
		if syftai == nil {
			t.Error("SyftAI() should not return nil")
		}

		// Second call should return same instance
		syftai2 := client.SyftAI()
		if syftai != syftai2 {
			t.Error("SyftAI() should return same instance")
		}
	})

	t.Run("APITokens resource", func(t *testing.T) {
		tokens := client.APITokens()
		if tokens == nil {
			t.Error("APITokens() should not return nil")
		}

		// Second call should return same instance
		tokens2 := client.APITokens()
		if tokens != tokens2 {
			t.Error("APITokens() should return same instance")
		}
	})
}

func TestClientAccounting(t *testing.T) {
	t.Run("fails when not authenticated", func(t *testing.T) {
		client, err := NewClient(WithBaseURL("https://hub.example.com"))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		defer client.Close()

		_, err = client.Accounting(context.Background())
		if err == nil {
			t.Fatal("expected error when not authenticated")
		}
		authErr, ok := err.(*AuthenticationError)
		if !ok {
			t.Fatalf("expected AuthenticationError, got %T", err)
		}
		if authErr == nil {
			t.Error("error should not be nil")
		}
	})

	t.Run("fails when no accounting URL configured", func(t *testing.T) {
		// Create server that returns empty accounting credentials
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/api/v1/users/me/accounting" {
				json.NewEncoder(w).Encode(map[string]interface{}{
					"email": "user@example.com",
					"url":   nil,
				})
				return
			}
			w.WriteHeader(http.StatusNotFound)
		}))
		defer server.Close()

		client, err := NewClient(WithBaseURL(server.URL))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		defer client.Close()

		// Authenticate the client
		client.SetTokens(&AuthTokens{
			AccessToken:  "test-token",
			RefreshToken: "refresh-token",
		})

		_, err = client.Accounting(context.Background())
		if err == nil {
			t.Fatal("expected error when no accounting URL")
		}
	})

	t.Run("fails when no accounting password", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/api/v1/users/me/accounting" {
				json.NewEncoder(w).Encode(map[string]interface{}{
					"email":    "user@example.com",
					"url":      "https://accounting.example.com",
					"password": nil,
				})
				return
			}
			w.WriteHeader(http.StatusNotFound)
		}))
		defer server.Close()

		client, err := NewClient(WithBaseURL(server.URL))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		defer client.Close()

		client.SetTokens(&AuthTokens{
			AccessToken:  "test-token",
			RefreshToken: "refresh-token",
		})

		_, err = client.Accounting(context.Background())
		if err == nil {
			t.Fatal("expected error when no accounting password")
		}
	})

	t.Run("success with valid credentials", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/api/v1/users/me/accounting" {
				url := "https://accounting.example.com"
				password := "secret123"
				json.NewEncoder(w).Encode(map[string]interface{}{
					"email":    "user@example.com",
					"url":      url,
					"password": password,
				})
				return
			}
			w.WriteHeader(http.StatusNotFound)
		}))
		defer server.Close()

		client, err := NewClient(WithBaseURL(server.URL))
		if err != nil {
			t.Fatalf("NewClient error: %v", err)
		}
		defer client.Close()

		client.SetTokens(&AuthTokens{
			AccessToken:  "test-token",
			RefreshToken: "refresh-token",
		})

		accounting, err := client.Accounting(context.Background())
		if err != nil {
			t.Fatalf("Accounting error: %v", err)
		}
		if accounting == nil {
			t.Error("Accounting should not be nil")
		}

		// Second call should return cached instance
		accounting2, err := client.Accounting(context.Background())
		if err != nil {
			t.Fatalf("Accounting error: %v", err)
		}
		if accounting != accounting2 {
			t.Error("should return cached instance")
		}
	})
}

func TestClientAuthAliases(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/auth/register":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"user":          map[string]interface{}{"id": 1, "username": "newuser"},
				"access_token":  "new-access",
				"refresh_token": "new-refresh",
			})
		case "/api/v1/auth/login":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"access_token":  "login-access",
				"refresh_token": "login-refresh",
			})
		case "/api/v1/auth/me":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":       1,
				"username": "testuser",
				"email":    "test@example.com",
			})
		case "/api/v1/auth/logout":
			w.WriteHeader(http.StatusNoContent)
		case "/api/v1/auth/refresh":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"access_token":  "refreshed-access",
				"refresh_token": "refreshed-refresh",
			})
		case "/api/v1/auth/me/password":
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	client, err := NewClient(WithBaseURL(server.URL))
	if err != nil {
		t.Fatalf("NewClient error: %v", err)
	}
	defer client.Close()

	t.Run("Register", func(t *testing.T) {
		user, err := client.Register(context.Background(), &RegisterRequest{
			Username: "newuser",
			Email:    "new@example.com",
			Password: "password123",
			FullName: "New User",
		})
		if err != nil {
			t.Fatalf("Register error: %v", err)
		}
		if user == nil {
			t.Error("user should not be nil")
		}
	})

	t.Run("Login", func(t *testing.T) {
		user, err := client.Login(context.Background(), "testuser", "password")
		if err != nil {
			t.Fatalf("Login error: %v", err)
		}
		if user == nil {
			t.Error("user should not be nil")
		}
	})

	t.Run("Me", func(t *testing.T) {
		client.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		user, err := client.Me(context.Background())
		if err != nil {
			t.Fatalf("Me error: %v", err)
		}
		if user == nil {
			t.Error("user should not be nil")
		}
	})

	t.Run("Refresh", func(t *testing.T) {
		client.SetTokens(&AuthTokens{AccessToken: "old", RefreshToken: "old"})
		err := client.Refresh(context.Background())
		if err != nil {
			t.Fatalf("Refresh error: %v", err)
		}
	})

	t.Run("ChangePassword", func(t *testing.T) {
		client.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		err := client.ChangePassword(context.Background(), "oldpass", "newpass")
		if err != nil {
			t.Fatalf("ChangePassword error: %v", err)
		}
	})

	t.Run("Logout", func(t *testing.T) {
		client.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		err := client.Logout(context.Background())
		if err != nil {
			t.Fatalf("Logout error: %v", err)
		}
	})
}

func TestClientClose(t *testing.T) {
	// Create server for accounting
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/users/me/accounting" {
			url := "https://accounting.example.com"
			password := "secret"
			json.NewEncoder(w).Encode(map[string]interface{}{
				"email":    "user@example.com",
				"url":      url,
				"password": password,
			})
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client, err := NewClient(WithBaseURL(server.URL))
	if err != nil {
		t.Fatalf("NewClient error: %v", err)
	}

	// Initialize accounting resource
	client.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	_, err = client.Accounting(context.Background())
	if err != nil {
		t.Fatalf("Accounting error: %v", err)
	}

	// Close should not panic
	client.Close()
}

func TestDefaultValues(t *testing.T) {
	t.Run("DefaultTimeout", func(t *testing.T) {
		if DefaultTimeout != 30*time.Second {
			t.Errorf("DefaultTimeout = %v, want 30s", DefaultTimeout)
		}
	})

	t.Run("DefaultAggTimeout", func(t *testing.T) {
		if DefaultAggTimeout != 120*time.Second {
			t.Errorf("DefaultAggTimeout = %v, want 120s", DefaultAggTimeout)
		}
	})

	t.Run("DefaultPageSize", func(t *testing.T) {
		if DefaultPageSize != 20 {
			t.Errorf("DefaultPageSize = %d, want 20", DefaultPageSize)
		}
	})
}

func TestEnvironmentVariableNames(t *testing.T) {
	if EnvSyftHubURL != "SYFTHUB_URL" {
		t.Errorf("EnvSyftHubURL = %q", EnvSyftHubURL)
	}
	if EnvAggregatorURL != "SYFTHUB_AGGREGATOR_URL" {
		t.Errorf("EnvAggregatorURL = %q", EnvAggregatorURL)
	}
	if EnvAPIToken != "SYFTHUB_API_TOKEN" {
		t.Errorf("EnvAPIToken = %q", EnvAPIToken)
	}
}
