package setupflow_test

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow/handlers"
)

// TestIntegration_TelegramBotSetup simulates a Telegram bot setup flow:
// 1. prompt(token) → http(verify) → http(webhook)
// 2. Mock IO returns "123456:ABC-DEF"
// 3. Mock HTTP server for api.telegram.org
// 4. Verify .env contains TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_USERNAME
// 5. Verify .setup-state.json has all steps completed
func TestIntegration_TelegramBotSetup(t *testing.T) {
	// Create mock Telegram API server
	telegramServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		switch {
		case r.URL.Path == "/bot123456:ABC-DEF/getMe":
			json.NewEncoder(w).Encode(map[string]any{
				"ok": true,
				"result": map[string]any{
					"id":         12345,
					"is_bot":     true,
					"first_name": "TestBot",
					"username":   "test_bot",
				},
			})
		case r.URL.Path == "/bot123456:ABC-DEF/setWebhook":
			json.NewEncoder(w).Encode(map[string]any{
				"ok":          true,
				"result":      true,
				"description": "Webhook was set",
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			fmt.Fprintf(w, `{"ok":false,"description":"not found: %s"}`, r.URL.Path)
		}
	}))
	defer telegramServer.Close()

	// Create temp directory for endpoint
	dir := t.TempDir()

	// Write setup.yaml
	setupYaml := fmt.Sprintf(`version: "1"
steps:
  - id: bot_token
    type: prompt
    name: "Enter Bot Token"
    required: true
    prompt:
      message: "Enter your Telegram Bot Token"
      env_key: "TELEGRAM_BOT_TOKEN"
    outputs:
      TELEGRAM_BOT_TOKEN: "{{value}}"

  - id: verify_bot
    type: http
    name: "Verify Bot Token"
    required: true
    depends_on: [bot_token]
    http:
      method: GET
      url: "%s/bot{{steps.bot_token.value}}/getMe"
      expect_status: 200
    outputs:
      TELEGRAM_BOT_USERNAME: "{{response.result.username}}"

  - id: set_webhook
    type: http
    name: "Set Webhook"
    required: true
    depends_on: [verify_bot]
    http:
      method: POST
      url: "%s/bot{{steps.bot_token.value}}/setWebhook"
      json:
        url: "https://example.com/webhook"
      expect_status: 200
`, telegramServer.URL, telegramServer.URL)

	if err := os.WriteFile(filepath.Join(dir, "setup.yaml"), []byte(setupYaml), 0644); err != nil {
		t.Fatalf("failed to write setup.yaml: %v", err)
	}

	// Create engine with all handlers
	engine := setupflow.NewEngine(
		setupflow.WithHandler("prompt", &handlers.PromptHandler{}),
		setupflow.WithHandler("select", &handlers.SelectHandler{}),
		setupflow.WithHandler("http", handlers.NewHTTPHandler()),
		setupflow.WithHandler("template", &handlers.TemplateHandler{}),
	)

	// Parse spec
	spec, err := nodeops.ParseSetupYaml(filepath.Join(dir, "setup.yaml"))
	if err != nil {
		t.Fatalf("failed to parse setup.yaml: %v", err)
	}

	// Create mock IO that returns the bot token
	mockIO := &MockSetupIO{
		PromptResponses: []string{"123456:ABC-DEF"},
	}

	state := &nodeops.SetupState{Version: "1", Steps: map[string]nodeops.StepState{}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		Slug:        "telegram-bot",
		HubURL:      "https://hub.example.com",
		IO:          mockIO,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       state,
		Spec:        spec,
	}

	// Execute
	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("engine.Execute failed: %v", err)
	}

	// Verify .env contains expected values
	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	envMap := make(map[string]string)
	for _, ev := range envVars {
		envMap[ev.Key] = ev.Value
	}

	if envMap["TELEGRAM_BOT_TOKEN"] != "123456:ABC-DEF" {
		t.Errorf("expected TELEGRAM_BOT_TOKEN='123456:ABC-DEF', got '%s'", envMap["TELEGRAM_BOT_TOKEN"])
	}
	if envMap["TELEGRAM_BOT_USERNAME"] != "test_bot" {
		t.Errorf("expected TELEGRAM_BOT_USERNAME='test_bot', got '%s'", envMap["TELEGRAM_BOT_USERNAME"])
	}

	// Verify .setup-state.json has all steps completed
	savedState, err := nodeops.ReadSetupState(dir)
	if err != nil {
		t.Fatalf("failed to read setup state: %v", err)
	}
	for _, stepID := range []string{"bot_token", "verify_bot", "set_webhook"} {
		ss, ok := savedState.Steps[stepID]
		if !ok {
			t.Errorf("step '%s' not found in state", stepID)
			continue
		}
		if ss.Status != "completed" {
			t.Errorf("step '%s' status = '%s', want 'completed'", stepID, ss.Status)
		}
	}
}

