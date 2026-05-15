package transport

import (
	"bytes"
	"context"
	"crypto/ecdh"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// agentLogSnapshotInterval is how often, at most, an in-flight agent session
// emits a "running" RequestLog snapshot via the configured log hook. A
// dedicated goroutine ticks at this rate and only emits when the event stream
// has produced something since the previous tick.
const agentLogSnapshotInterval = 1500 * time.Millisecond

// TokenVerifier is a callback that verifies a satellite token and returns
// the authenticated user context. It mirrors the signature of
// RequestProcessor.verifyToken / AuthClient.VerifyToken so the transport
// layer can verify tokens without importing the processor directly.
type TokenVerifier = func(ctx context.Context, token string) (*syfthubapi.UserContext, error)

// agentNATSBridge adapts the parent-package AgentSessionHandler interface
// to handle NATS-level concerns (decryption, token verification, event relay).
type agentNATSBridge struct {
	handler       syfthubapi.AgentSessionHandler
	transport     *NATSTransport
	tokenVerifier TokenVerifier
	logger        *slog.Logger
	// logHook is invoked at agent-session end with a RequestLog so the embedder
	// persists agent sessions through the same pipeline as model/data_source
	// requests. nil → no logging.
	logHook syfthubapi.RequestLogHook
	logMu   sync.Mutex // protects logHook against concurrent SetLogHook + emit
}

// handleAgentMessage decrypts an agent NATS message and delegates to the session handler.
func (b *agentNATSBridge) handleAgentMessage(msg *nats.Msg, req *syfthubapi.TunnelRequest, privateKey *ecdh.PrivateKey) {
	// All agent messages must be encrypted
	if req.EncryptionInfo == nil || req.EncryptedPayload == "" {
		b.logger.Error("[AGENT] agent message missing encryption fields",
			"correlation_id", req.CorrelationID, "type", req.Type)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeDecryptionFailed, "agent messages must be encrypted")
		return
	}

	plaintext, err := DecryptTunnelRequest(req.EncryptedPayload, req.EncryptionInfo, privateKey, req.CorrelationID)
	if err != nil {
		b.logger.Error("[AGENT] failed to decrypt agent message",
			"correlation_id", req.CorrelationID, "error", err)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeDecryptionFailed, "failed to decrypt agent message")
		return
	}

	switch req.Type {
	case syfthubapi.MsgTypeAgentSessionStart:
		b.handleSessionStart(msg, req, plaintext)
	case syfthubapi.MsgTypeAgentUserMessage:
		b.handleUserMessage(plaintext)
	case syfthubapi.MsgTypeAgentSessionCancel:
		b.handleSessionCancel(plaintext)
	case syfthubapi.MsgTypeAgentUserAttachment:
		b.handleUserAttachment(msg, req, plaintext)
	}
}

// handleUserAttachment decrypts an attachment delivery and routes it to the
// session. Inline-tier payloads are materialized to a tempfile under the
// session's AttachmentDir; the session's runner is then notified via
// AgentSession.DeliverAttachment. Object-store tier delegates to the
// session's AttachmentDownloader.
func (b *agentNATSBridge) handleUserAttachment(msg *nats.Msg, req *syfthubapi.TunnelRequest, payload []byte) {
	var attachPayload syfthubapi.AgentUserAttachmentPayload
	if err := json.Unmarshal(payload, &attachPayload); err != nil {
		b.logger.Error("[AGENT] failed to parse user attachment payload", "error", err)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeAttachmentInvalidMetadata, "invalid attachment metadata")
		return
	}

	info := attachPayload.Attachment
	sess, ok := b.handler.GetSession(attachPayload.SessionID)
	if !ok {
		b.logger.Warn("[AGENT] attachment for unknown session",
			"session_id", attachPayload.SessionID, "file_id", info.FileID)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeAttachmentNotFound, "session not found")
		return
	}

	if !sess.AttachmentsEnabled() {
		b.logger.Warn("[AGENT] attachment delivered to session without attachments enabled",
			"session_id", sess.ID, "file_id", info.FileID)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeAttachmentNotAccepted, "endpoint does not accept attachments")
		return
	}

	downloader := sess.AttachmentDownloader()
	if err := MaterializeAttachment(context.Background(), sess.AttachmentDir, &info, downloader); err != nil {
		b.logger.Error("[AGENT] failed to materialize attachment",
			"session_id", sess.ID, "file_id", info.FileID, "transport", info.Transport, "error", err)
		// Object-store failures may be transient (missing bucket/key, etc.);
		// surface a distinct error code so the aggregator can decide whether
		// to retry.
		errCode := syfthubapi.TunnelErrorCodeAttachmentIntegrity
		if info.Transport == syfthubapi.AttachmentTransportObjectStore {
			errCode = syfthubapi.TunnelErrorCodeAttachmentNotFound
		}
		b.transport.sendErrorResponse(msg, req, errCode, err.Error())
		return
	}

	if !sess.DeliverAttachment(info) {
		b.logger.Warn("[AGENT] attachment channel full, dropping",
			"session_id", sess.ID, "file_id", info.FileID)
	}
}

