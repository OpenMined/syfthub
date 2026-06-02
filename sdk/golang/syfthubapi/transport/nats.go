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
	"github.com/openmined/syfthub/sdk/golang/agenttypes"
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

// handleAgentMessage decrypts a v2 agent envelope and dispatches it. The
// session cipher is derived from the sender's identity public key (carried in
// the plaintext wrapper) and the session id; the identical derivation on both
// peers yields matching keys.
func (b *agentNATSBridge) handleAgentMessage(env *syfthubapi.AgentEnvelope) {
	if env.SenderPublicKey == "" || env.EncryptedPayload == "" || env.SessionID == "" {
		b.logger.Error("[AGENT] v2 agent message missing required fields",
			"correlation_id", env.CorrelationID, "type", env.Type)
		return
	}

	cipher, err := NewSessionCipher(b.transport.privateKey, env.SenderPublicKey, env.SessionID)
	if err != nil {
		b.logger.Error("[AGENT] failed to derive session cipher",
			"correlation_id", env.CorrelationID, "error", err)
		return
	}

	plaintext, err := cipher.DecryptRequest(env.Nonce, env.EncryptedPayload, env.CorrelationID)
	if err != nil {
		b.logger.Error("[AGENT] failed to decrypt agent message",
			"correlation_id", env.CorrelationID, "type", env.Type, "error", err)
		// The cipher derived fine, so a session_start decryption failure can
		// still be reported — otherwise the client would wait forever.
		if env.Type == syfthubapi.MsgTypeAgentSessionStart {
			b.sendAgentEvent(env.ReplyTo, cipher, env.SessionID, syfthubapi.EventTypeSessionFailed,
				agenttypes.SessionFailedEvent{Error: "failed to decrypt session start", Reason: string(syfthubapi.TunnelErrorCodeDecryptionFailed)})
		}
		return
	}

	switch env.Type {
	case syfthubapi.MsgTypeAgentSessionStart:
		b.handleSessionStart(env, cipher, plaintext)
	case syfthubapi.MsgTypeAgentUserMessage:
		b.handleUserMessage(plaintext)
	case syfthubapi.MsgTypeAgentSessionCancel:
		b.handleSessionCancel(plaintext)
	case syfthubapi.MsgTypeAgentUserAttachment:
		b.handleUserAttachment(env, cipher, plaintext)
	}
}

