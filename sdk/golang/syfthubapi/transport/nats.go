package transport

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// NATSTransport implements Transport for NATS tunnel mode.
type NATSTransport struct {
	conn    *nats.Conn
	sub     *nats.Subscription
	handler RequestHandler
	config  *Config
	logger  *slog.Logger

	mu      sync.Mutex
	running bool
	stopCh  chan struct{}
}

// NewNATSTransport creates a new NATS transport.
func NewNATSTransport(cfg *Config) (*NATSTransport, error) {
	logger := slog.Default()
	if cfg.Logger != nil {
		if l, ok := cfg.Logger.(*slog.Logger); ok {
			logger = l
		}
	}

	if cfg.NATSCredentials == nil {
		return nil, &syfthubapi.ConfigurationError{
			Field:   "NATSCredentials",
			Message: "required for tunnel mode",
		}
	}

	return &NATSTransport{
		config: cfg,
		logger: logger,
		stopCh: make(chan struct{}),
	}, nil
}

// Start begins listening for NATS messages.
func (t *NATSTransport) Start(ctx context.Context) error {
	t.mu.Lock()
	if t.running {
		t.mu.Unlock()
		return fmt.Errorf("NATS transport already running")
	}
	t.running = true
	t.stopCh = make(chan struct{})
	t.mu.Unlock()

	creds := t.config.NATSCredentials

	t.logger.Info("connecting to NATS",
		"url", creds.URL,
		"subject", creds.Subject,
	)

	t.logger.Debug("connecting with token", "token_prefix", creds.Token[:20])

	// Connect to NATS with token auth (exactly like Python: nats.connect(url, token=token, name=name))
	// Note: ProxyPath("/nats") is required for nginx-proxied WebSocket connections
	// See: https://github.com/nats-io/nats.go/issues/859
	conn, err := nats.Connect(
		creds.URL,
		nats.Token(creds.Token),
		nats.Name(fmt.Sprintf("syfthub-space-%s", GetTunnelUsername(t.config.SpaceURL))),
		nats.ProxyPath("/nats"),
		nats.Timeout(30*time.Second),
		nats.ReconnectWait(2*time.Second),
		nats.MaxReconnects(-1),
		nats.ConnectHandler(func(nc *nats.Conn) {
			t.logger.Info("NATS connected successfully", "url", nc.ConnectedUrl())
		}),
		nats.DisconnectErrHandler(func(nc *nats.Conn, err error) {
			t.logger.Warn("NATS disconnected", "error", err)
		}),
		nats.ReconnectHandler(func(nc *nats.Conn) {
			t.logger.Info("NATS reconnected", "url", nc.ConnectedUrl())
		}),
		nats.ErrorHandler(func(nc *nats.Conn, sub *nats.Subscription, err error) {
			t.logger.Error("NATS error", "error", err)
		}),
		nats.ClosedHandler(func(nc *nats.Conn) {
			t.logger.Info("NATS connection closed")
		}),
	)
	if err != nil {
		return &syfthubapi.TransportError{
			Transport: "nats",
			Message:   "failed to connect",
			Cause:     err,
		}
	}
	t.conn = conn

	t.logger.Info("connected to NATS", "server", conn.ConnectedUrl())

	// Subscribe to the space's subject
	sub, err := conn.Subscribe(creds.Subject, t.handleMessage)
	if err != nil {
		conn.Close()
		return &syfthubapi.TransportError{
			Transport: "nats",
			Message:   "failed to subscribe",
			Cause:     err,
		}
	}
	t.sub = sub

	t.logger.Info("subscribed to NATS subject", "subject", creds.Subject)

	// Wait for context cancellation or stop signal
	select {
	case <-ctx.Done():
		return nil
	case <-t.stopCh:
		return nil
	}
}

// Stop gracefully shuts down the NATS transport.
func (t *NATSTransport) Stop(ctx context.Context) error {
	t.mu.Lock()
	if !t.running {
		t.mu.Unlock()
		return nil
	}
	t.running = false
	close(t.stopCh)
	t.mu.Unlock()

	t.logger.Info("stopping NATS transport")

	// Unsubscribe
	if t.sub != nil {
		if err := t.sub.Unsubscribe(); err != nil {
			t.logger.Warn("error unsubscribing", "error", err)
		}
	}

	// Drain and close connection
	if t.conn != nil {
		if err := t.conn.Drain(); err != nil {
			t.logger.Warn("error draining connection", "error", err)
		}
		t.conn.Close()
	}

	t.logger.Info("NATS transport stopped")
	return nil
}