// TestIntegration_OAuthThenSelect simulates an OAuth + Select flow:
// 1. setup.yaml with: oauth2(google) → http(list files) → select(pick folder)
// 2. Uses template handler instead of full OAuth (can't test browser flow in unit tests)
// 3. Mock Google Drive API
// 4. Mock IO selects an option
// 5. Verify .env contains access_token and selected folder ID
func TestIntegration_OAuthThenSelect(t *testing.T) {
	// Create mock Google Drive API
	driveServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		// Verify authorization header
		auth := r.Header.Get("Authorization")
		if auth != "Bearer mock-access-token" {
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]any{
				"error": map[string]any{
					"message": "invalid token",
					"code":    401,
				},
			})
			return
		}

		json.NewEncoder(w).Encode(map[string]any{
			"files": []map[string]any{
				{"id": "folder-aaa", "name": "Project Alpha"},
				{"id": "folder-bbb", "name": "Project Beta"},
				{"id": "folder-ccc", "name": "Project Gamma"},
			},
		})
	}))
	defer driveServer.Close()

	dir := t.TempDir()

	// Write setup.yaml — use template step to simulate OAuth result
	// (can't do real OAuth in tests; template step provides the token value)
	setupYaml := fmt.Sprintf(`version: "1"
steps:
  - id: google_auth
    type: template
    name: "Google Auth Token"
    required: true
    template:
      value: "mock-access-token"
    outputs:
      GOOGLE_ACCESS_TOKEN: "{{value}}"

  - id: list_folders
    type: http
    name: "List Drive Folders"
    required: true
    depends_on: [google_auth]
    http:
      method: GET
      url: "%s/drive/v3/files"
      headers:
        Authorization: "Bearer {{steps.google_auth.value}}"
      expect_status: 200

  - id: pick_folder
    type: select
    name: "Select Folder"
    required: true
    depends_on: [list_folders]
    select:
      options_from:
        step_id: list_folders
        path: files
        value_field: id
        label_field: name
    outputs:
      GOOGLE_DRIVE_FOLDER_ID: "{{value}}"
`, driveServer.URL)

	if err := os.WriteFile(filepath.Join(dir, "setup.yaml"), []byte(setupYaml), 0644); err != nil {
		t.Fatalf("failed to write setup.yaml: %v", err)
	}

	engine := setupflow.NewEngine(
		setupflow.WithHandler("prompt", &handlers.PromptHandler{}),
		setupflow.WithHandler("select", &handlers.SelectHandler{}),
		setupflow.WithHandler("http", handlers.NewHTTPHandler()),
		setupflow.WithHandler("template", &handlers.TemplateHandler{}),
	)

	spec, err := nodeops.ParseSetupYaml(filepath.Join(dir, "setup.yaml"))
	if err != nil {
		t.Fatalf("failed to parse setup.yaml: %v", err)
	}

	// Mock IO: select the second folder (folder-bbb)
	mockIO := &MockSetupIO{
		SelectResponses: []string{"folder-bbb"},
	}

	state := &nodeops.SetupState{Version: "1", Steps: map[string]nodeops.StepState{}}
	ctx := &setupflow.SetupContext{
		EndpointDir: dir,
		Slug:        "google-drive-connector",
		HubURL:      "https://hub.example.com",
		IO:          mockIO,
		StepOutputs: make(map[string]*setupflow.StepResult),
		State:       state,
		Spec:        spec,
	}

	if err := engine.Execute(ctx); err != nil {
		t.Fatalf("engine.Execute failed: %v", err)
	}

	// Verify .env
	envVars, _ := nodeops.ReadEnvFile(filepath.Join(dir, ".env"))
	envMap := make(map[string]string)
	for _, ev := range envVars {
		envMap[ev.Key] = ev.Value
	}

	if envMap["GOOGLE_ACCESS_TOKEN"] != "mock-access-token" {
		t.Errorf("expected GOOGLE_ACCESS_TOKEN='mock-access-token', got '%s'", envMap["GOOGLE_ACCESS_TOKEN"])
	}
	if envMap["GOOGLE_DRIVE_FOLDER_ID"] != "folder-bbb" {
		t.Errorf("expected GOOGLE_DRIVE_FOLDER_ID='folder-bbb', got '%s'", envMap["GOOGLE_DRIVE_FOLDER_ID"])
	}

	// Verify state
	savedState, err := nodeops.ReadSetupState(dir)
	if err != nil {
		t.Fatalf("failed to read setup state: %v", err)
	}
	for _, stepID := range []string{"google_auth", "list_folders", "pick_folder"} {
		ss, ok := savedState.Steps[stepID]
		if !ok {
			t.Errorf("step '%s' not found in state", stepID)
			continue
		}
		if ss.Status != "completed" {
			t.Errorf("step '%s' status = '%s', want 'completed'", stepID, ss.Status)
		}
	}
}
