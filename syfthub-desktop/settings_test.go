package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestDefaultSettings(t *testing.T) {
	settings := DefaultSettings()

	if settings == nil {
		t.Fatal("DefaultSettings returned nil")
	}
	if settings.HubURL != "https://syfthub.openmined.org" {
		t.Errorf("HubURL = %q, want %q", settings.HubURL, "https://syfthub.openmined.org")
	}
	if settings.APIToken != "" {
		t.Errorf("APIKey should be empty by default, got %q", settings.APIToken)
	}
	if settings.Port != 8000 {
		t.Errorf("Port = %d, want 8000", settings.Port)
	}
	if !filepath.IsAbs(settings.EndpointsPath) || filepath.Base(settings.EndpointsPath) != "endpoints" {
		t.Errorf("EndpointsPath = %q, want absolute path ending in 'endpoints'", settings.EndpointsPath)
	}
	if settings.IsConfigured {
		t.Error("IsConfigured should be false by default")
	}
	if settings.Timeout != 30.0 {
		t.Errorf("Timeout = %f, want 30.0", settings.Timeout)
	}
	if settings.LogLevel != "INFO" {
		t.Errorf("LogLevel = %q, want %q", settings.LogLevel, "INFO")
	}
	if settings.ContainerEnabled {
		t.Error("ContainerEnabled should be false by default")
	}
}

func TestGetSettingsDir(t *testing.T) {
	dir, err := getSettingsDir()
	if err != nil {
		t.Fatalf("getSettingsDir error: %v", err)
	}

	if dir == "" {
		t.Error("getSettingsDir returned empty string")
	}

	// Check that it ends with syfthub
	if filepath.Base(dir) != "syfthub" {
		t.Errorf("dir = %q, should end with 'syfthub'", dir)
	}

	// Platform-specific checks
	switch runtime.GOOS {
	case "darwin":
		if !strings.Contains(dir, "Library/Application Support") {
			t.Errorf("macOS dir = %q, should contain 'Library/Application Support'", dir)
		}
	case "linux":
		if !strings.Contains(dir, ".config") && os.Getenv("XDG_CONFIG_HOME") == "" {
			t.Errorf("Linux dir = %q, should contain '.config' or use XDG_CONFIG_HOME", dir)
		}
	case "windows":
		// Windows should use APPDATA or fallback
		if !strings.Contains(dir, "AppData") && os.Getenv("APPDATA") == "" {
			t.Errorf("Windows dir = %q, should contain 'AppData'", dir)
		}
	}
}

func TestGetSettingsPath(t *testing.T) {
	path, err := getSettingsPath()
	if err != nil {
		t.Fatalf("getSettingsPath error: %v", err)
	}

	if path == "" {
		t.Error("getSettingsPath returned empty string")
	}

	if filepath.Base(path) != "settings.json" {
		t.Errorf("path = %q, should end with 'settings.json'", path)
	}
}

func TestGetDefaultEndpointsPath(t *testing.T) {
	path, err := getDefaultEndpointsPath()
	if err != nil {
		t.Fatalf("getDefaultEndpointsPath error: %v", err)
	}

	if path == "" {
		t.Error("getDefaultEndpointsPath returned empty string")
	}

	if filepath.Base(path) != "endpoints" {
		t.Errorf("path = %q, should end with 'endpoints'", path)
	}
}

