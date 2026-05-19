package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"
)

// policyCheckTimeout caps every per-turn policy evaluation. Long enough to
// absorb a Python policy-runner subprocess spawn under load; short enough to
// fail fast (closed) when the runner is wedged.
const policyCheckTimeout = 30 * time.Second

// AgentExecutor wraps a raw agent AgentHandler so that every conversational
// turn is gated by the policy chain — the inbound user message through the
// pre-execution policies, the agent's reply through the post-execution
// policies — exactly as a model endpoint request is gated by the runner.
//
// It is a decorator: the wrapped (inner) handler runs unchanged against a
// private inner AgentSession, and AgentExecutor relays events between that
// inner session and the transport-facing outer session, invoking the policy
// runner (via an Executor in PolicyPhase mode) at each turn boundary.
//
// Because policy lives in the handler, every path that runs the handler —
// AgentOneShotInvoker (synchronous) and AgentSessionManager (persistent) —
// inherits per-turn pre/post enforcement without path-specific code.
type AgentExecutor struct {
	inner          AgentHandler
	policyExecutor Executor // runs `python -m policy_manager.runner`
	slug           string
	logger         *slog.Logger
}

// NewAgentExecutor creates an AgentExecutor that gates inner with the policy
// chain carried by pol. pol is a policy-running Executor — it injects the
// endpoint's policy configs and store config into each invocation.
func NewAgentExecutor(inner AgentHandler, pol Executor, slug string, logger *slog.Logger) *AgentExecutor {
	if logger == nil {
		logger = slog.Default()
	}
	return &AgentExecutor{inner: inner, policyExecutor: pol, slug: slug, logger: logger}
}

// Handler returns an AgentHandler that runs the wrapped agent with per-turn
// policy enforcement.
func (a *AgentExecutor) Handler() AgentHandler {
	return a.run
}

// turnTracker carries the current turn's user message from the inbound relay
// (which pre-checks it) to the outbound relay (which post-checks the reply
// against it). Guarded because the two relays run on separate goroutines.
type turnTracker struct {
	mu          sync.Mutex
	currentUser string
}

func (t *turnTracker) setUser(s string) {
	t.mu.Lock()
	t.currentUser = s
	t.mu.Unlock()
}

func (t *turnTracker) user() string {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.currentUser
}

// run is the policy-enforcing AgentHandler. It runs against the transport's
// outer session; the raw runtime runs against a private inner session.
func (a *AgentExecutor) run(ctx context.Context, outer *AgentSession) error {
	a.logger.Info("[AGENT-POLICY] agent session start — per-turn policy active",
		"slug", a.slug, "session_id", outer.ID)
	tracker := &turnTracker{currentUser: outer.InitialPrompt}

	// Pre-check turn 1 (the initial prompt) before spawning the agent.
	if outer.InitialPrompt != "" && !a.gateTurn(ctx, outer, outer.InitialPrompt) {
		return nil // denied/pending — the verdict event was already sent
	}

	// Spawn the raw agent runtime against a private inner session.
	// AttachmentDir is intentionally omitted — relaying attachments through
	// the policy boundary is a follow-up; under policy v1 agents do not
	// exchange attachments.
	inner := NewAgentSession(ctx, AgentSessionParams{
		ID:           outer.ID + "/inner",
		Prompt:       outer.InitialPrompt,
		EndpointSlug: outer.EndpointSlug,
		Messages:     outer.Messages,
		Config:       outer.Config,
		User:         outer.User,
		Capabilities: outer.Capabilities,
	})
	inner.RunHandler(a.inner)

	var relays sync.WaitGroup
	relays.Add(2)
	go func() { defer relays.Done(); a.watchCancel(outer, inner) }()
	go func() { defer relays.Done(); a.relayInbound(ctx, outer, inner, tracker) }()

	// Outbound relay runs on this goroutine; it returns when the inner
	// runtime finishes (inner SendCh closes).
	outcome := a.relayOutbound(ctx, outer, inner, tracker)
	a.logger.Info("[AGENT-POLICY] agent session ended",
		"slug", a.slug, "session_id", outer.ID, "error", outcome)

	// Cancel unblocks the inbound relay's outer.Receive(); wait for both
	// relay goroutines to finish before returning so RunHandler cannot close
	// the outer sendCh while relayInbound might still be writing to it.
	outer.Cancel()
	relays.Wait()
	return outcome
}

