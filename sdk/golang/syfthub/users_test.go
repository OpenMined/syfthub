package syfthub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestUsersResourceUpdate(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/users/me" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Method != "PUT" {
			t.Errorf("method = %s", r.Method)
		}

		var body map[string]interface{}
		json.NewDecoder(r.Body).Decode(&body)

		if body["full_name"] != "Updated Name" {
			t.Errorf("full_name = %v", body["full_name"])
		}
		if body["avatar_url"] != "https://example.com/new-avatar.png" {
			t.Errorf("avatar_url = %v", body["avatar_url"])
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"id":         1,
			"username":   "testuser",
			"email":      "test@example.com",
			"full_name":  "Updated Name",
			"avatar_url": "https://example.com/new-avatar.png",
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	users := newUsersResource(http)

	fullName := "Updated Name"
	avatarURL := "https://example.com/new-avatar.png"
	user, err := users.Update(context.Background(), &UpdateUserRequest{
		FullName:  &fullName,
		AvatarURL: &avatarURL,
	})

	if err != nil {
		t.Fatalf("Update error: %v", err)
	}
	if user.FullName != "Updated Name" {
		t.Errorf("FullName = %q", user.FullName)
	}
}

func TestUsersResourceCheckUsername(t *testing.T) {
	t.Run("available username", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/check-username/newuser" {
				t.Errorf("path = %s", r.URL.Path)
			}
			json.NewEncoder(w).Encode(map[string]bool{"available": true})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		users := newUsersResource(http)

		available, err := users.CheckUsername(context.Background(), "newuser")
		if err != nil {
			t.Fatalf("CheckUsername error: %v", err)
		}
		if !available {
			t.Error("should be available")
		}
	})

	t.Run("taken username", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]bool{"available": false})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		users := newUsersResource(http)

		available, err := users.CheckUsername(context.Background(), "existinguser")
		if err != nil {
			t.Fatalf("CheckUsername error: %v", err)
		}
		if available {
			t.Error("should not be available")
		}
	})
}

func TestUsersResourceCheckEmail(t *testing.T) {
	t.Run("available email", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/users/check-email/new@example.com" {
				t.Errorf("path = %s", r.URL.Path)
			}
			json.NewEncoder(w).Encode(map[string]bool{"available": true})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		users := newUsersResource(http)

		available, err := users.CheckEmail(context.Background(), "new@example.com")
		if err != nil {
			t.Fatalf("CheckEmail error: %v", err)
		}
		if !available {
			t.Error("should be available")
		}
	})

	t.Run("taken email", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]bool{"available": false})
		}))
		defer server.Close()

		http := newHTTPClient(server.URL, DefaultTimeout)
		users := newUsersResource(http)

		available, err := users.CheckEmail(context.Background(), "existing@example.com")
		if err != nil {
			t.Fatalf("CheckEmail error: %v", err)
		}
		if available {
			t.Error("should not be available")
		}
	})
}

func TestUsersResourceGetAccountingCredentials(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/users/me/accounting" {
			t.Errorf("path = %s", r.URL.Path)
		}

		url := "https://accounting.example.com"
		password := "acctpass"
		json.NewEncoder(w).Encode(map[string]interface{}{
			"url":      url,
			"email":    "user@example.com",
			"password": password,
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	users := newUsersResource(http)

	creds, err := users.GetAccountingCredentials(context.Background())
	if err != nil {
		t.Fatalf("GetAccountingCredentials error: %v", err)
	}
	if creds.Email != "user@example.com" {
		t.Errorf("Email = %q", creds.Email)
	}
	if creds.URL == nil || *creds.URL != "https://accounting.example.com" {
		t.Errorf("URL = %v", creds.URL)
	}
}

func TestUsersResourceGetNatsCredentials(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/nats/credentials" {
			t.Errorf("path = %s", r.URL.Path)
		}

		json.NewEncoder(w).Encode(map[string]interface{}{
			"nats_auth_token": "nats-token-123",
		})
	}))
	defer server.Close()

	http := newHTTPClient(server.URL, DefaultTimeout)
	http.SetTokens(&AuthTokens{AccessToken: "test", RefreshToken: "test"})
	users := newUsersResource(http)

	creds, err := users.GetNatsCredentials(context.Background())
	if err != nil {
		t.Fatalf("GetNatsCredentials error: %v", err)
	}
	if creds.NatsAuthToken != "nats-token-123" {
		t.Errorf("NatsAuthToken = %q", creds.NatsAuthToken)
	}
}

func TestUsersResourceAggregatorsSubresource(t *testing.T) {
	http := newHTTPClient("http://localhost", DefaultTimeout)
	users := newUsersResource(http)

	if users.Aggregators == nil {
		t.Error("Aggregators should be initialized")
	}
}
