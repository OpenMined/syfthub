package transport

import (
	"context"
	"crypto/ecdh"
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

	// privateKey is the long-term X25519 private key used to decrypt incoming
	// tunnel requests. Generated at construction time; never rotated at runtime.
	privateKey *ecdh.PrivateKey

	mu      sync.Mutex
	running bool
	stopCh  chan struct{}
}

// NewNATSTransport creates a new NATS transport.
// A fresh X25519 keypair is generated immediately at construction time.
// Call PublicKeyB64() to retrieve the public key, then register it with the hub
// via APIAuthenticator.RegisterEncryptionPublicKey before starting the transport.
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

	privateKey, err := GenerateX25519Keypair()
	if err != nil {
		return nil, &syfthubapi.ConfigurationError{
			Field:   "encryption_keypair",
			Message: fmt.Sprintf("failed to generate X25519 keypair: %v", err),
		}
	}

	return &NATSTransport{
		config:     cfg,
		logger:     logger,
		privateKey: privateKey,
		stopCh:     make(chan struct{}),
	}, nil
}

// PublicKeyB64 returns the base64url-encoded X25519 public key for this transport.
// Register this with the hub so the aggregator can encrypt requests to this space.
func (t *NATSTransport) PublicKeyB64() string {
	return b64urlEncode(t.privateKey.PublicKey().Bytes())
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

	tokenPreview := creds.Token
	if len(tokenPreview) > 20 {
		tokenPreview = tokenPreview[:20]
	}
	t.logger.Debug("connecting with token", "token_prefix", tokenPreview)

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

	// Parse the tunnel request envelope
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

	// Decrypt the request payload — all requests must be encrypted (no plaintext fallback).
	if req.EncryptionInfo == nil || req.EncryptedPayload == "" {
		t.logger.Error("request missing encryption fields — plaintext requests are not accepted",
			"correlation_id", req.CorrelationID,
		)
		t.sendErrorResponse(msg, &req, "DECRYPTION_FAILED", "request must be encrypted (encryption_info and encrypted_payload are required)")
		return
	}

	plaintext, err := DecryptTunnelRequest(
		req.EncryptedPayload,
		req.EncryptionInfo,
		t.privateKey,
		req.CorrelationID,
	)
	if err != nil {
		t.logger.Error("failed to decrypt request payload",
			"correlation_id", req.CorrelationID,
			"error", err,
		)
		t.sendErrorResponse(msg, &req, "DECRYPTION_FAILED", "failed to decrypt request payload")
		return
	}
	req.Payload = json.RawMessage(plaintext)

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
	t.sendResponse(msg, &req, resp)
}

// sendResponse sends a response to the reply subject.
// req is the original parsed request; it may be nil only when the request envelope
// itself could not be parsed (in which case no encryption is applied).
func (t *NATSTransport) sendResponse(msg *nats.Msg, req *syfthubapi.TunnelRequest, resp *syfthubapi.TunnelResponse) {
	// Build reply subject — use ReplyTo from the parsed request when available.
	replySubject := ""
	if req != nil && req.ReplyTo != "" {
		// The aggregator subscribes to "syfthub.peer.{peer_channel}" for replies.
		replySubject = "syfthub.peer." + req.ReplyTo
	} else if msg.Reply != "" {
		// Fall back to NATS reply subject (already fully qualified).
		replySubject = msg.Reply
	}

	if replySubject == "" {
		t.logger.Warn("no reply subject available",
			"correlation_id", resp.CorrelationID,
		)
		return
	}

	// Encrypt the response payload.
	// All responses to encrypted requests MUST carry encrypted_payload so the aggregator
	// can decrypt them. For error responses with no payload we encrypt JSON null.
	if req != nil && req.EncryptionInfo != nil {
		payloadToEncrypt := resp.Payload
		if len(payloadToEncrypt) == 0 {
			payloadToEncrypt = []byte("null")
		}

		encInfo, encPayloadB64, err := EncryptTunnelResponse(
			payloadToEncrypt,
			req.EncryptionInfo.EphemeralPublicKey,
			resp.CorrelationID,
		)
		if err != nil {
			t.logger.Error("failed to encrypt response — dropping message",
				"correlation_id", resp.CorrelationID,
				"error", err,
			)
			// Cannot produce an encrypted response; drop the message so the aggregator
			// times out rather than receiving a malformed unencrypted reply.
			return
		}

		resp.EncryptionInfo = encInfo
		resp.EncryptedPayload = encPayloadB64
		resp.Payload = nil // clear plaintext; only encrypted_payload is sent
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
	t.sendResponse(msg, req, resp)
}

// Ensure NATSTransport implements Transport.
var _ Transport = (*NATSTransport)(nil)
