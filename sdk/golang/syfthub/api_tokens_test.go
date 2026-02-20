package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestAPITokensResourceCreate(t *testing.T) {
	t.Run("basic create", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/auth/tokens" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["name"] != "CI/CD Pipeline" {
				t.Errorf("name = %v", body["name"])
			}

			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":         1,
				"name":       "CI/CD Pipeline",
				"token":      "syfthub_abc123xyz789",
				"prefix":     "syfthub_abc",
				"scopes":     []string{"full"},
				"created_at": "2024-01-01T00:00:00Z",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		result, err := tokens.Create(context.Background(), &CreateAPITokenRequest{
			Name: "CI/CD Pipeline",
		})
		if err != nil {
			t.Fatalf("Create error: %v", err)
		}
		if result.Token != "syfthub_abc123xyz789" {
			t.Errorf("Token = %q", result.Token)
		}
		if result.Name != "CI/CD Pipeline" {
			t.Errorf("Name = %q", result.Name)
		}
	})

	t.Run("with scopes", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			scopes := body["scopes"].([]interface{})
			if len(scopes) != 2 {
				t.Errorf("scopes length = %d", len(scopes))
			}
			if scopes[0] != "read" || scopes[1] != "write" {
				t.Errorf("scopes = %v", scopes)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":     1,
				"name":   "Test",
				"token":  "syfthub_test",
				"scopes": []string{"read", "write"},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		_, err := tokens.Create(context.Background(), &CreateAPITokenRequest{
			Name:   "Test",
			Scopes: []APITokenScope{APITokenScopeRead, APITokenScopeWrite},
		})
		if err != nil {
			t.Fatalf("Create error: %v", err)
		}
	})

	t.Run("with expiration", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["expires_at"] == nil {
				t.Error("expires_at should be present")
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":         1,
				"name":       "Expiring Token",
				"token":      "syfthub_exp",
				"expires_at": "2024-12-31T23:59:59Z",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		expiry := time.Date(2024, 12, 31, 23, 59, 59, 0, time.UTC)
		_, err := tokens.Create(context.Background(), &CreateAPITokenRequest{
			Name:      "Expiring Token",
			ExpiresAt: &expiry,
		})
		if err != nil {
			t.Fatalf("Create error: %v", err)
		}
	})
}

func TestAPITokensResourceList(t *testing.T) {
	t.Run("default options", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/auth/tokens" {
				t.Errorf("path = %s", r.URL.Path)
			}

			skip := r.URL.Query().Get("skip")
			limit := r.URL.Query().Get("limit")
			includeInactive := r.URL.Query().Get("include_inactive")

			if skip != "0" {
				t.Errorf("skip = %s", skip)
			}
			if limit != "100" {
				t.Errorf("limit = %s", limit)
			}
			if includeInactive != "" {
				t.Errorf("include_inactive = %s", includeInactive)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"tokens": []map[string]interface{}{
					{"id": 1, "name": "Token 1", "prefix": "syfthub_t1", "is_active": true},
					{"id": 2, "name": "Token 2", "prefix": "syfthub_t2", "is_active": true},
				},
				"total": 2,
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		result, err := tokens.List(context.Background())
		if err != nil {
			t.Fatalf("List error: %v", err)
		}
		if len(result.Tokens) != 2 {
			t.Errorf("len(tokens) = %d", len(result.Tokens))
		}
		if result.Total != 2 {
			t.Errorf("total = %d", result.Total)
		}
	})

	t.Run("with options", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			skip := r.URL.Query().Get("skip")
			limit := r.URL.Query().Get("limit")
			includeInactive := r.URL.Query().Get("include_inactive")

			if skip != "10" {
				t.Errorf("skip = %s", skip)
			}
			if limit != "50" {
				t.Errorf("limit = %s", limit)
			}
			if includeInactive != "true" {
				t.Errorf("include_inactive = %s", includeInactive)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"tokens": []map[string]interface{}{},
				"total":  0,
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		_, err := tokens.List(context.Background(),
			WithTokensSkip(10),
			WithTokensLimit(50),
			WithIncludeInactive(),
		)
		if err != nil {
			t.Fatalf("List error: %v", err)
		}
	})
}

