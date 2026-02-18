package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAuthResourceRegister(t *testing.T) {
	t.Run("successful registration", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/auth/register" {
				t.Errorf("path = %s", r.URL.Path)
			}
			if r.Method != "POST" {
				t.Errorf("method = %s", r.Method)
			}

			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)
			if body["username"] != "newuser" {
				t.Errorf("username = %v", body["username"])
			}
			if body["email"] != "new@example.com" {
				t.Errorf("email = %v", body["email"])
			}

			w.WriteHeader(http.StatusCreated)
			json.NewEncoder(w).Encode(map[string]interface{}{
				"user": map[string]interface{}{
					"id":       1,
					"username": "newuser",
					"email":    "new@example.com",
				},
				"access_token":  "new-access-token",
				"refresh_token": "new-refresh-token",
				"token_type":    "bearer",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		auth := newAuthResource(http)

		user, err := auth.Register(context.Background(), &RegisterRequest{
			Username: "newuser",
			Email:    "new@example.com",
			Password: "password123",
			FullName: "New User",
		})

		if err != nil {
			t.Fatalf("Register error: %v", err)
		}
		if user == nil {
			t.Fatal("user should not be nil")
		}
		if user.Username != "newuser" {
			t.Errorf("Username = %q", user.Username)
		}

		// Should be authenticated after registration
		if !http.IsAuthenticated() {
			t.Error("should be authenticated after registration")
		}
	})

	t.Run("with accounting password", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]interface{}
			json.NewDecoder(r.Body).Decode(&body)

			if body["accounting_password"] != "acctpass123" {
				t.Errorf("accounting_password = %v", body["accounting_password"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"user":          map[string]interface{}{"id": 1},
				"access_token":  "token",
				"refresh_token": "refresh",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		auth := newAuthResource(http)

		acctPass := "acctpass123"
		_, err := auth.Register(context.Background(), &RegisterRequest{
			Username:           "user",
			Email:              "user@example.com",
			Password:           "password",
			FullName:           "User",
			AccountingPassword: &acctPass,
		})

		if err != nil {
			t.Fatalf("Register error: %v", err)
		}
	})
}

func TestAuthResourceLogin(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/auth/login" {
			if r.Header.Get("Content-Type") != "application/x-www-form-urlencoded" {
				t.Errorf("Content-Type = %s", r.Header.Get("Content-Type"))
			}

			r.ParseForm()
			if r.Form.Get("username") != "testuser" {
				t.Errorf("username = %q", r.Form.Get("username"))
			}
			if r.Form.Get("password") != "password123" {
				t.Errorf("password = %q", r.Form.Get("password"))
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"access_token":  "login-access",
				"refresh_token": "login-refresh",
				"token_type":    "bearer",
			})
			return
		}

		if r.URL.Path == "/api/v1/auth/me" {
			json.NewEncoder(w).Encode(map[string]interface{}{
				"id":       1,
				"username": "testuser",
				"email":    "test@example.com",
			})
			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	auth := newAuthResource(http)

	user, err := auth.Login(context.Background(), "testuser", "password123")
	if err != nil {
		t.Fatalf("Login error: %v", err)
	}
	if user == nil {
		t.Fatal("user should not be nil")
	}
	if user.Username != "testuser" {
		t.Errorf("Username = %q", user.Username)
	}

	if !http.IsAuthenticated() {
		t.Error("should be authenticated after login")
	}
}

func TestAuthResourceLogout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/auth/logout" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	auth := newAuthResource(http)

	err := auth.Logout(context.Background())
	if err != nil {
		t.Fatalf("Logout error: %v", err)
	}

	if http.IsAuthenticated() {
		t.Error("should not be authenticated after logout")
	}
}

func TestAuthResourceRefresh(t *testing.T) {
	t.Run("successful refresh", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/auth/refresh" {
				t.Errorf("path = %s", r.URL.Path)
			}

			var body map[string]string
			json.NewDecoder(r.Body).Decode(&body)
			if body["refresh_token"] != "old-refresh" {
				t.Errorf("refresh_token = %q", body["refresh_token"])
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"access_token":  "new-access",
				"refresh_token": "new-refresh",
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "old-access", RefreshToken: "old-refresh"})
		auth := newAuthResource(http)

		err := auth.Refresh(context.Background())
		if err != nil {
			t.Fatalf("Refresh error: %v", err)
		}

		tokens := http.GetTokens()
		if tokens.AccessToken != "new-access" {
			t.Errorf("AccessToken = %q", tokens.AccessToken)
		}
	})

	t.Run("fails without tokens", func(t *testing.T) {
		http := newHTTPClient("http://localhost", DefaultTimeout)
		auth := newAuthResource(http)

		err := auth.Refresh(context.Background())
		if err == nil {
			t.Fatal("expected error without tokens")
		}
	})
}

func TestAuthResourceMe(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/auth/me" {
			t.Errorf("path = %s", r.URL.Path)
		}
		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":        1,
			"username":  "currentuser",
			"email":     "current@example.com",
			"full_name": "Current User",
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	auth := newAuthResource(http)

	user, err := auth.Me(context.Background())
	if err != nil {
		t.Fatalf("Me error: %v", err)
	}
	if user.Username != "currentuser" {
		t.Errorf("Username = %q", user.Username)
	}
}

