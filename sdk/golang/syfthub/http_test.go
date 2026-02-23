package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"
)

func TestNewHTTPClient(t *testing.T) {
	client := newHTTPClient("https://api.example.com/", 30*time.Second)

	if client == nil {
		t.Fatal("client should not be nil")
	}
	if client.baseURL != "https://api.example.com" {
		t.Errorf("baseURL = %q, want %q", client.baseURL, "https://api.example.com")
	}
	if client.timeout != 30*time.Second {
		t.Errorf("timeout = %v, want 30s", client.timeout)
	}
}

func TestHTTPClientAuthentication(t *testing.T) {
	client := newHTTPClient("https://api.example.com", 30*time.Second)

	t.Run("initial state", func(t *testing.T) {
		if client.IsAuthenticated() {
			t.Error("should not be authenticated initially")
		}
		if client.IsUsingAPIToken() {
			t.Error("should not be using API token initially")
		}
	})

	t.Run("set JWT tokens", func(t *testing.T) {
		client.SetTokens(&AuthTokens{
			AccessToken:  "access-token",
			RefreshToken: "refresh-token",
			TokenType:    "bearer",
		})

		if !client.IsAuthenticated() {
			t.Error("should be authenticated after setting tokens")
		}
		if client.IsUsingAPIToken() {
			t.Error("should not be using API token")
		}

		tokens := client.GetTokens()
		if tokens == nil {
			t.Fatal("GetTokens should return tokens")
		}
		if tokens.AccessToken != "access-token" {
			t.Errorf("AccessToken = %q", tokens.AccessToken)
		}
	})

	t.Run("set API token", func(t *testing.T) {
		client.SetAPIToken("api-token-123")

		if !client.IsAuthenticated() {
			t.Error("should be authenticated after setting API token")
		}
		if !client.IsUsingAPIToken() {
			t.Error("should be using API token")
		}

		// JWT tokens should be cleared
		tokens := client.GetTokens()
		if tokens != nil {
			t.Error("JWT tokens should be nil when using API token")
		}
	})

	t.Run("clear tokens", func(t *testing.T) {
		client.ClearTokens()

		if client.IsAuthenticated() {
			t.Error("should not be authenticated after clearing tokens")
		}
		if client.IsUsingAPIToken() {
			t.Error("should not be using API token after clearing")
		}
	})
}

func TestHTTPClientGetBearerToken(t *testing.T) {
	client := newHTTPClient("https://api.example.com", 30*time.Second)

	t.Run("no tokens", func(t *testing.T) {
		token := client.getBearerToken()
		if token != "" {
			t.Errorf("getBearerToken = %q, want empty", token)
		}
	})

	t.Run("JWT token", func(t *testing.T) {
		client.SetTokens(&AuthTokens{
			AccessToken:  "jwt-access",
			RefreshToken: "jwt-refresh",
		})
		token := client.getBearerToken()
		if token != "jwt-access" {
			t.Errorf("getBearerToken = %q, want jwt-access", token)
		}
	})

	t.Run("API token takes precedence", func(t *testing.T) {
		client.SetAPIToken("api-token")
		token := client.getBearerToken()
		if token != "api-token" {
			t.Errorf("getBearerToken = %q, want api-token", token)
		}
	})
}

