// Package syfthubapi provides a framework for building SyftHub Spaces.
// It offers a FastAPI-like interface for registering endpoints and handling requests.
package syfthubapi

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds all configuration for SyftAPI.
type Config struct {
	// SyftHubURL is the URL of the SyftHub backend (required).
	SyftHubURL string

	// APIKey is the SyftHub API token/PAT for authentication (required).
	APIKey string

	// SpaceURL is the public URL of this space or "tunneling:username" for tunnel mode (required).
	SpaceURL string

	// LogLevel controls logging verbosity (DEBUG, INFO, WARNING, ERROR).
	LogLevel string

	// ServerHost is the HTTP server bind address (default: "0.0.0.0").
	ServerHost string

	// ServerPort is the HTTP server port (default: 8000).
	ServerPort int

	// HeartbeatEnabled enables periodic heartbeat to SyftHub (default: true).
	HeartbeatEnabled bool

	// HeartbeatTTLSeconds is the TTL for heartbeat signals (default: 300, range: 1-3600).
	HeartbeatTTLSeconds int

	// HeartbeatIntervalMultiplier determines heartbeat frequency as TTL * multiplier (default: 0.8).
	HeartbeatIntervalMultiplier float64

	// EndpointsPath is the directory for file-based endpoints (optional).
	EndpointsPath string

	// WatchEnabled enables hot-reload of file-based endpoints (default: true).
	WatchEnabled bool

	// WatchDebounceSeconds is the delay before reloading after file changes (default: 1.0).
	WatchDebounceSeconds float64

	// PythonPath is the path to the Python interpreter (default: "python3").
	PythonPath string
}

// DefaultConfig returns a Config with default values.
func DefaultConfig() *Config {
	return &Config{
		LogLevel:                    "INFO",
		ServerHost:                  "0.0.0.0",
		ServerPort:                  8000,
		HeartbeatEnabled:            true,
		HeartbeatTTLSeconds:         300,
		HeartbeatIntervalMultiplier: 0.8,
		WatchEnabled:                true,
		WatchDebounceSeconds:        1.0,
		PythonPath:                  "python3",
	}
}

// LoadFromEnv loads configuration from environment variables.
func (c *Config) LoadFromEnv() error {
	if url := os.Getenv("SYFTHUB_URL"); url != "" {
		c.SyftHubURL = url
	}

	if key := os.Getenv("SYFTHUB_API_KEY"); key != "" {
		c.APIKey = key
	}

	if url := os.Getenv("SPACE_URL"); url != "" {
		c.SpaceURL = url
	}

	if level := os.Getenv("LOG_LEVEL"); level != "" {
		c.LogLevel = strings.ToUpper(level)
	}

	if host := os.Getenv("SERVER_HOST"); host != "" {
		c.ServerHost = host
	}

	if port := os.Getenv("SERVER_PORT"); port != "" {
		p, err := strconv.Atoi(port)
		if err != nil {
			return fmt.Errorf("invalid SERVER_PORT: %w", err)
		}
		c.ServerPort = p
	}

	if enabled := os.Getenv("HEARTBEAT_ENABLED"); enabled != "" {
		c.HeartbeatEnabled = strings.ToLower(enabled) == "true"
	}

	if ttl := os.Getenv("HEARTBEAT_TTL_SECONDS"); ttl != "" {
		t, err := strconv.Atoi(ttl)
		if err != nil {
			return fmt.Errorf("invalid HEARTBEAT_TTL_SECONDS: %w", err)
		}
		c.HeartbeatTTLSeconds = t
	}

	if mult := os.Getenv("HEARTBEAT_INTERVAL_MULTIPLIER"); mult != "" {
		m, err := strconv.ParseFloat(mult, 64)
		if err != nil {
			return fmt.Errorf("invalid HEARTBEAT_INTERVAL_MULTIPLIER: %w", err)
		}
		c.HeartbeatIntervalMultiplier = m
	}

	if path := os.Getenv("ENDPOINTS_PATH"); path != "" {
		c.EndpointsPath = path
	}

	if enabled := os.Getenv("WATCH_ENABLED"); enabled != "" {
		c.WatchEnabled = strings.ToLower(enabled) == "true"
	}

	if debounce := os.Getenv("WATCH_DEBOUNCE_SECONDS"); debounce != "" {
		d, err := strconv.ParseFloat(debounce, 64)
		if err != nil {
			return fmt.Errorf("invalid WATCH_DEBOUNCE_SECONDS: %w", err)
		}
		c.WatchDebounceSeconds = d
	}

	if python := os.Getenv("PYTHON_PATH"); python != "" {
		c.PythonPath = python
	}

	return nil
}

