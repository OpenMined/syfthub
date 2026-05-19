package syfthubapi

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

// fakeExecutor is a scripted policy Executor for AgentExecutor tests.
type fakeExecutor struct {
	pre  *PolicyResultOutput                     // verdict returned for PolicyPhase=="pre"
	post func(in *ExecutorInput) *ExecutorOutput // response for PolicyPhase=="post"
}

func (f *fakeExecutor) Execute(_ context.Context, in *ExecutorInput) (*ExecutorOutput, error) {
	if in.PolicyPhase == PolicyPhasePre {
		if f.pre == nil {
			// nil pre verdict simulates a policy-runner error (no verdict).
			return &ExecutorOutput{
				Success: false, ErrorType: "PolicyFactoryError", Error: "policy misconfigured",
			}, nil
		}
		return &ExecutorOutput{Success: f.pre.Allowed, PolicyResult: f.pre}, nil
	}
	return f.post(in), nil
}

func (f *fakeExecutor) Close() error { return nil }

// allowPost echoes the supplied output back unchanged (policies passed).
func allowPost(in *ExecutorInput) *ExecutorOutput {
	return &ExecutorOutput{
		Success:      true,
		Result:       in.Output,
		PolicyResult: &PolicyResultOutput{Allowed: true},
	}
}

// runExecutor starts inner under an AgentExecutor, delivers any follow-up
// msgs, and returns every event the caller-facing session emitted.
func runExecutor(t *testing.T, fe *fakeExecutor, inner AgentHandler, prompt string, msgs ...UserMessage) []AgentEventPayload {
	t.Helper()
	outer := NewAgentSession(context.Background(), AgentSessionParams{
		ID:     "test",
		Prompt: prompt,
		User:   &UserContext{Username: "alice"},
	})
	ax := NewAgentExecutor(inner, fe, "ep", nil)
	outer.RunHandler(ax.Handler())
	for _, m := range msgs {
		outer.DeliverMessage(m)
	}
	return drainSendCh(t, outer, time.Second)
}

func hasEvent(evs []AgentEventPayload, eventType string) bool {
	for _, ev := range evs {
		if ev.EventType == eventType {
			return true
		}
	}
	return false
}

func firstContent(evs []AgentEventPayload, eventType string) string {
	for _, ev := range evs {
		if ev.EventType == eventType {
			return contentOfMessage(ev)
		}
	}
	return ""
}

// firstPolicyNotice returns the structured `policy` object of the first
// agent.message event that carries one, or nil if none do.
func firstPolicyNotice(evs []AgentEventPayload) *policyNotice {
	for _, ev := range evs {
		if ev.EventType != EventTypeAgentMessage {
			continue
		}
		var d struct {
			Policy *policyNotice `json:"policy"`
		}
		if json.Unmarshal(ev.Data, &d) == nil && d.Policy != nil {
			return d.Policy
		}
	}
	return nil
}

