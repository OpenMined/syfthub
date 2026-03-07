package setupflow_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
)

func TestLifecycle_NoSetupYaml(t *testing.T) {
	dir := t.TempDir()
	os.MkdirAll(filepath.Join(dir, "my-endpoint"), 0755)

	mgr := setupflow.NewLifecycleManager(setupflow.NewEngine())
	results := mgr.CheckAndRefresh(dir)

	if len(results) != 0 {
		t.Errorf("expected 0 results for endpoint without setup.yaml, got %d", len(results))
	}
}

func TestLifecycle_NoLifecycleConfig(t *testing.T) {
	dir := t.TempDir()
	epDir := filepath.Join(dir, "my-endpoint")
	os.MkdirAll(epDir, 0755)

	// Write setup.yaml without lifecycle section
	yaml := `version: "1"
steps:
  - id: token
    type: prompt
    name: "Enter token"
    required: true
    prompt:
      message: "Token"
`
	os.WriteFile(filepath.Join(epDir, "setup.yaml"), []byte(yaml), 0644)

	mgr := setupflow.NewLifecycleManager(setupflow.NewEngine())
	results := mgr.CheckAndRefresh(dir)

	if len(results) != 0 {
		t.Errorf("expected 0 results for endpoint without lifecycle config, got %d", len(results))
	}
}

func TestLifecycle_NotExpired(t *testing.T) {
	dir := t.TempDir()
	epDir := filepath.Join(dir, "my-endpoint")
	os.MkdirAll(epDir, 0755)

	yaml := `version: "1"
steps:
  - id: auth
    type: oauth2
    name: "Authenticate"
    required: true
    oauth2:
      auth_url: "https://example.com/auth"
      token_url: "https://example.com/token"
    outputs:
      ACCESS_TOKEN: "{{response.access_token}}"
      REFRESH_TOKEN: "{{response.refresh_token}}"
lifecycle:
  refresh:
    trigger: token_expiry
    steps: [auth]
    strategy: refresh_token
`
	os.WriteFile(filepath.Join(epDir, "setup.yaml"), []byte(yaml), 0644)

	// State with future expiry (1 hour from now)
	state := &nodeops.SetupState{
		Version: "1",
		Steps: map[string]nodeops.StepState{
			"auth": {
				Status:      "completed",
				CompletedAt: time.Now().Format(time.RFC3339),
				ExpiresAt:   time.Now().Add(1 * time.Hour).Format(time.RFC3339),
			},
		},
	}
	nodeops.WriteSetupState(epDir, state)

	mgr := setupflow.NewLifecycleManager(setupflow.NewEngine())
	results := mgr.CheckAndRefresh(dir)

	if len(results) != 0 {
		t.Errorf("expected 0 results for non-expired token, got %d", len(results))
	}
}

func TestLifecycle_RefreshExpiredToken(t *testing.T) {
	// Create a mock token server
	tokenServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		r.ParseForm()
		if r.Form.Get("grant_type") != "refresh_token" {
			t.Errorf("expected grant_type=refresh_token, got %s", r.Form.Get("grant_type"))
		}
		if r.Form.Get("refresh_token") != "old-refresh-token" {
			t.Errorf("expected refresh_token=old-refresh-token, got %s", r.Form.Get("refresh_token"))
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"access_token":  "new-access-token",
			"refresh_token": "new-refresh-token",
			"expires_in":    3600,
		})
	}))
	defer tokenServer.Close()

	dir := t.TempDir()
	epDir := filepath.Join(dir, "my-endpoint")
	os.MkdirAll(epDir, 0755)

	yaml := `version: "1"
steps:
  - id: auth
    type: oauth2
    name: "Authenticate"
    required: true
    oauth2:
      auth_url: "https://example.com/auth"
      token_url: "` + tokenServer.URL + `"
      client_id: "test-client-id"
      client_secret: "test-client-secret"
    outputs:
      ACCESS_TOKEN: "{{response.access_token}}"
      REFRESH_TOKEN: "{{response.refresh_token}}"
lifecycle:
  refresh:
    trigger: token_expiry
    steps: [auth]
    strategy: refresh_token
`
	os.WriteFile(filepath.Join(epDir, "setup.yaml"), []byte(yaml), 0644)

	// Write initial .env with old tokens
	nodeops.WriteEnvFile(filepath.Join(epDir, ".env"), []nodeops.EnvVar{
		{Key: "ACCESS_TOKEN", Value: "old-access-token"},
		{Key: "REFRESH_TOKEN", Value: "old-refresh-token"},
	})

	// State with past expiry (expired 10 minutes ago)
	state := &nodeops.SetupState{
		Version: "1",
		Steps: map[string]nodeops.StepState{
			"auth": {
				Status:      "completed",
				CompletedAt: time.Now().Add(-1 * time.Hour).Format(time.RFC3339),
				ExpiresAt:   time.Now().Add(-10 * time.Minute).Format(time.RFC3339),
			},
		},
	}
	nodeops.WriteSetupState(epDir, state)

	mgr := setupflow.NewLifecycleManager(setupflow.NewEngine())
	results := mgr.CheckAndRefresh(dir)

	if len(results) != 1 {
		t.Fatalf("expected 1 result, got %d", len(results))
	}
	if !results[0].Success {
		t.Fatalf("expected success, got error: %v", results[0].Error)
	}
	if results[0].StepID != "auth" {
		t.Errorf("expected stepID 'auth', got '%s'", results[0].StepID)
	}

	// Verify .env was updated
	envVars, _ := nodeops.ReadEnvFile(filepath.Join(epDir, ".env"))
	envMap := make(map[string]string)
	for _, ev := range envVars {
		envMap[ev.Key] = ev.Value
	}

	if envMap["ACCESS_TOKEN"] != "new-access-token" {
		t.Errorf("expected ACCESS_TOKEN='new-access-token', got '%s'", envMap["ACCESS_TOKEN"])
	}
	if envMap["REFRESH_TOKEN"] != "new-refresh-token" {
		t.Errorf("expected REFRESH_TOKEN='new-refresh-token', got '%s'", envMap["REFRESH_TOKEN"])
	}

	// Verify state was updated
	savedState, _ := nodeops.ReadSetupState(epDir)
	ss := savedState.Steps["auth"]
	if ss.Status != "completed" {
		t.Errorf("expected status 'completed', got '%s'", ss.Status)
	}
	if ss.ExpiresAt == "" {
		t.Error("expected non-empty expires_at after refresh")
	}
	// New expiry should be in the future
	newExpiry, _ := time.Parse(time.RFC3339, ss.ExpiresAt)
	if newExpiry.Before(time.Now()) {
		t.Error("expected new expiry to be in the future")
	}
}