// handleUserAttachment decrypts an attachment delivery and routes it to the
// session. Inline-tier payloads are materialized to a tempfile under the
// session's AttachmentDir; object-store tier delegates to the session's
// AttachmentDownloader. Delivery failures surface as a recoverable agent.error
// event so the session itself continues.
func (b *agentNATSBridge) handleUserAttachment(env *syfthubapi.AgentEnvelope, cipher *SessionCipher, payload []byte) {
	reject := func(code syfthubapi.TunnelErrorCode, msg string) {
		b.sendAgentEvent(env.ReplyTo, cipher, env.SessionID, syfthubapi.EventTypeAgentError,
			agenttypes.AgentErrorEvent{Code: string(code), Message: msg, Recoverable: true})
	}

	var attachPayload syfthubapi.AgentUserAttachmentPayload
	if err := json.Unmarshal(payload, &attachPayload); err != nil {
		b.logger.Error("[AGENT] failed to parse user attachment payload", "error", err)
		reject(syfthubapi.TunnelErrorCodeAttachmentInvalidMetadata, "invalid attachment metadata")
		return
	}

	info := attachPayload.Attachment
	sess, ok := b.handler.GetSession(attachPayload.SessionID)
	if !ok {
		b.logger.Warn("[AGENT] attachment for unknown session",
			"session_id", attachPayload.SessionID, "file_id", info.FileID)
		reject(syfthubapi.TunnelErrorCodeAttachmentNotFound, "session not found")
		return
	}

	if !sess.AttachmentsEnabled() {
		b.logger.Warn("[AGENT] attachment delivered to session without attachments enabled",
			"session_id", sess.ID, "file_id", info.FileID)
		reject(syfthubapi.TunnelErrorCodeAttachmentNotAccepted, "endpoint does not accept attachments")
		return
	}

	downloader := sess.AttachmentDownloader()
	if err := MaterializeAttachment(sess.Context(), sess.AttachmentDir, &info, downloader); err != nil {
		b.logger.Error("[AGENT] failed to materialize attachment",
			"session_id", sess.ID, "file_id", info.FileID, "transport", info.Transport, "error", err)
		reject(syfthubapi.TunnelErrorCodeAttachmentIntegrity, err.Error())
		return
	}

	// Only emit the accept-ack when the runtime actually accepted the
	// attachment. Materializing the file but failing to enqueue it is
	// indistinguishable from the agent never seeing it — telling the client
	// the file is "delivered" in that case produces a green check on a file
	// the agent cannot reference. Surface a recoverable agent.error instead
	// so the chip shows the failure and the user can resend.
	if !sess.DeliverAttachment(info) {
		b.logger.Warn("[AGENT] attachment channel full, dropping",
			"session_id", sess.ID, "file_id", info.FileID)
		reject(syfthubapi.TunnelErrorCodeAttachmentNotAccepted, "host attachment queue full; please retry")
		return
	}
	b.sendAgentEvent(env.ReplyTo, cipher, env.SessionID, syfthubapi.EventTypeUserAttachment,
		agenttypes.UserAttachmentEvent{FileID: info.FileID, SizeBytes: info.SizeBytes})
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

// bindObjectStoreAttachments wires a session's object-store attachment
// uploader/downloader from the client-supplied session_attachment_key. Every
// failure is non-fatal: it is logged and the session falls back to inline-only
// attachments.
func (b *agentNATSBridge) bindObjectStoreAttachments(session *syfthubapi.AgentSession, key string) {
	if !session.AttachmentsEnabled() || key == "" {
		return
	}
	keyBytes, err := base64.StdEncoding.DecodeString(key)
	if err != nil || len(keyBytes) != 32 {
		b.logger.Warn("[AGENT] invalid session_attachment_key — attachments will be inline-only",
			"session_id", session.ID, "decode_err", err, "len", len(keyBytes))
		return
	}
	store, err := b.transport.getAttachmentObjectStore()
	if err != nil {
		b.logger.Warn("[AGENT] failed to init attachment Object Store — attachments will be inline-only",
			"session_id", session.ID, "error", err)
		return
	}
	if uploader, err := NewObjectStoreUploader(context.Background(), keyBytes, store, session.ID); err != nil {
		b.logger.Warn("[AGENT] failed to bind ObjectStoreUploader",
			"session_id", session.ID, "error", err)
	} else {
		session.AttachmentUploader = uploader
	}
	if dl, err := NewObjectStoreDownloader(context.Background(), keyBytes, store); err != nil {
		b.logger.Warn("[AGENT] failed to bind ObjectStoreDownloader",
			"session_id", session.ID, "error", err)
	} else {
		session.SetAttachmentDownloader(dl)
	}
}

func (b *agentNATSBridge) handleSessionStart(env *syfthubapi.AgentEnvelope, cipher *SessionCipher, payload []byte) {
	startTime := time.Now()

	// fail ends the session before it starts by emitting a terminal
	// session.failed event to the client's peer channel.
	fail := func(errMsg string, code syfthubapi.TunnelErrorCode) {
		b.sendAgentEvent(env.ReplyTo, cipher, env.SessionID, syfthubapi.EventTypeSessionFailed,
			agenttypes.SessionFailedEvent{Error: errMsg, Reason: string(code)})
	}

	var startPayload syfthubapi.AgentSessionStartPayload
	if err := json.Unmarshal(payload, &startPayload); err != nil {
		b.logger.Error("[AGENT] failed to parse session start payload", "error", err)
		fail("invalid session start payload", syfthubapi.TunnelErrorCodeInvalidRequest)
		return
	}

	// Verify the satellite token to obtain the real user identity.
	if b.tokenVerifier == nil {
		b.logger.Error("[AGENT] token verifier not configured — cannot authenticate agent session",
			"endpoint", startPayload.EndpointSlug)
		fail("agent session authentication not configured", syfthubapi.TunnelErrorCodeAuthFailed)
		return
	}
	if env.SatelliteToken == "" {
		b.logger.Warn("[AGENT] agent session start missing satellite token",
			"endpoint", startPayload.EndpointSlug)
		fail("missing satellite token", syfthubapi.TunnelErrorCodeAuthFailed)
		return
	}

	verifyCtx, verifyCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer verifyCancel()

	user, err := b.tokenVerifier(verifyCtx, env.SatelliteToken)
	if err != nil {
		b.logger.Warn("[AGENT] agent session token verification failed",
			"endpoint", startPayload.EndpointSlug, "error", err)
		fail("agent session authentication failed", syfthubapi.TunnelErrorCodeAuthFailed)
		return
	}

	b.logger.Info("[AGENT] user authenticated for agent session",
		"endpoint", startPayload.EndpointSlug,
		"user_sub", user.Sub, "username", user.Username)

	// Lift caller-identity material from the envelope into the payload so the
	// session manager can plumb it into AgentSession. The envelope carries
	// these unconditionally on the v2 path; the wire JSON does not (the
	// fields are json:"-" on AgentSessionStartPayload) — this is the single
	// point where they enter the parent package.
	startPayload.CallerPublicKeyB64 = env.SenderPublicKey
	startPayload.CallerReplyTo = env.ReplyTo

	session, err := b.handler.StartSession(startPayload, user)
	if err == nil && session != nil {
		b.bindObjectStoreAttachments(session, startPayload.SessionAttachmentKey)
	}
	if err != nil {
		// Transaction-style policies surface a typed PaymentRequiredError; relay
		// the payment challenge to the client as an agent.payment_required event.
		var payErr *syfthubapi.PaymentRequiredError
		if errors.As(err, &payErr) {
			b.logger.Info("[AGENT] session pending payment",
				"endpoint", startPayload.EndpointSlug,
				"user_sub", user.Sub, "username", user.Username)
			b.sendAgentEvent(env.ReplyTo, cipher, env.SessionID, syfthubapi.EventTypeAgentPaymentRequired, payErr.Details)
			// The direct peer-to-peer path cannot complete a payment challenge,
			// so the session cannot proceed — end it with a terminal event.
			fail("payment is required to start this session", syfthubapi.TunnelErrorCodePaymentRequired)
			return
		}
		b.logger.Error("[AGENT] failed to start session",
			"endpoint", startPayload.EndpointSlug, "error", err)
		// Pre-session failure: no transcript yet, and no typed verdict
		// (StartSession surfaces a generic error) — synthesize a transcript
		// from the prompt and emit with a nil policyResult so the log shows
		// what was rejected without a policy badge.
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
			nil,
		)
		fail(fmt.Sprintf("failed to start agent session: %v", err), syfthubapi.TunnelErrorCodeExecutionFailed)
		return
	}

	// Relay the session's events to the client's peer channel.
	go b.relayEvents(session, env.ReplyTo, cipher, startTime)

	b.logger.Info("[AGENT] session started successfully",
		"session_id", session.ID, "endpoint", startPayload.EndpointSlug,
		"user_sub", user.Sub, "username", user.Username, "reply_to", env.ReplyTo)
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

// publishAgentEvent encrypts an already-serialized AgentEventPayload with the
// session cipher and publishes it as a v2 agent_event envelope to subject.
// senderPubB64 is the host's identity public key; relayEvents passes it cached
// so the hot token-streaming path stays allocation-free. Errors are logged.
func (b *agentNATSBridge) publishAgentEvent(subject, senderPubB64, sessionID, correlationID string, cipher *SessionCipher, payloadJSON []byte) {
	nonce, encPayload, err := cipher.EncryptResponse(payloadJSON, correlationID)
	if err != nil {
		b.logger.Error("[AGENT] failed to encrypt event", "session_id", sessionID, "error", err)
		return
	}
	envelope, err := json.Marshal(syfthubapi.AgentEnvelope{
		Protocol:         syfthubapi.AgentProtocolV2,
		Type:             syfthubapi.MsgTypeAgentEvent,
		CorrelationID:    correlationID,
		SessionID:        sessionID,
		SenderPublicKey:  senderPubB64,
		Nonce:            nonce,
		EncryptedPayload: encPayload,
	})
	if err != nil {
		b.logger.Error("[AGENT] failed to marshal event envelope", "session_id", sessionID, "error", err)
		return
	}
	if err := b.transport.conn.Publish(subject, envelope); err != nil {
		b.logger.Error("[AGENT] failed to publish event", "session_id", sessionID, "error", err)
	}
}

// sendAgentEvent encrypts a single agent event and publishes it to the
// client's peer channel. It is used for pre-session failures and mid-session
// attachment errors; the live event stream itself is published by relayEvents.
func (b *agentNATSBridge) sendAgentEvent(replyTo string, cipher *SessionCipher, sessionID, eventType string, data any) {
	if replyTo == "" {
		b.logger.Warn("[AGENT] cannot send event — no reply channel",
			"session_id", sessionID, "event_type", eventType)
		return
	}
	dataJSON, err := json.Marshal(data)
	if err != nil {
		b.logger.Error("[AGENT] failed to marshal event data", "event_type", eventType, "error", err)
		return
	}
	payloadJSON, err := json.Marshal(syfthubapi.AgentEventPayload{
		SessionID: sessionID,
		EventType: eventType,
		Data:      dataJSON,
	})
	if err != nil {
		b.logger.Error("[AGENT] failed to marshal event payload", "event_type", eventType, "error", err)
		return
	}
	b.publishAgentEvent(peerSubjectPrefix+replyTo, b.transport.PublicKeyB64(),
		sessionID, sessionID+"-"+eventType, cipher, payloadJSON)
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
	policyResult *syfthubapi.PolicyResultOutput,
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
	case syfthubapi.LogStatusCompleted, syfthubapi.LogStatusRunning:
		// Surface whatever assistant content has been produced. Success is true
		// only on completed; running snapshots stay false until finalized.
		log.Response.Success = status == syfthubapi.LogStatusCompleted
		log.Response.Content, log.Response.ContentTruncated =
			syfthubapi.TruncateForLog(joinAssistantContent(transcript))
	default:
		// LogStatusFailed / LogStatusTerminated / unknown — record any error
		// message but no synthetic success content.
		log.Response.Error = failError
	}

	// Attach the latest policy verdict observed for this session so the per-
	// request log carries Allowed/Denied/Pending instead of always rendering
	// N/A. nil is expected for pre-session failures (no session context).
	log.Policy = syfthubapi.NewLogPolicyFromResult(policyResult)

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
// as encrypted v2 agent_event envelopes to the client's peer channel.
//
// The session cipher (X25519 ECDH + HKDF) was derived once by handleAgentMessage
// and is reused for every event. AgentEventPayload JSON is built manually via
// appendEventJSON — Data is already json.RawMessage, so it is spliced verbatim
// with no encoding/json reflection cost on the hot token-streaming path.
func (b *agentNATSBridge) relayEvents(session *syfthubapi.AgentSession, replyTo string, cipher *SessionCipher, startTime time.Time) {
	subject := peerSubjectPrefix + replyTo
	hostPub := b.transport.PublicKeyB64()
	// failError is captured from the (at most one) terminal session.failed event
	// so it can be reported in the per-session RequestLog after the loop exits.
	var failError string

	// Single stable log ID for every snapshot of this session so the log store
	// upserts in place instead of producing duplicate rows.
	logID := syfthubapi.NewRequestLogID()
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
			session.LatestPolicyResult(),
		)
	}

	emit(syfthubapi.LogStatusRunning, "")

	// Coalesced snapshot ticker. The relay can fire hundreds of events/sec on
	// a streaming model; emitting per-event would saturate the log pipeline.
	// Tokens don't mutate the loggable transcript, so the dirty flag is only
	// set for transcript-changing events (see EventTypeAgentMessage branch
	// in the loop below).
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
	defer func() {
		close(tickerDone)
		<-tickerStopped
	}()

	// Pre-encode the session ID JSON string once; reused in every event.
	sessionIDJSON, _ := json.Marshal(session.ID)

	// Reusable buffer for building event JSON without per-event allocation.
	var buf bytes.Buffer

	// The terminal outcome is decided by which event RunHandler put on the
	// channel, NOT by the session context. Some agent runners (notably the
	// filemode subprocess executor) call session.Cancel() after cmd.Wait
	// regardless of whether the subprocess exited cleanly — so ctx.Err() is
	// context.Canceled on every normal completion. We have to observe the
	// terminal event ourselves to disambiguate completed / failed / terminated.
	// A single string ("" until a terminal arrives) avoids the invalid state
	// that two independent booleans would permit.
	var terminalEvent string

	for event := range session.SendCh() {
		switch event.EventType {
		case syfthubapi.EventTypeAgentMessage:
			// Assistant message appended to the session transcript — the
			// next ticker fire should emit a fresh snapshot. Tokens, status,
			// tool calls, etc. don't change the loggable Content so they
			// intentionally don't trip dirty.
			dirty.Store(true)
		case syfthubapi.EventTypeSessionCompleted, syfthubapi.EventTypeSessionCancelled:
			terminalEvent = event.EventType
		case syfthubapi.EventTypeSessionFailed:
			terminalEvent = event.EventType
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

		// Build correlation ID without fmt.Sprintf overhead.
		correlationID := session.ID + "-" + strconv.Itoa(event.Sequence)

		b.publishAgentEvent(subject, hostPub, session.ID, correlationID, cipher, buf.Bytes())
	}

	b.logger.Info("[AGENT] event relay stopped", "session_id", session.ID)

	// Decide the terminal status from the events we observed plus the
	// external-cancel flag. ctx.Err() alone is unreliable here: handlers like
	// the filemode subprocess bridge call session.Cancel() as cleanup after
	// cmd.Wait, so ctx is Canceled after every normal completion AND after
	// every user-requested stop. ExternalCancelled() is the authoritative
	// signal for "the user pressed Stop".
	terminalStatus, failError := decideTerminalStatus(session, terminalEvent, failError)
	emit(terminalStatus, failError)
}