func TestHTTPClientRequest(t *testing.T) {
	t.Run("successful GET request", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "GET" {
				t.Errorf("Method = %s, want GET", r.Method)
			}
			if r.URL.Path != "/api/test" {
				t.Errorf("Path = %s, want /api/test", r.URL.Path)
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		body, err := client.Request(context.Background(), "GET", "/api/test", nil)
		if err != nil {
			t.Fatalf("Request error: %v", err)
		}

		var result map[string]string
		json.Unmarshal(body, &result)
		if result["status"] != "ok" {
			t.Errorf("status = %q", result["status"])
		}
	})

	t.Run("POST with JSON body", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "POST" {
				t.Errorf("Method = %s, want POST", r.Method)
			}
			if r.Header.Get("Content-Type") != "application/json" {
				t.Errorf("Content-Type = %s", r.Header.Get("Content-Type"))
			}

			var body map[string]string
			json.NewDecoder(r.Body).Decode(&body)
			if body["name"] != "test" {
				t.Errorf("body name = %q", body["name"])
			}

			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(map[string]string{"id": "123"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		body, err := client.Request(context.Background(), "POST", "/api/create", map[string]string{"name": "test"})
		if err != nil {
			t.Fatalf("Request error: %v", err)
		}

		var result map[string]string
		json.Unmarshal(body, &result)
		if result["id"] != "123" {
			t.Errorf("id = %q", result["id"])
		}
	})

	t.Run("with query parameters", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Query().Get("page") != "1" {
				t.Errorf("page = %q, want 1", r.URL.Query().Get("page"))
			}
			if r.URL.Query().Get("limit") != "10" {
				t.Errorf("limit = %q, want 10", r.URL.Query().Get("limit"))
			}
			json.NewEncoder(w).Encode(map[string]string{"ok": "true"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		query := url.Values{}
		query.Set("page", "1")
		query.Set("limit", "10")

		_, err := client.Request(context.Background(), "GET", "/api/list", nil, WithQuery(query))
		if err != nil {
			t.Fatalf("Request error: %v", err)
		}
	})

	t.Run("with form data", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Header.Get("Content-Type") != "application/x-www-form-urlencoded" {
				t.Errorf("Content-Type = %s", r.Header.Get("Content-Type"))
			}
			r.ParseForm()
			if r.Form.Get("username") != "testuser" {
				t.Errorf("username = %q", r.Form.Get("username"))
			}
			json.NewEncoder(w).Encode(map[string]string{"token": "abc"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		formData := url.Values{}
		formData.Set("username", "testuser")
		formData.Set("password", "secret")

		_, err := client.Request(context.Background(), "POST", "/api/login", nil, WithFormData(formData))
		if err != nil {
			t.Fatalf("Request error: %v", err)
		}
	})

	t.Run("with authorization header", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			auth := r.Header.Get("Authorization")
			if auth != "Bearer test-token" {
				t.Errorf("Authorization = %q, want Bearer test-token", auth)
			}
			json.NewEncoder(w).Encode(map[string]string{"ok": "true"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		client.SetAPIToken("test-token")

		_, err := client.Request(context.Background(), "GET", "/api/protected", nil)
		if err != nil {
			t.Fatalf("Request error: %v", err)
		}
	})

	t.Run("without auth", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Header.Get("Authorization") != "" {
				t.Errorf("Authorization should be empty")
			}
			json.NewEncoder(w).Encode(map[string]string{"ok": "true"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		client.SetAPIToken("test-token")

		_, err := client.Request(context.Background(), "GET", "/api/public", nil, WithoutAuth())
		if err != nil {
			t.Fatalf("Request error: %v", err)
		}
	})

	t.Run("204 no content", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		body, err := client.Request(context.Background(), "DELETE", "/api/delete", nil)
		if err != nil {
			t.Fatalf("Request error: %v", err)
		}
		if string(body) != "{}" {
			t.Errorf("body = %q, want {}", string(body))
		}
	})
}

func TestHTTPClientErrorHandling(t *testing.T) {
	t.Run("401 authentication error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]string{"detail": "invalid token"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		_, err := client.Request(context.Background(), "GET", "/api/test", nil, WithNoRetry())

		if err == nil {
			t.Fatal("expected error")
		}
		authErr, ok := err.(*AuthenticationError)
		if !ok {
			t.Fatalf("expected AuthenticationError, got %T", err)
		}
		if authErr.StatusCode != 401 {
			t.Errorf("StatusCode = %d", authErr.StatusCode)
		}
	})

	t.Run("403 authorization error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusForbidden)
			json.NewEncoder(w).Encode(map[string]string{"detail": "access denied"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		_, err := client.Request(context.Background(), "GET", "/api/test", nil)

		if err == nil {
			t.Fatal("expected error")
		}
		authzErr, ok := err.(*AuthorizationError)
		if !ok {
			t.Fatalf("expected AuthorizationError, got %T", err)
		}
		if authzErr.StatusCode != 403 {
			t.Errorf("StatusCode = %d", authzErr.StatusCode)
		}
	})

	t.Run("404 not found error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"detail": "not found"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		_, err := client.Request(context.Background(), "GET", "/api/test", nil)

		if err == nil {
			t.Fatal("expected error")
		}
		notFoundErr, ok := err.(*NotFoundError)
		if !ok {
			t.Fatalf("expected NotFoundError, got %T", err)
		}
		if notFoundErr.StatusCode != 404 {
			t.Errorf("StatusCode = %d", notFoundErr.StatusCode)
		}
	})

	t.Run("422 validation error with field errors", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusUnprocessableEntity)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"detail": map[string]interface{}{
					"message": "validation failed",
					"errors": map[string]interface{}{
						"email": []string{"invalid format"},
					},
				},
			})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		_, err := client.Request(context.Background(), "POST", "/api/test", nil)

		if err == nil {
			t.Fatal("expected error")
		}
		validErr, ok := err.(*ValidationError)
		if !ok {
			t.Fatalf("expected ValidationError, got %T", err)
		}
		if validErr.StatusCode != 422 {
			t.Errorf("StatusCode = %d", validErr.StatusCode)
		}
	})

	t.Run("500 API error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]string{"message": "server error"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		_, err := client.Request(context.Background(), "GET", "/api/test", nil)

		if err == nil {
			t.Fatal("expected error")
		}
		apiErr, ok := err.(*APIError)
		if !ok {
			t.Fatalf("expected APIError, got %T", err)
		}
		if apiErr.StatusCode != 500 {
			t.Errorf("StatusCode = %d", apiErr.StatusCode)
		}
	})

	t.Run("accounting-specific error codes", func(t *testing.T) {
		testCases := []struct {
			code        string
			errType     string
			expectedErr interface{}
		}{
			{"ACCOUNTING_ACCOUNT_EXISTS", "AccountingAccountExistsError", &AccountingAccountExistsError{}},
			{"INVALID_ACCOUNTING_PASSWORD", "InvalidAccountingPasswordError", &InvalidAccountingPasswordError{}},
			{"ACCOUNTING_SERVICE_UNAVAILABLE", "AccountingServiceUnavailableError", &AccountingServiceUnavailableError{}},
		}

		for _, tc := range testCases {
			t.Run(tc.code, func(t *testing.T) {
				server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					w.WriteHeader(http.StatusBadRequest)
					json.NewEncoder(w).Encode(map[string]interface{}{
						"detail": map[string]interface{}{
							"code":    tc.code,
							"message": "test error",
						},
					})
				}))
				defer server.Close()

				client := newHTTPClient(server.URL, 30*time.Second)
				_, err := client.Request(context.Background(), "POST", "/api/test", nil)

				if err == nil {
					t.Fatal("expected error")
				}
			})
		}
	})
}

