package syfthubapi

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"sync"
	"sync/atomic"

	"github.com/openmined/syfthub/sdk/golang/agenttypes"
)

// newUUID returns a random UUIDv4 string. Local helper to avoid a new
// dependency just for ID generation in this package.
func newUUID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// AgentConfig is an alias for the shared agent config type.
// Kept for backward compatibility so callers can continue using syfthubapi.AgentConfig.
type AgentConfig = agenttypes.AgentConfig

// ToolCall is an alias for the shared tool call type.
// Kept for backward compatibility so callers can continue using syfthubapi.ToolCall.
type ToolCall = agenttypes.ToolCall

// ToolResult is an alias for the shared tool result type.
// Kept for backward compatibility so callers can continue using syfthubapi.ToolResult.
type ToolResult = agenttypes.ToolResult

// PaymentRequiredError signals that an agent session start was blocked by a
// transaction-style policy and the caller must obtain a payment credential
// (e.g. a Tempo on-chain payment) and retry. The NATS bridge maps this error
// to a TunnelResponse with TunnelErrorCodePaymentRequired so the aggregator /
// client can surface a payment challenge to the user.
type PaymentRequiredError struct {
	// Challenge is the WWW-Authenticate-style "Payment …" challenge string
	// returned by the policy, e.g. `Payment id="…", realm="…", amount="…"`.
	Challenge string

	// Details is a copy of the safe payment_* keys from the policy metadata,
	// suitable for placing into TunnelError.Details.
	Details map[string]any
}

// Error implements the error interface.
func (e *PaymentRequiredError) Error() string { return "payment required" }

// AgentHandler is the function signature for agent endpoint handlers.
// The handler receives a context (cancelled on user cancel or timeout) and
// an AgentSession for bidirectional communication with the user.
// Return nil on success (triggers session.completed), non-nil error on failure
// (triggers session.failed).
type AgentHandler func(ctx context.Context, session *AgentSession) error

