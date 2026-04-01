package syfthub

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"

	"github.com/coder/websocket"
	"github.com/openmined/syfthub/sdk/golang/agenttypes"
)

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
}

func (e *MessageEvent) EventType() string { return "agent.message" }

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

// AgentSessionClient wraps a WebSocket connection with typed send/receive
// methods for agent sessions.
type AgentSessionClient struct {
	// SessionID is the unique session identifier.
	SessionID string

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
	default:
		return nil, nil
	}

	if err != nil {
		return nil, fmt.Errorf("failed to parse %s event: %w", eventType, err)
	}
	return event, nil
}
