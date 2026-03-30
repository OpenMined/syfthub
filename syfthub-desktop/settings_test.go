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
	if settings.HubURL != "https://syfthub-dev.openmined.org" {
		t.Errorf("SyftHubURL = %q, want %q", settings.HubURL, "https://syfthub-dev.openmined.org")
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
		HubURL: "https://test.example.com",
		APIToken: "my-api-key",
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
		t.Errorf("JSON syfthubUrl = %v, want %v", decoded["hub_url"], settings.HubURL)
	}
	if decoded["api_token"] != settings.APIToken {
		t.Errorf("JSON apiKey = %v, want %v", decoded["api_token"], settings.APIToken)
	}
	if decoded["endpoints_path"] != settings.EndpointsPath {
		t.Errorf("JSON endpointsPath = %v, want %v", decoded["endpoints_path"], settings.EndpointsPath)
	}
	if decoded["is_configured"] != settings.IsConfigured {
		t.Errorf("JSON isConfigured = %v, want %v", decoded["is_configured"], settings.IsConfigured)
	}
}