// AgentSession represents an active agent session. Agent handlers interact
// with this struct to send events and receive user input.
type AgentSession struct {
	// ID is the unique session identifier.
	ID string

	// InitialPrompt is the user's initial prompt.
	InitialPrompt string

	// Messages is the conversation history from session.start.
	Messages []Message

	// Config contains session configuration from session.start payload.
	Config AgentConfig

	// User contains authenticated user information.
	User *UserContext

	// EndpointSlug is the slug of the agent endpoint handling this session.
	EndpointSlug string

	// Capabilities lists optional protocol extensions the caller advertised
	// in session.start. See docs/architecture/attachments.md.
	Capabilities []string

	// CallerPublicKeyB64 is the caller's X25519 identity pubkey (base64url),
	// lifted from AgentEnvelope.SenderPublicKey on session_start. Used by
	// AgentExecutor to capture routing for a manual_review hold so the host
	// can later encrypt the resolution back to the caller. Empty for sessions
	// that arrived through paths that don't carry it (e.g. HTTP transport).
	CallerPublicKeyB64 string

	// CallerReplyTo is the caller's per-session NATS reply channel suffix
	// (the part after "syfthub.peer."). Lifted from AgentEnvelope.ReplyTo on
	// session_start; recorded so a manual-review resolution arriving while
	// the session is still subscribed can be best-effort live-injected.
	CallerReplyTo string

	// PaymentCredential is the on-chain payment proof (a wire-format mppx
	// credential) supplied by the caller in the agent_session_start envelope
	// to satisfy an x402_pay_per_request policy. AgentExecutor threads this
	// into per-turn RequestContext so the mppx gate's PreVerify can run
	// before policy evaluation. Empty when the session was started without
	// a pre-paid credential — the policy's pre_execute then issues a
	// challenge and the caller is expected to restart the session with one.
	PaymentCredential string

	// AttachmentDir is the per-session tempdir for materialized attachment
	// files. Set by the session manager when attachments are enabled; empty
	// otherwise. Files in this directory are cleaned up on session end.
	AttachmentDir string

	// AttachmentUploader, if set, routes outbound attachments larger than
	// InlineMaxBytes through Object Store.
	AttachmentUploader AttachmentUploader

	// attachmentDownloader is the inbound counterpart: fetches object_store-
	// transport attachments from Object Store and materializes them under
	// AttachmentDir. Exposed via AttachmentDownloader().
	attachmentDownloader AttachmentDownloader

	// recvAttachCh carries inbound attachment metadata to the handler.
	// nil if attachments are not enabled for this session.
	recvAttachCh chan AttachmentInfo

	// ctx is the session lifecycle context; cancelled on user cancel or timeout.
	ctx context.Context

	// cancel cancels the session context.
	cancel context.CancelFunc

	// sendCh carries outbound events to the NATS relay goroutine.
	sendCh chan AgentEventPayload

	// recvCh carries inbound user messages from the NATS relay goroutine.
	recvCh chan UserMessage

	// done is closed when the handler goroutine returns.
	done chan struct{}

	// OnDone is an optional callback invoked after the handler completes
	// (and terminal events are sent) but before sendCh and done are closed.
	// Use this for cleanup such as removing the session from a manager map.
	OnDone func()

	// sequence is a monotonically increasing event counter.
	sequence atomic.Int64

	// externalCancelled is set when something outside the handler asks the
	// session to stop — user clicked Stop, NATS user.cancel arrived,
	// AgentSessionManager.CancelAllSessions during shutdown, etc. The handler
	// may also call s.cancel() as part of its own cleanup (e.g. the filemode
	// executor cancels after cmd.Wait so the writer goroutine unblocks); that
	// internal cancel must NOT be treated as a user cancel because the
	// resulting cmd.Wait "signal: killed" error would otherwise be reported
	// as Cancelled instead of Completed. The relay reads this flag to decide
	// whether a SessionFailed event is a real failure or a side-effect of a
	// requested cancel.
	externalCancelled atomic.Bool

	// transcript records the conversational messages (user + assistant)
	// exchanged during the session, in chronological order. Populated
	// automatically by NewAgentSession (initial Messages + Prompt),
	// DeliverMessage (Type=="user_message" only), and Send (events with
	// EventType == EventTypeAgentMessage). Control signals
	// (user_confirm/user_deny/user_cancel) and non-message agent events
	// (tokens, thinking, tool calls, status, attachments) are excluded.
	// Read via Transcript().
	transcript   []Message
	transcriptMu sync.Mutex

	// latestPolicy holds the most recent PolicyResult observed for this
	// session. Read on every emitSessionLog snapshot (per session, ~1.5s)
	// and written rarely (once per pre/post check), so atomic.Pointer keeps
	// the hot snapshot path lock-free.
	latestPolicy atomic.Pointer[PolicyResultOutput]

	// lastTurnMetadata is a per-turn scratchpad shared between checkPre
	// (which the mppx gate's PreVerify writes into) and the post-handler
	// settlement hook (which reads payment_signed_tx_hex / payment_challenge_id
	// to broadcast the held tx and update the policy ledger). The map is
	// REPLACED on each new turn, not merged, so stale fields from a prior
	// turn cannot leak into the next pre/post evaluation. Guarded by
	// lastTurnMetadataMu because checkPre and handleReply may run on
	// different goroutines for the same session.
	lastTurnMetadataMu sync.Mutex
	lastTurnMetadata   map[string]any
}

// LastTurnMetadata returns a defensive copy of the per-turn metadata map
// populated by the most recent checkPre. Callers that mutate the returned
// map see no effect on the session; to push updates back, call
// setLastTurnMetadata with the modified copy.
func (s *AgentSession) LastTurnMetadata() map[string]any {
	s.lastTurnMetadataMu.Lock()
	defer s.lastTurnMetadataMu.Unlock()
	if s.lastTurnMetadata == nil {
		return nil
	}
	out := make(map[string]any, len(s.lastTurnMetadata))
	for k, v := range s.lastTurnMetadata {
		out[k] = v
	}
	return out
}

// setLastTurnMetadata installs metadata as the per-turn scratchpad. The map
// reference is stored as-is (no copy) — callers must not mutate it after the
// handoff. Use a fresh map per turn to avoid leaking fields across turns.
func (s *AgentSession) setLastTurnMetadata(metadata map[string]any) {
	s.lastTurnMetadataMu.Lock()
	defer s.lastTurnMetadataMu.Unlock()
	s.lastTurnMetadata = metadata
}

