// Package transport provides transport implementations for SyftAPI.
package transport

import (
	"log/slog"

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
	Logger *slog.Logger

	// NATSCredentials are the NATS credentials (for tunnel mode).
	NATSCredentials *syfthubapi.NATSCredentials

	// KeyFilePath is the path to persist the X25519 private key for NATS encryption.
	// If set, the key is loaded from this file on startup (or generated and saved if missing).
	// If empty, a new ephemeral key is generated every time.
	KeyFilePath string
}

// New creates a transport from the configuration. For tunnel mode it dials a
// dedicated NATS connection that the returned transport owns and closes on
// Stop. Callers that need to share the connection — e.g. a desktop that also
// runs an outbound AgentDialer — should create a NATSConn explicitly and call
// NewNATSTransport.
func New(cfg *Config) (Transport, error) {
	if syfthubapi.IsTunnelMode(cfg.SpaceURL) {
		name := "syfthub-space-" + syfthubapi.GetTunnelUsername(cfg.SpaceURL)
		natsConn, err := NewNATSConn(cfg.NATSCredentials, name, cfg.Logger)
		if err != nil {
			return nil, err
		}
		t, err := NewNATSTransport(natsConn, cfg)
		if err != nil {
			natsConn.Close()
			return nil, err
		}
		t.ownsConn = true
		return t, nil
	}
	return NewHTTPTransport(cfg)
}
