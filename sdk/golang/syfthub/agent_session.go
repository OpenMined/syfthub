package syfthub

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"strings"
	"sync"

	"github.com/coder/websocket"
	"github.com/openmined/syfthub/sdk/golang/agenttypes"
)

// AttachmentCapability is the capability string clients advertise in
// session.start to opt into the attachments protocol. See
// docs/architecture/attachments.md.
const AttachmentCapability = "attachments"

// InlineAttachmentMaxBytes is the maximum plaintext size supported by the
// inline transport. Larger files require the Object Store transport.
// MUST equal syfthubapi.InlineMaxBytes.
const InlineAttachmentMaxBytes = 64 * 1024

// newAttachmentID returns a fresh "att-<uuid>" identifier.
func newAttachmentID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("att-%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// AgentEvent is the interface for all agent events.
type AgentEvent interface {
	EventType() string
}

// ThinkingEvent represents an agent thinking/reasoning event.
type ThinkingEvent struct {
	Content     string `json:"content"`
	IsStreaming bool   `json:"is_streaming"`
}

func (e *ThinkingEvent) EventType() string { return "agent.thinking" }

// ToolCallEvent represents a tool invocation request.
// It embeds agenttypes.ToolCall so both packages share the same struct layout.
type ToolCallEvent struct {
	agenttypes.ToolCall
}

func (e *ToolCallEvent) EventType() string { return "agent.tool_call" }

// ToolResultEvent represents a tool execution result.
// It embeds agenttypes.ToolResult so both packages share the same struct layout.
type ToolResultEvent struct {
	agenttypes.ToolResult
}

func (e *ToolResultEvent) EventType() string { return "agent.tool_result" }

// MessageEvent represents an agent message.
type MessageEvent struct {
	Content    string `json:"content"`
	IsComplete bool   `json:"is_complete"`

	// Policy, when set, marks this message as a policy notice — the agent's
	// reply was blocked, or is pending review — rather than a normal reply.
	// Clients should render it as a distinct notice; Content is the
	// human-readable fallback.
	Policy *MessagePolicyNotice `json:"policy,omitempty"`
}

func (e *MessageEvent) EventType() string { return "agent.message" }

// MessagePolicyNotice is the structured policy outcome carried by a
// policy-notice MessageEvent.
type MessagePolicyNotice struct {
	Status     string `json:"status"`          // "blocked" | "pending"
	Phase      string `json:"phase,omitempty"` // "pre" | "post"
	PolicyName string `json:"policy_name,omitempty"`
	Reason     string `json:"reason,omitempty"`
}

// AgentTokenEvent represents a streaming token.
type AgentTokenEvent struct {
	Token string `json:"token"`
}

func (e *AgentTokenEvent) EventType() string { return "agent.token" }

// AgentStatusEvent represents a status update.
type AgentStatusEvent struct {
	Status   string   `json:"status"`
	Detail   string   `json:"detail"`
	Progress *float64 `json:"progress,omitempty"`
}

func (e *AgentStatusEvent) EventType() string { return "agent.status" }

// RequestInputEvent represents an agent requesting user input.
type RequestInputEvent struct {
	Prompt string `json:"prompt"`
}

func (e *RequestInputEvent) EventType() string { return "agent.request_input" }

// SessionCompletedEvent indicates the session completed successfully.
type SessionCompletedEvent struct {
	SessionID string `json:"session_id"`
}

func (e *SessionCompletedEvent) EventType() string { return "session.completed" }

// SessionFailedEvent indicates the session failed.
type SessionFailedEvent struct {
	Error  string `json:"error"`
	Reason string `json:"reason"`
}

func (e *SessionFailedEvent) EventType() string { return "session.failed" }

// AgentErrorEvent represents an error from the agent system.
type AgentErrorEvent struct {
	Code        string `json:"code"`
	Message     string `json:"message"`
	Recoverable bool   `json:"recoverable"`
}

func (e *AgentErrorEvent) EventType() string { return "agent.error" }

// AgentPaymentRequiredEvent indicates the agent endpoint's transaction policy
// requires the caller to sign + submit an on-chain payment credential before
// the session can proceed. Mirrors the chat SDK's PaymentRequiredEvent but
// flows over the agent WebSocket envelope ("payment_required" / "agent.payment_required").
//
// See unit 10 of the transaction-policy plan (nifty-skipping-rainbow.md).
type AgentPaymentRequiredEvent struct {
	ChatSessionID string `json:"chat_session_id"`
	EndpointSlug  string `json:"endpoint_slug"`
	Challenge     string `json:"challenge"`
	Amount        string `json:"amount"`
	Currency      string `json:"currency"`
	Recipient     string `json:"recipient"`
	ChallengeID   string `json:"challenge_id"`
	Intent        string `json:"intent"`
	RPCURL        string `json:"rpc_url,omitempty"`
}

func (e *AgentPaymentRequiredEvent) EventType() string { return "agent.payment_required" }

// AttachmentEvent represents an attachment emitted by the agent (HOST → CLIENT
// direction). The bytes are either inline (transport=inline, base64 in
// InlineDataB64) or live in JetStream Object Store (transport=object_store).
// See docs/architecture/attachments.md.
type AttachmentEvent struct {
	FileID          string `json:"file_id"`
	Name            string `json:"name"`
	MIME            string `json:"mime"`
	SizeBytes       int64  `json:"size_bytes"`
	PlaintextSHA256 string `json:"plaintext_sha256"`
	Transport       string `json:"transport"`

	// Inline tier:
	InlineDataB64 string `json:"inline_data_b64,omitempty"`

	// Object-store tier:
	ObjectBucket string                 `json:"object_bucket,omitempty"`
	ObjectKey    string                 `json:"object_key,omitempty"`
	ChunkSize    int                    `json:"chunk_size,omitempty"`
	WrappedKey   map[string]interface{} `json:"wrapped_key,omitempty"`
}

func (e *AttachmentEvent) EventType() string { return "agent.attachment" }

// Bytes returns the decoded plaintext bytes for an inline-tier attachment.
// For object-store-tier attachments it returns an error; callers should use
// AgentSessionClient.DownloadAttachment instead.
func (e *AttachmentEvent) Bytes() ([]byte, error) {
	if e.Transport != "inline" {
		return nil, fmt.Errorf("attachment %q is not inline (transport=%q)", e.FileID, e.Transport)
	}
	if e.InlineDataB64 == "" {
		return nil, fmt.Errorf("inline_data_b64 is empty")
	}
	return base64.StdEncoding.DecodeString(e.InlineDataB64)
}

// AgentSessionClient wraps a WebSocket connection with typed send/receive
// methods for agent sessions.
type AgentSessionClient struct {
	// SessionID is the unique session identifier.
	SessionID string

	// AggregatorHTTPURL is the base HTTP URL used by the attachments side-
	// channel (POST/GET /api/v1/agent/session/{sid}/attachment[/{fid}]).
	// Set by AgentResource.StartSession.
	AggregatorHTTPURL string

	conn   *websocket.Conn
	events chan AgentEvent
	errs   chan error
	done   chan struct{}
	mu     sync.Mutex
	closed bool

	// ctx and cancel control the readLoop lifecycle. Cancelling ctx
	// unblocks conn.Read immediately so Close() doesn't hang waiting
	// for the server to respond to the close frame.
	ctx    context.Context
	cancel context.CancelFunc
}

// newAgentSessionClient creates a new session client and starts the read loop.
func newAgentSessionClient(conn *websocket.Conn, sessionID string) *AgentSessionClient {
	ctx, cancel := context.WithCancel(context.Background())
	c := &AgentSessionClient{
		SessionID: sessionID,
		conn:      conn,
		events:    make(chan AgentEvent, 64),
		errs:      make(chan error, 8),
		done:      make(chan struct{}),
		ctx:       ctx,
		cancel:    cancel,
	}
	go c.readLoop()
	return c
}

// Events returns a channel of typed agent events.
func (c *AgentSessionClient) Events() <-chan AgentEvent {
	return c.events
}

// Errors returns a channel of errors.
func (c *AgentSessionClient) Errors() <-chan error {
	return c.errs
}

// Done returns a channel that is closed when the session ends.
func (c *AgentSessionClient) Done() <-chan struct{} {
	return c.done
}

// SendMessage sends a user message to the agent.
func (c *AgentSessionClient) SendMessage(ctx context.Context, content string) error {
	return c.sendJSON(ctx, map[string]any{
		"type": "user.message",
		"payload": map[string]string{
			"content": content,
		},
	})
}

// Confirm confirms a tool call.
func (c *AgentSessionClient) Confirm(ctx context.Context, toolCallID string) error {
	return c.sendJSON(ctx, map[string]any{
		"type": "user.confirm",
		"payload": map[string]string{
			"tool_call_id": toolCallID,
		},
	})
}

// Deny denies a tool call.
func (c *AgentSessionClient) Deny(ctx context.Context, toolCallID string, reason string) error {
	return c.sendJSON(ctx, map[string]any{
		"type": "user.deny",
		"payload": map[string]any{
			"tool_call_id": toolCallID,
			"reason":       reason,
		},
	})
}

// Cancel cancels the session.
func (c *AgentSessionClient) Cancel(ctx context.Context) error {
	return c.sendJSON(ctx, map[string]any{
		"type": "user.cancel",
	})
}

// AttachmentOpts holds the per-call options for SendAttachment.
type AttachmentOpts struct {
	// Name is the display name (defaults to "attachment.bin").
	Name string
	// MIME is the declared media type (defaults to application/octet-stream).
	MIME string
}

// SendAttachment uploads a file to the agent.
//
// Behavior:
//   - Payload <= InlineAttachmentMaxBytes: rides inline (base64) in a
//     user.attachment WebSocket frame.
//   - Payload > InlineAttachmentMaxBytes: streamed via HTTP POST to the
//     aggregator's relay endpoint (POST /api/v1/agent/session/{sid}/attachment).
//     The aggregator handles encryption + Object Store storage + the
//     accompanying user.attachment metadata event published over NATS.
//
// Returns the assigned file_id. Callers should reference attachments in
// subsequent text with the URI scheme `attachment://{file_id}`.
func (c *AgentSessionClient) SendAttachment(ctx context.Context, r io.Reader, opts AttachmentOpts) (string, error) {
	// Try inline first by reading up to InlineAttachmentMaxBytes+1.
	head, err := io.ReadAll(io.LimitReader(r, InlineAttachmentMaxBytes+1))
	if err != nil {
		return "", fmt.Errorf("read attachment: %w", err)
	}
	name := opts.Name
	if name == "" {
		name = "attachment.bin"
	}
	mime := opts.MIME
	if mime == "" {
		mime = "application/octet-stream"
	}

	if len(head) <= InlineAttachmentMaxBytes {
		fileID := newAttachmentID()
		sum := sha256.Sum256(head)
		return fileID, c.sendJSON(ctx, map[string]any{
			"type": "user.attachment",
			"payload": map[string]any{
				"file_id":          fileID,
				"name":             name,
				"mime":             mime,
				"size_bytes":       int64(len(head)),
				"plaintext_sha256": hex.EncodeToString(sum[:]),
				"transport":        "inline",
				"inline_data_b64":  base64.StdEncoding.EncodeToString(head),
			},
		})
	}

	// Spill-over to HTTP relay.
	if c.AggregatorHTTPURL == "" {
		return "", fmt.Errorf("attachment exceeds inline limit and AggregatorHTTPURL is unset")
	}
	combined := io.MultiReader(bytesReader(head), r)
	return c.uploadAttachmentHTTP(ctx, name, mime, combined)
}

// DownloadAttachment fetches an attachment by file_id and streams it into w.
// Used to retrieve agent-emitted attachments that landed in Object Store.
func (c *AgentSessionClient) DownloadAttachment(ctx context.Context, fileID string, w io.Writer) error {
	if c.AggregatorHTTPURL == "" {
		return fmt.Errorf("AggregatorHTTPURL is unset")
	}
	url := strings.TrimRight(c.AggregatorHTTPURL, "/") + "/api/v1/agent/session/" + c.SessionID + "/attachment/" + fileID
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("http get: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download returned %d", resp.StatusCode)
	}
	if _, err := io.Copy(w, resp.Body); err != nil {
		return fmt.Errorf("stream body: %w", err)
	}
	return nil
}

