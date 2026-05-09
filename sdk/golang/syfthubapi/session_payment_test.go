package syfthubapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"strings"
	"testing"
)

// newTestSessionManager builds an AgentSessionManager with a discarded logger
// suitable for unit tests.
func newTestSessionManager(t *testing.T) (*AgentSessionManager, *EndpointRegistry) {
	t.Helper()
	registry := NewEndpointRegistry()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	return NewAgentSessionManager(registry, logger, 0), registry
}

// registerAgentEndpoint adds an agent endpoint with the given handler and a
// policy executor whose Execute is supplied by the caller.
func registerAgentEndpoint(
	t *testing.T,
	registry *EndpointRegistry,
	slug string,
	handler AgentHandler,
	policyExec func(ctx context.Context, input *ExecutorInput) (*ExecutorOutput, error),
) *Endpoint {
	t.Helper()
	ep := &Endpoint{
		Slug:    slug,
		Type:    EndpointTypeAgent,
		Enabled: true,
	}
	ep.SetAgentHandler(handler)
	if policyExec != nil {
		ep.SetPolicyExecutor(&mockExecutor{executeFunc: policyExec})
	}
	if err := registry.Register(ep); err != nil {
		t.Fatalf("register endpoint: %v", err)
	}
	return ep
}

// noopAgentHandler is a benign handler that returns immediately without
// emitting any events. Sessions using this handler complete cleanly.
func noopAgentHandler(_ context.Context, _ *AgentSession) error { return nil }

// drainSession blocks until the session's send channel closes, draining all
// emitted events. Used in tests so the goroutine can finish cleanly before
// the test exits.
func drainSession(t *testing.T, session *AgentSession) {
	t.Helper()
	if session == nil {
		return
	}
	for range session.SendCh() {
		// drop
	}
}

// TestStartSession_PaymentCredentialPassed confirms that StartSession reaches
// the policy executor with the user identity intact and accepts a non-empty
// PaymentCredential without erroring. The credential's path from
// reqCtx.PaymentCredential into input.PaymentCredential is owned by
// Endpoint.buildExecutorInput (unit 3) — this test only verifies the agent
// session start does not regress when the field is set.
func TestStartSession_PaymentCredentialPassed(t *testing.T) {
	mgr, registry := newTestSessionManager(t)

	var capturedUserID string
	registerAgentEndpoint(t, registry, "agent-ep", noopAgentHandler,
		func(_ context.Context, input *ExecutorInput) (*ExecutorOutput, error) {
			if input != nil && input.Context != nil {
				capturedUserID = input.Context.UserID
			}
			return &ExecutorOutput{
				Success:      true,
				PolicyResult: &PolicyResultOutput{Allowed: true},
			}, nil
		},
	)

	user := &UserContext{Sub: "user-1", Username: "alice", Email: "a@b"}
	session, err := mgr.StartSession(AgentSessionStartPayload{
		SessionID:         "sess-1",
		Prompt:            "hi",
		EndpointSlug:      "agent-ep",
		PaymentCredential: "Payment xyz",
	}, user)
	if err != nil {
		t.Fatalf("StartSession returned error: %v", err)
	}
	defer drainSession(t, session)

	if capturedUserID != "alice" {
		t.Errorf("ExecutionContext.UserID = %q, want %q", capturedUserID, "alice")
	}
}

func TestStartSession_PaymentRequired_ReturnsTypedError(t *testing.T) {
	mgr, registry := newTestSessionManager(t)

	registerAgentEndpoint(t, registry, "agent-ep", noopAgentHandler,
		func(_ context.Context, _ *ExecutorInput) (*ExecutorOutput, error) {
			return &ExecutorOutput{
				Success: true,
				PolicyResult: &PolicyResultOutput{
					Allowed:    false,
					Pending:    true,
					PolicyName: "transaction",
					Reason:     "payment required",
					Metadata: map[string]any{
						"payment_challenge": `Payment id="abc", realm="syfthub", amount="0.10"`,
						"payment_amount":    "0.10",
						"payment_currency":  "PathUSD",
						"payment_recipient": "0xfeed",
						"challenge_id":      "abc",
						"intent":            "charge",
						// Unsafe key; should not be copied.
						"_secret_nonce": "should-not-leak",
					},
				},
			}, nil
		},
	)

	user := &UserContext{Sub: "u", Username: "alice"}
	_, err := mgr.StartSession(AgentSessionStartPayload{
		SessionID: "s1", EndpointSlug: "agent-ep",
	}, user)

	if err == nil {
		t.Fatal("StartSession should have returned an error")
	}

	var payErr *PaymentRequiredError
	if !errors.As(err, &payErr) {
		t.Fatalf("expected *PaymentRequiredError, got %T: %v", err, err)
	}

	wantChallenge := `Payment id="abc", realm="syfthub", amount="0.10"`
	if payErr.Challenge != wantChallenge {
		t.Errorf("Challenge = %q, want %q", payErr.Challenge, wantChallenge)
	}
	if payErr.Details["payment_amount"] != "0.10" {
		t.Errorf("Details.payment_amount = %v, want %q", payErr.Details["payment_amount"], "0.10")
	}
	if payErr.Details["payment_currency"] != "PathUSD" {
		t.Errorf("Details.payment_currency = %v, want %q", payErr.Details["payment_currency"], "PathUSD")
	}
	if payErr.Details["challenge_id"] != "abc" {
		t.Errorf("Details.challenge_id = %v, want %q", payErr.Details["challenge_id"], "abc")
	}
	if payErr.Details["intent"] != "charge" {
		t.Errorf("Details.intent = %v, want %q", payErr.Details["intent"], "charge")
	}
	if _, leaked := payErr.Details["_secret_nonce"]; leaked {
		t.Errorf("Details should not contain unsafe key %q", "_secret_nonce")
	}
	if payErr.Error() != "payment required" {
		t.Errorf("Error() = %q, want %q", payErr.Error(), "payment required")
	}
}

