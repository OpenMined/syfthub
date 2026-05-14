package syfthubapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// newSilentManager builds a session manager that discards log output so the
// test stream stays focused on assertion failures.
func newSilentManager(t *testing.T, registry *EndpointRegistry) *AgentSessionManager {
	t.Helper()
	return NewAgentSessionManager(registry, slog.New(slog.NewTextHandler(io.Discard, nil)), 0)
}

// newAgentEndpointWithPolicy wires an agent endpoint backed by a stub handler
// (which never returns) plus the supplied policy executor. The handler runs in
// a goroutine started by StartSession; passing a noop handler keeps the
// session alive for follow-up message routing.
func newAgentEndpointWithPolicy(slug string, policyExec Executor) *Endpoint {
	ep := &Endpoint{
		Slug:    slug,
		Type:    EndpointTypeAgent,
		Enabled: true,
	}
	ep.SetHandler(EndpointHandlerConfig{
		AgentHandler: func(ctx context.Context, session *AgentSession) error {
			<-ctx.Done()
			return nil
		},
		PolicyExecutor: policyExec,
	})
	return ep
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

func startAllowedSession(t *testing.T, m *AgentSessionManager, slug string) *AgentSession {
	t.Helper()
	session, err := m.StartSession(AgentSessionStartPayload{
		SessionID:    "sess-" + slug,
		Prompt:       "hello",
		EndpointSlug: slug,
	}, &UserContext{Username: "alice"})
	if err != nil {
		t.Fatalf("StartSession: %v", err)
	}
	return session
}

// TestRouteMessage_PolicyDeniedTerminatesSession exercises the headline bug:
// once a session is established, a policy that flips to deny must take effect
// on the very next user message — not after the user manually starts a new
// session.
func TestRouteMessage_PolicyDeniedTerminatesSession(t *testing.T) {
	var callCount atomic.Int32
	policyExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			n := callCount.Add(1)
			if n == 1 {
				return &ExecutorOutput{PolicyResult: &PolicyResultOutput{Allowed: true}}, nil
			}
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{
				Allowed:    false,
				PolicyName: "access_group_a",
				Reason:     "user removed from group",
			}}, nil
		},
	}
	registry := NewEndpointRegistry()
	ep := newAgentEndpointWithPolicy("agent-1", policyExec)
	if err := registry.Register(ep); err != nil {
		t.Fatal(err)
	}
	m := newSilentManager(t, registry)

	session := startAllowedSession(t, m, "agent-1")

	if err := m.RouteMessage(AgentUserMessagePayload{
		SessionID: session.ID,
		Message:   UserMessage{Type: UserMessageTypeMessage, Content: "ping"},
	}); err == nil {
		t.Fatal("expected denial error from RouteMessage")
	}

	if got := callCount.Load(); got != 2 {
		t.Errorf("expected 2 policy executor calls (start+message), got %d", got)
	}

	if !session.ExternalCancelled() {
		t.Error("session should be marked externally cancelled on denial")
	}

	events := drainSendCh(t, session, 500*time.Millisecond)
	var sawDenied bool
	for _, ev := range events {
		if ev.EventType == EventTypeAgentPolicyDenied {
			sawDenied = true
			var data struct {
				PolicyName string `json:"policy_name"`
				Reason     string `json:"reason"`
			}
			if err := json.Unmarshal(ev.Data, &data); err != nil {
				t.Errorf("policy_denied event payload not JSON: %v", err)
			}
			if data.PolicyName != "access_group_a" {
				t.Errorf("policy_denied policy_name = %q", data.PolicyName)
			}
			if data.Reason == "" {
				t.Error("policy_denied reason should be populated")
			}
		}
	}
	if !sawDenied {
		t.Error("expected agent.policy_denied event on session.sendCh")
	}
}

// TestRouteMessage_RateLimitDecrementsAcrossMessages models the rate-limit
// case: every conversational message must run policies so the runner's
// stateful counter decrements turn-by-turn.
func TestRouteMessage_RateLimitDecrementsAcrossMessages(t *testing.T) {
	var calls atomic.Int32
	policyExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			calls.Add(1)
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{Allowed: true}}, nil
		},
	}
	registry := NewEndpointRegistry()
	ep := newAgentEndpointWithPolicy("agent-rl", policyExec)
	if err := registry.Register(ep); err != nil {
		t.Fatal(err)
	}
	m := newSilentManager(t, registry)

	session := startAllowedSession(t, m, "agent-rl")
	// Drain the recv channel so DeliverMessage doesn't fill it up and force
	// the warn-and-drop path during a multi-message test.
	go func() {
		for {
			if _, err := session.Receive(); err != nil {
				return
			}
		}
	}()

	for i := range 3 {
		if err := m.RouteMessage(AgentUserMessagePayload{
			SessionID: session.ID,
			Message:   UserMessage{Type: UserMessageTypeMessage, Content: "ping"},
		}); err != nil {
			t.Fatalf("RouteMessage #%d: %v", i, err)
		}
	}

	// 1 (StartSession) + 3 (each user_message) = 4 total.
	if got := calls.Load(); got != 4 {
		t.Errorf("expected 4 policy executor calls, got %d", got)
	}
}

