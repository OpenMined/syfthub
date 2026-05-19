// conn.go provides NATSConn, the single NATS connection shared by an app's
// inbound host transport (NATSTransport) and outbound agent client
// (AgentDialer). Centralizing the connection here keeps one set of connect /
// reconnect logic and lets a desktop multiplex many concurrent inbound and
// outbound agent sessions over one *nats.Conn.

package transport

import (
	"fmt"
	"log/slog"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// NATSConn owns a single *nats.Conn. It is safe for concurrent use: many
// subscriptions and publishes — inbound host sessions and outbound client
// sessions alike — share the one underlying connection.
type NATSConn struct {
	conn *nats.Conn
}

// NewNATSConn dials NATS with the given credentials. name identifies the
// connection in NATS monitoring (e.g. "syfthub-desktop-alice").
func NewNATSConn(creds *syfthubapi.NATSCredentials, name string, logger *slog.Logger) (*NATSConn, error) {
	if creds == nil {
		return nil, fmt.Errorf("nats credentials are required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	conn, err := nats.Connect(
		creds.URL,
		nats.Token(creds.Token),
		nats.Name(name),
		// ProxyPath is required for nginx-proxied WebSocket NATS connections
		// and is ignored for plain nats:// URLs.
		nats.ProxyPath("/nats"),
		nats.Timeout(30*time.Second),
		nats.ReconnectWait(2*time.Second),
		nats.MaxReconnects(-1),
		nats.ConnectHandler(func(nc *nats.Conn) {
			logger.Info("NATS connected", "url", nc.ConnectedUrl())
		}),
		nats.DisconnectErrHandler(func(_ *nats.Conn, err error) {
			logger.Warn("NATS disconnected", "error", err)
		}),
		nats.ReconnectHandler(func(nc *nats.Conn) {
			logger.Info("NATS reconnected", "url", nc.ConnectedUrl())
		}),
		nats.ClosedHandler(func(_ *nats.Conn) {
			logger.Info("NATS connection closed")
		}),
		nats.ErrorHandler(func(_ *nats.Conn, _ *nats.Subscription, err error) {
			logger.Error("NATS error", "error", err)
		}),
	)
	if err != nil {
		return nil, fmt.Errorf("connect to NATS at %s: %w", creds.URL, err)
	}
	return &NATSConn{conn: conn}, nil
}

// Conn returns the underlying *nats.Conn for subscribing and publishing.
func (c *NATSConn) Conn() *nats.Conn { return c.conn }

// Close closes the underlying NATS connection.
func (c *NATSConn) Close() {
	if c.conn != nil {
		c.conn.Close()
	}
}