// A — policies pass: the agent's reply is delivered unchanged.
func TestAgentExecutor_AllowsReplyThrough(t *testing.T) {
	fe := &fakeExecutor{pre: &PolicyResultOutput{Allowed: true}, post: allowPost}
	inner := func(_ context.Context, s *AgentSession) error {
		return s.Send(agentMessageEvent("the real reply"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	if got := firstContent(evs, EventTypeAgentMessage); got != "the real reply" {
		t.Errorf("agent.message content = %q, want %q", got, "the real reply")
	}
	if !hasEvent(evs, EventTypeSessionCompleted) {
		t.Error("expected a single session.completed terminal event")
	}
}

// B — a post policy that substitutes the reply body WITHOUT setting the
// pending flag is still surfaced as a pending notice: the user is no longer
// seeing the agent's own answer, and the real reply must not leak. This is the
// manual_review case where the policy runner does not set Pending.
func TestAgentExecutor_PostSubstitutionBecomesPendingNotice(t *testing.T) {
	fe := &fakeExecutor{
		pre: &PolicyResultOutput{Allowed: true},
		post: func(_ *ExecutorInput) *ExecutorOutput {
			return &ExecutorOutput{
				Success: true,
				Result:  json.RawMessage(`"Request submitted to manual review"`),
				// Allowed, and Pending intentionally NOT set — detection must
				// fall back to the body no longer matching the agent's reply.
				// metadata carries the manual-review handle (as policy_manager
				// reports it) so the notice can surface a trackable review_id.
				PolicyResult: &PolicyResultOutput{
					Allowed:  true,
					Metadata: map[string]any{"review_id": "fab1cef00d12"},
				},
			}
		},
	}
	inner := func(_ context.Context, s *AgentSession) error {
		return s.Send(agentMessageEvent("the real reply"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	n := firstPolicyNotice(evs)
	if n == nil {
		t.Fatal("a substituted reply must surface a structured policy notice")
	}
	if n.Status != policyStatusPending {
		t.Errorf("notice status = %q, want %q", n.Status, policyStatusPending)
	}
	if n.Reason != "Request submitted to manual review" {
		t.Errorf("notice reason = %q, want the substituted text", n.Reason)
	}
	if n.ReviewID != "fab1cef00d12" {
		t.Errorf("notice review_id = %q, want it plumbed from PolicyResult.metadata", n.ReviewID)
	}
	if got := firstContent(evs, EventTypeAgentMessage); strings.Contains(got, "the real reply") {
		t.Errorf("the real agent reply leaked: %q", got)
	}
}

// C — a post policy denies the reply: the real reply is blocked and the user
// instead receives a message explaining the block.
func TestAgentExecutor_PostDenyBlocksReply(t *testing.T) {
	fe := &fakeExecutor{
		pre: &PolicyResultOutput{Allowed: true},
		post: func(_ *ExecutorInput) *ExecutorOutput {
			return &ExecutorOutput{
				Success: false,
				PolicyResult: &PolicyResultOutput{
					Allowed: false, PolicyName: "pf", Reason: "matched a forbidden pattern",
				},
			}
		},
	}
	inner := func(_ context.Context, s *AgentSession) error {
		return s.Send(agentMessageEvent("a reply that should be blocked"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	// The block is surfaced as an agent.message carrying the reason; the
	// real (blocked) reply must not reach the user.
	msg := firstContent(evs, EventTypeAgentMessage)
	if msg == "" {
		t.Fatal("expected a policy-block agent.message")
	}
	if strings.Contains(msg, "a reply that should be blocked") {
		t.Error("the blocked reply leaked to the user")
	}
	if !strings.Contains(msg, "pf") || !strings.Contains(msg, "matched a forbidden pattern") {
		t.Errorf("block message = %q, should name the policy and reason", msg)
	}
}

// D — a pre policy denies the initial prompt: the agent never runs.
func TestAgentExecutor_PreDenyNeverRunsAgent(t *testing.T) {
	fe := &fakeExecutor{
		pre:  &PolicyResultOutput{Allowed: false, PolicyName: "ag", Reason: "access denied"},
		post: allowPost,
	}
	ranAgent := false
	inner := func(_ context.Context, s *AgentSession) error {
		ranAgent = true
		return s.Send(agentMessageEvent("should never happen"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	if ranAgent {
		t.Error("inner agent must not run when the pre-check denies the prompt")
	}
	msg := firstContent(evs, EventTypeAgentMessage)
	if msg == "" {
		t.Fatal("expected a policy-block agent.message explaining the denial")
	}
	if !strings.Contains(msg, "ag") || !strings.Contains(msg, "access denied") {
		t.Errorf("block message = %q, should name the policy and reason", msg)
	}
}

// E — streamed tokens are suppressed; only the post-checked message is sent.
func TestAgentExecutor_SuppressesTokens(t *testing.T) {
	fe := &fakeExecutor{pre: &PolicyResultOutput{Allowed: true}, post: allowPost}
	inner := func(_ context.Context, s *AgentSession) error {
		_ = s.Send(AgentEventPayload{
			EventType: EventTypeAgentToken,
			Data:      json.RawMessage(`{"token":"hel"}`),
		})
		return s.Send(agentMessageEvent("hello"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	if hasEvent(evs, EventTypeAgentToken) {
		t.Error("agent.token events must be suppressed under policy")
	}
	if got := firstContent(evs, EventTypeAgentMessage); got != "hello" {
		t.Errorf("agent.message content = %q, want %q", got, "hello")
	}
}

// F — a mid-session follow-up message is pre-checked, then delivered to the
// agent (no initial prompt, so the agent waits for input).
func TestAgentExecutor_InboundMessagePreChecked(t *testing.T) {
	fe := &fakeExecutor{pre: &PolicyResultOutput{Allowed: true}, post: allowPost}
	inner := func(_ context.Context, s *AgentSession) error {
		msg, err := s.Receive()
		if err != nil {
			return err
		}
		return s.Send(agentMessageEvent("echo:" + msg.Content))
	}
	evs := runExecutor(t, fe, inner, "",
		UserMessage{Type: UserMessageTypeMessage, Content: "follow up"})

	if got := firstContent(evs, EventTypeAgentMessage); got != "echo:follow up" {
		t.Errorf("agent.message content = %q, want %q", got, "echo:follow up")
	}
}

// G — a post-check runner error (no verdict, e.g. a misconfigured policy)
// surfaces a block message instead of a silent empty reply.
func TestAgentExecutor_PostRunnerErrorSurfaced(t *testing.T) {
	fe := &fakeExecutor{
		pre: &PolicyResultOutput{Allowed: true},
		post: func(_ *ExecutorInput) *ExecutorOutput {
			// success=false with NO PolicyResult — what the runner returns
			// for a PolicyFactoryError / unhandled exception.
			return &ExecutorOutput{
				Success: false, ErrorType: "PolicyFactoryError", Error: "policy misconfigured",
			}
		},
	}
	inner := func(_ context.Context, s *AgentSession) error {
		return s.Send(agentMessageEvent("the real reply"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	msg := firstContent(evs, EventTypeAgentMessage)
	if msg == "" {
		t.Fatal("a policy-runner error must surface a message, not a silent empty reply")
	}
	if strings.Contains(msg, "the real reply") {
		t.Error("the un-reviewed reply leaked when the policy check errored")
	}
	if !strings.Contains(strings.ToLower(msg), "blocked") {
		t.Errorf("block message = %q, should explain the request was blocked", msg)
	}
}

// H — a pre-check runner error fails closed: the agent never runs and the
// user gets a block message.
func TestAgentExecutor_PreRunnerErrorSurfaced(t *testing.T) {
	fe := &fakeExecutor{pre: nil, post: allowPost} // nil pre → runner error
	ranAgent := false
	inner := func(_ context.Context, s *AgentSession) error {
		ranAgent = true
		return s.Send(agentMessageEvent("should not happen"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	if ranAgent {
		t.Error("the agent must not run when the pre-check errors")
	}
	msg := firstContent(evs, EventTypeAgentMessage)
	if msg == "" {
		t.Fatal("a pre-check runner error must surface a block message")
	}
	if !strings.Contains(strings.ToLower(msg), "blocked") {
		t.Errorf("block message = %q, should explain the request was blocked", msg)
	}
}

// I — a pre-check denial carries a structured `policy` notice so the client
// can render a distinct blocked card rather than a plain agent reply.
func TestAgentExecutor_PreDenyCarriesPolicyNotice(t *testing.T) {
	fe := &fakeExecutor{
		pre:  &PolicyResultOutput{Allowed: false, PolicyName: "access group", Reason: "not a member"},
		post: allowPost,
	}
	inner := func(_ context.Context, s *AgentSession) error {
		return s.Send(agentMessageEvent("never"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	n := firstPolicyNotice(evs)
	if n == nil {
		t.Fatal("expected a structured policy notice on the agent.message event")
	}
	if n.Status != policyStatusBlocked {
		t.Errorf("notice status = %q, want %q", n.Status, policyStatusBlocked)
	}
	if n.Phase != PolicyPhasePre {
		t.Errorf("notice phase = %q, want %q", n.Phase, PolicyPhasePre)
	}
	if n.PolicyName != "access group" {
		t.Errorf("notice policy_name = %q, want %q", n.PolicyName, "access group")
	}
	if n.Reason != "not a member" {
		t.Errorf("notice reason = %q, want %q", n.Reason, "not a member")
	}
}

// J — a post-check denial carries a `blocked` policy notice tagged to the
// post phase.
func TestAgentExecutor_PostDenyCarriesPolicyNotice(t *testing.T) {
	fe := &fakeExecutor{
		pre: &PolicyResultOutput{Allowed: true},
		post: func(_ *ExecutorInput) *ExecutorOutput {
			return &ExecutorOutput{
				Success: false,
				PolicyResult: &PolicyResultOutput{
					Allowed: false, PolicyName: "pf", Reason: "matched a forbidden pattern",
				},
			}
		},
	}
	inner := func(_ context.Context, s *AgentSession) error {
		return s.Send(agentMessageEvent("blocked reply"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	n := firstPolicyNotice(evs)
	if n == nil {
		t.Fatal("expected a structured policy notice on the agent.message event")
	}
	if n.Status != policyStatusBlocked || n.Phase != PolicyPhasePost {
		t.Errorf("notice = %+v, want blocked/post", n)
	}
}

// K — a policy that allows the turn but flags it pending (manual_review)
// carries a `pending` notice, and the agent's real reply never leaks.
func TestAgentExecutor_PendingReplyCarriesPolicyNotice(t *testing.T) {
	fe := &fakeExecutor{
		pre: &PolicyResultOutput{Allowed: true},
		post: func(_ *ExecutorInput) *ExecutorOutput {
			return &ExecutorOutput{
				Success: true,
				Result:  json.RawMessage(`"Submitted for manual review"`),
				PolicyResult: &PolicyResultOutput{
					Allowed: true, Pending: true, PolicyName: "manual_review",
					Metadata: map[string]any{"review_id": "0a1b2c3d4e5f", "status": "pending"},
				},
			}
		},
	}
	inner := func(_ context.Context, s *AgentSession) error {
		return s.Send(agentMessageEvent("the real reply"))
	}
	evs := runExecutor(t, fe, inner, "hello")

	n := firstPolicyNotice(evs)
	if n == nil {
		t.Fatal("expected a structured policy notice on the agent.message event")
	}
	if n.Status != policyStatusPending {
		t.Errorf("notice status = %q, want %q", n.Status, policyStatusPending)
	}
	if n.PolicyName != "manual_review" {
		t.Errorf("notice policy_name = %q, want %q", n.PolicyName, "manual_review")
	}
	if n.ReviewID != "0a1b2c3d4e5f" {
		t.Errorf("notice review_id = %q, want it plumbed from PolicyResult.metadata", n.ReviewID)
	}
	if got := firstContent(evs, EventTypeAgentMessage); strings.Contains(got, "the real reply") {
		t.Errorf("the real reply leaked into a pending notice: %q", got)
	}
}