func TestSaveAndLoadSettings(t *testing.T) {
	// Create a temp directory for testing
	tempDir := t.TempDir()

	// Override the settings dir for testing
	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	if runtime.GOOS != "windows" {
		os.Setenv("XDG_CONFIG_HOME", tempDir)
		defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)
	} else {
		// On Windows, use APPDATA
		origAppData := os.Getenv("APPDATA")
		os.Setenv("APPDATA", tempDir)
		defer os.Setenv("APPDATA", origAppData)
	}

	// Create test settings
	settings := &Settings{
		HubURL: "https://test.example.com",
		APIToken: "test-api-key",
		EndpointsPath: "/custom/endpoints",
		IsConfigured:  true,
	}

	// Save settings
	err := SaveSettings(settings)
	if err != nil {
		t.Fatalf("SaveSettings error: %v", err)
	}

	// Load settings back
	loaded, err := LoadSettings()
	if err != nil {
		t.Fatalf("LoadSettings error: %v", err)
	}

	if loaded.HubURL != settings.HubURL {
		t.Errorf("SyftHubURL = %q, want %q", loaded.HubURL, settings.HubURL)
	}
	if loaded.APIToken != settings.APIToken {
		t.Errorf("APIKey = %q, want %q", loaded.APIToken, settings.APIToken)
	}
	if loaded.EndpointsPath != settings.EndpointsPath {
		t.Errorf("EndpointsPath = %q, want %q", loaded.EndpointsPath, settings.EndpointsPath)
	}
	if loaded.IsConfigured != settings.IsConfigured {
		t.Errorf("IsConfigured = %v, want %v", loaded.IsConfigured, settings.IsConfigured)
	}
}

func TestLoadSettingsNoFile(t *testing.T) {
	// Create a temp directory for testing
	tempDir := t.TempDir()

	// Override the settings dir for testing
	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	if runtime.GOOS != "windows" {
		os.Setenv("XDG_CONFIG_HOME", tempDir)
		defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)
	} else {
		origAppData := os.Getenv("APPDATA")
		os.Setenv("APPDATA", tempDir)
		defer os.Setenv("APPDATA", origAppData)
	}

	// Load settings when file doesn't exist
	loaded, err := LoadSettings()
	if err != nil {
		t.Fatalf("LoadSettings should not error on missing file: %v", err)
	}

	// Should return default settings
	defaults := DefaultSettings()
	if loaded.HubURL != defaults.HubURL {
		t.Errorf("SyftHubURL = %q, want default %q", loaded.HubURL, defaults.HubURL)
	}
}

func TestLoadSettingsInvalidJSON(t *testing.T) {
	// Create a temp directory for testing
	tempDir := t.TempDir()

	// Override the settings dir for testing
	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	if runtime.GOOS != "windows" {
		os.Setenv("XDG_CONFIG_HOME", tempDir)
		defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)
	} else {
		origAppData := os.Getenv("APPDATA")
		os.Setenv("APPDATA", tempDir)
		defer os.Setenv("APPDATA", origAppData)
	}

	// Create settings directory and invalid JSON file
	settingsDir := filepath.Join(tempDir, "syfthub")
	os.MkdirAll(settingsDir, 0755)
	settingsFile := filepath.Join(settingsDir, "settings.json")
	os.WriteFile(settingsFile, []byte("invalid json {"), 0644)

	// Load settings - should return defaults with error
	loaded, err := LoadSettings()
	if err == nil {
		t.Error("LoadSettings should return error for invalid JSON")
	}

	// Should still return default settings
	if loaded == nil {
		t.Fatal("LoadSettings should return default settings even on error")
	}
}

func TestSettingsExist(t *testing.T) {
	// Create a temp directory for testing
	tempDir := t.TempDir()

	// Override the settings dir for testing
	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	if runtime.GOOS != "windows" {
		os.Setenv("XDG_CONFIG_HOME", tempDir)
		defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)
	} else {
		origAppData := os.Getenv("APPDATA")
		os.Setenv("APPDATA", tempDir)
		defer os.Setenv("APPDATA", origAppData)
	}

	// Initially should not exist
	if SettingsExist() {
		t.Error("SettingsExist should return false when no settings file")
	}

	// Save settings
	SaveSettings(DefaultSettings())

	// Now should exist
	if !SettingsExist() {
		t.Error("SettingsExist should return true after saving settings")
	}
}

func TestResolveEndpointsPath(t *testing.T) {
	tests := []struct {
		name        string
		path        string
		wantAbs     bool
		wantContain string
	}{
		{
			name:    "absolute path",
			path:    "/usr/local/endpoints",
			wantAbs: true,
		},
		{
			name:        "relative path",
			path:        ".endpoints",
			wantContain: ".endpoints",
		},
		{
			name:        "relative path with subdir",
			path:        "my/custom/path",
			wantContain: "my/custom/path",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := resolveEndpointsPath(tt.path)
			if err != nil {
				t.Fatalf("resolveEndpointsPath error: %v", err)
			}

			if tt.wantAbs && !filepath.IsAbs(result) {
				// Absolute paths should stay absolute
				if tt.path != result {
					t.Errorf("result = %q, want %q", result, tt.path)
				}
			}

			if tt.wantContain != "" && !strings.Contains(result, tt.wantContain) {
				t.Errorf("result = %q, should contain %q", result, tt.wantContain)
			}
		})
	}
}

