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
	"slices"
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
}

// HasCapability returns true if the session advertised the named capability.
func (s *AgentSession) HasCapability(cap string) bool {
	return slices.Contains(s.Capabilities, cap)
}

// AttachmentsEnabled reports whether the attachments capability is active
// for this session AND a tempdir is configured. Handlers SHOULD gate calls
// to attachment helpers on this.
func (s *AgentSession) AttachmentsEnabled() bool {
	return s.AttachmentDir != "" && s.HasCapability(AttachmentCapability)
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
		ID:            params.ID,
		InitialPrompt: params.Prompt,
		Messages:      params.Messages,
		Config:        params.Config,
		User:          params.User,
		EndpointSlug:  params.EndpointSlug,
		Capabilities:  params.Capabilities,
		AttachmentDir: params.AttachmentDir,
		recvAttachCh:  recvAttachCh,
		ctx:           ctx,
		cancel:        cancel,
		sendCh:        make(chan AgentEventPayload, 100),
		recvCh:        make(chan UserMessage, 100),
		done:          make(chan struct{}),
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
	if len(s.Messages) > 0 {
		s.transcript = append(s.transcript, s.Messages...)
	}
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
		if msg.Type == "user_message" && msg.Content != "" {
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
	var payload struct {
		Content string `json:"content"`
	}
	if err := json.Unmarshal(event.Data, &payload); err != nil || payload.Content == "" {
		return
	}
	s.appendTranscript(Message{Role: "assistant", Content: payload.Content})
}

// SendThinking sends a thinking/reasoning event.
func (s *AgentSession) SendThinking(content string) error {
	data, err := json.Marshal(map[string]any{
		"content":      content,
		"is_streaming": false,
	})
	if err != nil {
		return fmt.Errorf("marshal thinking event: %w", err)
	}
	return s.Send(AgentEventPayload{
		EventType: EventTypeAgentThinking,
		Data:      data,
	})
}

// SendToolCall sends a tool call event.
func (s *AgentSession) SendToolCall(tc ToolCall) error {
	data, err := json.Marshal(tc)
	if err != nil {
		return fmt.Errorf("marshal tool call event: %w", err)
	}
	return s.Send(AgentEventPayload{
		EventType: EventTypeAgentToolCall,
		Data:      data,
	})
}

// SendToolResult sends a tool result event.
func (s *AgentSession) SendToolResult(tr ToolResult) error {
	data, err := json.Marshal(tr)
	if err != nil {
		return fmt.Errorf("marshal tool result event: %w", err)
	}
	return s.Send(AgentEventPayload{
		EventType: EventTypeAgentToolResult,
		Data:      data,
	})
}

// SendMessage sends a message event to the user.
func (s *AgentSession) SendMessage(content string) error {
	data, err := json.Marshal(map[string]any{
		"content":     content,
		"is_complete": true,
	})
	if err != nil {
		return fmt.Errorf("marshal message event: %w", err)
	}
	return s.Send(AgentEventPayload{
		EventType: EventTypeAgentMessage,
		Data:      data,
	})
}

// SendToken sends a streaming token event.
func (s *AgentSession) SendToken(token string) error {
	data, err := json.Marshal(map[string]any{
		"token": token,
	})
	if err != nil {
		return fmt.Errorf("marshal token event: %w", err)
	}
	return s.Send(AgentEventPayload{
		EventType: EventTypeAgentToken,
		Data:      data,
	})
}

// SendStatus sends a status update event.
func (s *AgentSession) SendStatus(status, detail string) error {
	data, err := json.Marshal(map[string]any{
		"status": status,
		"detail": detail,
	})
	if err != nil {
		return fmt.Errorf("marshal status event: %w", err)
	}
	return s.Send(AgentEventPayload{
		EventType: EventTypeAgentStatus,
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
	info, err := s.AttachmentUploader.Upload(fileID, name, mime, -1, combined)
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

// SendAttachmentBytes is a convenience for SendAttachment with a []byte source.
func (s *AgentSession) SendAttachmentBytes(b []byte, name, mime string) (string, error) {
	return s.SendAttachment(bytes.NewReader(b), name, mime)
}

// RequestInput sends an agent.request_input event, then blocks for user response.
func (s *AgentSession) RequestInput(prompt string) (UserMessage, error) {
	data, err := json.Marshal(map[string]any{
		"prompt": prompt,
	})
	if err != nil {
		return UserMessage{}, fmt.Errorf("marshal request_input event: %w", err)
	}
	if err := s.Send(AgentEventPayload{
		EventType: EventTypeAgentRequestInput,
		Data:      data,
	}); err != nil {
		return UserMessage{}, err
	}
	return s.Receive()
}

// RequestConfirmation sends a tool_call with requires_confirmation=true,
// then blocks for a user_confirm or user_deny response.
// Returns true if confirmed, false if denied.
func (s *AgentSession) RequestConfirmation(action string, args map[string]any) (bool, error) {
	tc := ToolCall{
		ID:                   fmt.Sprintf("confirm-%d", s.sequence.Load()+1),
		Name:                 action,
		Arguments:            args,
		RequiresConfirmation: true,
	}
	if err := s.SendToolCall(tc); err != nil {
		return false, err
	}

	msg, err := s.Receive()
	if err != nil {
		return false, err
	}

	return msg.Type == "user_confirm", nil
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