func TestAuthResourceChangePassword(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/auth/me/password" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "PUT" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]string
		json.NewDecoder(r.Body).Decode(&body)
		if body["current_password"] != "oldpass" {
			t.Errorf("current_password = %q", body["current_password"])
		}
		if body["new_password"] != "newpass" {
			t.Errorf("new_password = %q", body["new_password"])
		}

		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	auth := newAuthResource(http)

	err := auth.ChangePassword(context.Background(), "oldpass", "newpass")
	if err != nil {
		t.Fatalf("ChangePassword error: %v", err)
	}
}

func TestAuthResourceGetSatelliteToken(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/token" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.URL.Query().Get("aud") != "alice" {
			t.Errorf("aud = %q", r.URL.Query().Get("aud"))
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"target_token": "satellite-token-123",
			"expires_in":   3600,
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	auth := newAuthResource(http)

	resp, err := auth.GetSatelliteToken(context.Background(), "alice")
	if err != nil {
		t.Fatalf("GetSatelliteToken error: %v", err)
	}
	if resp.TargetToken != "satellite-token-123" {
		t.Errorf("TargetToken = %q", resp.TargetToken)
	}
	if resp.ExpiresIn != 3600 {
		t.Errorf("ExpiresIn = %d", resp.ExpiresIn)
	}
}

func TestAuthResourceGetSatelliteTokens(t *testing.T) {
	t.Run("successful batch fetch", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			aud := r.URL.Query().Get("aud")
			json.NewEncoder(w).Encode(map[string]interface{}{
				"target_token": "token-for-" + aud,
				"expires_in":   3600,
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		auth := newAuthResource(http)

		tokens, err := auth.GetSatelliteTokens(context.Background(), []string{"alice", "bob", "alice"}) // includes duplicate
		if err != nil {
			t.Fatalf("GetSatelliteTokens error: %v", err)
		}

		// Should have 2 tokens (alice deduplicated)
		if len(tokens) != 2 {
			t.Errorf("tokens length = %d, want 2", len(tokens))
		}
		if tokens["alice"] != "token-for-alice" {
			t.Errorf("tokens[alice] = %q", tokens["alice"])
		}
		if tokens["bob"] != "token-for-bob" {
			t.Errorf("tokens[bob] = %q", tokens["bob"])
		}
	})

	t.Run("empty audiences", func(t *testing.T) {
		http := newHTTPClient("http://localhost", DefaultTimeout)
		auth := newAuthResource(http)

		tokens, err := auth.GetSatelliteTokens(context.Background(), []string{})
		if err != nil {
			t.Fatalf("GetSatelliteTokens error: %v", err)
		}
		if len(tokens) != 0 {
			t.Errorf("tokens length = %d, want 0", len(tokens))
		}
	})
}

func TestAuthResourceGetPeerToken(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/peer-token" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "POST" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)
		usernames := body["target_usernames"].([]interface{})
		if len(usernames) != 2 {
			t.Errorf("target_usernames length = %d", len(usernames))
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"peer_token":   "peer-token-123",
			"peer_channel": "syfthub.peer.abc123",
			"expires_in":   300,
			"nats_url":     "wss://nats.example.com",
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	auth := newAuthResource(http)

	resp, err := auth.GetPeerToken(context.Background(), []string{"alice", "bob"})
	if err != nil {
		t.Fatalf("GetPeerToken error: %v", err)
	}
	if resp.PeerToken != "peer-token-123" {
		t.Errorf("PeerToken = %q", resp.PeerToken)
	}
	if resp.PeerChannel != "syfthub.peer.abc123" {
		t.Errorf("PeerChannel = %q", resp.PeerChannel)
	}
	if resp.NatsURL != "wss://nats.example.com" {
		t.Errorf("NatsURL = %q", resp.NatsURL)
	}
}

func TestAuthResourceGetTransactionTokens(t *testing.T) {
	t.Run("successful fetch", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/accounting/transaction-tokens" {
				t.Errorf("path = %s", r.URL.Path)
			}

			json.NewEncoder(w).Encode(map[string]interface{}{
				"tokens": map[string]string{
					"alice": "tx-token-alice",
					"bob":   "tx-token-bob",
				},
			})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		auth := newAuthResource(http)

		resp, err := auth.GetTransactionTokens(context.Background(), []string{"alice", "bob", "alice"})
		if err != nil {
			t.Fatalf("GetTransactionTokens error: %v", err)
		}
		if resp.Tokens["alice"] != "tx-token-alice" {
			t.Errorf("Tokens[alice] = %q", resp.Tokens["alice"])
		}
	})

	t.Run("empty owners", func(t *testing.T) {
		http := newHTTPClient("http://localhost", DefaultTimeout)
		auth := newAuthResource(http)

		resp, err := auth.GetTransactionTokens(context.Background(), []string{})
		if err != nil {
			t.Fatalf("GetTransactionTokens error: %v", err)
		}
		if len(resp.Tokens) != 0 {
			t.Errorf("Tokens length = %d, want 0", len(resp.Tokens))
		}
	})

	t.Run("handles server error gracefully", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
		auth := newAuthResource(http)

		resp, err := auth.GetTransactionTokens(context.Background(), []string{"alice"})
		// Should not return error, just empty tokens
		if err != nil {
			t.Fatalf("GetTransactionTokens error: %v", err)
		}
		if len(resp.Tokens) != 0 {
			t.Errorf("Tokens should be empty on error")
		}
	})
}
