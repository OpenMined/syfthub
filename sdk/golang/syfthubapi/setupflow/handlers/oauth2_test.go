package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

func TestOAuth2_Validate_MissingAuthURL(t *testing.T) {
	h := &OAuth2Handler{}
	step := &nodeops.SetupStep{
		OAuth2: &nodeops.OAuth2Config{TokenURL: "https://example.com/token"},
	}
	if err := h.Validate(step); err == nil {
		t.Fatal("expected error for missing auth_url")
	}
}

func TestOAuth2_Validate_MissingTokenURL(t *testing.T) {
	h := &OAuth2Handler{}
	step := &nodeops.SetupStep{
		OAuth2: &nodeops.OAuth2Config{AuthURL: "https://example.com/auth"},
	}
	if err := h.Validate(step); err == nil {
		t.Fatal("expected error for missing token_url")
	}
}

func TestOAuth2_Execute_FullFlow(t *testing.T) {
	// Create mock token endpoint
	tokenServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			t.Errorf("expected POST, got %s", r.Method)
		}
		r.ParseForm()
		if r.Form.Get("grant_type") != "authorization_code" {
			t.Errorf("expected grant_type=authorization_code")
		}
		if r.Form.Get("code") == "" {
			t.Error("expected code parameter")
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"access_token":  "test_access_token",
			"refresh_token": "test_refresh_token",
			"expires_in":    3600,
			"token_type":    "bearer",
		})
	}))
	defer tokenServer.Close()

	// Create mock auth endpoint (just to have a valid URL)
	authServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Real flow would redirect, but we simulate the callback directly
	}))
	defer authServer.Close()

	h := &OAuth2Handler{}
	step := &nodeops.SetupStep{
		ID:   "oauth",
		Name: "Test OAuth",
		OAuth2: &nodeops.OAuth2Config{
			AuthURL:      authServer.URL + "/auth",
			TokenURL:     tokenServer.URL + "/token",
			Scopes:       []string{"read", "write"},
			ClientID:     "test-client-id",
			ClientSecret: "test-client-secret",
		},
	}

	// We can't fully test the browser flow in unit tests.
	// Instead, test the individual components.

	// Test buildAuthURL
	authURL, err := buildAuthURL(step.OAuth2, "test-client-id", "http://localhost:12345/callback", "test-state")
	if err != nil {
		t.Fatalf("buildAuthURL error: %v", err)
	}
	if authURL == "" {
		t.Fatal("expected non-empty auth URL")
	}

	// Test exchangeToken
	tokenResp, err := exchangeToken(tokenServer.URL+"/token", "test-code", "http://localhost:12345/callback", "test-client-id", "test-client-secret")
	if err != nil {
		t.Fatalf("exchangeToken error: %v", err)
	}

	var tokenData map[string]any
	if err := json.Unmarshal(tokenResp, &tokenData); err != nil {
		t.Fatalf("failed to parse token response: %v", err)
	}
	if tokenData["access_token"] != "test_access_token" {
		t.Errorf("expected access_token=test_access_token, got %v", tokenData["access_token"])
	}

	_ = h
	_ = step
}

func TestOAuth2_Execute_ClientCredFromEnv(t *testing.T) {
	dir := t.TempDir()

	// Write client credentials to .env
	nodeops.WriteEnvFile(dir+"/.env", []nodeops.EnvVar{
		{Key: "GOOGLE_CLIENT_ID", Value: "env-client-id"},
		{Key: "GOOGLE_CLIENT_SECRET", Value: "env-client-secret"},
	})

	mockIO := &testIO{promptResponses: []string{}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		IO:          mockIO,
		StepOutputs: make(map[string]*setupflow.StepResult),
	}

	clientID, err := resolveClientCredential("", "GOOGLE_CLIENT_ID", "Client ID", "test", ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if clientID != "env-client-id" {
		t.Errorf("expected 'env-client-id', got '%s'", clientID)
	}
}

func TestOAuth2_Execute_ExpiresIn(t *testing.T) {
	tokenServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"access_token": "tok",
			"expires_in":   7200,
		})
	}))
	defer tokenServer.Close()

	resp, err := exchangeToken(tokenServer.URL, "code", "http://localhost/cb", "id", "secret")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var data map[string]any
	json.Unmarshal(resp, &data)
	if data["expires_in"].(float64) != 7200 {
		t.Errorf("expected expires_in=7200")
	}
}