// uploadAttachmentHTTP POSTs a multipart upload to the aggregator's relay.
// Returns the file_id assigned by the server.
func (c *AgentSessionClient) uploadAttachmentHTTP(ctx context.Context, name, mime string, r io.Reader) (string, error) {
	pr, pw := io.Pipe()
	mw := multipart.NewWriter(pw)
	url := strings.TrimRight(c.AggregatorHTTPURL, "/") + "/api/v1/agent/session/" + c.SessionID + "/attachment"

	uploadErr := make(chan error, 1)
	go func() {
		defer pw.Close()
		defer mw.Close()
		hdr := make(textproto.MIMEHeader)
		hdr.Set("Content-Disposition", fmt.Sprintf(`form-data; name="file"; filename=%q`, name))
		hdr.Set("Content-Type", mime)
		part, err := mw.CreatePart(hdr)
		if err != nil {
			uploadErr <- err
			return
		}
		if _, err := io.Copy(part, r); err != nil {
			uploadErr <- err
			return
		}
		uploadErr <- nil
	}()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, pr)
	if err != nil {
		return "", fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("http post: %w", err)
	}
	defer resp.Body.Close()
	if err := <-uploadErr; err != nil {
		return "", fmt.Errorf("upload body: %w", err)
	}
	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("aggregator returned %d: %s", resp.StatusCode, string(bodyBytes))
	}
	var out struct {
		FileID string `json:"file_id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}
	if out.FileID == "" {
		return "", fmt.Errorf("aggregator returned empty file_id")
	}
	return out.FileID, nil
}

// SendAttachmentBytes is a convenience wrapper for SendAttachment with a
// []byte source.
func (c *AgentSessionClient) SendAttachmentBytes(ctx context.Context, data []byte, opts AttachmentOpts) (string, error) {
	return c.SendAttachment(ctx, bytesReader(data), opts)
}

// bytesReader is a tiny helper to avoid importing bytes just for NewReader.
func bytesReader(b []byte) io.Reader {
	return &sliceReader{b: b}
}

type sliceReader struct {
	b   []byte
	pos int
}

func (r *sliceReader) Read(p []byte) (int, error) {
	if r.pos >= len(r.b) {
		return 0, io.EOF
	}
	n := copy(p, r.b[r.pos:])
	r.pos += n
	return n, nil
}

// Close closes the WebSocket connection and cleans up resources.
// It cancels the read context first so that readLoop unblocks
// immediately instead of waiting for the server's close frame.
func (c *AgentSessionClient) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return nil
	}
	c.closed = true

	// Cancel the read context so conn.Read returns immediately.
	c.cancel()

	return c.conn.Close(websocket.StatusNormalClosure, "session closed")
}

// sendJSON marshals and sends a JSON message.
func (c *AgentSessionClient) sendJSON(ctx context.Context, msg any) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return fmt.Errorf("session is closed")
	}

	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal message: %w", err)
	}

	return c.conn.Write(ctx, websocket.MessageText, data)
}

// readLoop reads messages from the WebSocket and dispatches typed events.
func (c *AgentSessionClient) readLoop() {
	defer close(c.done)
	defer close(c.errs)
	defer close(c.events)

	for {
		_, data, err := c.conn.Read(c.ctx)
		if err != nil {
			c.mu.Lock()
			wasClosed := c.closed
			c.mu.Unlock()
			if !wasClosed {
				c.errs <- err
			}
			return
		}

		var envelope struct {
			Type    string          `json:"type"`
			Payload json.RawMessage `json:"payload"`
		}
		if err := json.Unmarshal(data, &envelope); err != nil {
			c.errs <- fmt.Errorf("failed to parse event: %w", err)
			continue
		}

		event, err := c.parseEvent(envelope.Type, envelope.Payload)
		if err != nil {
			c.errs <- err
			continue
		}
		if event == nil {
			continue
		}

		c.events <- event

		// Close on terminal events
		switch envelope.Type {
		case "session.completed", "session.failed":
			return
		}
	}
}

// parseEvent parses a raw event into a typed AgentEvent.
func (c *AgentSessionClient) parseEvent(eventType string, payload json.RawMessage) (AgentEvent, error) {
	var event AgentEvent
	var err error

	switch eventType {
	case "agent.thinking":
		var e ThinkingEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.tool_call":
		var e ToolCallEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.tool_result":
		var e ToolResultEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.message":
		var e MessageEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.token":
		var e AgentTokenEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.status":
		var e AgentStatusEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.request_input":
		var e RequestInputEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "session.completed":
		var e SessionCompletedEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "session.failed":
		var e SessionFailedEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.error":
		var e AgentErrorEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.payment_required", "payment_required":
		var e AgentPaymentRequiredEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	case "agent.attachment":
		var e AttachmentEvent
		err = json.Unmarshal(payload, &e)
		event = &e
	default:
		return nil, nil
	}

	if err != nil {
		return nil, fmt.Errorf("failed to parse %s event: %w", eventType, err)
	}
	return event, nil
}