func TestEnsureEndpointsDir(t *testing.T) {
	tempDir := t.TempDir()

	// Override the settings dir
	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	if runtime.GOOS != "windows" {
		os.Setenv("XDG_CONFIG_HOME", tempDir)
		defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)
	} else {
		origAppData := os.Getenv("APPDATA")
		os.Setenv("APPDATA", tempDir)
		defer os.Setenv("APPDATA", origAppData)
	}

	// Test with relative path
	err := EnsureEndpointsDir(".endpoints")
	if err != nil {
		t.Fatalf("EnsureEndpointsDir error: %v", err)
	}

	// Verify the directory was created
	resolved, _ := resolveEndpointsPath(".endpoints")
	info, err := os.Stat(resolved)
	if err != nil {
		t.Fatalf("directory not created: %v", err)
	}
	if !info.IsDir() {
		t.Error("path should be a directory")
	}

	// Test with absolute path
	absPath := filepath.Join(tempDir, "custom-endpoints")
	err = EnsureEndpointsDir(absPath)
	if err != nil {
		t.Fatalf("EnsureEndpointsDir error for absolute path: %v", err)
	}

	info, err = os.Stat(absPath)
	if err != nil {
		t.Fatalf("directory not created: %v", err)
	}
	if !info.IsDir() {
		t.Error("path should be a directory")
	}
}

func TestSettingsJSON(t *testing.T) {
	settings := &Settings{
		HubURL:        "https://test.example.com",
		APIToken:      "my-api-key",
		EndpointsPath: "/path/to/endpoints",
		IsConfigured:  true,
	}

	// Marshal to JSON
	data, err := json.Marshal(settings)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	// Verify JSON structure
	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("json.Unmarshal error: %v", err)
	}

	if decoded["hub_url"] != settings.HubURL {
		t.Errorf("JSON hub_url = %v, want %v", decoded["hub_url"], settings.HubURL)
	}
	if decoded["api_token"] != settings.APIToken {
		t.Errorf("JSON api_token = %v, want %v", decoded["api_token"], settings.APIToken)
	}
	if decoded["endpoints_path"] != settings.EndpointsPath {
		t.Errorf("JSON endpoints_path = %v, want %v", decoded["endpoints_path"], settings.EndpointsPath)
	}
	if decoded["is_configured"] != settings.IsConfigured {
		t.Errorf("JSON is_configured = %v, want %v", decoded["is_configured"], settings.IsConfigured)
	}
}