// TestRouteMessage_ControlSignalsBypassPolicy ensures user_confirm /
// user_deny / user_cancel skip the gate. Counting them toward rate limits
// would let a hostile policy chain trip the limit using cancellation
// signals alone.
func TestRouteMessage_ControlSignalsBypassPolicy(t *testing.T) {
	var calls atomic.Int32
	policyExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			calls.Add(1)
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{Allowed: true}}, nil
		},
	}
	registry := NewEndpointRegistry()
	ep := newAgentEndpointWithPolicy("agent-ctl", policyExec)
	if err := registry.Register(ep); err != nil {
		t.Fatal(err)
	}
	m := newSilentManager(t, registry)

	session := startAllowedSession(t, m, "agent-ctl")
	go func() {
		for {
			if _, err := session.Receive(); err != nil {
				return
			}
		}
	}()

	for _, ctlType := range []string{UserMessageTypeConfirm, UserMessageTypeDeny, UserMessageTypeCancel} {
		if err := m.RouteMessage(AgentUserMessagePayload{
			SessionID: session.ID,
			Message:   UserMessage{Type: ctlType},
		}); err != nil {
			t.Fatalf("RouteMessage(%s): %v", ctlType, err)
		}
	}

	if got := calls.Load(); got != 1 {
		t.Errorf("expected 1 policy executor call (start only), got %d", got)
	}
}

// TestRouteMessage_ExecutorErrorKeepsSessionAlive verifies the soft-error
// posture: a transient policy-runner failure must NOT terminate the
// session. Tearing down a healthy chat because the policy subprocess hiccupped
// would be worse UX than the bug we're fixing.
func TestRouteMessage_ExecutorErrorKeepsSessionAlive(t *testing.T) {
	var calls atomic.Int32
	policyExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			n := calls.Add(1)
			if n == 1 {
				return &ExecutorOutput{PolicyResult: &PolicyResultOutput{Allowed: true}}, nil
			}
			return nil, errors.New("python subprocess crashed")
		},
	}
	registry := NewEndpointRegistry()
	ep := newAgentEndpointWithPolicy("agent-err", policyExec)
	if err := registry.Register(ep); err != nil {
		t.Fatal(err)
	}
	m := newSilentManager(t, registry)

	session := startAllowedSession(t, m, "agent-err")

	err := m.RouteMessage(AgentUserMessagePayload{
		SessionID: session.ID,
		Message:   UserMessage{Type: UserMessageTypeMessage, Content: "ping"},
	})
	if err == nil {
		t.Fatal("expected error from RouteMessage when policy executor fails")
	}
	if session.ExternalCancelled() {
		t.Error("session must remain alive on transient policy executor error")
	}
}

// TestRouteMessage_EndpointSwappedMidSessionUsesFreshPolicy is the
// reload-mid-session test. It models the file watcher recreating the
// endpoint with a stricter policy after the session has already started,
// then sending a follow-up message and verifying the NEW (deny) executor
// is what gates it.
func TestRouteMessage_EndpointSwappedMidSessionUsesFreshPolicy(t *testing.T) {
	allowExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{Allowed: true}}, nil
		},
	}
	registry := NewEndpointRegistry()
	ep := newAgentEndpointWithPolicy("agent-swap", allowExec)
	if err := registry.Register(ep); err != nil {
		t.Fatal(err)
	}
	m := newSilentManager(t, registry)

	session := startAllowedSession(t, m, "agent-swap")

	// Simulate provider.handleReload: build a brand-new endpoint with a
	// stricter policy executor and ReplaceFileBased it into the registry.
	denyExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{
				Allowed:    false,
				PolicyName: "new_strict_policy",
				Reason:     "reloaded with deny rule",
			}}, nil
		},
	}
	newEp := newAgentEndpointWithPolicy("agent-swap", denyExec)
	registry.ReplaceFileBased([]*Endpoint{newEp})

	err := m.RouteMessage(AgentUserMessagePayload{
		SessionID: session.ID,
		Message:   UserMessage{Type: UserMessageTypeMessage, Content: "ping"},
	})
	if err == nil {
		t.Fatal("expected denial from the reloaded endpoint")
	}

	events := drainSendCh(t, session, 500*time.Millisecond)
	var foundReloadedReason bool
	for _, ev := range events {
		if ev.EventType != EventTypeAgentPolicyDenied {
			continue
		}
		var data struct {
			PolicyName string `json:"policy_name"`
		}
		if err := json.Unmarshal(ev.Data, &data); err != nil {
			continue
		}
		if data.PolicyName == "new_strict_policy" {
			foundReloadedReason = true
		}
	}
	if !foundReloadedReason {
		t.Error("expected policy_denied event to reference the reloaded policy name")
	}
}

