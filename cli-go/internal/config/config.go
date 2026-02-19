// Package config provides configuration management for the SyftHub CLI.
// Config file location: ~/.syfthub/config.json
package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
)

// Default configuration values.
const (
	DefaultHubURL  = "https://hub.syftbox.org"
	DefaultTimeout = 30.0
)

var (
	// ConfigDir is the directory containing config files.
	ConfigDir = filepath.Join(os.Getenv("HOME"), ".syfthub")
	// ConfigFile is the path to the main config file.
	ConfigFile = filepath.Join(ConfigDir, "config.json")
	// UpdateCheckFile is the path to the update check cache file.
	UpdateCheckFile = filepath.Join(ConfigDir, ".update_check")
	// CompletionCacheFile is the path to the completion cache file.
	CompletionCacheFile = filepath.Join(ConfigDir, ".completion_cache.json")
)

// AggregatorConfig represents configuration for an aggregator endpoint.
type AggregatorConfig struct {
	URL string `json:"url"`
}

// AccountingConfig represents configuration for an accounting service.
type AccountingConfig struct {
	URL string `json:"url"`
}

// Config is the main configuration model for SyftHub CLI.
// This struct mirrors the Python CLI config for cross-compatibility.
type Config struct {
	// Authentication tokens
	AccessToken  *string `json:"access_token"`
	RefreshToken *string `json:"refresh_token"`

	// Infrastructure aliases
	Aggregators       map[string]AggregatorConfig  `json:"aggregators"`
	AccountingServices map[string]AccountingConfig `json:"accounting_services"`

	// Default selections
	DefaultAggregator  *string `json:"default_aggregator"`
	DefaultAccounting  *string `json:"default_accounting"`

	// API settings
	Timeout float64 `json:"timeout"`
	HubURL  string  `json:"hub_url"`
}

// configMutex protects concurrent access to config file.
var configMutex sync.Mutex

// NewConfig creates a new Config with default values.
func NewConfig() *Config {
	return &Config{
		Aggregators:       make(map[string]AggregatorConfig),
		AccountingServices: make(map[string]AccountingConfig),
		Timeout:           DefaultTimeout,
		HubURL:            DefaultHubURL,
	}
}

// EnsureConfigDir ensures the config directory exists.
func EnsureConfigDir() error {
	return os.MkdirAll(ConfigDir, 0755)
}

// Load loads configuration from file.
// Returns default config if file doesn't exist or is corrupted.
func Load() *Config {
	return LoadFrom(ConfigFile)
}

// LoadFrom loads configuration from a specific path.
func LoadFrom(path string) *Config {
	configMutex.Lock()
	defer configMutex.Unlock()

	config := NewConfig()

	data, err := os.ReadFile(path)
	if err != nil {
		return config
	}

	if err := json.Unmarshal(data, config); err != nil {
		return NewConfig()
	}

	// Ensure maps are initialized
	if config.Aggregators == nil {
		config.Aggregators = make(map[string]AggregatorConfig)
	}
	if config.AccountingServices == nil {
		config.AccountingServices = make(map[string]AccountingConfig)
	}

	return config
}

// Save saves configuration to file.
func (c *Config) Save() error {
	return c.SaveTo(ConfigFile)
}

// SaveTo saves configuration to a specific path.
func (c *Config) SaveTo(path string) error {
	configMutex.Lock()
	defer configMutex.Unlock()

	if err := EnsureConfigDir(); err != nil {
		return err
	}

	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(path, data, 0600)
}

// GetAggregatorURL returns the URL for an aggregator alias.
// If alias is provided and matches a configured alias, returns that URL.
// If alias looks like a URL, returns it directly.
// Otherwise returns the default aggregator URL if configured.
func (c *Config) GetAggregatorURL(alias string) string {
	if alias != "" {
		if agg, ok := c.Aggregators[alias]; ok {
			return agg.URL
		}
		// Treat as direct URL if not an alias
		return alias
	}
	if c.DefaultAggregator != nil && *c.DefaultAggregator != "" {
		if agg, ok := c.Aggregators[*c.DefaultAggregator]; ok {
			return agg.URL
		}
	}
	return ""
}

// GetAccountingURL returns the URL for an accounting service alias.
func (c *Config) GetAccountingURL(alias string) string {
	if alias != "" {
		if acc, ok := c.AccountingServices[alias]; ok {
			return acc.URL
		}
		// Treat as direct URL if not an alias
		return alias
	}
	if c.DefaultAccounting != nil && *c.DefaultAccounting != "" {
		if acc, ok := c.AccountingServices[*c.DefaultAccounting]; ok {
			return acc.URL
		}
	}
	return ""
}

// ClearTokens clears authentication tokens from config.
func (c *Config) ClearTokens() {
	c.AccessToken = nil
	c.RefreshToken = nil
}

// SetTokens sets authentication tokens.
func (c *Config) SetTokens(accessToken, refreshToken string) {
	c.AccessToken = &accessToken
	c.RefreshToken = &refreshToken
}

// HasTokens returns true if access token is present.
func (c *Config) HasTokens() bool {
	return c.AccessToken != nil && *c.AccessToken != ""
}

// ClearTokensAndSave clears tokens and saves config.
func ClearTokensAndSave() error {
	config := Load()
	config.ClearTokens()
	return config.Save()
}