// gateTurn pre-checks one user message through the policy chain. It returns
// true when the turn may proceed; on a denial, a pending verdict, or a runner
// error it surfaces the appropriate event to the caller and returns false.
func (a *AgentExecutor) gateTurn(ctx context.Context, outer *AgentSession, userText string) bool {
	verdict, err := a.checkPre(ctx, outer, userText)
	if err != nil {
		// Fail closed and tell the user — a broken policy check must not
		// silently let the request through or end with no message.
		a.logger.Error("[AGENT-POLICY] pre-check failed", "slug", a.slug, "error", err)
		a.sendPolicyNotice(outer, policyNotice{
			Status: policyStatusBlocked,
			Phase:  PolicyPhasePre,
			Reason: "the policy check could not be completed — check the endpoint's policy configuration",
		})
		return false
	}
	return a.applyVerdict(outer, verdict)
}

// watchCancel propagates an outer cancellation to the inner session as a
// user-cancel so the runtime reports termination correctly.
func (a *AgentExecutor) watchCancel(outer, inner *AgentSession) {
	select {
	case <-outer.Context().Done():
		inner.CancelByUser()
	case <-inner.Done():
	}
}

// relayInbound forwards outer user messages to the inner runtime, pre-checking
// each conversational message through the policy chain.
func (a *AgentExecutor) relayInbound(
	ctx context.Context, outer, inner *AgentSession, tracker *turnTracker,
) {
	for {
		msg, err := outer.Receive()
		if err != nil {
			return // outer cancelled / session closing
		}

		// Only conversational messages are policy-gated; control signals
		// (user_confirm / user_deny / user_cancel) pass straight through.
		if msg.Type != UserMessageTypeMessage || msg.Content == "" {
			a.deliverInbound(inner, msg)
			continue
		}

		if !a.gateTurn(ctx, outer, msg.Content) {
			a.reprompt(outer)
			continue
		}

		tracker.setUser(msg.Content)
		a.deliverInbound(inner, msg)
	}
}

// deliverInbound hands a message to the inner runtime, logging a drop (recv
// channel full, or the inner handler already returned) rather than discarding
// it silently — a follow-up turn that vanishes with no feedback is worse than
// a logged one.
func (a *AgentExecutor) deliverInbound(inner *AgentSession, msg UserMessage) {
	if !inner.DeliverMessage(msg) {
		a.logger.Warn("[AGENT-POLICY] inbound message dropped — inner session full or closing",
			"slug", a.slug, "type", msg.Type)
	}
}

// relayOutbound forwards inner runtime events to the outer session. The agent's
// reply (agent.message) is post-checked; streamed tokens are suppressed so an
// un-reviewed reply never reaches the user; the inner terminal event is
// consumed and returned as the handler outcome (the outer session's RunHandler
// emits the single terminal event).
func (a *AgentExecutor) relayOutbound(
	ctx context.Context, outer, inner *AgentSession, tracker *turnTracker,
) error {
	for ev := range inner.SendCh() {
		switch ev.EventType {
		case EventTypeAgentToken:
			// Suppressed — the full reply is delivered post-check as
			// agent.message; streaming raw tokens would leak it un-reviewed.
			continue
		case EventTypeSessionCompleted:
			return nil
		case EventTypeSessionFailed:
			return errorFromFailedEvent(ev)
		case EventTypeAgentMessage:
			a.handleReply(ctx, outer, tracker, ev)
		default:
			// thinking / tool_call / tool_result / status / request_input
			// / attachment — forwarded unchanged.
			if err := outer.Send(ev); err != nil {
				a.logger.Warn("[AGENT-POLICY] failed to forward event to caller",
					"slug", a.slug, "type", ev.EventType, "error", err)
			}
		}
	}
	return nil
}