func TestLifecycle_FullReauthSkipped(t *testing.T) {
	dir := t.TempDir()
	epDir := filepath.Join(dir, "my-endpoint")
	os.MkdirAll(epDir, 0755)

	yaml := `version: "1"
steps:
  - id: auth
    type: oauth2
    name: "Authenticate"
    required: true
    oauth2:
      auth_url: "https://example.com/auth"
      token_url: "https://example.com/token"
lifecycle:
  refresh:
    trigger: token_expiry
    steps: [auth]
    strategy: full_reauth
`
	os.WriteFile(filepath.Join(epDir, "setup.yaml"), []byte(yaml), 0644)

	state := &nodeops.SetupState{
		Version: "1",
		Steps: map[string]nodeops.StepState{
			"auth": {
				Status:    "completed",
				ExpiresAt: time.Now().Add(-10 * time.Minute).Format(time.RFC3339),
			},
		},
	}
	nodeops.WriteSetupState(epDir, state)

	mgr := setupflow.NewLifecycleManager(setupflow.NewEngine())
	results := mgr.CheckAndRefresh(dir)

	// full_reauth strategy should be skipped (requires user interaction)
	if len(results) != 0 {
		t.Errorf("expected 0 results for full_reauth strategy, got %d", len(results))
	}
}

func TestLifecycle_RefreshTokenNotFound(t *testing.T) {
	dir := t.TempDir()
	epDir := filepath.Join(dir, "my-endpoint")
	os.MkdirAll(epDir, 0755)

	yaml := `version: "1"
steps:
  - id: auth
    type: oauth2
    name: "Authenticate"
    required: true
    oauth2:
      auth_url: "https://example.com/auth"
      token_url: "https://example.com/token"
    outputs:
      ACCESS_TOKEN: "{{response.access_token}}"
lifecycle:
  refresh:
    trigger: token_expiry
    steps: [auth]
    strategy: refresh_token
`
	os.WriteFile(filepath.Join(epDir, "setup.yaml"), []byte(yaml), 0644)

	// Write .env without any refresh token
	nodeops.WriteEnvFile(filepath.Join(epDir, ".env"), []nodeops.EnvVar{
		{Key: "ACCESS_TOKEN", Value: "some-token"},
	})

	state := &nodeops.SetupState{
		Version: "1",
		Steps: map[string]nodeops.StepState{
			"auth": {
				Status:    "completed",
				ExpiresAt: time.Now().Add(-10 * time.Minute).Format(time.RFC3339),
			},
		},
	}
	nodeops.WriteSetupState(epDir, state)

	mgr := setupflow.NewLifecycleManager(setupflow.NewEngine())
	results := mgr.CheckAndRefresh(dir)

	if len(results) != 1 {
		t.Fatalf("expected 1 result, got %d", len(results))
	}
	if results[0].Success {
		t.Error("expected failure when refresh token not found")
	}
	if results[0].Error == nil {
		t.Error("expected error when refresh token not found")
	}
}

func TestLifecycle_MultipleEndpoints(t *testing.T) {
	dir := t.TempDir()

	// Create two endpoints, only one has setup.yaml
	os.MkdirAll(filepath.Join(dir, "ep-with-setup"), 0755)
	os.MkdirAll(filepath.Join(dir, "ep-without-setup"), 0755)

	yaml := `version: "1"
steps:
  - id: token
    type: prompt
    name: "Enter token"
    required: true
    prompt:
      message: "Token"
`
	os.WriteFile(filepath.Join(dir, "ep-with-setup", "setup.yaml"), []byte(yaml), 0644)

	mgr := setupflow.NewLifecycleManager(setupflow.NewEngine())
	results := mgr.CheckAndRefresh(dir)

	// Neither endpoint should produce results (no lifecycle config / no setup.yaml)
	if len(results) != 0 {
		t.Errorf("expected 0 results, got %d", len(results))
	}
}