func TestHTTPClientTokenRefresh(t *testing.T) {
	refreshCalled := false
	requestCount := 0

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++

		if r.URL.Path == "/api/v1/auth/refresh" {
			refreshCalled = true
			json.NewEncoder(w).Encode(map[string]string{
				"access_token":  "new-access",
				"refresh_token": "new-refresh",
			})
			return
		}

		// First request fails with 401, second succeeds
		if requestCount == 1 {
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]string{"detail": "expired"})
			return
		}

		json.NewEncoder(w).Encode(map[string]string{"ok": "true"})
	}))
	defer server.Close()

	client := newHTTPClient(server.URL, 30*time.Second)
	client.SetTokens(&AuthTokens{
		AccessToken:  "old-access",
		RefreshToken: "old-refresh",
	})

	_, err := client.Request(context.Background(), "GET", "/api/protected", nil)
	if err != nil {
		t.Fatalf("Request error: %v", err)
	}

	if !refreshCalled {
		t.Error("refresh should have been called")
	}

	tokens := client.GetTokens()
	if tokens.AccessToken != "new-access" {
		t.Errorf("AccessToken = %q, want new-access", tokens.AccessToken)
	}
}

func TestHTTPClientHelperMethods(t *testing.T) {
	t.Run("Get", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]string{"name": "test"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		var result map[string]string
		err := client.Get(context.Background(), "/api/test", &result)
		if err != nil {
			t.Fatalf("Get error: %v", err)
		}
		if result["name"] != "test" {
			t.Errorf("name = %q", result["name"])
		}
	})

	t.Run("Post", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(map[string]int{"id": 123})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		var result map[string]int
		err := client.Post(context.Background(), "/api/create", map[string]string{"name": "test"}, &result)
		if err != nil {
			t.Fatalf("Post error: %v", err)
		}
		if result["id"] != 123 {
			t.Errorf("id = %d", result["id"])
		}
	})

	t.Run("Put", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "PUT" {
				t.Errorf("Method = %s", r.Method)
			}
			json.NewEncoder(w).Encode(map[string]string{"updated": "true"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		var result map[string]string
		err := client.Put(context.Background(), "/api/update", map[string]string{"name": "test"}, &result)
		if err != nil {
			t.Fatalf("Put error: %v", err)
		}
	})

	t.Run("Patch", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "PATCH" {
				t.Errorf("Method = %s", r.Method)
			}
			json.NewEncoder(w).Encode(map[string]string{"patched": "true"})
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		var result map[string]string
		err := client.Patch(context.Background(), "/api/patch", map[string]string{"field": "value"}, &result)
		if err != nil {
			t.Fatalf("Patch error: %v", err)
		}
	})

	t.Run("Delete", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "DELETE" {
				t.Errorf("Method = %s", r.Method)
			}
			w.WriteHeader(http.StatusNoContent)
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		err := client.Delete(context.Background(), "/api/delete")
		if err != nil {
			t.Fatalf("Delete error: %v", err)
		}
	})

	t.Run("GetRaw", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Write([]byte(`{"raw":"data"}`))
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		body, err := client.GetRaw(context.Background(), "/api/raw")
		if err != nil {
			t.Fatalf("GetRaw error: %v", err)
		}
		if string(body) != `{"raw":"data"}` {
			t.Errorf("body = %s", string(body))
		}
	})

	t.Run("PostRaw", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Write([]byte(`raw response`))
		}))
		defer server.Close()

		client := newHTTPClient(server.URL, 30*time.Second)
		body, err := client.PostRaw(context.Background(), "/api/raw", map[string]string{"test": "data"})
		if err != nil {
			t.Fatalf("PostRaw error: %v", err)
		}
		if string(body) != `raw response` {
			t.Errorf("body = %s", string(body))
		}
	})
}

