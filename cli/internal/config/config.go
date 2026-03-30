// Package config provides configuration management for the SyftHub CLI.
// This package is a thin re-export layer over nodeconfig. All configuration
// is stored in the unified settings.json file (~/.config/syfthub/settings.json).
package config

import (
	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
)

var (
	// ConfigDir is the shared SyftHub config directory.
	ConfigDir = nodeconfig.ConfigDir
	// ConfigFile is the path to the unified settings file.
	// Kept as a named export so callers like 'syft config path' still work.
	ConfigFile = nodeconfig.ConfigFile
	// UpdateCheckFile is the path to the update check cache file.
	UpdateCheckFile = nodeconfig.UpdateCheckFile
	// CompletionCacheFile is the path to the shell completion cache file.
	CompletionCacheFile = nodeconfig.CompletionCacheFile
)

// Type aliases — all CLI command files import this package and use Config,
// AggregatorConfig, and AccountingConfig without needing to change their imports.
type (
	Config           = nodeconfig.NodeConfig
	AggregatorConfig = nodeconfig.AggregatorConfig
	AccountingConfig = nodeconfig.AccountingConfig
)

// Load loads configuration from the unified settings file.
func Load() *Config { return nodeconfig.Load() }

// LoadFrom loads configuration from a specific path.
func LoadFrom(path string) *Config { return nodeconfig.LoadFrom(path) }

// EnsureConfigDir ensures the config directory exists.
func EnsureConfigDir() error { return nodeconfig.EnsureConfigDir() }

// ClearAPITokenAndSave clears the API token and saves the config.
func ClearAPITokenAndSave() error { return nodeconfig.ClearAPITokenAndSave() }
