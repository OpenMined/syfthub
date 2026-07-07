// Package nodeconfig provides unified configuration management for SyftHub.
// This is the single source of truth for all CLI and desktop settings.
// Config file: ~/.config/syfthub/settings.json (platform-aware, shared with syfthub-desktop)
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
	"time"
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
	// ConfigFile is the path to the unified settings file (shared with syfthub-desktop).
	ConfigFile = filepath.Join(ConfigDir, "settings.json")
	// UpdateCheckFile is the path to the update check cache file.
	UpdateCheckFile = filepath.Join(ConfigDir, ".update_check")
	// CompletionCacheFile is the path to the shell completion cache file.
	CompletionCacheFile = filepath.Join(ConfigDir, ".completion_cache.json")
	// PIDFile is the path to the node PID file.
	PIDFile = filepath.Join(ConfigDir, "node.pid")
	// LogFile is the path to the node daemon log file.
	LogFile = filepath.Join(ConfigDir, "node.log")
	// LogsDir is the directory for per-endpoint request logs (JSONL files).
	LogsDir = filepath.Join(ConfigDir, "logs")
	// NodeKeyFile is the path to the persisted X25519 private key used for
	// NATS tunnel encryption. Persisting it means the registered public key
	// stays valid across node restarts, avoiding decryption failures caused
	// by a stale key in the aggregator's 5-minute cache.
	NodeKeyFile = filepath.Join(ConfigDir, "node.key")
)

// AggregatorConfig represents configuration for an aggregator endpoint.
type AggregatorConfig struct {
	URL string `json:"url"`
}

// AccountingConfig represents configuration for an accounting service.
type AccountingConfig struct {
	URL string `json:"url"`
}

// NodeConfig holds the unified SyftHub configuration shared between the CLI and desktop app.
// All JSON field names use snake_case and are written to ~/.config/syfthub/settings.json.
type NodeConfig struct {
	// Identity — used by all tools
	HubURL   string `json:"hub_url"`
	APIToken string `json:"api_token,omitempty"`

	// CLI infrastructure aliases
	Aggregators        map[string]AggregatorConfig `json:"aggregators,omitempty"`
	AccountingServices map[string]AccountingConfig `json:"accounting_services,omitempty"`
	DefaultAggregator  string                      `json:"default_aggregator,omitempty"`
	DefaultAccounting  string                      `json:"default_accounting,omitempty"`
	Timeout            float64                     `json:"timeout,omitempty"`

	// Node / desktop daemon settings
	EndpointsPath string `json:"endpoints_path,omitempty"`
	IsConfigured  bool   `json:"is_configured,omitempty"`
	LogLevel      string `json:"log_level,omitempty"`
	PythonPath    string `json:"python_path,omitempty"`
	Port          int    `json:"port,omitempty"`

	// Container mode
	ContainerEnabled bool   `json:"container_enabled,omitempty"`
	ContainerRuntime string `json:"container_runtime,omitempty"` // "docker", "podman", or "auto"
	ContainerImage   string `json:"container_image,omitempty"`   // default: "syfthub/endpoint-runner:latest"
}

const (
	defaultHubURL          = "https://syfthub.openmined.org"
	defaultAggregatorURL   = "https://syfthub.openmined.org/aggregator/api/v1"
	defaultAccountingURL   = "https://syftaccounting.centralus.cloudapp.azure.com"
	defaultTimeout         = 30.0
	defaultAggregatorAlias = "default"
	defaultAccountingAlias = "default"
)

// DefaultNodeConfig returns a NodeConfig with sensible defaults.
func DefaultNodeConfig() *NodeConfig {
	return &NodeConfig{
		HubURL:        defaultHubURL,
		EndpointsPath: filepath.Join(ConfigDir, "endpoints"),
		Port:          8000,
		LogLevel:      "INFO",
		Timeout:       defaultTimeout,
		Aggregators: map[string]AggregatorConfig{
			defaultAggregatorAlias: {URL: defaultAggregatorURL},
		},
		AccountingServices: map[string]AccountingConfig{
			defaultAccountingAlias: {URL: defaultAccountingURL},
		},
		DefaultAggregator: defaultAggregatorAlias,
		DefaultAccounting: defaultAccountingAlias,
	}
}

// EnsureConfigDir creates the config directory.
func EnsureConfigDir() error {
	if err := os.MkdirAll(ConfigDir, 0755); err != nil {
		return fmt.Errorf("failed to create config directory: %w", err)
	}
	return nil
}

// Load loads configuration from the shared settings file.
// Returns default config if the file doesn't exist.
func Load() *NodeConfig {
	return LoadFrom(ConfigFile)
}

// LoadFrom loads configuration from a specific path.
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

	// Ensure maps are initialized after unmarshal.
	if config.Aggregators == nil {
		config.Aggregators = make(map[string]AggregatorConfig)
	}
	if config.AccountingServices == nil {
		config.AccountingServices = make(map[string]AccountingConfig)
	}

	return config
}

// Save saves configuration to the shared settings file.
func (c *NodeConfig) Save() error {
	return c.SaveTo(ConfigFile)
}

// SaveTo saves configuration to a specific path.
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

// Configured returns true if the node has been initialized with required fields.
func (c *NodeConfig) Configured() bool {
	return c.IsConfigured && c.HubURL != "" && c.APIToken != ""
}

func (c *NodeConfig) HasAPIToken() bool {
	return c.APIToken != ""
}

// TimeoutDuration returns the configured request timeout as a time.Duration.
// Returns 0 if Timeout is not positive.
func (c *NodeConfig) TimeoutDuration() time.Duration {
	if c.Timeout <= 0 {
		return 0
	}
	return time.Duration(c.Timeout * float64(time.Second))
}

func (c *NodeConfig) SetAPIToken(token string) {
	c.APIToken = token
}

func (c *NodeConfig) ClearAPIToken() {
	c.APIToken = ""
}

// ClearAPITokenAndSave clears the API token and saves the config.
func ClearAPITokenAndSave() error {
	config := Load()
	config.ClearAPIToken()
	return config.Save()
}

// GetAggregatorURL returns the URL for an aggregator alias or a direct URL.
// Falls back to the default aggregator if no alias is given.
func (c *NodeConfig) GetAggregatorURL(alias string) string {
	if alias != "" {
		if agg, ok := c.Aggregators[alias]; ok {
			return agg.URL
		}
		// Treat as direct URL if it doesn't match any alias.
		return alias
	}
	if c.DefaultAggregator != "" {
		if agg, ok := c.Aggregators[c.DefaultAggregator]; ok {
			return agg.URL
		}
	}
	return ""
}

// GetAccountingURL returns the URL for an accounting service alias or a direct URL.
func (c *NodeConfig) GetAccountingURL(alias string) string {
	if alias != "" {
		if acc, ok := c.AccountingServices[alias]; ok {
			return acc.URL
		}
		return alias
	}
	if c.DefaultAccounting != "" {
		if acc, ok := c.AccountingServices[c.DefaultAccounting]; ok {
			return acc.URL
		}
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
