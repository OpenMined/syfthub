// events.go defines the typed agent session events shared by the hub client
// SDK (syfthub) and the syfthubapi transport agent client. Keeping them here,
// in the dependency-free agenttypes package, lets both clients decode events
// with one parser and one set of struct definitions.

package agenttypes

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
)

// AttachmentCapability is the capability string a client advertises when
// opening an agent session to opt into the attachments protocol.
const AttachmentCapability = "attachments"

// InlineAttachmentMaxBytes is the maximum plaintext size carried by the inline
// attachment transport; larger payloads use the object-store transport.
const InlineAttachmentMaxBytes = 64 * 1024

// AgentEvent is implemented by every typed agent session event.
type AgentEvent interface {
	EventType() string
}

// ThinkingEvent is an agent reasoning/thinking event.
type ThinkingEvent struct {
	Content     string `json:"content"`
	IsStreaming bool   `json:"is_streaming"`
}

func (e *ThinkingEvent) EventType() string { return "agent.thinking" }

// ToolCallEvent is a tool invocation request. It embeds ToolCall so callers
// share one struct layout.
type ToolCallEvent struct {
	ToolCall
}

func (e *ToolCallEvent) EventType() string { return "agent.tool_call" }

// ToolResultEvent is a tool execution result. It embeds ToolResult.
type ToolResultEvent struct {
	ToolResult
}

func (e *ToolResultEvent) EventType() string { return "agent.tool_result" }

// MessageEvent is an agent message.
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
	// ReviewID is the manual-review handle (a 12-hex id) carried on a pending
	// notice when a manual_review policy held the turn. It is the durable,
	// machine-readable reference a client uses to track the held request.
	ReviewID string `json:"review_id,omitempty"`
}

// AgentTokenEvent is a streaming token.
type AgentTokenEvent struct {
	Token string `json:"token"`
}

func (e *AgentTokenEvent) EventType() string { return "agent.token" }

// AgentStatusEvent is a status update.
type AgentStatusEvent struct {
	Status   string   `json:"status"`
	Detail   string   `json:"detail"`
	Progress *float64 `json:"progress,omitempty"`
}

func (e *AgentStatusEvent) EventType() string { return "agent.status" }

// RequestInputEvent is an agent request for user input.
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

// AgentErrorEvent is an error from the agent system.
type AgentErrorEvent struct {
	Code        string `json:"code"`
	Message     string `json:"message"`
	Recoverable bool   `json:"recoverable"`
}

func (e *AgentErrorEvent) EventType() string { return "agent.error" }

// AgentPaymentRequiredEvent indicates the agent endpoint's transaction policy
// requires the caller to submit an on-chain payment credential before the
// session can proceed.
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

// AttachmentEvent is an attachment emitted by the agent (host → client). The
// bytes are inline (transport="inline", base64 in InlineDataB64) or in object
// storage (transport="object_store").
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
	ObjectBucket string         `json:"object_bucket,omitempty"`
	ObjectKey    string         `json:"object_key,omitempty"`
	ChunkSize    int            `json:"chunk_size,omitempty"`
	WrappedKey   map[string]any `json:"wrapped_key,omitempty"`
}

func (e *AttachmentEvent) EventType() string { return "agent.attachment" }

// Bytes returns the decoded plaintext for an inline-tier attachment. For
// object-store-tier attachments it returns an error.
func (e *AttachmentEvent) Bytes() ([]byte, error) {
	if e.Transport != "inline" {
		return nil, fmt.Errorf("attachment %q is not inline (transport=%q)", e.FileID, e.Transport)
	}
	if e.InlineDataB64 == "" {
		return nil, fmt.Errorf("inline_data_b64 is empty")
	}
	return base64.StdEncoding.DecodeString(e.InlineDataB64)
}

// ParseAgentEvent decodes a raw agent event payload into its typed form.
// It returns (nil, nil) for an unrecognized event type.
func ParseAgentEvent(eventType string, payload json.RawMessage) (AgentEvent, error) {
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