// Validate checks that required configuration is present and valid.
func (c *Config) Validate() error {
	if c.SyftHubURL == "" {
		return &ConfigurationError{Field: "SyftHubURL", Message: "required but not set"}
	}

	if c.APIKey == "" {
		return &ConfigurationError{Field: "APIKey", Message: "required but not set"}
	}

	if c.SpaceURL == "" {
		return &ConfigurationError{Field: "SpaceURL", Message: "required but not set"}
	}

	// Validate SpaceURL format
	if !strings.HasPrefix(c.SpaceURL, "http://") &&
		!strings.HasPrefix(c.SpaceURL, "https://") &&
		!strings.HasPrefix(c.SpaceURL, "tunneling:") {
		return &ConfigurationError{
			Field:   "SpaceURL",
			Message: "must start with http://, https://, or tunneling:",
		}
	}

	// Validate log level
	validLogLevels := map[string]bool{
		"DEBUG": true, "INFO": true, "WARNING": true, "WARN": true, "ERROR": true,
	}
	if !validLogLevels[strings.ToUpper(c.LogLevel)] {
		return &ConfigurationError{
			Field:   "LogLevel",
			Message: "must be one of: DEBUG, INFO, WARNING, ERROR",
		}
	}

	// Validate heartbeat TTL
	if c.HeartbeatTTLSeconds < 1 || c.HeartbeatTTLSeconds > 3600 {
		return &ConfigurationError{
			Field:   "HeartbeatTTLSeconds",
			Message: "must be between 1 and 3600",
		}
	}

	// Validate heartbeat interval multiplier
	if c.HeartbeatIntervalMultiplier <= 0 || c.HeartbeatIntervalMultiplier > 1 {
		return &ConfigurationError{
			Field:   "HeartbeatIntervalMultiplier",
			Message: "must be between 0 and 1 (exclusive)",
		}
	}

	return nil
}

// IsTunnelMode returns true if the space is configured for NATS tunneling.
func (c *Config) IsTunnelMode() bool {
	return strings.HasPrefix(c.SpaceURL, "tunneling:")
}

// GetTunnelUsername extracts the username from a tunneling:username SpaceURL.
func (c *Config) GetTunnelUsername() string {
	if !c.IsTunnelMode() {
		return ""
	}
	return strings.TrimPrefix(c.SpaceURL, "tunneling:")
}

// HeartbeatInterval returns the calculated heartbeat interval.
func (c *Config) HeartbeatInterval() time.Duration {
	seconds := float64(c.HeartbeatTTLSeconds) * c.HeartbeatIntervalMultiplier
	return time.Duration(seconds * float64(time.Second))
}

// WatchDebounce returns the watch debounce duration.
func (c *Config) WatchDebounce() time.Duration {
	return time.Duration(c.WatchDebounceSeconds * float64(time.Second))
}

// DeriveNATSWebSocketURL derives the NATS WebSocket URL from a SyftHub URL.
// Note: Returns URL without path - use nats.ProxyPath("/nats") option instead.
// See: https://github.com/nats-io/nats.go/issues/859
// http://host:port  -> ws://host:port
// https://host:port -> wss://host:port
// Returns error if URL does not start with http:// or https://.
func DeriveNATSWebSocketURL(syfthubURL string) (string, error) {
	if strings.HasPrefix(syfthubURL, "https://") {
		host := strings.TrimRight(syfthubURL[len("https://"):], "/")
		// Add default port if not specified (nats.go requires explicit port)
		if !strings.Contains(host, ":") {
			host += ":443"
		}
		return "wss://" + host, nil
	}
	if strings.HasPrefix(syfthubURL, "http://") {
		host := strings.TrimRight(syfthubURL[len("http://"):], "/")
		// Add default port if not specified
		if !strings.Contains(host, ":") {
			host += ":80"
		}
		return "ws://" + host, nil
	}
	return "", fmt.Errorf("cannot derive NATS URL from %q: must start with http:// or https://", syfthubURL)
}

// Option is a functional option for configuring SyftAPI.
type Option func(*Config)

// WithSyftHubURL sets the SyftHub backend URL.
func WithSyftHubURL(url string) Option {
	return func(c *Config) {
		c.SyftHubURL = url
	}
}

// WithAPIKey sets the API key for authentication.
func WithAPIKey(key string) Option {
	return func(c *Config) {
		c.APIKey = key
	}
}

// WithSpaceURL sets the space URL.
func WithSpaceURL(url string) Option {
	return func(c *Config) {
		c.SpaceURL = url
	}
}

// WithLogLevel sets the logging level.
func WithLogLevel(level string) Option {
	return func(c *Config) {
		c.LogLevel = level
	}
}

// WithServerHost sets the HTTP server host.
func WithServerHost(host string) Option {
	return func(c *Config) {
		c.ServerHost = host
	}
}

// WithServerPort sets the HTTP server port.
func WithServerPort(port int) Option {
	return func(c *Config) {
		c.ServerPort = port
	}
}

// WithHeartbeatEnabled enables or disables heartbeat.
func WithHeartbeatEnabled(enabled bool) Option {
	return func(c *Config) {
		c.HeartbeatEnabled = enabled
	}
}

// WithHeartbeatTTL sets the heartbeat TTL in seconds.
func WithHeartbeatTTL(seconds int) Option {
	return func(c *Config) {
		c.HeartbeatTTLSeconds = seconds
	}
}

// WithHeartbeatIntervalMultiplier sets the heartbeat interval multiplier.
func WithHeartbeatIntervalMultiplier(multiplier float64) Option {
	return func(c *Config) {
		c.HeartbeatIntervalMultiplier = multiplier
	}
}

// WithEndpointsPath sets the file-based endpoints directory.
func WithEndpointsPath(path string) Option {
	return func(c *Config) {
		c.EndpointsPath = path
	}
}

// WithWatchEnabled enables or disables file watching.
func WithWatchEnabled(enabled bool) Option {
	return func(c *Config) {
		c.WatchEnabled = enabled
	}
}

// WithWatchDebounce sets the watch debounce duration in seconds.
func WithWatchDebounce(seconds float64) Option {
	return func(c *Config) {
		c.WatchDebounceSeconds = seconds
	}
}

// WithPythonPath sets the path to the Python interpreter.
func WithPythonPath(path string) Option {
	return func(c *Config) {
		c.PythonPath = path
	}
}