// materializeInlineAttachment decodes inline base64 bytes, verifies the
// declared SHA-256, and writes plaintext to a 0600-mode file inside dir.
// On success, info.LocalPath is set to the materialized file path so the
// runner protocol layer can hand it to the agent handler.
func materializeInlineAttachment(dir string, info *syfthubapi.AttachmentInfo) error {
	if info.Transport != syfthubapi.AttachmentTransportInline {
		return fmt.Errorf("inline materialization called for transport=%q", info.Transport)
	}
	if info.InlineDataB64 == "" {
		return fmt.Errorf("inline_data_b64 is empty")
	}
	raw, err := base64.StdEncoding.DecodeString(info.InlineDataB64)
	if err != nil {
		return fmt.Errorf("decode inline bytes: %w", err)
	}
	if int64(len(raw)) != info.SizeBytes {
		return fmt.Errorf("size mismatch: declared %d, actual %d", info.SizeBytes, len(raw))
	}
	sum := sha256.Sum256(raw)
	if hex.EncodeToString(sum[:]) != info.PlaintextSHA256 {
		return fmt.Errorf("sha256 mismatch")
	}

	// Use the file_id as the on-disk name to keep paths unguessable + 1:1
	// with the wire identifier. Preserve the original extension for the
	// runner's convenience.
	name := info.FileID
	if ext := filepath.Ext(info.Name); ext != "" {
		name += ext
	}
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		return fmt.Errorf("write attachment: %w", err)
	}
	info.LocalPath = path
	return nil
}

