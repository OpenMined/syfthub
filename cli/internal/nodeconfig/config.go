// Package nodeconfig provides configuration management for the SyftHub node subsystem.
// Config file location: ~/.config/syfthub/settings.json (shared with syfthub-desktop)
// PID file location: ~/.config/syfthub/node.pid
package nodeconfig

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
)

var configMutex sync.Mutex

// getConfigDir returns the platform-specific config directory for SyftHub.
// On Windows: %APPDATA%\syfthub
// On macOS: ~/Library/Application Support/syfthub
// On Linux: $XDG_CONFIG_HOME/syfthub (defaults to ~/.config/syfthub)
func getConfigDir() string {
	var baseDir string

	switch runtime.GOOS {
	case "windows":
		baseDir = os.Getenv("APPDATA")
		if baseDir == "" {
			homeDir, err := os.UserHomeDir()
			if err != nil {
				baseDir = filepath.Join(os.Getenv("HOME"), "AppData", "Roaming")
			} else {
				baseDir = filepath.Join(homeDir, "AppData", "Roaming")
			}
		}
	case "darwin":
		homeDir, err := os.UserHomeDir()
		if err != nil {
			homeDir = os.Getenv("HOME")
		}
		baseDir = filepath.Join(homeDir, "Library", "Application Support")
	default: // Linux and others
		baseDir = os.Getenv("XDG_CONFIG_HOME")
		if baseDir == "" {
			homeDir, err := os.UserHomeDir()
			if err != nil {
				homeDir = os.Getenv("HOME")
			}
			baseDir = filepath.Join(homeDir, ".config")
		}
	}

	return filepath.Join(baseDir, "syfthub")
}

var (
	// ConfigDir is the directory containing shared SyftHub config.
	ConfigDir = getConfigDir()
	// ConfigFile is the path to the shared settings file.
	ConfigFile = filepath.Join(ConfigDir, "settings.json")
	// PIDFile is the path to the node PID file.
	PIDFile = filepath.Join(ConfigDir, "node.pid")
	// LogFile is the path to the node daemon log file.
	LogFile = filepath.Join(ConfigDir, "node.log")
	// LogsDir is the directory for per-endpoint request logs (JSONL files).
	LogsDir = filepath.Join(ConfigDir, "logs")
)

// NodeConfig holds node/desktop shared settings.
// JSON field names match the desktop app's settings.json format (camelCase).
type NodeConfig struct {
	SyftHubURL     string `json:"syfthubUrl"`
	APIKey         string `json:"apiKey,omitempty"`
	EndpointsPath  string `json:"endpointsPath"`
	IsConfigured   bool   `json:"isConfigured"`
	MarketplaceURL string `json:"marketplaceUrl,omitempty"`
	LogLevel       string `json:"logLevel,omitempty"`
	PythonPath     string `json:"pythonPath,omitempty"`
	Port           int    `json:"port,omitempty"`

	// Container mode settings
	ContainerEnabled bool   `json:"containerEnabled,omitempty"`
	ContainerRuntime string `json:"containerRuntime,omitempty"` // "docker", "podman", or "auto"
	ContainerImage   string `json:"containerImage,omitempty"`   // default: "syfthub/endpoint-runner:latest"
}

// DefaultNodeConfig returns a NodeConfig with sensible defaults matching the desktop app.
func DefaultNodeConfig() *NodeConfig {
	return &NodeConfig{
		SyftHubURL:    "https://syfthub-dev.openmined.org",
		EndpointsPath: filepath.Join(ConfigDir, "endpoints"),
		Port:          8000,
		LogLevel:      "INFO",
	}
}

// EnsureConfigDir creates the config directory.
func EnsureConfigDir() error {
	if err := os.MkdirAll(ConfigDir, 0755); err != nil {
		return fmt.Errorf("failed to create config directory: %w", err)
	}
	return nil
}

// Load loads node configuration from the shared settings file.
// Returns default config if the file doesn't exist.
func Load() *NodeConfig {
	return LoadFrom(ConfigFile)
}

// LoadFrom loads node configuration from a specific path.
func LoadFrom(path string) *NodeConfig {
	configMutex.Lock()
	defer configMutex.Unlock()

	config := DefaultNodeConfig()

	data, err := os.ReadFile(path)
	if err != nil {
		return config
	}

	if err := json.Unmarshal(data, config); err != nil {
		return DefaultNodeConfig()
	}

	return config
}

// Save saves node configuration to the shared settings file.
func (c *NodeConfig) Save() error {
	return c.SaveTo(ConfigFile)
}

// SaveTo saves node configuration to a specific path.
func (c *NodeConfig) SaveTo(path string) error {
	configMutex.Lock()
	defer configMutex.Unlock()

	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return fmt.Errorf("failed to create config directory: %w", err)
	}

	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(path, data, 0600)
}

// Configured returns true if the node has been initialized.
func (c *NodeConfig) Configured() bool {
	return c.IsConfigured && c.SyftHubURL != "" && c.APIKey != ""
}

// GetMarketplaceURL returns the marketplace manifest URL.
func (c *NodeConfig) GetMarketplaceURL() string {
	if c.MarketplaceURL != "" {
		return c.MarketplaceURL
	}
	if c.SyftHubURL != "" {
		return strings.TrimRight(c.SyftHubURL, "/") + "/marketplace/manifest.json"
	}
	return ""
}

// WritePID writes the given PID to the PID file.
func WritePID(pid int) error {
	if err := EnsureConfigDir(); err != nil {
		return err
	}
	return os.WriteFile(PIDFile, []byte(strconv.Itoa(pid)), 0600)
}

// ReadPID reads the PID from the PID file.
func ReadPID() (int, error) {
	data, err := os.ReadFile(PIDFile)
	if err != nil {
		return 0, err
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(data)))
	if err != nil {
		return 0, fmt.Errorf("invalid PID file: %w", err)
	}
	return pid, nil
}

// RemovePID removes the PID file.
func RemovePID() error {
	if err := os.Remove(PIDFile); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}