// TestRouteMessage_EndpointRemovedMidSessionFailsCleanly: if the endpoint is
// deleted from disk while a session is running, the next user_message must
// fail loudly via agent.policy_denied (rather than silently dropping into a
// full channel) so the caller knows to stop sending.
func TestRouteMessage_EndpointRemovedMidSessionFailsCleanly(t *testing.T) {
	policyExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{Allowed: true}}, nil
		},
	}
	registry := NewEndpointRegistry()
	ep := newAgentEndpointWithPolicy("agent-rm", policyExec)
	if err := registry.Register(ep); err != nil {
		t.Fatal(err)
	}
	m := newSilentManager(t, registry)

	session := startAllowedSession(t, m, "agent-rm")
	if !registry.Remove("agent-rm") {
		t.Fatal("Remove should succeed")
	}

	err := m.RouteMessage(AgentUserMessagePayload{
		SessionID: session.ID,
		Message:   UserMessage{Type: UserMessageTypeMessage, Content: "ping"},
	})
	if err == nil {
		t.Fatal("expected error when endpoint is no longer registered")
	}
	if !session.ExternalCancelled() {
		t.Error("session should be cancelled when endpoint is removed")
	}
}

// TestRouteMessage_PaymentRequiredMidSessionEmitsEventAndCancels verifies the
// transaction-policy mid-session payment-required path.
func TestRouteMessage_PaymentRequiredMidSessionEmitsEventAndCancels(t *testing.T) {
	var calls atomic.Int32
	policyExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			n := calls.Add(1)
			if n == 1 {
				return &ExecutorOutput{PolicyResult: &PolicyResultOutput{Allowed: true}}, nil
			}
			// Mid-session, simulate a transaction policy demanding payment
			// for the next prompt.
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{
				Pending:    true,
				PolicyName: "transaction_xrp",
				Metadata: map[string]any{
					"payment_challenge": `Payment id="abc", amount="1"`,
					"payment_amount":    "1",
				},
			}}, nil
		},
	}
	registry := NewEndpointRegistry()
	ep := newAgentEndpointWithPolicy("agent-pay", policyExec)
	if err := registry.Register(ep); err != nil {
		t.Fatal(err)
	}
	m := newSilentManager(t, registry)

	session := startAllowedSession(t, m, "agent-pay")

	err := m.RouteMessage(AgentUserMessagePayload{
		SessionID: session.ID,
		Message:   UserMessage{Type: UserMessageTypeMessage, Content: "expensive prompt"},
	})
	if err == nil {
		t.Fatal("expected payment_required error from RouteMessage")
	}
	if !session.ExternalCancelled() {
		t.Error("session should be cancelled on mid-session payment_required")
	}

	events := drainSendCh(t, session, 500*time.Millisecond)
	var sawPaymentRequired bool
	for _, ev := range events {
		if ev.EventType == EventTypeAgentPaymentRequired {
			sawPaymentRequired = true
		}
	}
	if !sawPaymentRequired {
		t.Error("expected agent.payment_required event on session.sendCh")
	}
}

// TestRouteMessage_PassesActualUserContentToPolicy guards the contract that
// prompt_filter / token_limit policies receive the real message content
// rather than the placeholder.
func TestRouteMessage_PassesActualUserContentToPolicy(t *testing.T) {
	var seen sync.Map // call # -> Message content
	var calls atomic.Int32
	policyExec := &mockExecutor{
		executeFunc: func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			n := calls.Add(1)
			if len(input.Messages) > 0 {
				seen.Store(int(n), input.Messages[0].Content)
			}
			return &ExecutorOutput{PolicyResult: &PolicyResultOutput{Allowed: true}}, nil
		},
	}
	registry := NewEndpointRegistry()
	ep := newAgentEndpointWithPolicy("agent-content", policyExec)
	if err := registry.Register(ep); err != nil {
		t.Fatal(err)
	}
	m := newSilentManager(t, registry)

	session := startAllowedSession(t, m, "agent-content")
	go func() {
		for {
			if _, err := session.Receive(); err != nil {
				return
			}
		}
	}()

	if err := m.RouteMessage(AgentUserMessagePayload{
		SessionID: session.ID,
		Message:   UserMessage{Type: UserMessageTypeMessage, Content: "the actual prompt"},
	}); err != nil {
		t.Fatalf("RouteMessage: %v", err)
	}

	// Start passed the initial prompt; the follow-up should pass its own content.
	if got, _ := seen.Load(1); got != "hello" {
		t.Errorf("StartSession should pass initial prompt; got %v", got)
	}
	if got, _ := seen.Load(2); got != "the actual prompt" {
		t.Errorf("RouteMessage should pass real user content; got %v", got)
	}
}