func TestSettingsJSONSnakeCaseAllFields(t *testing.T) {
	settings := &Settings{
		HubURL:   "https://syfthub.openmined.org",
		APIToken: "token-123",
		Aggregators: map[string]AggregatorConfig{
			"default": {URL: "https://agg.example.com"},
		},
		AccountingServices: map[string]AccountingConfig{
			"primary": {URL: "https://acct.example.com"},
		},
		DefaultAggregator: "default",
		DefaultAccounting: "primary",
		Timeout:           45.0,
		EndpointsPath:     "/my/endpoints",
		IsConfigured:      true,
		MarketplaceURL:    "https://marketplace.example.com",
		LogLevel:          "DEBUG",
		PythonPath:        "/usr/bin/python3",
		Port:              9000,
		ContainerEnabled:  true,
		ContainerRuntime:  "docker",
		ContainerImage:    "syfthub/node:latest",
	}

	data, err := json.Marshal(settings)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("json.Unmarshal error: %v", err)
	}

	// Verify all snake_case keys exist with correct values
	tests := []struct {
		key  string
		want interface{}
	}{
		{"hub_url", "https://syfthub.openmined.org"},
		{"api_token", "token-123"},
		{"default_aggregator", "default"},
		{"default_accounting", "primary"},
		{"timeout", 45.0},
		{"endpoints_path", "/my/endpoints"},
		{"is_configured", true},
		{"marketplace_url", "https://marketplace.example.com"},
		{"log_level", "DEBUG"},
		{"python_path", "/usr/bin/python3"},
		{"port", 9000.0}, // JSON numbers decode as float64
		{"container_enabled", true},
		{"container_runtime", "docker"},
		{"container_image", "syfthub/node:latest"},
	}

	for _, tt := range tests {
		t.Run(tt.key, func(t *testing.T) {
			val, ok := decoded[tt.key]
			if !ok {
				t.Fatalf("key %q not found in JSON output", tt.key)
			}
			if val != tt.want {
				t.Errorf("%s = %v (%T), want %v (%T)", tt.key, val, val, tt.want, tt.want)
			}
		})
	}

	// Verify aggregators sub-struct serializes correctly
	aggs, ok := decoded["aggregators"].(map[string]interface{})
	if !ok {
		t.Fatal("aggregators not found or wrong type in JSON output")
	}
	defaultAgg, ok := aggs["default"].(map[string]interface{})
	if !ok {
		t.Fatal("aggregators.default not found or wrong type")
	}
	if defaultAgg["url"] != "https://agg.example.com" {
		t.Errorf("aggregators.default.url = %v, want %v", defaultAgg["url"], "https://agg.example.com")
	}

	// Verify accounting_services sub-struct serializes correctly
	accts, ok := decoded["accounting_services"].(map[string]interface{})
	if !ok {
		t.Fatal("accounting_services not found or wrong type in JSON output")
	}
	primaryAcct, ok := accts["primary"].(map[string]interface{})
	if !ok {
		t.Fatal("accounting_services.primary not found or wrong type")
	}
	if primaryAcct["url"] != "https://acct.example.com" {
		t.Errorf("accounting_services.primary.url = %v, want %v", primaryAcct["url"], "https://acct.example.com")
	}

	// Verify no camelCase keys leak through
	camelCaseKeys := []string{
		"hubUrl", "syfthubUrl", "apiKey", "apiToken",
		"endpointsPath", "isConfigured", "marketplaceUrl",
		"logLevel", "pythonPath", "containerEnabled",
		"containerRuntime", "containerImage", "defaultAggregator",
		"defaultAccounting", "accountingServices",
	}
	for _, key := range camelCaseKeys {
		if _, ok := decoded[key]; ok {
			t.Errorf("unexpected camelCase key %q found in JSON output", key)
		}
	}
}

