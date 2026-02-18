// Package transport provides transport implementations for SyftAPI.
package transport

import (
	"strings"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// Re-export syfthubapi types for convenience within this package
type (
	// Transport is an alias for syfthubapi.Transport
	Transport = syfthubapi.Transport

	// RequestHandler is an alias for syfthubapi.RequestHandler
	RequestHandler = syfthubapi.RequestHandler
)

// Config holds transport configuration.
type Config struct {
	// SpaceURL is the space URL or tunneling:username.
	SpaceURL string

	// Host is the HTTP server bind address.
	Host string

	// Port is the HTTP server port.
	Port int

	// Logger is the logger to use.
	Logger syfthubapi.Logger

	// NATSCredentials are the NATS credentials (for tunnel mode).
	NATSCredentials *syfthubapi.NATSCredentials
}

// Logger interface for transport logging.
type Logger interface {
	Debug(msg string, args ...any)
	Info(msg string, args ...any)
	Warn(msg string, args ...any)
	Error(msg string, args ...any)
}

// New creates a new transport based on the configuration.
func New(cfg *Config) (Transport, error) {
	if strings.HasPrefix(cfg.SpaceURL, "tunneling:") {
		return NewNATSTransport(cfg)
	}
	return NewHTTPTransport(cfg)
}

// IsTunnelMode returns true if the URL indicates tunnel mode.
func IsTunnelMode(spaceURL string) bool {
	return strings.HasPrefix(spaceURL, "tunneling:")
}

// GetTunnelUsername extracts the username from a tunneling URL.
func GetTunnelUsername(spaceURL string) string {
	if !IsTunnelMode(spaceURL) {
		return ""
	}
	return strings.TrimPrefix(spaceURL, "tunneling:")
}
