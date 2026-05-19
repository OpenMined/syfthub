package syfthubapi

import (
	"context"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"
)

// newSilentManager builds a session manager that discards log output so the
// test stream stays focused on assertion failures.
func newSilentManager(t *testing.T, registry *EndpointRegistry) *AgentSessionManager {
	t.Helper()
	return NewAgentSessionManager(registry, slog.New(slog.NewTextHandler(io.Discard, nil)), 0)
}

// drainSendCh empties the session's outbound channel into a slice for
// assertion. Returns when the channel closes OR the deadline expires.
func drainSendCh(t *testing.T, session *AgentSession, deadline time.Duration) []AgentEventPayload {
	t.Helper()
	var events []AgentEventPayload
	timer := time.NewTimer(deadline)
	defer timer.Stop()
	for {
		select {
		case ev, ok := <-session.SendCh():
			if !ok {
				return events
			}
			events = append(events, ev)
		case <-timer.C:
			return events
		}
	}
}

func registerAgent(t *testing.T, registry *EndpointRegistry, slug string, cfg EndpointHandlerConfig) {
	t.Helper()
	ep := &Endpoint{Slug: slug, Type: EndpointTypeAgent, Enabled: true}
	ep.SetHandler(cfg)
	if err := registry.Register(ep); err != nil {
		t.Fatalf("Register(%s): %v", slug, err)
	}
}

// StartSession runs the endpoint's handler against a new session.
func TestStartSession_RunsHandler(t *testing.T) {
	registry := NewEndpointRegistry()
	registerAgent(t, registry, "a1", EndpointHandlerConfig{
		AgentHandler: func(_ context.Context, s *AgentSession) error {
			return s.Send(agentMessageEvent("handler ran"))
		},
	})
	m := newSilentManager(t, registry)

	session, err := m.StartSession(AgentSessionStartPayload{
		SessionID: "s1", Prompt: "hi", EndpointSlug: "a1",
	}, &UserContext{Username: "alice"})
	if err != nil {
		t.Fatalf("StartSession: %v", err)
	}

	events := drainSendCh(t, session, time.Second)
	if firstContent(events, EventTypeAgentMessage) != "handler ran" {
		t.Error("the endpoint handler's message was not delivered")
	}
}

// RouteMessage delivers a follow-up message to a live session's handler.
func TestRouteMessage_DeliversToSession(t *testing.T) {
	registry := NewEndpointRegistry()
	registerAgent(t, registry, "a2", EndpointHandlerConfig{
		AgentHandler: func(_ context.Context, s *AgentSession) error {
			msg, err := s.Receive()
			if err != nil {
				return err
			}
			return s.Send(agentMessageEvent("echo:" + msg.Content))
		},
	})
	m := newSilentManager(t, registry)

	session, err := m.StartSession(AgentSessionStartPayload{
		SessionID: "s2", EndpointSlug: "a2",
	}, &UserContext{Username: "alice"})
	if err != nil {
		t.Fatalf("StartSession: %v", err)
	}

	if err := m.RouteMessage(AgentUserMessagePayload{
		SessionID: "s2",
		Message:   UserMessage{Type: UserMessageTypeMessage, Content: "ping"},
	}); err != nil {
		t.Fatalf("RouteMessage: %v", err)
	}

	events := drainSendCh(t, session, time.Second)
	if got := firstContent(events, EventTypeAgentMessage); got != "echo:ping" {
		t.Errorf("message not delivered to handler; got %q", got)
	}
}

// RouteMessage to an unknown session is an error.
func TestRouteMessage_UnknownSessionErrors(t *testing.T) {
	m := newSilentManager(t, NewEndpointRegistry())
	err := m.RouteMessage(AgentUserMessagePayload{
		SessionID: "does-not-exist",
		Message:   UserMessage{Type: UserMessageTypeMessage, Content: "x"},
	})
	if err == nil {
		t.Error("expected an error routing to an unknown session")
	}
}

// Integration: SetHandler wires AgentExecutor when the endpoint has a policy
// executor, so a policy denial gates the session through StartSession — the
// initial prompt is denied, the user receives a message explaining the block,
// and the agent never runs.
func TestStartSession_PolicyDenialGatesSession(t *testing.T) {
	denyExec := &mockExecutor{
		executeFunc: func(_ context.Context, _ *ExecutorInput) (*ExecutorOutput, error) {
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{
				Allowed: false, PolicyName: "ag", Reason: "access denied",
			}}, nil
		},
	}
	ranAgent := false
	registry := NewEndpointRegistry()
	registerAgent(t, registry, "a3", EndpointHandlerConfig{
		AgentHandler: func(ctx context.Context, _ *AgentSession) error {
			ranAgent = true
			<-ctx.Done()
			return nil
		},
		PolicyExecutor: denyExec,
	})
	m := newSilentManager(t, registry)

	session, err := m.StartSession(AgentSessionStartPayload{
		SessionID: "s3", Prompt: "blocked prompt", EndpointSlug: "a3",
	}, &UserContext{Username: "alice"})
	if err != nil {
		t.Fatalf("StartSession: %v", err)
	}

	events := drainSendCh(t, session, time.Second)
	msg := firstContent(events, EventTypeAgentMessage)
	if msg == "" {
		t.Error("expected a policy-block agent.message — AgentExecutor must gate the initial prompt")
	}
	if !strings.Contains(msg, "ag") {
		t.Errorf("block message = %q, should name the denying policy", msg)
	}
	if ranAgent {
		t.Error("the agent must not run when its initial prompt is policy-denied")
	}
}
