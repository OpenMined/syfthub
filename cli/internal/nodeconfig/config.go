// Package nodeconfig provides configuration management for the SyftHub node subsystem.
// Config file location: ~/.syfthub/node/config.json
// PID file location: ~/.syfthub/node/node.pid
package nodeconfig

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
)

var (
	// NodeDir is the directory containing node config and state.
	NodeDir = filepath.Join(os.Getenv("HOME"), ".syfthub", "node")
	// NodeConfigFile is the path to the node config file.
	NodeConfigFile = filepath.Join(NodeDir, "config.json")
	// PIDFile is the path to the node PID file.
	PIDFile = filepath.Join(NodeDir, "node.pid")
)

var configMutex sync.Mutex

// NodeConfig holds node-specific settings.
type NodeConfig struct {
	SyftHubURL     string `json:"syfthub_url"`
	APIKey         string `json:"api_key,omitempty"`
	SpaceURL       string `json:"space_url,omitempty"`
	EndpointsPath  string `json:"endpoints_path"`
	LogLevel       string `json:"log_level,omitempty"`
	MarketplaceURL string `json:"marketplace_url,omitempty"`
	PythonPath     string `json:"python_path,omitempty"`
	Port           int    `json:"port"`
}

// DefaultNodeConfig returns a NodeConfig with sensible defaults.
func DefaultNodeConfig() *NodeConfig {
	return &NodeConfig{
		SyftHubURL:    "https://syfthub.openmined.org",
		EndpointsPath: filepath.Join(NodeDir, "endpoints"),
		Port:          8000,
		LogLevel:      "INFO",
	}
}

// EnsureNodeDir creates the node directory and default endpoints directory.
func EnsureNodeDir() error {
	if err := os.MkdirAll(NodeDir, 0755); err != nil {
		return fmt.Errorf("failed to create node directory: %w", err)
	}
	return nil
}

// Load loads node configuration from file.
// Returns default config if the file doesn't exist.
func Load() *NodeConfig {
	return LoadFrom(NodeConfigFile)
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

// Save saves node configuration to file.
func (c *NodeConfig) Save() error {
	return c.SaveTo(NodeConfigFile)
}

// SaveTo saves node configuration to a specific path.
func (c *NodeConfig) SaveTo(path string) error {
	configMutex.Lock()
	defer configMutex.Unlock()

	if err := EnsureNodeDir(); err != nil {
		return err
	}

	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(path, data, 0600)
}

// IsConfigured returns true if the node has been initialized.
func (c *NodeConfig) IsConfigured() bool {
	return c.SyftHubURL != "" && c.APIKey != ""
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
	if err := EnsureNodeDir(); err != nil {
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