// AttachmentsEnabled reports whether attachments are active for this session.
// The session manager only sets AttachmentDir when both the endpoint declared
// AcceptsAttachments and the caller advertised the attachment capability, so
// AttachmentDir != "" is the single canonical gate.
func (s *AgentSession) AttachmentsEnabled() bool {
	return s.AttachmentDir != ""
}

// AttachmentCh returns the channel of inbound user attachments. Returns nil
// if attachments are not enabled for this session — handlers should check
// AttachmentsEnabled() first.
func (s *AgentSession) AttachmentCh() <-chan AttachmentInfo {
	return s.recvAttachCh
}

// SetAttachmentDownloader installs the downloader the agentNATSBridge uses
// when an inbound user.attachment arrives in the object_store transport.
// Wired by the transport package's handleSessionStart after the session
// AES key is established.
func (s *AgentSession) SetAttachmentDownloader(d AttachmentDownloader) {
	s.attachmentDownloader = d
}

// AttachmentDownloader returns the configured downloader (or nil if
// attachments are inline-only for this session).
func (s *AgentSession) AttachmentDownloader() AttachmentDownloader {
	return s.attachmentDownloader
}

// DeliverAttachment pushes an attachment to the session's receive channel.
// Returns false if the channel is full or attachments are disabled.
func (s *AgentSession) DeliverAttachment(a AttachmentInfo) bool {
	if s.recvAttachCh == nil {
		return false
	}
	select {
	case s.recvAttachCh <- a:
		return true
	default:
		return false
	}
}

// AgentSessionParams holds the parameters for creating a new AgentSession.
type AgentSessionParams struct {
	ID            string
	Prompt        string
	EndpointSlug  string
	Messages      []Message
	Config        AgentConfig
	User          *UserContext
	Capabilities  []string
	AttachmentDir string

	// CallerPublicKeyB64 / CallerReplyTo are carried through from the
	// session_start envelope so AgentSession can expose them. Both are
	// optional — sessions not arriving over the v2 NATS transport may leave
	// them empty.
	CallerPublicKeyB64 string
	CallerReplyTo      string

	// PaymentCredential is the wire-format mppx credential the caller
	// supplied in session_start (empty when not pre-paid). See the field
	// of the same name on AgentSession for usage.
	PaymentCredential string
}

// NewAgentSession creates a new AgentSession with the given parameters.
// parentCtx controls the session's lifetime — when it is cancelled, the
// session's context is also cancelled, causing the handler to unblock.
// Pass context.Background() for sessions with no external deadline.
func NewAgentSession(parentCtx context.Context, params AgentSessionParams) *AgentSession {
	ctx, cancel := context.WithCancel(parentCtx)
	var recvAttachCh chan AttachmentInfo
	if params.AttachmentDir != "" {
		recvAttachCh = make(chan AttachmentInfo, 32)
	}
	s := &AgentSession{
		ID:                 params.ID,
		InitialPrompt:      params.Prompt,
		Messages:           params.Messages,
		Config:             params.Config,
		User:               params.User,
		EndpointSlug:       params.EndpointSlug,
		Capabilities:       params.Capabilities,
		AttachmentDir:      params.AttachmentDir,
		CallerPublicKeyB64: params.CallerPublicKeyB64,
		CallerReplyTo:      params.CallerReplyTo,
		PaymentCredential:  params.PaymentCredential,
		recvAttachCh:       recvAttachCh,
		ctx:                ctx,
		cancel:             cancel,
		sendCh:             make(chan AgentEventPayload, 100),
		recvCh:             make(chan UserMessage, 100),
		done:               make(chan struct{}),
	}
	s.seedTranscript()
	return s
}

// seedTranscript initializes the transcript from the construction-time
// Messages history and InitialPrompt. The prompt is appended only when it
// would not duplicate the trailing user message in the history.
func (s *AgentSession) seedTranscript() {
	s.transcriptMu.Lock()
	defer s.transcriptMu.Unlock()
	s.transcript = append(s.transcript, s.Messages...)
	if s.InitialPrompt == "" {
		return
	}
	if n := len(s.transcript); n > 0 {
		last := s.transcript[n-1]
		if last.Role == "user" && last.Content == s.InitialPrompt {
			return
		}
	}
	s.transcript = append(s.transcript, Message{Role: "user", Content: s.InitialPrompt})
}

