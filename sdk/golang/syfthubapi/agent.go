package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
	"sync/atomic"

	"github.com/openmined/syfthub/sdk/golang/agenttypes"
)

// AgentConfig is an alias for the shared agent config type.
// Kept for backward compatibility so callers can continue using syfthubapi.AgentConfig.
type AgentConfig = agenttypes.AgentConfig

// ToolCall is an alias for the shared tool call type.
// Kept for backward compatibility so callers can continue using syfthubapi.ToolCall.
type ToolCall = agenttypes.ToolCall

// ToolResult is an alias for the shared tool result type.
// Kept for backward compatibility so callers can continue using syfthubapi.ToolResult.
type ToolResult = agenttypes.ToolResult

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
}

// AgentSessionParams holds the parameters for creating a new AgentSession.
type AgentSessionParams struct {
	ID           string
	Prompt       string
	EndpointSlug string
	Messages     []Message
	Config       AgentConfig
	User         *UserContext
}

// NewAgentSession creates a new AgentSession with the given parameters.
// parentCtx controls the session's lifetime — when it is cancelled, the
// session's context is also cancelled, causing the handler to unblock.
// Pass context.Background() for sessions with no external deadline.
func NewAgentSession(parentCtx context.Context, params AgentSessionParams) *AgentSession {
	ctx, cancel := context.WithCancel(parentCtx)
	return &AgentSession{
		ID:            params.ID,
		InitialPrompt: params.Prompt,
		Messages:      params.Messages,
		Config:        params.Config,
		User:          params.User,
		EndpointSlug:  params.EndpointSlug,
		ctx:           ctx,
		cancel:        cancel,
		sendCh:        make(chan AgentEventPayload, 100),
		recvCh:        make(chan UserMessage, 100),
		done:          make(chan struct{}),
	}
}

// Context returns the session's context.
func (s *AgentSession) Context() context.Context {
	return s.ctx
}

// Cancel cancels the session context, causing the handler to return.
func (s *AgentSession) Cancel() {
	s.cancel()
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
func (s *AgentSession) DeliverMessage(msg UserMessage) bool {
	select {
	case s.recvCh <- msg:
		return true
	default:
		return false
	}
}

// Send sends a raw AgentEventPayload to the user.
func (s *AgentSession) Send(event AgentEventPayload) error {
	event.SessionID = s.ID
	event.Sequence = int(s.sequence.Add(1))
	select {
	case s.sendCh <- event:
		return nil
	case <-s.ctx.Done():
		return s.ctx.Err()
	}
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
		EventType: "agent.thinking",
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
		EventType: "agent.tool_call",
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
		EventType: "agent.tool_result",
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
		EventType: "agent.message",
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
		EventType: "agent.token",
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
		EventType: "agent.status",
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

// RequestInput sends an agent.request_input event, then blocks for user response.
func (s *AgentSession) RequestInput(prompt string) (UserMessage, error) {
	data, err := json.Marshal(map[string]any{
		"prompt": prompt,
	})
	if err != nil {
		return UserMessage{}, fmt.Errorf("marshal request_input event: %w", err)
	}
	if err := s.Send(AgentEventPayload{
		EventType: "agent.request_input",
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
					EventType: "session.failed",
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
				EventType: "session.failed",
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
				EventType: "session.completed",
				Sequence:  int(s.sequence.Add(1)),
				Data:      data,
			}:
			default:
			}
		}
	}()
}