func (b *agentNATSBridge) handleSessionStart(msg *nats.Msg, req *syfthubapi.TunnelRequest, payload []byte) {
	startTime := time.Now()
	var startPayload syfthubapi.AgentSessionStartPayload
	if err := json.Unmarshal(payload, &startPayload); err != nil {
		b.logger.Error("[AGENT] failed to parse session start payload", "error", err)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeInvalidRequest, "failed to parse session start payload")
		return
	}

	// Verify satellite token to get real user identity
	if b.tokenVerifier == nil {
		b.logger.Error("[AGENT] token verifier not configured — cannot authenticate agent session",
			"endpoint", startPayload.EndpointSlug)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeAuthFailed,
			"agent session authentication not configured")
		return
	}

	if req.SatelliteToken == "" {
		b.logger.Warn("[AGENT] agent session start missing satellite token",
			"endpoint", startPayload.EndpointSlug)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeAuthFailed,
			"missing satellite token")
		return
	}

	verifyCtx, verifyCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer verifyCancel()

	user, err := b.tokenVerifier(verifyCtx, req.SatelliteToken)
	if err != nil {
		b.logger.Warn("[AGENT] agent session token verification failed",
			"endpoint", startPayload.EndpointSlug, "error", err)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeAuthFailed,
			"agent session authentication failed")
		return
	}

	b.logger.Info("[AGENT] user authenticated for agent session",
		"endpoint", startPayload.EndpointSlug,
		"user_sub", user.Sub, "username", user.Username)

	session, err := b.handler.StartSession(startPayload, user)
	if err == nil && session != nil && session.AttachmentsEnabled() && startPayload.SessionAttachmentKey != "" {
		keyBytes, decErr := base64.StdEncoding.DecodeString(startPayload.SessionAttachmentKey)
		if decErr != nil || len(keyBytes) != 32 {
			b.logger.Warn("[AGENT] invalid session_attachment_key — attachments will be inline-only",
				"session_id", session.ID, "decode_err", decErr, "len", len(keyBytes))
		} else {
			store, osErr := b.transport.getAttachmentObjectStore()
			if osErr != nil {
				b.logger.Warn("[AGENT] failed to init attachment Object Store — attachments will be inline-only",
					"session_id", session.ID, "error", osErr)
			} else {
				uploader, upErr := NewObjectStoreUploader(context.Background(), keyBytes, store, session.ID)
				if upErr != nil {
					b.logger.Warn("[AGENT] failed to bind ObjectStoreUploader",
						"session_id", session.ID, "error", upErr)
				} else {
					session.AttachmentUploader = uploader
				}
				dl, dlErr := NewObjectStoreDownloader(context.Background(), keyBytes, store)
				if dlErr != nil {
					b.logger.Warn("[AGENT] failed to bind ObjectStoreDownloader",
						"session_id", session.ID, "error", dlErr)
				} else {
					session.SetAttachmentDownloader(dl)
				}
			}
		}
	}
	if err != nil {
		// Transaction-style policies surface a typed PaymentRequiredError so we
		// can emit a structured PAYMENT_REQUIRED tunnel response carrying the
		// payment challenge and amount/recipient details.
		var payErr *syfthubapi.PaymentRequiredError
		if errors.As(err, &payErr) {
			b.logger.Info("[AGENT] session pending payment",
				"endpoint", startPayload.EndpointSlug,
				"user_sub", user.Sub, "username", user.Username)
			b.transport.sendPaymentRequiredResponse(msg, req, payErr.Details)
			return
		}
		b.logger.Error("[AGENT] failed to start session",
			"endpoint", startPayload.EndpointSlug, "error", err)
		// Pre-session failures (policy denial, auth) have no transcript yet —
		// synthesize one from the prompt so the log shows what was rejected.
		// Use a fresh logID because this entry has no in-flight predecessor
		// (the session never reached the relay loop).
		b.emitSessionLog(
			syfthubapi.NewRequestLogID(),
			startPayload.SessionID,
			startPayload.EndpointSlug,
			user,
			[]syfthubapi.Message{{Role: "user", Content: startPayload.Prompt}},
			len(startPayload.Prompt),
			syfthubapi.LogStatusFailed,
			err.Error(),
			startTime,
		)
		b.transport.sendErrorResponse(msg, req, syfthubapi.TunnelErrorCodeExecutionFailed,
			fmt.Sprintf("failed to start agent session: %v", err))
		return
	}

	// Start relay goroutine: read from session.sendCh and publish encrypted events to peer channel
	go b.relayEvents(session, req.ReplyTo, req.EncryptionInfo.EphemeralPublicKey, startTime)

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

// setLogHook stores the per-session log hook (concurrent-safe with emitSessionLog).
func (b *agentNATSBridge) setLogHook(h syfthubapi.RequestLogHook) {
	b.logMu.Lock()
	b.logHook = h
	b.logMu.Unlock()
}