// appendTranscript adds a single conversational message to the session
// transcript under the transcript lock.
func (s *AgentSession) appendTranscript(msg Message) {
	s.transcriptMu.Lock()
	defer s.transcriptMu.Unlock()
	s.transcript = append(s.transcript, msg)
}

// Transcript returns a defensive copy of every conversational message
// exchanged during this session in chronological order: the seeded
// history + initial prompt, user messages delivered via DeliverMessage
// (Type=="user_message" only), and assistant messages emitted via Send
// with EventType==EventTypeAgentMessage. Safe to call from any goroutine
// at any point in the session lifecycle, including after termination.
func (s *AgentSession) Transcript() []Message {
	s.transcriptMu.Lock()
	defer s.transcriptMu.Unlock()
	out := make([]Message, len(s.transcript))
	copy(out, s.transcript)
	return out
}

// RecordPolicyResult stores the most recent policy verdict. nil is ignored
// so a failed check (no verdict) leaves the previous result in place.
func (s *AgentSession) RecordPolicyResult(v *PolicyResultOutput) {
	if v == nil {
		return
	}
	s.latestPolicy.Store(v)
}

// LatestPolicyResult returns the most recent recorded verdict, or nil if no
// policy check has fired yet.
func (s *AgentSession) LatestPolicyResult() *PolicyResultOutput {
	return s.latestPolicy.Load()
}

// Context returns the session's context.
func (s *AgentSession) Context() context.Context {
	return s.ctx
}

// Cancel cancels the session context, causing the handler to return. This is
// the "internal" cancellation entry point used by handlers (e.g. filemode's
// agent_executor after cmd.Wait) to unblock their own goroutines; it does
// NOT mark the session as user-cancelled.
func (s *AgentSession) Cancel() {
	s.cancel()
}

// CancelByUser marks the session as cancelled by an external actor (user
// Stop button, NATS user.cancel, manager shutdown) and then cancels the
// context. The relay uses ExternalCancelled() to distinguish a
// SessionFailed-from-killed-subprocess that resulted from this cancel
// (report as Cancelled) from a genuine handler failure (report as Failed).
func (s *AgentSession) CancelByUser() {
	s.externalCancelled.Store(true)
	s.cancel()
}

// ExternalCancelled reports whether the session was cancelled by an external
// actor via CancelByUser.
func (s *AgentSession) ExternalCancelled() bool {
	return s.externalCancelled.Load()
}

// Done returns a channel that is closed when the handler goroutine returns.
func (s *AgentSession) Done() <-chan struct{} {
	return s.done
}

// SendCh returns the outbound event channel (for the NATS relay).
func (s *AgentSession) SendCh() <-chan AgentEventPayload {
	return s.sendCh
}

// DeliverMessage pushes a user message to the session's receive channel.
// Returns false if the channel is full.
//
// On successful delivery, conversational messages (Type == "user_message"
// with non-empty Content) are recorded in the session transcript. Control
// signals (user_confirm/user_deny/user_cancel) are intentionally excluded.
func (s *AgentSession) DeliverMessage(msg UserMessage) bool {
	select {
	case s.recvCh <- msg:
		if msg.Type == UserMessageTypeMessage && msg.Content != "" {
			s.appendTranscript(Message{Role: "user", Content: msg.Content})
		}
		return true
	default:
		return false
	}
}

// Send sends a raw AgentEventPayload to the user.
//
// After a successful channel write, EventTypeAgentMessage events are
// recorded in the session transcript (other event types — tokens,
// thinking, tool calls, status, attachments, terminal session events —
// are excluded). Recording happens post-write so a context-cancelled
// send never produces a phantom transcript entry.
func (s *AgentSession) Send(event AgentEventPayload) error {
	event.SessionID = s.ID
	event.Sequence = int(s.sequence.Add(1))
	select {
	case s.sendCh <- event:
		s.recordOutboundEvent(event)
		return nil
	case <-s.ctx.Done():
		return s.ctx.Err()
	}
}