// handleReply post-checks one agent reply and delivers the (possibly
// substituted) result, or a denial.
func (a *AgentExecutor) handleReply(
	ctx context.Context, outer *AgentSession, tracker *turnTracker, ev AgentEventPayload,
) {
	reply := contentOfMessage(ev)
	a.logger.Info("[AGENT-POLICY] agent reply received — post-checking",
		"slug", a.slug, "reply_len", len(reply))

	out, err := a.checkPost(ctx, outer, tracker.user(), reply)
	if err != nil {
		// Fail closed: a failed or verdict-less policy check must not deliver
		// an un-reviewed reply.
		a.logger.Error("[AGENT-POLICY] post-check failed", "slug", a.slug, "error", err)
		a.sendPolicyNotice(outer, policyNotice{
			Status: policyStatusBlocked,
			Phase:  PolicyPhasePost,
			Reason: "the policy check could not be completed — check the endpoint's policy configuration",
		})
		return
	}

	if !out.PolicyResult.Allowed {
		a.logger.Info("[AGENT-POLICY] reply blocked by policy",
			"slug", a.slug, "policy", out.PolicyResult.PolicyName,
			"pending", out.PolicyResult.Pending)
		if out.PolicyResult.Pending {
			a.emitPending(outer, PolicyPhasePost, out.PolicyResult)
		} else {
			a.sendPolicyNotice(outer, policyNotice{
				Status:     policyStatusBlocked,
				Phase:      PolicyPhasePost,
				PolicyName: out.PolicyResult.PolicyName,
				Reason:     out.PolicyResult.Reason,
			})
		}
		return
	}

	// Deliver the reply the post chain produced — unchanged when policies
	// passed, or a placeholder when a policy (e.g. manual_review) substituted.
	delivered := extractContent(out.Result, reply)

	// A policy can allow the turn yet replace the agent's answer — e.g.
	// manual_review swaps in a "submitted for review" placeholder. Detect that
	// two ways: the explicit Pending flag, and — as a fallback, since not every
	// such policy sets the flag — the delivered body no longer matching the
	// agent's actual reply. Either way the user is not seeing the agent's own
	// answer, so surface it as a pending notice rather than a plain reply.
	if out.PolicyResult.Pending || delivered != reply {
		a.logger.Info("[AGENT-POLICY] reply withheld pending policy resolution",
			"slug", a.slug, "policy", out.PolicyResult.PolicyName,
			"pending_flag", out.PolicyResult.Pending)
		a.sendPolicyNotice(outer, policyNotice{
			Status:     policyStatusPending,
			Phase:      PolicyPhasePost,
			PolicyName: out.PolicyResult.PolicyName,
			Reason:     delivered,
			ReviewID:   metadataString(out.PolicyResult.Metadata, metadataReviewIDKey),
		})
		return
	}

	if err := outer.Send(agentMessageEvent(delivered)); err != nil {
		a.logger.Error("[AGENT-POLICY] failed to forward reply to caller",
			"slug", a.slug, "error", err)
		return
	}
	a.logger.Info("[AGENT-POLICY] reply forwarded to caller",
		"slug", a.slug, "delivered_len", len(delivered))
}

// ── policy invocations ───────────────────────────────────────

// runPolicy invokes the policy runner for one turn under the per-turn
// timeout. A missing verdict is folded into an error so every caller fails
// closed instead of treating "no verdict" as "allowed".
func (a *AgentExecutor) runPolicy(ctx context.Context, in *ExecutorInput) (*ExecutorOutput, error) {
	cctx, cancel := context.WithTimeout(ctx, policyCheckTimeout)
	defer cancel()
	out, err := a.policyExecutor.Execute(cctx, in)
	if err != nil {
		return nil, err
	}
	if out.PolicyResult == nil {
		return nil, fmt.Errorf("policy runner produced no verdict (%s): %s",
			out.ErrorType, out.Error)
	}
	return out, nil
}

// checkPre runs the pre-execution chain against a user message.
func (a *AgentExecutor) checkPre(
	ctx context.Context, outer *AgentSession, userText string,
) (*PolicyResultOutput, error) {
	in := a.baseInput(outer)
	in.PolicyPhase = PolicyPhasePre
	in.Messages = []Message{{Role: "user", Content: userText}}
	out, err := a.runPolicy(ctx, in)
	if err != nil {
		return nil, err
	}
	return out.PolicyResult, nil
}