// emitSessionLog builds a RequestLog snapshot for an agent session and invokes
// the configured hook. Safe to call with a nil hook (no-op). The same logID
// must be reused across every snapshot of a single session so downstream
// stores can upsert on it; `status` controls whether the entry is treated as
// in-flight (LogStatusRunning) or terminal (LogStatusCompleted /
// LogStatusFailed / LogStatusTerminated).
//
// For terminal-success entries, Response.Content is derived from the
// assistant-role messages already present in `transcript` (recorded by
// AgentSession.Send). `failError` is recorded on failure / cancellation paths
// (cancellation typically passes "" because the cancel is the expected outcome).
func (b *agentNATSBridge) emitSessionLog(
	logID, sessionID, endpointSlug string,
	user *syfthubapi.UserContext,
	transcript []syfthubapi.Message,
	rawSize int,
	status string,
	failError string,
	startTime time.Time,
) {
	b.logMu.Lock()
	hook := b.logHook
	b.logMu.Unlock()
	if hook == nil {
		return
	}

	processedAt := time.Now()
	log := &syfthubapi.RequestLog{
		ID:            logID,
		Timestamp:     startTime,
		CorrelationID: sessionID,
		EndpointSlug:  endpointSlug,
		EndpointType:  string(syfthubapi.EndpointTypeAgent),
		Status:        status,
		Request: &syfthubapi.LogRequest{
			Type:     string(syfthubapi.EndpointTypeAgent),
			Messages: transcript,
			RawSize:  rawSize,
		},
		Response: &syfthubapi.LogResponse{},
		Timing: &syfthubapi.LogTiming{
			ReceivedAt:  startTime,
			ProcessedAt: processedAt,
			DurationMs:  processedAt.Sub(startTime).Milliseconds(),
		},
	}

	if user != nil {
		log.User = &syfthubapi.LogUserInfo{
			ID:       user.Sub,
			Username: user.Username,
			Email:    user.Email,
			Role:     user.Role,
		}
	}

	switch status {
	case syfthubapi.LogStatusCompleted:
		log.Response.Success = true
		content, truncated := syfthubapi.TruncateForLog(joinAssistantContent(transcript))
		log.Response.Content = content
		log.Response.ContentTruncated = truncated
	case syfthubapi.LogStatusRunning:
		// In-flight snapshot: surface whatever assistant content has been
		// produced so far so the operator sees the transcript grow. Success
		// stays false because the session has not finalized yet.
		log.Response.Success = false
		content, truncated := syfthubapi.TruncateForLog(joinAssistantContent(transcript))
		log.Response.Content = content
		log.Response.ContentTruncated = truncated
	default:
		// LogStatusFailed / LogStatusTerminated / unknown — record any error
		// message but no synthetic success content.
		log.Response.Success = false
		log.Response.Error = failError
	}

	hook(context.Background(), log)
}