func TestStartSession_PendingWithoutChallenge_FallsBackToDeny(t *testing.T) {
	// A Pending result with no payment_challenge metadata is treated as a
	// regular denial (existing behaviour) — it must NOT surface as a typed
	// PaymentRequiredError.
	mgr, registry := newTestSessionManager(t)

	registerAgentEndpoint(t, registry, "agent-ep", noopAgentHandler,
		func(_ context.Context, _ *ExecutorInput) (*ExecutorOutput, error) {
			return &ExecutorOutput{
				Success: true,
				PolicyResult: &PolicyResultOutput{
					Allowed:    false,
					Pending:    true,
					PolicyName: "manual_review",
					Reason:     "awaiting reviewer",
					// no payment_challenge
				},
			}, nil
		},
	)

	user := &UserContext{Sub: "u", Username: "u"}
	_, err := mgr.StartSession(AgentSessionStartPayload{
		SessionID: "s1", EndpointSlug: "agent-ep",
	}, user)

	if err == nil {
		t.Fatal("expected denial error")
	}
	var payErr *PaymentRequiredError
	if errors.As(err, &payErr) {
		t.Fatalf("did not expect *PaymentRequiredError, got: %v", err)
	}
	if !strings.Contains(err.Error(), "manual_review") {
		t.Errorf("error %q should mention denying policy name", err.Error())
	}
}

func TestStartSession_NormalPolicyDeny_StillReturnsGenericError(t *testing.T) {
	mgr, registry := newTestSessionManager(t)

	registerAgentEndpoint(t, registry, "agent-ep", noopAgentHandler,
		func(_ context.Context, _ *ExecutorInput) (*ExecutorOutput, error) {
			return &ExecutorOutput{
				Success: true,
				PolicyResult: &PolicyResultOutput{
					Allowed:    false,
					Pending:    false,
					PolicyName: "rate_limit",
					Reason:     "too many requests",
				},
			}, nil
		},
	)

	user := &UserContext{Sub: "u", Username: "u"}
	_, err := mgr.StartSession(AgentSessionStartPayload{
		SessionID: "s1", EndpointSlug: "agent-ep",
	}, user)
	if err == nil {
		t.Fatal("expected denial error")
	}
	var payErr *PaymentRequiredError
	if errors.As(err, &payErr) {
		t.Fatalf("did not expect *PaymentRequiredError for non-payment denial, got: %v", err)
	}
}

func TestAgentSessionStartPayload_PaymentCredentialJSONRoundTrip(t *testing.T) {
	in := AgentSessionStartPayload{
		SessionID:         "s",
		Prompt:            "hi",
		EndpointSlug:      "ep",
		PaymentCredential: "Payment xyz",
	}
	data, err := json.Marshal(in)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !strings.Contains(string(data), `"payment_credential":"Payment xyz"`) {
		t.Errorf("missing payment_credential in JSON: %s", data)
	}

	var out AgentSessionStartPayload
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if out.PaymentCredential != "Payment xyz" {
		t.Errorf("PaymentCredential = %q, want %q", out.PaymentCredential, "Payment xyz")
	}

	// Empty value must omit (omitempty).
	emptyData, _ := json.Marshal(AgentSessionStartPayload{SessionID: "s"})
	if strings.Contains(string(emptyData), "payment_credential") {
		t.Errorf("payment_credential should be omitted when empty: %s", emptyData)
	}
}

func TestCopyPaymentMetadata_NilAndEmpty(t *testing.T) {
	if got := copyPaymentMetadata(nil); got != nil {
		t.Errorf("copyPaymentMetadata(nil) = %v, want nil", got)
	}
	if got := copyPaymentMetadata(map[string]any{"unrelated": "x"}); got != nil {
		t.Errorf("copyPaymentMetadata(no payment keys) = %v, want nil", got)
	}
}

func TestPaymentChallengeFromMetadata(t *testing.T) {
	if _, ok := paymentChallengeFromMetadata(nil); ok {
		t.Error("nil metadata should return ok=false")
	}
	if _, ok := paymentChallengeFromMetadata(map[string]any{}); ok {
		t.Error("missing key should return ok=false")
	}
	if _, ok := paymentChallengeFromMetadata(map[string]any{"payment_challenge": ""}); ok {
		t.Error("empty challenge string should return ok=false")
	}
	if _, ok := paymentChallengeFromMetadata(map[string]any{"payment_challenge": 42}); ok {
		t.Error("non-string challenge should return ok=false")
	}
	got, ok := paymentChallengeFromMetadata(map[string]any{"payment_challenge": "Payment id=x"})
	if !ok || got != "Payment id=x" {
		t.Errorf("got (%q, %v), want (%q, true)", got, ok, "Payment id=x")
	}
}
