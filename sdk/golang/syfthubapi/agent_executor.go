package syfthubapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
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

	// routingRecorder, when non-nil, captures a routing row for every pending
	// policy notice that carries a manual_review handle. It lets the host
	// later deliver the resolution back to the original caller via the
	// durable resolution-inbox path (manualreview package). nil-safe: when
	// no recorder is configured the executor still surfaces the notice,
	// just without the durable-delivery side-effect.
	routingRecorder manualreview.RoutingRecorder

	// gate, when non-nil, materializes an x402 challenge spec into a
	// canonical mppx payment_challenge before emitPending surfaces it as
	// an agent.payment_required event. nil-safe: pending notices that do
	// not carry a spec are unaffected.
	gate MppxGate
}

// AgentExecutorConfig holds the optional dependencies an AgentExecutor can
// be constructed with. Keeping these in a struct rather than positional args
// lets new optional plumbing (like routingRecorder) land without churning
// every caller.
type AgentExecutorConfig struct {
	Logger          *slog.Logger
	RoutingRecorder manualreview.RoutingRecorder
}

// NewAgentExecutor creates an AgentExecutor that gates inner with the policy
// chain carried by pol. pol is a policy-running Executor — it injects the
// endpoint's policy configs and store config into each invocation.
//
// The signature is preserved for backwards compatibility; the new optional
// plumbing (routing recorder) is set after construction via SetRoutingRecorder
// or — preferred — through NewAgentExecutorWithConfig.
func NewAgentExecutor(inner AgentHandler, pol Executor, slug string, logger *slog.Logger) *AgentExecutor {
	if logger == nil {
		logger = slog.Default()
	}
	return &AgentExecutor{inner: inner, policyExecutor: pol, slug: slug, logger: logger}
}

// NewAgentExecutorWithConfig is the preferred constructor for callers that
// want to wire the routing recorder at build time. Falls back to slog.Default
// when cfg.Logger is nil.
func NewAgentExecutorWithConfig(inner AgentHandler, pol Executor, slug string, cfg AgentExecutorConfig) *AgentExecutor {
	a := NewAgentExecutor(inner, pol, slug, cfg.Logger)
	a.routingRecorder = cfg.RoutingRecorder
	return a
}

// SetRoutingRecorder installs (or replaces) the recorder. Safe to call
// before Handler() is invoked; not safe to swap mid-session. Used by paths
// that build the executor before the recorder is ready.
func (a *AgentExecutor) SetRoutingRecorder(r manualreview.RoutingRecorder) {
	a.routingRecorder = r
}

