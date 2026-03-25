package transport

import (
	"bytes"
	"context"
	"crypto/ecdh"
	"encoding/json"
	"fmt"
	"log/slog"
	"strconv"
	"sync"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// TokenVerifier is a callback that verifies a satellite token and returns
// the authenticated user context. It mirrors the signature of
// RequestProcessor.verifyToken / AuthClient.VerifyToken so the transport
// layer can verify tokens without importing the processor directly.
type TokenVerifier func(ctx context.Context, token string) (*syfthubapi.UserContext, error)

// agentNATSBridge adapts the parent-package AgentSessionHandler interface
// to handle NATS-level concerns (decryption, token verification, event relay).
type agentNATSBridge struct {
	handler       syfthubapi.AgentSessionHandler
	transport     *NATSTransport
	tokenVerifier TokenVerifier
	logger        *slog.Logger
}

// handleAgentMessage decrypts an agent NATS message and delegates to the session handler.
func (b *agentNATSBridge) handleAgentMessage(msg *nats.Msg, req *syfthubapi.TunnelRequest, privateKey *ecdh.PrivateKey) {
	// All agent messages must be encrypted
	if req.EncryptionInfo == nil || req.EncryptedPayload == "" {
		b.logger.Error("[AGENT] agent message missing encryption fields",
			"correlation_id", req.CorrelationID, "type", req.Type)
		b.transport.sendErrorResponse(msg, req, "DECRYPTION_FAILED", "agent messages must be encrypted")
		return
	}

	plaintext, err := DecryptTunnelRequest(req.EncryptedPayload, req.EncryptionInfo, privateKey, req.CorrelationID)
	if err != nil {
		b.logger.Error("[AGENT] failed to decrypt agent message",
			"correlation_id", req.CorrelationID, "error", err)
		b.transport.sendErrorResponse(msg, req, "DECRYPTION_FAILED", "failed to decrypt agent message")
		return
	}

	switch req.Type {
	case syfthubapi.MsgTypeAgentSessionStart:
		b.handleSessionStart(msg, req, plaintext)
	case syfthubapi.MsgTypeAgentUserMessage:
		b.handleUserMessage(plaintext)
	case syfthubapi.MsgTypeAgentSessionCancel:
		b.handleSessionCancel(plaintext)
	}
}

func (b *agentNATSBridge) handleSessionStart(msg *nats.Msg, req *syfthubapi.TunnelRequest, payload []byte) {
	var startPayload syfthubapi.AgentSessionStartPayload
	if err := json.Unmarshal(payload, &startPayload); err != nil {
		b.logger.Error("[AGENT] failed to parse session start payload", "error", err)
		b.transport.sendErrorResponse(msg, req, "INVALID_REQUEST", "failed to parse session start payload")
		return
	}

	// Verify satellite token to get real user identity
	if b.tokenVerifier == nil {
		b.logger.Error("[AGENT] token verifier not configured — cannot authenticate agent session",
			"endpoint", startPayload.EndpointSlug)
		b.transport.sendErrorResponse(msg, req, string(syfthubapi.TunnelErrorCodeAuthFailed),
			"agent session authentication not configured")
		return
	}

	if req.SatelliteToken == "" {
		b.logger.Warn("[AGENT] agent session start missing satellite token",
			"endpoint", startPayload.EndpointSlug)
		b.transport.sendErrorResponse(msg, req, string(syfthubapi.TunnelErrorCodeAuthFailed),
			"missing satellite token")
		return
	}

	verifyCtx, verifyCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer verifyCancel()

	user, err := b.tokenVerifier(verifyCtx, req.SatelliteToken)
	if err != nil {
		b.logger.Warn("[AGENT] agent session token verification failed",
			"endpoint", startPayload.EndpointSlug, "error", err)
		b.transport.sendErrorResponse(msg, req, string(syfthubapi.TunnelErrorCodeAuthFailed),
			"agent session authentication failed")
		return
	}

	b.logger.Info("[AGENT] user authenticated for agent session",
		"endpoint", startPayload.EndpointSlug,
		"user_sub", user.Sub, "username", user.Username)

	session, err := b.handler.StartSession(startPayload, user)
	if err != nil {
		b.logger.Error("[AGENT] failed to start session",
			"endpoint", startPayload.EndpointSlug, "error", err)
		b.transport.sendErrorResponse(msg, req, string(syfthubapi.TunnelErrorCodeExecutionFailed),
			fmt.Sprintf("failed to start agent session: %v", err))
		return
	}

	// Start relay goroutine: read from session.sendCh and publish encrypted events to peer channel
	go b.relayEvents(session, req.ReplyTo, req.EncryptionInfo.EphemeralPublicKey)

	b.logger.Info("[AGENT] session started successfully",
		"session_id", session.ID, "endpoint", startPayload.EndpointSlug,
		"user_sub", user.Sub, "username", user.Username, "reply_to", req.ReplyTo)
}

func (b *agentNATSBridge) handleUserMessage(payload []byte) {
	var msgPayload syfthubapi.AgentUserMessagePayload
	if err := json.Unmarshal(payload, &msgPayload); err != nil {
		b.logger.Error("[AGENT] failed to parse user message payload", "error", err)
		return
	}

	if err := b.handler.RouteMessage(msgPayload); err != nil {
		b.logger.Warn("[AGENT] failed to route user message",
			"session_id", msgPayload.SessionID, "error", err)
	}
}

func (b *agentNATSBridge) handleSessionCancel(payload []byte) {
	var cancelPayload syfthubapi.AgentSessionCancelPayload
	if err := json.Unmarshal(payload, &cancelPayload); err != nil {
		b.logger.Error("[AGENT] failed to parse cancel payload", "error", err)
		return
	}

	if err := b.handler.CancelSession(cancelPayload.SessionID); err != nil {
		b.logger.Warn("[AGENT] failed to cancel session",
			"session_id", cancelPayload.SessionID, "error", err)
	}
}

// relayEvents reads events from the agent session's sendCh and publishes them
// as encrypted agent_event messages to the peer channel via NATS.
//
// The expensive X25519 keypair generation + ECDH + HKDF key derivation is
// performed once at the start via SessionEncryptor. Each event is then encrypted
// with the pre-derived AES-256-GCM key using a unique random nonce.
//
// Optimizations for high-frequency token streaming:
//   - AgentEventPayload JSON is built manually via appendEventJSON, avoiding
//     encoding/json reflection overhead. Since Data is already json.RawMessage,
//     it is spliced in verbatim — no re-serialization.
//   - Correlation IDs use string concatenation + strconv instead of fmt.Sprintf.
//   - A reusable bytes.Buffer reduces per-event heap allocations for the event JSON.
func (b *agentNATSBridge) relayEvents(session *syfthubapi.AgentSession, replyTo string, requestEphPubKeyB64 string) {
	subject := "syfthub.peer." + replyTo

	// Pre-compute the session encryption context: one ephemeral keypair + ECDH + HKDF
	// for the entire event stream. Individual events get unique random nonces.
	encryptor, err := NewSessionEncryptor(requestEphPubKeyB64)
	if err != nil {
		b.logger.Error("[AGENT] failed to initialize session encryptor — cannot relay events",
			"session_id", session.ID, "error", err)
		// Drain the channel to avoid blocking the session goroutine
		for range session.SendCh() {
		}
		return
	}

	// Pre-encode the session ID JSON string once; reused in every event.
	sessionIDJSON, _ := json.Marshal(session.ID)

	// Reusable buffer for building event JSON without per-event allocation.
	var buf bytes.Buffer

	// Pre-allocate the NATS message and header map once for the entire session.
	// Per-event we only reassign Data and header values, avoiding repeated
	// map + slice allocations on the hot token-streaming path.
	msg := nats.NewMsg(subject)
	msg.Header.Set("Syft-Session-Id", session.ID)

	for event := range session.SendCh() {
		// Build AgentEventPayload JSON manually. The struct has a fixed 4-field
		// schema and Data is already json.RawMessage, so we splice it verbatim
		// instead of paying encoding/json reflection cost per event.
		buf.Reset()
		appendEventJSON(&buf, sessionIDJSON, event)
		eventJSON := buf.Bytes()

		// Build correlation ID without fmt.Sprintf overhead.
		correlationID := session.ID + "-" + strconv.Itoa(event.Sequence)

		// Encrypt with the pre-derived key; each event gets a unique random nonce
		encInfo, encPayload, err := encryptor.Encrypt(eventJSON, correlationID)
		if err != nil {
			b.logger.Error("[AGENT] failed to encrypt event", "session_id", session.ID, "error", err)
			continue
		}

		response := syfthubapi.TunnelResponse{
			Protocol:         syfthubapi.TunnelProtocolV1,
			Type:             syfthubapi.MsgTypeAgentEvent,
			CorrelationID:    correlationID,
			SessionID:        session.ID,
			EndpointSlug:     session.EndpointSlug,
			Status:           syfthubapi.TunnelStatusSuccess,
			EncryptionInfo:   encInfo,
			EncryptedPayload: encPayload,
		}

		respJSON, err := json.Marshal(response)
		if err != nil {
			b.logger.Error("[AGENT] failed to marshal response", "session_id", session.ID, "error", err)
			continue
		}

		// Reuse the pre-allocated msg — only update per-event fields.
		msg.Header.Set("Syft-Msg-Type", event.EventType)
		msg.Header.Set("Syft-Sequence", strconv.Itoa(event.Sequence))
		msg.Data = respJSON
		if err := b.transport.PublishMsg(msg); err != nil {
			b.logger.Error("[AGENT] failed to publish event", "session_id", session.ID, "error", err)
		}
	}

	b.logger.Info("[AGENT] event relay stopped", "session_id", session.ID)
}

// appendEventJSON writes the JSON encoding of an AgentEventPayload to buf
// without using encoding/json reflection. Since Data is json.RawMessage (already
// valid JSON bytes), it is spliced verbatim — the only encoding overhead is
// json.Marshal for the EventType string, which handles any characters that
// require JSON escaping (SessionID is pre-encoded once per session).
//
// Output format: {"session_id":...,"event_type":...,"sequence":N,"data":...}
func appendEventJSON(buf *bytes.Buffer, sessionIDJSON []byte, event syfthubapi.AgentEventPayload) {
	eventTypeJSON, _ := json.Marshal(event.EventType)

	buf.WriteString(`{"session_id":`)
	buf.Write(sessionIDJSON)
	buf.WriteString(`,"event_type":`)
	buf.Write(eventTypeJSON)
	buf.WriteString(`,"sequence":`)
	buf.WriteString(strconv.Itoa(event.Sequence))
	buf.WriteString(`,"data":`)
	if len(event.Data) == 0 {
		buf.WriteString("null")
	} else {
		buf.Write(event.Data)
	}
	buf.WriteByte('}')
}

// NATSTransport implements Transport for NATS tunnel mode.
type NATSTransport struct {
	conn        *nats.Conn
	sub         *nats.Subscription
	handler     RequestHandler
	agentBridge *agentNATSBridge
	config      *Config
	logger      *slog.Logger

	// privateKey is the long-term X25519 private key used to decrypt incoming
	// tunnel requests. Generated at construction time; never rotated at runtime.
	privateKey *ecdh.PrivateKey

	mu      sync.Mutex
	running bool
	stopCh  chan struct{}
}

// NewNATSTransport creates a new NATS transport.
// If cfg.KeyFilePath is set, the X25519 keypair is loaded from (or generated and
// saved to) that file so the key survives restarts. Otherwise a fresh ephemeral
// keypair is generated.
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

	var privateKey *ecdh.PrivateKey
	var err error
	if cfg.KeyFilePath != "" {
		privateKey, err = loadOrGenerateKey(cfg.KeyFilePath)
	} else {
		privateKey, err = GenerateX25519Keypair()
	}
	if err != nil {
		return nil, &syfthubapi.ConfigurationError{
			Field:   "encryption_keypair",
			Message: fmt.Sprintf("failed to load or generate X25519 keypair: %v", err),
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
		nats.Name(fmt.Sprintf("syfthub-space-%s", syfthubapi.GetTunnelUsername(t.config.SpaceURL))),
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

	// Attempt to initialize JetStream KV session registry for agent sessions.
	// Gracefully degrades if JetStream is not available on the server.
	if t.agentBridge != nil {
		registry, err := NewNATSSessionRegistry(conn, t.logger)
		if err != nil {
			t.logger.Warn("JetStream KV session registry not available — continuing without it", "error", err)
		} else {
			// Wire registry to the session manager via the SessionRegistrar interface.
			type registrarSetter interface {
				SetRegistrar(r syfthubapi.SessionRegistrar)
			}
			if rs, ok := t.agentBridge.handler.(registrarSetter); ok {
				rs.SetRegistrar(registry)
				t.logger.Info("JetStream KV session registry wired to agent session manager")
			}
		}
	}

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

// SetAgentHandler sets the handler for agent session messages.
// Accepts an AgentSessionHandler from the parent package and creates a NATS bridge.
func (t *NATSTransport) SetAgentHandler(handler syfthubapi.AgentSessionHandler) {
	t.agentBridge = &agentNATSBridge{
		handler:   handler,
		transport: t,
		logger:    t.logger,
	}
}

// SetTokenVerifier sets the token verification callback for agent sessions.
// Must be called after SetAgentHandler. The verifier is used to authenticate
// satellite tokens on agent_session_start messages, extracting the real user
// identity instead of using a placeholder.
func (t *NATSTransport) SetTokenVerifier(verifier TokenVerifier) {
	if t.agentBridge != nil {
		t.agentBridge.tokenVerifier = verifier
	}
}

// PublishMsg publishes a NATS message with headers to a subject.
// Used by the agent event relay to attach session metadata headers
// (Syft-Session-Id, Syft-Msg-Type, Syft-Sequence) for transport-level filtering.
func (t *NATSTransport) PublishMsg(msg *nats.Msg) error {
	if t.conn == nil {
		return fmt.Errorf("NATS connection not established")
	}
	return t.conn.PublishMsg(msg)
}

// PrivateKey returns the transport's X25519 private key for agent message decryption.
func (t *NATSTransport) PrivateKey() *ecdh.PrivateKey {
	return t.privateKey
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
		"type", req.Type,
	)

	// Dispatch agent messages to the agent bridge before the standard pipeline.
	// The bridge handles decryption, session management, and NATS event relay.
	switch req.Type {
	case syfthubapi.MsgTypeAgentSessionStart,
		syfthubapi.MsgTypeAgentUserMessage,
		syfthubapi.MsgTypeAgentSessionCancel:
		if t.agentBridge == nil {
			t.sendErrorResponse(msg, &req, "INVALID_REQUEST", "agent sessions not supported")
			return
		}
		t.agentBridge.handleAgentMessage(msg, &req, t.privateKey)
		return
	}

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

	// Publish response — relies on NATS auto-flushing (consistent with the
	// agent event relay path which intentionally skips per-publish flushing).
	if err := t.conn.Publish(replySubject, data); err != nil {
		t.logger.Error("failed to publish response",
			"correlation_id", resp.CorrelationID,
			"subject", replySubject,
			"error", err,
		)
		return
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
		Protocol:      syfthubapi.TunnelProtocolV1,
		Type:          syfthubapi.TunnelTypeResponse,
		CorrelationID: correlationID,
		Status:        syfthubapi.TunnelStatusError,
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