func TestHTTPClientStreamRequest(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Accept") != "text/event-stream" {
			t.Errorf("Accept = %s", r.Header.Get("Accept"))
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.Write([]byte("data: test\n\n"))
	}))
	defer server.Close()

	client := newHTTPClient(server.URL, 30*time.Second)
	resp, err := client.StreamRequest(context.Background(), "POST", "/api/stream", map[string]string{"prompt": "test"})
	if err != nil {
		t.Fatalf("StreamRequest error: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		t.Errorf("StatusCode = %d", resp.StatusCode)
	}
}

func TestBasicAuthHTTPClient(t *testing.T) {
	t.Run("request with basic auth", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			username, password, ok := r.BasicAuth()
			if !ok {
				t.Error("Basic auth not provided")
			}
			if username != "user@example.com" {
				t.Errorf("username = %q", username)
			}
			if password != "secret123" {
				t.Errorf("password = %q", password)
			}
			json.NewEncoder(w).Encode(map[string]string{"ok": "true"})
		}))
		defer server.Close()

		client := newBasicAuthHTTPClient(server.URL, 30*time.Second, "user@example.com", "secret123")
		_, err := client.Request(context.Background(), "GET", "/api/test", nil)
		if err != nil {
			t.Fatalf("Request error: %v", err)
		}
	})

	t.Run("Get", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			_, _, ok := r.BasicAuth()
			if !ok {
				t.Error("Basic auth not provided")
			}
			json.NewEncoder(w).Encode(map[string]int{"balance": 100})
		}))
		defer server.Close()

		client := newBasicAuthHTTPClient(server.URL, 30*time.Second, "user", "pass")
		var result map[string]int
		err := client.Get(context.Background(), "/user", &result)
		if err != nil {
			t.Fatalf("Get error: %v", err)
		}
		if result["balance"] != 100 {
			t.Errorf("balance = %d", result["balance"])
		}
	})

	t.Run("Post", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]string{"id": "tx-123"})
		}))
		defer server.Close()

		client := newBasicAuthHTTPClient(server.URL, 30*time.Second, "user", "pass")
		var result map[string]string
		err := client.Post(context.Background(), "/transactions", map[string]interface{}{"amount": 10.0}, &result)
		if err != nil {
			t.Fatalf("Post error: %v", err)
		}
		if result["id"] != "tx-123" {
			t.Errorf("id = %s", result["id"])
		}
	})

	t.Run("Patch", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "PATCH" {
				t.Errorf("Method = %s", r.Method)
			}
			json.NewEncoder(w).Encode(map[string]string{"updated": "true"})
		}))
		defer server.Close()

		client := newBasicAuthHTTPClient(server.URL, 30*time.Second, "user", "pass")
		var result map[string]string
		err := client.Patch(context.Background(), "/user", map[string]string{"name": "new name"}, &result)
		if err != nil {
			t.Fatalf("Patch error: %v", err)
		}
	})
}

func TestHTTPClientClose(t *testing.T) {
	client := newHTTPClient("https://api.example.com", 30*time.Second)
	// Should not panic
	client.Close()
}

func TestNewHTTPClientWithDoer(t *testing.T) {
	mockDoer := &mockHTTPDoer{
		doFunc: func(req *http.Request) (*http.Response, error) {
			// Return a mock response
			return &http.Response{
				StatusCode: 200,
				Body:       http.NoBody,
			}, nil
		},
	}

	client := newHTTPClientWithDoer("https://api.example.com", 30*time.Second, mockDoer)
	if client == nil {
		t.Fatal("client should not be nil")
	}
}

type mockHTTPDoer struct {
	doFunc func(req *http.Request) (*http.Response, error)
}

func (m *mockHTTPDoer) Do(req *http.Request) (*http.Response, error) {
	if m.doFunc != nil {
		return m.doFunc(req)
	}
	return nil, nil
}