// recordOutboundEvent appends an outgoing event to the transcript when
// it carries conversational assistant content. Silently skips events
// that aren't agent.message or whose payload doesn't unmarshal/contain
// a non-empty content field.
func (s *AgentSession) recordOutboundEvent(event AgentEventPayload) {
	if event.EventType != EventTypeAgentMessage {
		return
	}
	content := contentOfMessage(event)
	if content == "" {
		return
	}
	s.appendTranscript(Message{Role: "assistant", Content: content})
}

// SendPaymentRequired sends an agent.payment_required event mid-session.
// challenge is the WWW-Authenticate-style Payment challenge string; details
// is the safe metadata projection from the policy result. Caller is expected
// to cancel the session after this returns.
//
// Wire shape MUST line up with agenttypes.AgentPaymentRequiredEvent so the
// consumer's typed deserializer can populate its fields. That struct reads
// amount / currency / recipient / challenge_id / intent at the TOP level
// with no payment_ prefix — so we lift them out of `details` here. The
// `details` map keys use mppxgate's MetaKey* names (payment_amount, ...);
// hub-bound non-agent endpoints still consume that map verbatim via the
// TunnelError.Details path.
func (s *AgentSession) SendPaymentRequired(policyName, challenge string, details map[string]any) error {
	payload := map[string]any{
		"policy_name": policyName,
		// chat_session_id and endpoint_slug are required JSON fields on
		// agenttypes.AgentPaymentRequiredEvent. CLI/SDK consumers route the
		// payment retry by chat_session_id, so omitting either yields a
		// "session not found" 404 even though the user paid. Always emit them
		// — the session has both at hand.
		"chat_session_id": s.ID,
		"endpoint_slug":   s.EndpointSlug,
	}
	if challenge != "" {
		payload["challenge"] = challenge
	}
	// Hoist the safe-projected fields into the top-level wire shape the
	// consumer expects. Keep `details` too for forward-compat — newer
	// clients can read it if they want the full safe projection.
	lift := func(srcKey, dstKey string) {
		if v, ok := details[srcKey]; ok {
			if s, ok := v.(string); ok && s != "" {
				payload[dstKey] = s
			}
		}
	}
	lift("payment_amount", "amount")
	lift("payment_currency", "currency")
	lift("payment_recipient", "recipient")
	lift("challenge_id", "challenge_id")
	lift("intent", "intent")
	if len(details) > 0 {
		payload["details"] = details
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal payment_required event: %w", err)
	}
	return s.Send(AgentEventPayload{
		EventType: EventTypeAgentPaymentRequired,
		Data:      data,
	})
}

// Receive blocks until a user message arrives or the context is cancelled.
func (s *AgentSession) Receive() (UserMessage, error) {
	select {
	case msg := <-s.recvCh:
		return msg, nil
	case <-s.ctx.Done():
		return UserMessage{}, s.ctx.Err()
	}
}

// SendAttachment sends an attachment to the user.
//
// Behavior:
//   - For payloads up to InlineMaxBytes the bytes ride inline (base64) in the
//     event payload — single round-trip, low latency.
//   - For larger payloads, an AttachmentUploader (Object Store transport) is
//     required: bytes are encrypted with a fresh per-file key and uploaded
//     to JetStream Object Store; the event payload carries the wrapped key
//     and bucket/key refs.
//
// Returns the assigned file_id.
func (s *AgentSession) SendAttachment(r io.Reader, name, mime string) (string, error) {
	if !s.AttachmentsEnabled() {
		return "", fmt.Errorf("attachments not enabled for this session")
	}

	// Read up to (InlineMaxBytes+1) so we can detect the spill-over and switch
	// to Object Store without two passes for small files.
	head, err := io.ReadAll(io.LimitReader(r, int64(InlineMaxBytes)+1))
	if err != nil {
		return "", fmt.Errorf("read attachment head: %w", err)
	}

	fileID := "att-" + newUUID()

	if len(head) <= InlineMaxBytes {
		sum := sha256.Sum256(head)
		info := AttachmentInfo{
			FileID:          fileID,
			Name:            name,
			MIME:            mime,
			SizeBytes:       int64(len(head)),
			PlaintextSHA256: hex.EncodeToString(sum[:]),
			Transport:       AttachmentTransportInline,
			InlineDataB64:   base64.StdEncoding.EncodeToString(head),
		}
		return fileID, s.emitAttachmentEvent(info)
	}

	// Spill-over: route through Object Store.
	if s.AttachmentUploader == nil {
		return "", fmt.Errorf("attachment exceeds inline limit (%d bytes) and no AttachmentUploader configured", InlineMaxBytes)
	}
	combined := io.MultiReader(bytes.NewReader(head), r)
	// We don't know the exact size yet — pass -1 so the uploader streams
	// and computes the true size from the stream.
	info, err := s.AttachmentUploader.Upload(s.ctx, fileID, name, mime, -1, combined)
	if err != nil {
		return "", fmt.Errorf("object-store upload: %w", err)
	}
	return fileID, s.emitAttachmentEvent(info)
}