// SetRequestHandler sets the request handler.
func (t *NATSTransport) SetRequestHandler(handler RequestHandler) {
	t.handler = handler
}

// handleMessage processes an incoming NATS message.
func (t *NATSTransport) handleMessage(msg *nats.Msg) {
	if t.handler == nil {
		t.logger.Error("no handler configured")
		return
	}

	// Parse the tunnel request
	var req syfthubapi.TunnelRequest
	if err := json.Unmarshal(msg.Data, &req); err != nil {
		t.logger.Error("failed to parse request",
			"error", err,
			"data", string(msg.Data),
		)
		t.sendErrorResponse(msg, nil, "INVALID_REQUEST", "failed to parse request")
		return
	}

	t.logger.Debug("received request",
		"correlation_id", req.CorrelationID,
		"endpoint", req.Endpoint.Slug,
		"reply_to", req.ReplyTo,
	)

	// Create context with timeout (use request timeout or default to 120s)
	timeout := 120 * time.Second
	if req.TimeoutMs > 0 {
		timeout = time.Duration(req.TimeoutMs) * time.Millisecond
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// Process request
	resp, err := t.handler(ctx, &req)
	if err != nil {
		t.logger.Error("handler error",
			"correlation_id", req.CorrelationID,
			"error", err,
		)
		t.sendErrorResponse(msg, &req, "INTERNAL_ERROR", err.Error())
		return
	}

	// Send response
	t.sendResponse(msg, resp)
}

// sendResponse sends a response to the reply subject.
func (t *NATSTransport) sendResponse(msg *nats.Msg, resp *syfthubapi.TunnelResponse) {
	// Parse the original request to get reply_to
	var req syfthubapi.TunnelRequest
	if err := json.Unmarshal(msg.Data, &req); err != nil {
		t.logger.Error("failed to parse request for reply", "error", err)
		return
	}

	// Build reply subject with syfthub.peer. prefix
	// The aggregator subscribes to "syfthub.peer.{peer_channel}" for replies
	replySubject := ""
	if req.ReplyTo != "" {
		replySubject = "syfthub.peer." + req.ReplyTo
	} else if msg.Reply != "" {
		// Fall back to NATS reply subject (already fully qualified)
		replySubject = msg.Reply
	}

	if replySubject == "" {
		t.logger.Warn("no reply subject available",
			"correlation_id", resp.CorrelationID,
		)
		return
	}

	// Serialize response
	data, err := json.Marshal(resp)
	if err != nil {
		t.logger.Error("failed to serialize response",
			"correlation_id", resp.CorrelationID,
			"error", err,
		)
		return
	}

	t.logger.Debug("response payload",
		"correlation_id", resp.CorrelationID,
		"json", string(data),
	)

	// Publish response
	if err := t.conn.Publish(replySubject, data); err != nil {
		t.logger.Error("failed to publish response",
			"correlation_id", resp.CorrelationID,
			"subject", replySubject,
			"error", err,
		)
		return
	}

	// Flush to ensure message is sent
	if err := t.conn.Flush(); err != nil {
		t.logger.Warn("flush after publish failed",
			"correlation_id", resp.CorrelationID,
			"error", err,
		)
	}

	t.logger.Debug("sent response",
		"correlation_id", resp.CorrelationID,
		"subject", replySubject,
		"status", resp.Status,
	)
}

// sendErrorResponse sends an error response.
func (t *NATSTransport) sendErrorResponse(msg *nats.Msg, req *syfthubapi.TunnelRequest, code, message string) {
	correlationID := ""
	endpointSlug := ""
	if req != nil {
		correlationID = req.CorrelationID
		endpointSlug = req.Endpoint.Slug
	}

	resp := &syfthubapi.TunnelResponse{
		Protocol:      "syfthub-tunnel/v1",
		Type:          "endpoint_response",
		CorrelationID: correlationID,
		Status:        "error",
		EndpointSlug:  endpointSlug,
		Error: &syfthubapi.TunnelError{
			Code:    syfthubapi.TunnelErrorCode(code),
			Message: message,
		},
	}
	t.sendResponse(msg, resp)
}

// Ensure NATSTransport implements Transport.
var _ Transport = (*NATSTransport)(nil)