// decideTerminalStatus picks the final log status for an agent session from
// the terminal event the relay observed plus whether the session was cancelled
// externally. failErrorIn may be cleared (e.g. cancellation is not a real
// error) — the returned failError is what the terminal log should record.
// terminalEvent is the EventType of the last terminal event seen on the
// channel, or "" if none arrived before the channel closed.
func decideTerminalStatus(session *syfthubapi.AgentSession, terminalEvent, failErrorIn string) (status, failError string) {
	switch {
	case session.ExternalCancelled():
		return syfthubapi.LogStatusTerminated, ""
	case terminalEvent == syfthubapi.EventTypeSessionCompleted:
		return syfthubapi.LogStatusCompleted, ""
	case terminalEvent == syfthubapi.EventTypeSessionCancelled:
		return syfthubapi.LogStatusTerminated, ""
	case terminalEvent == syfthubapi.EventTypeSessionFailed:
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
	// EventType is a package-level ASCII string constant with no characters
	// requiring JSON escaping — write the quotes directly to avoid a
	// json.Marshal allocation on the hot token-streaming path.
	buf.WriteString(`{"session_id":`)
	buf.Write(sessionIDJSON)
	buf.WriteString(`,"event_type":"`)
	buf.WriteString(event.EventType)
	buf.WriteByte('"')
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
	// natsConn is the shared NATS connection; conn caches natsConn.Conn().
	natsConn *NATSConn
	conn     *nats.Conn
	// ownsConn is true when this transport dialed the connection itself (via
	// New) and must close it on Stop. When the connection is injected via
	// NewNATSTransport it is shared — e.g. with an outbound AgentDialer — and
	// the owner closes it.
	ownsConn bool

	sub         *nats.Subscription
	handler     RequestHandler
	agentBridge *agentNATSBridge
	config      *Config
	logger      *slog.Logger

	// privateKey is the long-term X25519 private key used to decrypt incoming
	// tunnel requests. Generated at construction time; never rotated at runtime.
	privateKey *ecdh.PrivateKey
	// pubKeyB64 is the base64url-encoded public key — pre-computed once at
	// construction so PublicKeyB64() is a field read, not an alloc+encode.
	pubKeyB64 string

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

// NewNATSTransport creates a NATS transport over an existing, caller-owned
// NATSConn. The connection is shared — Stop does not close it; the caller
// (which may also attach an outbound AgentDialer to the same NATSConn) owns
// its lifecycle. Use New for the host-only case where the transport owns the
// connection.
//
// If cfg.KeyFilePath is set, the X25519 keypair is loaded from (or generated
// and saved to) that file so the key survives restarts. Otherwise a fresh
// ephemeral keypair is generated. Call PublicKeyB64() to retrieve the public
// key, then register it with the hub before starting the transport.
func NewNATSTransport(natsConn *NATSConn, cfg *Config) (*NATSTransport, error) {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	if natsConn == nil {
		return nil, fmt.Errorf("config: NATSConn is required for tunnel mode")
	}
	if cfg.NATSCredentials == nil {
		return nil, fmt.Errorf("config: NATSCredentials is required for tunnel mode")
	}

	var privateKey *ecdh.PrivateKey
	var err error
	if cfg.KeyFilePath != "" {
		privateKey, err = LoadOrGenerateKey(cfg.KeyFilePath)
	} else {
		privateKey, err = GenerateX25519Keypair()
	}
	if err != nil {
		return nil, fmt.Errorf("config: failed to load or generate X25519 keypair: %w", err)
	}

	return &NATSTransport{
		natsConn:   natsConn,
		conn:       natsConn.Conn(),
		config:     cfg,
		logger:     logger,
		privateKey: privateKey,
		pubKeyB64:  b64urlEncode(privateKey.PublicKey().Bytes()),
		stopCh:     make(chan struct{}),
	}, nil
}

// PublicKeyB64 returns the base64url-encoded X25519 public key for this transport.
// Register this with the hub so peers can encrypt requests to this space — the
// aggregator on the v1 model/data_source path, and direct clients on the v2
// agent path.
func (t *NATSTransport) PublicKeyB64() string {
	return t.pubKeyB64
}

// Start subscribes to the space subject on the shared NATS connection and
// blocks until the context is cancelled or Stop is called.
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
	t.logger.Info("starting NATS transport", "subject", creds.Subject)

	sub, err := t.conn.Subscribe(creds.Subject, t.handleMessage)
	if err != nil {
		return fmt.Errorf("nats transport: failed to subscribe to %s: %w", creds.Subject, err)
	}
	t.sub = sub
	t.logger.Info("subscribed to NATS subject", "subject", creds.Subject)

	// Attempt to initialize the JetStream KV session registry for agent
	// sessions. Gracefully degrades if JetStream is not available.
	if t.agentBridge != nil {
		registry, err := NewNATSSessionRegistry(t.conn, t.logger)
		if err != nil {
			t.logger.Warn("JetStream KV session registry not available — continuing without it", "error", err)
		} else {
			type registrarSetter interface {
				SetRegistrar(r syfthubapi.SessionRegistrar)
			}
			if rs, ok := t.agentBridge.handler.(registrarSetter); ok {
				rs.SetRegistrar(registry)
				t.logger.Info("JetStream KV session registry wired to agent session manager")
			}
		}
	}

	// Wait for context cancellation or stop signal.
	select {
	case <-ctx.Done():
		return nil
	case <-t.stopCh:
		return nil
	}
}

// Stop gracefully shuts down the NATS transport. It unsubscribes from the
// space subject; the NATS connection is closed only when this transport owns
// it (created via New). A shared connection is closed by its owner.
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

	if t.sub != nil {
		if err := t.sub.Unsubscribe(); err != nil {
			t.logger.Warn("error unsubscribing", "error", err)
		}
	}

	if t.ownsConn && t.natsConn != nil {
		t.natsConn.Close()
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

// PrivateKey returns the transport's X25519 private key for agent message decryption.
func (t *NATSTransport) PrivateKey() *ecdh.PrivateKey {
	return t.privateKey
}

// handleMessage processes an incoming NATS message.
func (t *NATSTransport) handleMessage(msg *nats.Msg) {
	// Route v2 direct peer-to-peer agent sessions to the agent bridge; v1
	// tunnel requests (model / data_source via the aggregator) fall through to
	// the standard pipeline below.
	var probe struct {
		Protocol string `json:"protocol"`
	}
	if err := json.Unmarshal(msg.Data, &probe); err != nil {
		t.logger.Error("failed to parse message", "error", err, "data", string(msg.Data))
		return
	}

	if probe.Protocol == syfthubapi.AgentProtocolV2 {
		if t.agentBridge == nil {
			t.logger.Error("received a v2 agent message but agent sessions are not supported")
			return
		}
		var env syfthubapi.AgentEnvelope
		if err := json.Unmarshal(msg.Data, &env); err != nil {
			t.logger.Error("failed to parse agent envelope", "error", err)
			return
		}
		t.agentBridge.handleAgentMessage(&env)
		return
	}

	// The v1 model / data_source path requires the request processor; the v2
	// agent path above does not.
	if t.handler == nil {
		t.logger.Error("no request handler configured")
		return
	}

	// Parse the v1 tunnel request envelope (model / data_source).
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

// Ensure NATSTransport implements Transport.
var _ Transport = (*NATSTransport)(nil)