// checkPost runs the post-execution chain against the agent's reply.
func (a *AgentExecutor) checkPost(
	ctx context.Context, outer *AgentSession, userText, reply string,
) (*ExecutorOutput, error) {
	in := a.baseInput(outer)
	in.PolicyPhase = PolicyPhasePost
	in.Messages = []Message{{Role: "user", Content: userText}}
	in.Output, _ = json.Marshal(map[string]any{"response": reply})
	return a.runPolicy(ctx, in)
}

// baseInput builds the common ExecutorInput. The policy-running Executor
// injects Policies / Store / HandlerPath / WorkDir; AgentExecutor only
// supplies the per-turn input. The wire shape is "model" because agents are
// parsed/formatted by ModelCodec, while the context records the true type.
func (a *AgentExecutor) baseInput(outer *AgentSession) *ExecutorInput {
	return buildExecutorInput(
		string(EndpointTypeModel), a.slug, EndpointTypeAgent,
		&RequestContext{User: outer.User},
	)
}

// policyStatus values carried by a policyNotice.
const (
	policyStatusBlocked = "blocked"
	policyStatusPending = "pending"
)

// policyNotice is the structured policy outcome attached to an agent.message
// event. It lets a client render a distinct blocked/pending notice instead of
// a normal agent reply; the message Content remains a human-readable fallback.
type policyNotice struct {
	Status     string `json:"status"`          // policyStatusBlocked | policyStatusPending
	Phase      string `json:"phase,omitempty"` // PolicyPhasePre | PolicyPhasePost
	PolicyName string `json:"policy_name,omitempty"`
	Reason     string `json:"reason,omitempty"`
	// ReviewID is the manual-review handle the caller can use to track a held
	// request — the 12-hex id manual_review records in its manual_reviews
	// table. It originates in PolicyResult.metadata; see metadataReviewIDKey.
	// Empty for blocks and for pending notices that are not a manual-review
	// hold (e.g. a payment challenge surfaces as agent.payment_required).
	ReviewID string `json:"review_id,omitempty"`
}

// metadataReviewIDKey is the PolicyResult.metadata key under which
// manual_review (policy_manager) reports the held request's identifier.
const metadataReviewIDKey = "review_id"

// applyVerdict acts on a pre-check verdict. Returns true when the turn may
// proceed; on deny/pending it emits the appropriate notice and returns false.
func (a *AgentExecutor) applyVerdict(outer *AgentSession, v *PolicyResultOutput) bool {
	if v == nil || v.Allowed {
		return true
	}
	if v.Pending {
		a.emitPending(outer, PolicyPhasePre, v)
		return false
	}
	a.sendPolicyNotice(outer, policyNotice{
		Status:     policyStatusBlocked,
		Phase:      PolicyPhasePre,
		PolicyName: v.PolicyName,
		Reason:     v.Reason,
	})
	return false
}

// emitPending surfaces a pending policy verdict. A pending result carrying a
// payment challenge becomes an agent.payment_required event; otherwise it is a
// pending policy notice (e.g. manual_review without payment) so the user sees
// why the turn did not produce a normal reply.
func (a *AgentExecutor) emitPending(outer *AgentSession, phase string, v *PolicyResultOutput) {
	if challenge, ok := PaymentChallengeFromMetadata(v.Metadata); ok {
		_ = outer.SendPaymentRequired(v.PolicyName, challenge, CopyPaymentMetadata(v.Metadata))
		return
	}
	a.sendPolicyNotice(outer, policyNotice{
		Status:     policyStatusPending,
		Phase:      phase,
		PolicyName: v.PolicyName,
		Reason:     v.Reason,
		ReviewID:   metadataString(v.Metadata, metadataReviewIDKey),
	})
}