func TestSettingsJSONRoundTrip(t *testing.T) {
	original := &Settings{
		HubURL:   "https://syfthub.openmined.org",
		APIToken: "token-abc",
		Aggregators: map[string]AggregatorConfig{
			"agg1": {URL: "https://agg1.example.com"},
			"agg2": {URL: "https://agg2.example.com"},
		},
		AccountingServices: map[string]AccountingConfig{
			"acct1": {URL: "https://acct1.example.com"},
		},
		DefaultAggregator: "agg1",
		DefaultAccounting: "acct1",
		Timeout:           60.0,
		EndpointsPath:     "/data/endpoints",
		IsConfigured:      true,
		MarketplaceURL:    "https://mp.example.com",
		LogLevel:          "WARN",
		PythonPath:        "/opt/python/bin/python3",
		Port:              7000,
		ContainerEnabled:  true,
		ContainerRuntime:  "podman",
		ContainerImage:    "ghcr.io/syfthub/node:v2",
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var roundTripped Settings
	if err := json.Unmarshal(data, &roundTripped); err != nil {
		t.Fatalf("json.Unmarshal error: %v", err)
	}

	// Verify all fields survive the round trip
	if roundTripped.HubURL != original.HubURL {
		t.Errorf("HubURL = %q, want %q", roundTripped.HubURL, original.HubURL)
	}
	if roundTripped.APIToken != original.APIToken {
		t.Errorf("APIToken = %q, want %q", roundTripped.APIToken, original.APIToken)
	}
	if roundTripped.DefaultAggregator != original.DefaultAggregator {
		t.Errorf("DefaultAggregator = %q, want %q", roundTripped.DefaultAggregator, original.DefaultAggregator)
	}
	if roundTripped.DefaultAccounting != original.DefaultAccounting {
		t.Errorf("DefaultAccounting = %q, want %q", roundTripped.DefaultAccounting, original.DefaultAccounting)
	}
	if roundTripped.Timeout != original.Timeout {
		t.Errorf("Timeout = %f, want %f", roundTripped.Timeout, original.Timeout)
	}
	if roundTripped.EndpointsPath != original.EndpointsPath {
		t.Errorf("EndpointsPath = %q, want %q", roundTripped.EndpointsPath, original.EndpointsPath)
	}
	if roundTripped.IsConfigured != original.IsConfigured {
		t.Errorf("IsConfigured = %v, want %v", roundTripped.IsConfigured, original.IsConfigured)
	}
	if roundTripped.MarketplaceURL != original.MarketplaceURL {
		t.Errorf("MarketplaceURL = %q, want %q", roundTripped.MarketplaceURL, original.MarketplaceURL)
	}
	if roundTripped.LogLevel != original.LogLevel {
		t.Errorf("LogLevel = %q, want %q", roundTripped.LogLevel, original.LogLevel)
	}
	if roundTripped.PythonPath != original.PythonPath {
		t.Errorf("PythonPath = %q, want %q", roundTripped.PythonPath, original.PythonPath)
	}
	if roundTripped.Port != original.Port {
		t.Errorf("Port = %d, want %d", roundTripped.Port, original.Port)
	}
	if roundTripped.ContainerEnabled != original.ContainerEnabled {
		t.Errorf("ContainerEnabled = %v, want %v", roundTripped.ContainerEnabled, original.ContainerEnabled)
	}
	if roundTripped.ContainerRuntime != original.ContainerRuntime {
		t.Errorf("ContainerRuntime = %q, want %q", roundTripped.ContainerRuntime, original.ContainerRuntime)
	}
	if roundTripped.ContainerImage != original.ContainerImage {
		t.Errorf("ContainerImage = %q, want %q", roundTripped.ContainerImage, original.ContainerImage)
	}

	// Verify sub-structs survived
	if len(roundTripped.Aggregators) != 2 {
		t.Errorf("len(Aggregators) = %d, want 2", len(roundTripped.Aggregators))
	}
	if agg, ok := roundTripped.Aggregators["agg1"]; !ok || agg.URL != "https://agg1.example.com" {
		t.Errorf("Aggregators[agg1] = %+v, want URL=https://agg1.example.com", roundTripped.Aggregators["agg1"])
	}
	if len(roundTripped.AccountingServices) != 1 {
		t.Errorf("len(AccountingServices) = %d, want 1", len(roundTripped.AccountingServices))
	}
	if acct, ok := roundTripped.AccountingServices["acct1"]; !ok || acct.URL != "https://acct1.example.com" {
		t.Errorf("AccountingServices[acct1] = %+v, want URL=https://acct1.example.com", roundTripped.AccountingServices["acct1"])
	}
}

func TestSettingsJSONOmitEmpty(t *testing.T) {
	// A settings struct with only required fields set
	settings := &Settings{
		HubURL: "https://syfthub.openmined.org",
	}

	data, err := json.Marshal(settings)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("json.Unmarshal error: %v", err)
	}

	// These fields should be omitted when empty/zero
	omittedKeys := []string{
		"api_token",
		"aggregators",
		"accounting_services",
		"default_aggregator",
		"default_accounting",
		"timeout",
		"endpoints_path",
		"is_configured",
		"marketplace_url",
		"log_level",
		"python_path",
		"port",
		"container_enabled",
		"container_runtime",
		"container_image",
	}
	for _, key := range omittedKeys {
		if _, ok := decoded[key]; ok {
			t.Errorf("key %q should be omitted when zero value, but was present", key)
		}
	}

	// hub_url should always be present (no omitempty)
	if _, ok := decoded["hub_url"]; !ok {
		t.Error("hub_url should always be present")
	}
}