func TestAPITokensResourceGet(t *testing.T) {
	t.Run("found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/auth/tokens/1" {
				t.Errorf("path = %s", r.URL.Path)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":           1,
				"name":         "My Token",
				"token_prefix": "syfthub_my",
				"scopes":       []string{"full"},
				"is_active":    true,
				"created_at":   "2024-01-01T00:00:00Z",
				"last_used_at": "2024-01-15T12:00:00Z",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		token, err := tokens.Get(context.Background(), 1)
		if err != nil {
			t.Fatalf("Get error: %v", err)
		}
		if token.Name != "My Token" {
			t.Errorf("Name = %q", token.Name)
		}
		if token.TokenPrefix != "syfthub_my" {
			t.Errorf("TokenPrefix = %q", token.TokenPrefix)
		}
		if !token.IsActive {
			t.Error("should be active")
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Token not found"})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		_, err := tokens.Get(context.Background(), 999)
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*NotFoundError)
		if !ok {
			t.Fatalf("expected NotFoundError, got %T", err)
		}
	})
}

func TestAPITokensResourceUpdate(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/auth/tokens/1" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "PATCH" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]string
		json.NewDecoder(r.Body).Decode(&body)

		if body["name"] != "Updated Name" {
			t.Errorf("name = %v", body["name"])
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":        1,
			"name":      "Updated Name",
			"prefix":    "syfthub_t1",
			"is_active": true,
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	tokens := newAPITokensResource(http)

	token, err := tokens.Update(context.Background(), 1, "Updated Name")
	if err != nil {
		t.Fatalf("Update error: %v", err)
	}
	if token.Name != "Updated Name" {
		t.Errorf("Name = %q", token.Name)
	}
}

func TestAPITokensResourceRevoke(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/auth/tokens/1" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "DELETE" {
				t.Errorf("method = %s", r.Method)
			}
			w.WriteHeader(http.StatusNoContent)
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		err := tokens.Revoke(context.Background(), 1)
		if err != nil {
			t.Fatalf("Revoke error: %v", err)
		}
	})

	t.Run("not found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"detail": "Token not found"})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		tokens := newAPITokensResource(http)

		err := tokens.Revoke(context.Background(), 999)
		if err == nil {
			t.Fatal("expected error")
		}
		_, ok := err.(*NotFoundError)
		if !ok {
			t.Fatalf("expected NotFoundError, got %T", err)
		}
	})
}

func TestNewAPITokensResource(t *testing.T) {
	http := newHTTPClient("http://localhost", DefaultTimeout)
	tokens := newAPITokensResource(http)

	if tokens == nil {
		t.Fatal("tokens should not be nil")
	}
	if tokens.http != http {
		t.Error("http client not set correctly")
	}
}

func TestAPITokenScopeConstants(t *testing.T) {
	tests := []struct {
		scope    APITokenScope
		expected string
	}{
		{APITokenScopeRead, "read"},
		{APITokenScopeWrite, "write"},
		{APITokenScopeFull, "full"},
	}

	for _, tt := range tests {
		if string(tt.scope) != tt.expected {
			t.Errorf("APITokenScope %q should be %q", tt.scope, tt.expected)
		}
	}
}

func TestListAPITokensOptions(t *testing.T) {
	t.Run("WithIncludeInactive", func(t *testing.T) {
		opts := &listAPITokensOptions{}
		WithIncludeInactive()(opts)
		if !opts.includeInactive {
			t.Error("includeInactive should be true")
		}
	})

	t.Run("WithTokensSkip", func(t *testing.T) {
		opts := &listAPITokensOptions{}
		WithTokensSkip(25)(opts)
		if opts.skip != 25 {
			t.Errorf("skip = %d, want 25", opts.skip)
		}
	})

	t.Run("WithTokensLimit", func(t *testing.T) {
		opts := &listAPITokensOptions{}
		WithTokensLimit(50)(opts)
		if opts.limit != 50 {
			t.Errorf("limit = %d, want 50", opts.limit)
		}
	})
}