// sendPolicyNotice surfaces a policy outcome (a hard block or a pending
// verdict) to the caller as an agent.message carrying a structured policy
// notice. It rides on agent.message — not a dedicated event — because that is
// the one event type rendered end-to-end and recorded in the session
// transcript: a modern client renders the `policy` object as a distinct notice
// card, while the Content sentence remains a fallback for everything else.
func (a *AgentExecutor) sendPolicyNotice(outer *AgentSession, n policyNotice) {
	a.logger.Info("[AGENT-POLICY] surfacing policy notice to caller",
		"slug", a.slug, "status", n.Status, "phase", n.Phase,
		"policy", n.PolicyName, "reason", n.Reason)
	if err := outer.Send(policyNoticeEvent(policyNoticeText(n), n)); err != nil {
		a.logger.Error("[AGENT-POLICY] failed to deliver policy notice",
			"slug", a.slug, "error", err)
	}
}

// policyNoticeText renders the human-readable fallback sentence for a notice —
// shown by clients that don't render the structured `policy` object, and
// recorded in the session transcript.
func policyNoticeText(n policyNotice) string {
	subject := "Request blocked"
	switch {
	case n.Status == policyStatusPending && n.Phase == PolicyPhasePost:
		subject = "The agent's response is pending review"
	case n.Status == policyStatusPending:
		subject = "Your request is pending review"
	case n.Phase == PolicyPhasePost:
		subject = "The agent's response was blocked"
	}
	if n.PolicyName != "" {
		subject += ` by the "` + n.PolicyName + `" policy`
	}
	if n.Reason != "" {
		subject += ": " + n.Reason
	}
	return subject + "."
}

// reprompt re-emits agent.request_input so the user can retry after a denial.
func (a *AgentExecutor) reprompt(outer *AgentSession) {
	data, _ := json.Marshal(map[string]any{"prompt": "Please send a different message."})
	_ = outer.Send(AgentEventPayload{EventType: EventTypeAgentRequestInput, Data: data})
}

// ── helpers ──────────────────────────────────────────────────

// metadataString returns the string at key in a PolicyResult metadata map, or
// "" when the map is nil, the key is absent, or the value is not a string.
// PolicyResultOutput.Metadata is free-form (decoded from the runner's JSON).
func metadataString(m map[string]any, key string) string {
	s, _ := m[key].(string)
	return s
}

// contentOfMessage extracts the content field of an agent.message event.
func contentOfMessage(ev AgentEventPayload) string {
	var d struct {
		Content string `json:"content"`
	}
	_ = json.Unmarshal(ev.Data, &d)
	return d.Content
}

// extractContent normalizes a post-check result body to message text. The
// runner returns either the supplied {"response": ...} object (policies
// passed) or a bare string (a policy substituted the body).
func extractContent(raw json.RawMessage, fallback string) string {
	if len(raw) == 0 {
		return fallback
	}
	var s string
	// A bare JSON string is the substituted body. JSON null also unmarshals
	// into a string without error (leaving it ""), so require a non-empty
	// result here — otherwise fall through to the fallback.
	if err := json.Unmarshal(raw, &s); err == nil && s != "" {
		return s
	}
	var obj struct {
		Response string `json:"response"`
	}
	if err := json.Unmarshal(raw, &obj); err == nil && obj.Response != "" {
		return obj.Response
	}
	return fallback
}

// agentMessageEvent builds a complete agent.message event from reply text.
func agentMessageEvent(content string) AgentEventPayload {
	data, _ := json.Marshal(map[string]any{"content": content, "is_complete": true})
	return AgentEventPayload{EventType: EventTypeAgentMessage, Data: data}
}

// policyNoticeEvent builds an agent.message event carrying a structured policy
// notice. content is the human-readable fallback; the `policy` object lets a
// client render a distinct blocked/pending notice instead of a plain reply.
func policyNoticeEvent(content string, n policyNotice) AgentEventPayload {
	data, _ := json.Marshal(map[string]any{
		"content":     content,
		"is_complete": true,
		"policy":      n,
	})
	return AgentEventPayload{EventType: EventTypeAgentMessage, Data: data}
}

// errorFromFailedEvent reconstructs an error from a session.failed event.
func errorFromFailedEvent(ev AgentEventPayload) error {
	var d struct {
		Error string `json:"error"`
	}
	_ = json.Unmarshal(ev.Data, &d)
	if d.Error == "" {
		return fmt.Errorf("agent session failed")
	}
	return fmt.Errorf("agent session failed: %s", d.Error)
}