// joinAssistantContent concatenates the Content of all assistant-role messages
// in transcript with newline separators.
func joinAssistantContent(transcript []syfthubapi.Message) string {
	total := 0
	for _, m := range transcript {
		if m.Role == "assistant" {
			total += len(m.Content) + 1
		}
	}
	if total == 0 {
		return ""
	}
	out := make([]byte, 0, total)
	for _, m := range transcript {
		if m.Role != "assistant" {
			continue
		}
		if len(out) > 0 {
			out = append(out, '\n')
		}
		out = append(out, m.Content...)
	}
	return string(out)
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
func (b *agentNATSBridge) relayEvents(session *syfthubapi.AgentSession, replyTo string, requestEphPubKeyB64 string, startTime time.Time) {
	subject := "syfthub.peer." + replyTo
	// failError is captured from the (at most one) terminal session.failed event
	// so it can be reported in the per-session RequestLog after the loop exits.
	var failError string

	// Single stable log ID for every snapshot of this session. The desktop
	// log store and frontend both upsert on RequestLog.ID, so reusing the
	// same value across the initial / mid-session / terminal emits causes the
	// same row to update in place instead of producing duplicates.
	logID := syfthubapi.NewRequestLogID()

	// emit captures the per-session fields shared by every snapshot so the
	// caller only varies status + error message. Builds the transcript copy
	// lazily inside emitSessionLog only when the hook is actually wired up.
	emit := func(status, errMsg string) {
		b.emitSessionLog(
			logID,
			session.ID,
			session.EndpointSlug,
			session.User,
			session.Transcript(),
			len(session.InitialPrompt),
			status,
			errMsg,
			startTime,
		)
	}

	encryptor, err := NewSessionEncryptor(requestEphPubKeyB64)
	if err != nil {
		b.logger.Error("[AGENT] failed to initialize session encryptor — cannot relay events",
			"session_id", session.ID, "error", err)
		emit(syfthubapi.LogStatusFailed, "failed to initialize session encryptor")
		for range session.SendCh() {
		}
		return
	}

	emit(syfthubapi.LogStatusRunning, "")

	// Coalesced snapshot ticker. The relay can fire hundreds of events/sec on
	// a streaming model; emitting per-event would saturate the log pipeline.
	// Tokens don't mutate the loggable transcript, so the dirty flag is only
	// set for transcript-changing events (see EventTypeAgentMessage branch
	// in the loop below) — otherwise the ticker would re-emit byte-identical
	// snapshots every interval for the duration of a long stream.
	var dirty atomic.Bool
	tickerDone := make(chan struct{})
	tickerStopped := make(chan struct{})
	go func() {
		ticker := time.NewTicker(agentLogSnapshotInterval)
		defer ticker.Stop()
		defer close(tickerStopped)
		for {
			select {
			case <-tickerDone:
				return
			case <-ticker.C:
				if !dirty.Swap(false) {
					continue
				}
				emit(syfthubapi.LogStatusRunning, "")
			}
		}
	}()
	// Defer the ticker shutdown so any future early-return between here and
	// the terminal emit can't leak the goroutine.
	defer func() {
		close(tickerDone)
		<-tickerStopped
	}()

	// Pre-encode the session ID JSON string once; reused in every event.
	sessionIDJSON, _ := json.Marshal(session.ID)

	// Reusable buffer for building event JSON without per-event allocation.
	var buf bytes.Buffer

	// Pre-allocate the NATS message and header map once for the entire session.
	// Per-event we only reassign Data and header values, avoiding repeated
	// map + slice allocations on the hot token-streaming path.
	msg := nats.NewMsg(subject)
	msg.Header.Set("Syft-Session-Id", session.ID)

	// The terminal outcome is decided by which event RunHandler put on the
	// channel, NOT by the session context. Some agent runners (notably the
	// filemode subprocess executor) call session.Cancel() after cmd.Wait
	// regardless of whether the subprocess exited cleanly — so ctx.Err() is
	// context.Canceled on every normal completion. We have to observe the
	// terminal event ourselves to disambiguate completed / failed / terminated.
	var sawCompleted, sawFailed bool

	for event := range session.SendCh() {
		switch event.EventType {
		case syfthubapi.EventTypeAgentMessage:
			// Assistant message appended to the session transcript — the
			// next ticker fire should emit a fresh snapshot. Tokens, status,
			// tool calls, etc. don't change the loggable Content so they
			// intentionally don't trip dirty.
			dirty.Store(true)
		case syfthubapi.EventTypeSessionCompleted:
			sawCompleted = true
		case syfthubapi.EventTypeSessionFailed:
			sawFailed = true
			// Best-effort failure-reason decode; safe outside the hot
			// token-stream path because session.failed is terminal.
			var failData struct {
				Error string `json:"error"`
			}
			if json.Unmarshal(event.Data, &failData) == nil && failData.Error != "" {
				failError = failData.Error
			}
		}

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

	// Decide the terminal status from the events we observed plus the
	// external-cancel flag. ctx.Err() alone is unreliable here: handlers like
	// the filemode subprocess bridge call session.Cancel() as cleanup after
	// cmd.Wait, so ctx is Canceled after every normal completion AND after
	// every user-requested stop. ExternalCancelled() is the authoritative
	// signal for "the user pressed Stop" and overrides any spurious
	// SessionFailed event produced by exec.CommandContext killing the
	// subprocess in response to that cancel.
	terminalStatus, failError := decideTerminalStatus(session, sawCompleted, sawFailed, failError)
	emit(terminalStatus, failError)
}

// decideTerminalStatus picks the final log status for an agent session from
// the terminal events the relay observed plus whether the session was
// cancelled externally. failErrorIn may be cleared (e.g. cancellation is not
// a real error) — the returned failError is what the terminal log should
// record.
func decideTerminalStatus(session *syfthubapi.AgentSession, sawCompleted, sawFailed bool, failErrorIn string) (status, failError string) {
	switch {
	case session.ExternalCancelled():
		return syfthubapi.LogStatusTerminated, ""
	case sawCompleted:
		return syfthubapi.LogStatusCompleted, ""
	case sawFailed:
		return syfthubapi.LogStatusFailed, failErrorIn
	case errors.Is(session.Context().Err(), context.Canceled):
		return syfthubapi.LogStatusTerminated, ""
	default:
		if failErrorIn == "" {
			failErrorIn = "session ended without a terminal event"
		}
		return syfthubapi.LogStatusFailed, failErrorIn
	}
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

	// attachmentObjectStore is lazily initialized on first attachment-capable
	// session. Shared across sessions on this transport.
	attachmentObjectStore AttachmentObjectStore
}

// getAttachmentObjectStore returns the lazily-initialized Object Store
// backing per-session attachment buckets. Safe for concurrent use.
func (t *NATSTransport) getAttachmentObjectStore() (AttachmentObjectStore, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.attachmentObjectStore != nil {
		return t.attachmentObjectStore, nil
	}
	store, err := NewNATSAttachmentObjectStore(t.conn)
	if err != nil {
		return nil, err
	}
	t.attachmentObjectStore = store
	return store, nil
}

// NewNATSTransport creates a new NATS transport.
// If cfg.KeyFilePath is set, the X25519 keypair is loaded from (or generated and
// saved to) that file so the key survives restarts. Otherwise a fresh ephemeral
// keypair is generated.
// Call PublicKeyB64() to retrieve the public key, then register it with the hub
// via APIAuthenticator.RegisterEncryptionPublicKey before starting the transport.
func NewNATSTransport(cfg *Config) (*NATSTransport, error) {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	if cfg.NATSCredentials == nil {
		return nil, fmt.Errorf("config: NATSCredentials is required for tunnel mode")
	}

	var privateKey *ecdh.PrivateKey
	var err error
	if cfg.KeyFilePath != "" {
		privateKey, err = loadOrGenerateKey(cfg.KeyFilePath)
	} else {
		privateKey, err = GenerateX25519Keypair()
	}
	if err != nil {
		return nil, fmt.Errorf("config: failed to load or generate X25519 keypair: %w", err)
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
		return fmt.Errorf("nats transport: failed to connect: %w", err)
	}
	t.conn = conn

	t.logger.Info("connected to NATS", "server", conn.ConnectedUrl())

	// Subscribe to the space's subject
	sub, err := conn.Subscribe(creds.Subject, t.handleMessage)
	if err != nil {
		conn.Close()
		return fmt.Errorf("nats transport: failed to subscribe: %w", err)
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

// SetAgentLogHook wires the embedder's RequestLog sink into the host-side
// agent session lifecycle. No-op until SetAgentHandler has constructed the
// bridge.
func (t *NATSTransport) SetAgentLogHook(hook syfthubapi.RequestLogHook) {
	if t.agentBridge != nil {
		t.agentBridge.setLogHook(hook)
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
		t.sendErrorResponse(msg, nil, syfthubapi.TunnelErrorCodeInvalidRequest, "failed to parse request")
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
		syfthubapi.MsgTypeAgentSessionCancel,
		syfthubapi.MsgTypeAgentUserAttachment:
		if t.agentBridge == nil {
			t.sendErrorResponse(msg, &req, syfthubapi.TunnelErrorCodeInvalidRequest, "agent sessions not supported")
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
		t.sendErrorResponse(msg, &req, syfthubapi.TunnelErrorCodeDecryptionFailed, "request must be encrypted (encryption_info and encrypted_payload are required)")
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
		t.sendErrorResponse(msg, &req, syfthubapi.TunnelErrorCodeDecryptionFailed, "failed to decrypt request payload")
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
		t.sendErrorResponse(msg, &req, syfthubapi.TunnelErrorCodeInternalError, err.Error())
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
func (t *NATSTransport) sendErrorResponse(msg *nats.Msg, req *syfthubapi.TunnelRequest, code syfthubapi.TunnelErrorCode, message string) {
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
			Code:    code,
			Message: message,
		},
	}
	t.sendResponse(msg, req, resp)
}

// sendPaymentRequiredResponse sends a PAYMENT_REQUIRED tunnel response with
// the supplied payment-challenge details placed on TunnelError.Details so the
// caller (aggregator / client) can surface the challenge to the user.
func (t *NATSTransport) sendPaymentRequiredResponse(msg *nats.Msg, req *syfthubapi.TunnelRequest, details map[string]any) {
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
			Code:    syfthubapi.TunnelErrorCodePaymentRequired,
			Message: "payment required",
			Details: details,
		},
	}
	t.sendResponse(msg, req, resp)
}

// Ensure NATSTransport implements Transport.
var _ Transport = (*NATSTransport)(nil)