func (s *AgentSession) emitAttachmentEvent(info AttachmentInfo) error {
	data, err := json.Marshal(info)
	if err != nil {
		return fmt.Errorf("marshal attachment metadata: %w", err)
	}
	return s.Send(AgentEventPayload{
		EventType: EventTypeAgentAttachment,
		Data:      data,
	})
}

// UserMessage represents a message from the user during an agent session.
type UserMessage struct {
	// Type is the message type: "user_message", "user_confirm", "user_deny", "user_cancel".
	Type string `json:"type"`

	// Content is the message content (for user_message).
	Content string `json:"content,omitempty"`

	// ToolCallID references a specific tool call (for user_confirm/user_deny).
	ToolCallID string `json:"tool_call_id,omitempty"`

	// Reason is provided with user_deny.
	Reason string `json:"reason,omitempty"`

	// PaymentCredential is the wire-format mppx credential the caller signed
	// for THIS specific turn (empty for free turns). x402_pay_per_request
	// policies charge per request, so each priced turn carries its own
	// credential rather than reusing the session-start one. Empty triggers
	// the policy's pre_execute to issue a fresh challenge; the caller signs
	// it and resends the same content via SendMessageWithCredential.
	PaymentCredential string `json:"payment_credential,omitempty"`
}

// RunHandler spawns the agent handler in a goroutine with proper lifecycle management.
// It sends session.completed or session.failed before closing the sendCh channel.
// If OnDone is set, it is called after terminal events are sent but before
// sendCh and done are closed.
// Callers should drain SendCh() until it is closed to receive all events.
func (s *AgentSession) RunHandler(handler AgentHandler) {
	go func() {
		defer func() {
			// Recover from panics
			if r := recover(); r != nil {
				data, _ := json.Marshal(map[string]any{
					"error":  fmt.Sprintf("handler panicked: %v", r),
					"reason": "internal_error",
				})
				select {
				case s.sendCh <- AgentEventPayload{
					SessionID: s.ID,
					EventType: EventTypeSessionFailed,
					Sequence:  int(s.sequence.Add(1)),
					Data:      data,
				}:
				default:
				}
			}

			// Invoke cleanup callback before closing channels.
			if s.OnDone != nil {
				s.OnDone()
			}

			close(s.sendCh)
			close(s.done)
		}()

		err := handler(s.ctx, s)

		if err != nil {
			data, _ := json.Marshal(map[string]any{
				"error":  err.Error(),
				"reason": "handler_error",
			})
			select {
			case s.sendCh <- AgentEventPayload{
				SessionID: s.ID,
				EventType: EventTypeSessionFailed,
				Sequence:  int(s.sequence.Add(1)),
				Data:      data,
			}:
			default:
			}
		} else {
			data, _ := json.Marshal(map[string]any{
				"session_id": s.ID,
			})
			select {
			case s.sendCh <- AgentEventPayload{
				SessionID: s.ID,
				EventType: EventTypeSessionCompleted,
				Sequence:  int(s.sequence.Add(1)),
				Data:      data,
			}:
			default:
			}
		}
	}()
}