// SetMppxGate installs (or replaces) the x402 mppx gate. Safe to call before
// Handler() is invoked; not safe to swap mid-session.
func (a *AgentExecutor) SetMppxGate(g MppxGate) {
	a.gate = g
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
	// The credential supplied in the session_start envelope pays for THIS
	// turn only; we move it off the session afterwards so a subsequent turn
	// cannot replay it. x402_pay_per_request is per-request, not per-session.
	initialCredential := outer.PaymentCredential
	outer.PaymentCredential = ""
	if outer.InitialPrompt != "" {
		if outcome := a.gateTurn(ctx, outer, outer.InitialPrompt, initialCredential); outcome != turnGateProceed {
			// Denied or pending — the verdict event was already sent.
			// We do not reprompt on the initial prompt because the consumer
			// either restarts the session (payment) or sees the block notice
			// and is in a terminal state regardless.
			return nil
		}
	}

	// Spawn the raw agent runtime against a private inner session.
	// AttachmentDir is intentionally omitted — relaying attachments through
	// the policy boundary is a follow-up; under policy v1 agents do not
	// exchange attachments.
	//
	// The inner ID uses an underscore (not a slash) as the suffix separator:
	// containermode/agent_handler.go's HTTP/SSE routes embed the session id
	// as a URL path segment ("/session/<id>/events" expects 3 segments).
	inner := NewAgentSession(ctx, AgentSessionParams{
		ID:           outer.ID + "_inner",
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

// turnGateOutcome captures what happened in a pre-check so relayInbound can
// decide whether to reprompt the user. A blocked verdict (hard deny) means
// the user must change their input — reprompt. A payment-required pending
// verdict means the consumer's chat hook auto-retries with a credential —
// reprompting would just show a misleading "send a different message"
// banner mid-flight.
type turnGateOutcome int

const (
	turnGateProceed        turnGateOutcome = iota // verdict allowed: handler may run
	turnGateBlocked                               // hard deny: caller should reprompt
	turnGatePaymentPending                        // payment_required: caller must NOT reprompt
	turnGateOtherPending                          // any other pending (e.g. manual_review hold)
)

// gateTurn pre-checks one user message through the policy chain. It returns
// the outcome so the caller can decide how to proceed.
//
// credential is the wire-format mppx payment credential for THIS turn (empty
// for unpaid turns). Carried as a parameter rather than read from the session
// so each turn can present a distinct credential — pay-per-request, not
// pay-per-session. Threaded into checkPre's ExecutorInput so the mppx gate
// can verify it before the Python policy runs.
func (a *AgentExecutor) gateTurn(ctx context.Context, outer *AgentSession, userText, credential string) turnGateOutcome {
	verdict, err := a.checkPre(ctx, outer, userText, credential)
	if err != nil {
		// Fail closed and tell the user — a broken policy check must not
		// silently let the request through or end with no message.
		a.logger.Error("[AGENT-POLICY] pre-check failed", "slug", a.slug, "error", err)
		a.sendPolicyNotice(outer, policyNotice{
			Status: policyStatusBlocked,
			Phase:  PolicyPhasePre,
			Reason: "the policy check could not be completed — check the endpoint's policy configuration",
		})
		return turnGateBlocked
	}
	if a.applyVerdict(outer, verdict) {
		return turnGateProceed
	}
	if verdict != nil && verdict.Pending {
		if _, hasSpec := verdict.Metadata["x402_challenge_spec"]; hasSpec {
			return turnGatePaymentPending
		}
		if _, hasChallenge := PaymentChallengeFromMetadata(verdict.Metadata); hasChallenge {
			return turnGatePaymentPending
		}
		return turnGateOtherPending
	}
	return turnGateBlocked
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

		switch a.gateTurn(ctx, outer, msg.Content, msg.PaymentCredential) {
		case turnGateProceed:
			// fall through to deliverInbound below
		case turnGatePaymentPending:
			// The consumer's chat hook auto-handles payment_required: it
			// signs a credential and resends the SAME content via
			// SendMessageWithCredential. Reprompting here would surface a
			// misleading "please send a different message" mid-flight,
			// suppress the thinking indicator, and confuse the user.
			continue
		case turnGateBlocked, turnGateOtherPending:
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
		reviewID := metadataString(out.PolicyResult.Metadata, metadataReviewIDKey)
		a.captureManualReviewRouting(outer, reviewID)
		a.sendPolicyNotice(outer, policyNotice{
			Status:     policyStatusPending,
			Phase:      PolicyPhasePost,
			PolicyName: out.PolicyResult.PolicyName,
			Reason:     delivered,
			ReviewID:   reviewID,
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
//
// We pass the FULL conversation transcript (prior turns + the just-delivered
// user message) — not just the new user text — so the policy runner stores
// real context against the held request. The host's manual-review UI reads
// manual_reviews.input verbatim, and a one-line snapshot of "user N just
// said X" with no preceding context makes long threads impossible to review.
// outer.Transcript() already returns the right sequence: seeded history from
// session_start plus user messages appended by DeliverMessage plus assistant
// messages appended by Send. The current user turn has already been
// DeliverMessage'd by the bridge before we get here.
func (a *AgentExecutor) checkPre(
	ctx context.Context, outer *AgentSession, userText, credential string,
) (*PolicyResultOutput, error) {
	in := a.baseInput(outer)
	in.PolicyPhase = PolicyPhasePre
	in.Messages = transcriptForPolicy(outer, userText)
	in.PaymentCredential = credential

	// If a credential was supplied AND a mppx gate is wired, verify it BEFORE
	// the Python policy runs. PreVerify populates in.Context.Metadata with
	// payment_verified=true, payment_challenge_id, payment_nonce, and
	// payment_signed_tx_hex (the unbroadcast raw tx, used by SettleAfterHandler
	// once the handler succeeds). The Python x402 policy then short-circuits
	// to allow on round 2 instead of issuing a fresh challenge.
	//
	// A verification failure is logged but not surfaced as an error — the
	// Python policy will see no payment_verified flag and return a fresh
	// challenge, which the caller can pay and retry. This matches how the
	// model/data_source processor handles the same failure mode.
	if a.gate != nil && in.PaymentCredential != "" {
		if in.Context.Metadata == nil {
			in.Context.Metadata = map[string]any{}
		}
		if err := a.gate.PreVerify(ctx, in.PaymentCredential, in.Context.Metadata); err != nil {
			a.logger.Warn("[AGENT-POLICY] mppx PreVerify failed; policy will issue fresh challenge",
				"slug", a.slug, "error", err)
		}
	}

	out, err := a.runPolicy(ctx, in)
	if err != nil {
		return nil, err
	}
	outer.RecordPolicyResult(out.PolicyResult)
	// Stash the verify-time metadata on the session so checkPost can reuse
	// it (and so SettleAfterHandler can find payment_signed_tx_hex after the
	// handler returns). The session-scoped map is a turn-local channel
	// between checkPre and the post-handler hook in handleReply.
	outer.setLastTurnMetadata(in.Context.Metadata)
	return out.PolicyResult, nil
}

// checkPost runs the post-execution chain against the agent's reply.
//
// As with checkPre, in.Messages carries the full transcript context — but
// NOT the assistant reply being checked. The reply lives in in.Output, which
// is what the post-execution policies (manual_review included) actually
// evaluate against. The transcript ends at the user message that prompted
// this reply so manual_reviews.input is the conversation up to (but not
// including) the assistant turn that was held.
func (a *AgentExecutor) checkPost(
	ctx context.Context, outer *AgentSession, userText, reply string,
) (*ExecutorOutput, error) {
	in := a.baseInput(outer)
	in.PolicyPhase = PolicyPhasePost
	in.Messages = transcriptForPolicy(outer, userText)
	in.Output, _ = json.Marshal(map[string]any{"response": reply})

	// Carry the per-turn metadata populated by checkPre's PreVerify forward
	// into the post phase so x402's post_execute can find
	// payment_challenge_id (the row key it updates). If the gate is wired
	// and a credential was supplied, also run SettleAfterHandler here — the
	// handler has just succeeded, so the held signed tx can be broadcast
	// and the resulting payment_receipt / payment_status surfaced to the
	// post-execute policy chain.
	if turnMeta := outer.LastTurnMetadata(); turnMeta != nil {
		if in.Context.Metadata == nil {
			in.Context.Metadata = turnMeta
		} else {
			for k, v := range turnMeta {
				if _, exists := in.Context.Metadata[k]; !exists {
					in.Context.Metadata[k] = v
				}
			}
		}
	}
	if a.gate != nil && in.Context.Metadata != nil {
		if _, settle := in.Context.Metadata["payment_signed_tx_hex"]; settle {
			if err := a.gate.SettleAfterHandler(ctx, in.Context.Metadata); err != nil {
				a.logger.Warn("[AGENT-POLICY] mppx SettleAfterHandler failed; post_execute will record failure",
					"slug", a.slug, "error", err)
			}
		}
	}

	out, err := a.runPolicy(ctx, in)
	if err != nil {
		return nil, err
	}
	outer.RecordPolicyResult(out.PolicyResult)
	return out, nil
}

// transcriptForPolicy returns the conversation the policy runner should see
// for this turn. It prefers outer.Transcript() — which already accumulates
// the seeded history + user/assistant messages — but defends against two
// race-y states: an empty transcript (the bridge has not yet appended the
// just-delivered user text), and a transcript whose tail does not match
// userText (an external Send / DeliverMessage ordering edge case). In both
// cases we synthesise / fix up the tail so the policy sees exactly
// "[...prior, {user, userText}]".
//
// A transcript that DOES end with userText (the normal path) is returned
// unchanged — the user message has already been recorded by DeliverMessage.
func transcriptForPolicy(outer *AgentSession, userText string) []Message {
	t := outer.Transcript()
	if userText == "" {
		return t
	}
	if n := len(t); n > 0 {
		last := t[n-1]
		if last.Role == "user" && last.Content == userText {
			return t
		}
	}
	return append(t, Message{Role: "user", Content: userText})
}

// baseInput builds the common ExecutorInput. The policy-running Executor
// injects Policies / Store / HandlerPath / WorkDir; AgentExecutor only
// supplies the per-turn input. The wire shape is "model" because agents are
// parsed/formatted by ModelCodec, while the context records the true type.
func (a *AgentExecutor) baseInput(outer *AgentSession) *ExecutorInput {
	// PaymentCredential is intentionally NOT copied from the session — x402
	// is per-request, so each turn's credential is supplied as a parameter
	// to checkPre and threaded onto the ExecutorInput there. Reading it
	// from the session would let one turn's payment cover every subsequent
	// turn until session end (the bug observed before this refactor).
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
//
// When v.Metadata carries an x402_challenge_spec (the new
// X402PayPerRequestPolicy round 1) and a gate is configured, BuildChallenge
// is invoked first to materialize the canonical mppx payment_challenge in
// place — after which the existing PaymentChallengeFromMetadata branch
// emits the agent.payment_required as usual.
func (a *AgentExecutor) emitPending(outer *AgentSession, phase string, v *PolicyResultOutput) {
	if spec, ok := v.Metadata["x402_challenge_spec"].(map[string]any); ok && a.gate != nil {
		if err := a.gate.BuildChallenge(outer.Context(), spec, v.Metadata); err != nil {
			a.logger.Error("[AGENT-POLICY] failed to build x402 challenge",
				"slug", a.slug, "session_id", outer.ID, "error", err)
			// Fall through — without payment_challenge in metadata the
			// next branch will not fire and we'll emit a plain pending
			// notice so the user at least sees that the turn was held.
		}
	}
	if challenge, ok := PaymentChallengeFromMetadata(v.Metadata); ok {
		_ = outer.SendPaymentRequired(v.PolicyName, challenge, CopyPaymentMetadata(v.Metadata))
		return
	}
	reviewID := metadataString(v.Metadata, metadataReviewIDKey)
	a.captureManualReviewRouting(outer, reviewID)
	a.sendPolicyNotice(outer, policyNotice{
		Status:     policyStatusPending,
		Phase:      phase,
		PolicyName: v.PolicyName,
		Reason:     v.Reason,
		ReviewID:   reviewID,
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

// captureManualReviewRouting persists the metadata the host needs to deliver a
// manual-review resolution back to the original caller hours or days after the
// session ends. It is best-effort: a nil recorder, a missing review_id, or a
// recorder error are logged and otherwise ignored — the pending notice still
// surfaces. Capture must precede the notice surfacing so a crash between the
// two leaves the routing row present rather than orphaning the caller.
//
// CallerPublicKeyB64 is the prerequisite — without it the host has no way to
// derive a resolution cipher. When the session arrived through a path that
// doesn't carry it (e.g. HTTP transport, in-process tests), the row would be
// undeliverable, so we skip capture and the caller falls back to the existing
// "manual status override" path on their side.
func (a *AgentExecutor) captureManualReviewRouting(outer *AgentSession, reviewID string) {
	if reviewID == "" {
		return
	}
	if a.routingRecorder == nil {
		// At info level so a misconfiguration (e.g. recorder factory not
		// wired into the provider for one of the agent paths) is loud rather
		// than silent. Phase 1 of this feature shipped with subprocess and
		// container-mode wired in two different places — easy to forget one.
		a.logger.Info("[AGENT-POLICY] manual-review routing recorder not configured — resolution will not be deliverable for this review",
			"slug", a.slug, "session_id", outer.ID, "review_id", reviewID)
		return
	}
	if outer.CallerPublicKeyB64 == "" {
		a.logger.Info("[AGENT-POLICY] skipping routing capture — no caller pubkey on session (HTTP transport?)",
			"slug", a.slug, "session_id", outer.ID, "review_id", reviewID)
		return
	}
	if outer.User == nil || outer.User.Username == "" {
		a.logger.Warn("[AGENT-POLICY] skipping routing capture — session has no authenticated user",
			"slug", a.slug, "session_id", outer.ID, "review_id", reviewID)
		return
	}
	row := manualreview.Routing{
		ReviewID:        reviewID,
		CallerUsername:  outer.User.Username,
		CallerPubkeyB64: outer.CallerPublicKeyB64,
		InboxSubject:    manualreview.InboxSubjectFor(outer.User.Username),
		SessionID:       outer.ID,
		PeerChannel:     outer.CallerReplyTo,
		CapturedAt:      time.Now().UTC().Format(manualreview.ISOMicroLayout),
	}
	if err := a.routingRecorder.Record(row); err != nil {
		// A capture failure must not block the user from learning the request
		// was held — log and continue. The resolution can still be set
		// manually on the caller side; only the durable-delivery path is lost.
		a.logger.Error("[AGENT-POLICY] failed to record manual-review routing",
			"slug", a.slug, "review_id", reviewID, "error", err)
		return
	}
	a.logger.Info("[AGENT-POLICY] recorded manual-review routing",
		"slug", a.slug, "review_id", reviewID,
		"caller", outer.User.Username, "session_id", outer.ID)
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