func TestContainerEnabledSaveLoadCycle(t *testing.T) {
	tempDir := t.TempDir()

	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	if runtime.GOOS != "windows" {
		os.Setenv("XDG_CONFIG_HOME", tempDir)
		defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)
	} else {
		origAppData := os.Getenv("APPDATA")
		os.Setenv("APPDATA", tempDir)
		defer os.Setenv("APPDATA", origAppData)
	}

	// Save settings with container mode enabled
	settings := &Settings{
		HubURL:           "https://syfthub.openmined.org",
		EndpointsPath:    "/test/endpoints",
		IsConfigured:     true,
		ContainerEnabled: true,
		ContainerRuntime: "docker",
		ContainerImage:   "syfthub/node:latest",
		Port:             8000,
	}

	err := SaveSettings(settings)
	if err != nil {
		t.Fatalf("SaveSettings error: %v", err)
	}

	// Load and verify container fields persisted
	loaded, err := LoadSettings()
	if err != nil {
		t.Fatalf("LoadSettings error: %v", err)
	}

	if !loaded.ContainerEnabled {
		t.Error("ContainerEnabled should be true after load")
	}
	if loaded.ContainerRuntime != "docker" {
		t.Errorf("ContainerRuntime = %q, want %q", loaded.ContainerRuntime, "docker")
	}
	if loaded.ContainerImage != "syfthub/node:latest" {
		t.Errorf("ContainerImage = %q, want %q", loaded.ContainerImage, "syfthub/node:latest")
	}
}

func TestLoadSettingsAppliesDefaults(t *testing.T) {
	tempDir := t.TempDir()

	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	if runtime.GOOS != "windows" {
		os.Setenv("XDG_CONFIG_HOME", tempDir)
		defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)
	} else {
		origAppData := os.Getenv("APPDATA")
		os.Setenv("APPDATA", tempDir)
		defer os.Setenv("APPDATA", origAppData)
	}

	// Write a minimal JSON file with only hub_url set
	settingsDir := filepath.Join(tempDir, "syfthub")
	os.MkdirAll(settingsDir, 0755)
	settingsFile := filepath.Join(settingsDir, "settings.json")
	os.WriteFile(settingsFile, []byte(`{"hub_url":"https://custom.example.com"}`), 0600)

	loaded, err := LoadSettings()
	if err != nil {
		t.Fatalf("LoadSettings error: %v", err)
	}

	// Custom value should be preserved
	if loaded.HubURL != "https://custom.example.com" {
		t.Errorf("HubURL = %q, want %q", loaded.HubURL, "https://custom.example.com")
	}

	// Default values should fill in missing fields
	defaults := DefaultSettings()
	if loaded.Port != defaults.Port {
		t.Errorf("Port = %d, want default %d", loaded.Port, defaults.Port)
	}
	if loaded.Timeout != defaults.Timeout {
		t.Errorf("Timeout = %f, want default %f", loaded.Timeout, defaults.Timeout)
	}
	if loaded.LogLevel != defaults.LogLevel {
		t.Errorf("LogLevel = %q, want default %q", loaded.LogLevel, defaults.LogLevel)
	}
	// EndpointsPath should get the default (absolute path ending in "endpoints")
	if loaded.EndpointsPath == "" {
		t.Error("EndpointsPath should get a default value, got empty string")
	}
}

func TestSaveSettingsFilePermissions(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("File permission test not applicable on Windows")
	}

	tempDir := t.TempDir()

	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	os.Setenv("XDG_CONFIG_HOME", tempDir)
	defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)

	settings := DefaultSettings()
	err := SaveSettings(settings)
	if err != nil {
		t.Fatalf("SaveSettings error: %v", err)
	}

	// Verify file permissions are 0600 (owner read/write only)
	settingsFile := filepath.Join(tempDir, "syfthub", "settings.json")
	info, err := os.Stat(settingsFile)
	if err != nil {
		t.Fatalf("os.Stat error: %v", err)
	}

	perm := info.Mode().Perm()
	if perm != 0600 {
		t.Errorf("file permissions = %o, want 0600", perm)
	}
}

