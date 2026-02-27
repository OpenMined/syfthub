// Package main provides settings persistence for the SyftHub Desktop GUI.
// Settings are stored in a JSON file in the user's config directory.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

// Settings holds persistent application settings.
// These are stored in settings.json in the user config directory.
type Settings struct {
	SyftHubURL    string `json:"syfthubUrl"`
	APIKey        string `json:"apiKey,omitempty"`
	EndpointsPath string `json:"endpointsPath"`
	IsConfigured  bool   `json:"isConfigured"`
	AggregatorURL string `json:"aggregatorUrl,omitempty"`
}

// DefaultSettings returns settings with sensible defaults.
func DefaultSettings() *Settings {
	return &Settings{
		SyftHubURL:    "https://syfthub-dev.openmined.org",
		APIKey:        "",
		EndpointsPath: ".endpoints",
		IsConfigured:  false,
	}
}

// getSettingsDir returns the platform-specific settings directory.
// On Windows: %APPDATA%\syfthub-desktop
// On macOS: ~/Library/Application Support/syfthub-desktop
// On Linux: ~/.config/syfthub-desktop
func getSettingsDir() (string, error) {
	var baseDir string

	switch runtime.GOOS {
	case "windows":
		baseDir = os.Getenv("APPDATA")
		if baseDir == "" {
			homeDir, err := os.UserHomeDir()
			if err != nil {
				return "", fmt.Errorf("failed to get home directory: %w", err)
			}
			baseDir = filepath.Join(homeDir, "AppData", "Roaming")
		}
	case "darwin":
		homeDir, err := os.UserHomeDir()
		if err != nil {
			return "", fmt.Errorf("failed to get home directory: %w", err)
		}
		baseDir = filepath.Join(homeDir, "Library", "Application Support")
	default: // Linux and others
		baseDir = os.Getenv("XDG_CONFIG_HOME")
		if baseDir == "" {
			homeDir, err := os.UserHomeDir()
			if err != nil {
				return "", fmt.Errorf("failed to get home directory: %w", err)
			}
			baseDir = filepath.Join(homeDir, ".config")
		}
	}

	return filepath.Join(baseDir, "syfthub-desktop"), nil
}

// getSettingsPath returns the full path to the settings file.
func getSettingsPath() (string, error) {
	dir, err := getSettingsDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "settings.json"), nil
}

// getDefaultEndpointsPath returns the default endpoints directory path.
func getDefaultEndpointsPath() (string, error) {
	dir, err := getSettingsDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "endpoints"), nil
}

// LoadSettings reads settings from the settings file.
// Returns default settings if the file doesn't exist.
func LoadSettings() (*Settings, error) {
	path, err := getSettingsPath()
	if err != nil {
		return DefaultSettings(), err
	}

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return DefaultSettings(), nil
		}
		return DefaultSettings(), fmt.Errorf("failed to read settings: %w", err)
	}

	var settings Settings
	if err := json.Unmarshal(data, &settings); err != nil {
		return DefaultSettings(), fmt.Errorf("failed to parse settings: %w", err)
	}

	return &settings, nil
}

// SaveSettings writes settings to the settings file.
func SaveSettings(settings *Settings) error {
	dir, err := getSettingsDir()
	if err != nil {
		return err
	}

	// Create directory if it doesn't exist
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create settings directory: %w", err)
	}

	path := filepath.Join(dir, "settings.json")
	data, err := json.MarshalIndent(settings, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal settings: %w", err)
	}

	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("failed to write settings: %w", err)
	}

	return nil
}

// SettingsExist checks if a settings file exists.
func SettingsExist() bool {
	path, err := getSettingsPath()
	if err != nil {
		return false
	}
	_, err = os.Stat(path)
	return err == nil
}

// resolveEndpointsPath resolves the endpoints path to an absolute path.
// If the path is relative and starts with ".", it's relative to the settings dir.
// Otherwise, it's treated as an absolute path.
func resolveEndpointsPath(path string) (string, error) {
	if filepath.IsAbs(path) {
		return path, nil
	}

	// Relative path - resolve relative to settings dir
	dir, err := getSettingsDir()
	if err != nil {
		return "", err
	}

	return filepath.Join(dir, path), nil
}

// EnsureEndpointsDir ensures the endpoints directory exists.
func EnsureEndpointsDir(path string) error {
	absPath, err := resolveEndpointsPath(path)
	if err != nil {
		return err
	}

	if err := os.MkdirAll(absPath, 0755); err != nil {
		return fmt.Errorf("failed to create endpoints directory: %w", err)
	}

	return nil
}
