// Package main provides settings persistence for the SyftHub Desktop GUI.
// Settings are stored in settings.json in the user's config directory.
// Field names and JSON tags match the CLI's nodeconfig.NodeConfig for file compatibility.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

// AggregatorConfig represents configuration for an aggregator endpoint.
// Mirrored from nodeconfig for JSON round-trip compatibility.
type AggregatorConfig struct {
	URL string `json:"url"`
}

// AccountingConfig represents configuration for an accounting service.
type AccountingConfig struct {
	URL string `json:"url"`
}

// Settings holds persistent application settings.
// JSON field names use snake_case to match the CLI's unified settings format.
// Fields the desktop does not actively use are preserved here so that
// saving settings never silently drops CLI-managed values (aggregators, timeout, etc.).
type Settings struct {
	// Identity — shared across CLI and desktop
	HubURL   string `json:"hub_url"`
	APIToken string `json:"api_token,omitempty"`

	// CLI infrastructure aliases (preserved on save, not exposed in desktop UI)
	Aggregators        map[string]AggregatorConfig `json:"aggregators,omitempty"`
	AccountingServices map[string]AccountingConfig `json:"accounting_services,omitempty"`
	DefaultAggregator  string                      `json:"default_aggregator,omitempty"`
	DefaultAccounting  string                      `json:"default_accounting,omitempty"`
	Timeout            float64                     `json:"timeout,omitempty"`

	// Node / desktop daemon settings
	EndpointsPath  string `json:"endpoints_path,omitempty"`
	IsConfigured   bool   `json:"is_configured,omitempty"`
	MarketplaceURL string `json:"marketplace_url,omitempty"`
	LogLevel       string `json:"log_level,omitempty"`
	PythonPath     string `json:"python_path,omitempty"`
	Port           int    `json:"port,omitempty"`

	// Container mode
	ContainerEnabled bool   `json:"container_enabled,omitempty"`
	ContainerRuntime string `json:"container_runtime,omitempty"`
	ContainerImage   string `json:"container_image,omitempty"`
}

// DefaultSettings returns settings with sensible defaults.
func DefaultSettings() *Settings {
	endpointsPath := "endpoints"
	if dir, err := getSettingsDir(); err == nil {
		endpointsPath = filepath.Join(dir, "endpoints")
	}
	return &Settings{
		HubURL:        "https://syfthub.openmined.org",
		EndpointsPath: endpointsPath,
		Port:          8000,
		LogLevel:      "INFO",
		Timeout:       30.0,
	}
}

// getSettingsDir returns the platform-specific settings directory.
// On Windows: %APPDATA%\syfthub
// On macOS: ~/Library/Application Support/syfthub
// On Linux: ~/.config/syfthub
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

	return filepath.Join(baseDir, "syfthub"), nil
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

	settings := DefaultSettings()
	if err := json.Unmarshal(data, settings); err != nil {
		return DefaultSettings(), fmt.Errorf("failed to parse settings: %w", err)
	}

	return settings, nil
}

// SaveSettings writes settings to the settings file.
// Existing fields not present in s are not preserved — callers should
// load first (LoadSettings) then mutate before saving.
func SaveSettings(settings *Settings) error {
	dir, err := getSettingsDir()
	if err != nil {
		return err
	}

	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create settings directory: %w", err)
	}

	path := filepath.Join(dir, "settings.json")
	data, err := json.MarshalIndent(settings, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal settings: %w", err)
	}

	if err := os.WriteFile(path, data, 0600); err != nil {
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
// Relative paths are resolved relative to the settings directory.
func resolveEndpointsPath(path string) (string, error) {
	if filepath.IsAbs(path) {
		return path, nil
	}

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