func TestSaveSettingsPreservesCLIManagedFields(t *testing.T) {
	tempDir := t.TempDir()

	origSettingsDir := os.Getenv("XDG_CONFIG_HOME")
	if runtime.GOOS != "windows" {
		os.Setenv("XDG_CONFIG_HOME", tempDir)
		defer os.Setenv("XDG_CONFIG_HOME", origSettingsDir)
	} else {
		origAppData := os.Getenv("APPDATA")
		os.Setenv("APPDATA", tempDir)
		defer os.Setenv("APPDATA", origAppData)
	}

	// Simulate CLI having written settings with aggregators and timeout
	settings := &Settings{
		HubURL: "https://syfthub.openmined.org",
		Aggregators: map[string]AggregatorConfig{
			"default":  {URL: "https://agg.example.com"},
			"fallback": {URL: "https://agg2.example.com"},
		},
		AccountingServices: map[string]AccountingConfig{
			"main": {URL: "https://acct.example.com"},
		},
		DefaultAggregator: "default",
		DefaultAccounting: "main",
		Timeout:           90.0,
		Port:              8000,
	}

	err := SaveSettings(settings)
	if err != nil {
		t.Fatalf("SaveSettings error: %v", err)
	}

	// Load settings back and verify CLI fields survived
	loaded, err := LoadSettings()
	if err != nil {
		t.Fatalf("LoadSettings error: %v", err)
	}

	if len(loaded.Aggregators) != 2 {
		t.Errorf("len(Aggregators) = %d, want 2", len(loaded.Aggregators))
	}
	if agg, ok := loaded.Aggregators["default"]; !ok || agg.URL != "https://agg.example.com" {
		t.Errorf("Aggregators[default] = %+v, want URL=https://agg.example.com", loaded.Aggregators["default"])
	}
	if agg, ok := loaded.Aggregators["fallback"]; !ok || agg.URL != "https://agg2.example.com" {
		t.Errorf("Aggregators[fallback] = %+v, want URL=https://agg2.example.com", loaded.Aggregators["fallback"])
	}
	if len(loaded.AccountingServices) != 1 {
		t.Errorf("len(AccountingServices) = %d, want 1", len(loaded.AccountingServices))
	}
	if acct, ok := loaded.AccountingServices["main"]; !ok || acct.URL != "https://acct.example.com" {
		t.Errorf("AccountingServices[main] = %+v, want URL=https://acct.example.com", loaded.AccountingServices["main"])
	}
	if loaded.DefaultAggregator != "default" {
		t.Errorf("DefaultAggregator = %q, want %q", loaded.DefaultAggregator, "default")
	}
	if loaded.DefaultAccounting != "main" {
		t.Errorf("DefaultAccounting = %q, want %q", loaded.DefaultAccounting, "main")
	}
	if loaded.Timeout != 90.0 {
		t.Errorf("Timeout = %f, want 90.0", loaded.Timeout)
	}
}

func TestAggregatorConfigJSON(t *testing.T) {
	cfg := AggregatorConfig{URL: "https://agg.example.com"}

	data, err := json.Marshal(cfg)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("json.Unmarshal error: %v", err)
	}

	if decoded["url"] != "https://agg.example.com" {
		t.Errorf("url = %v, want %v", decoded["url"], "https://agg.example.com")
	}

	// Round-trip
	var roundTripped AggregatorConfig
	if err := json.Unmarshal(data, &roundTripped); err != nil {
		t.Fatalf("json.Unmarshal round-trip error: %v", err)
	}
	if roundTripped.URL != cfg.URL {
		t.Errorf("round-trip URL = %q, want %q", roundTripped.URL, cfg.URL)
	}
}

func TestAccountingConfigJSON(t *testing.T) {
	cfg := AccountingConfig{URL: "https://acct.example.com"}

	data, err := json.Marshal(cfg)
	if err != nil {
		t.Fatalf("json.Marshal error: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("json.Unmarshal error: %v", err)
	}

	if decoded["url"] != "https://acct.example.com" {
		t.Errorf("url = %v, want %v", decoded["url"], "https://acct.example.com")
	}

	// Round-trip
	var roundTripped AccountingConfig
	if err := json.Unmarshal(data, &roundTripped); err != nil {
		t.Fatalf("json.Unmarshal round-trip error: %v", err)
	}
	if roundTripped.URL != cfg.URL {
		t.Errorf("round-trip URL = %q, want %q", roundTripped.URL, cfg.URL)
	}
}
