package main

import (
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
)

// withLoggedInApp returns an *App seeded with `identity` for tests that need
// a.RecordSentReview to succeed.
func withLoggedInApp(t *testing.T, identity string) *App {
	t.Helper()
	withTempSettingsDir(t)
	a := &App{}
	a.mu.Lock()
	a.username = identity
	a.mu.Unlock()
	return a
}

func sampleEnvelope(reviewID string) manualreview.ResolvedEnvelope {
	return manualreview.ResolvedEnvelope{
		Protocol:      manualreview.ProtocolVersion,
		Type:          manualreview.MsgTypeResolved,
		ReviewID:      reviewID,
		SessionID:     "sess-1",
		EndpointOwner: "alice",
		EndpointSlug:  "research-agent",
		EndpointName:  "Research Agent",
		PolicyName:    "review-policy",
	}
}

func samplePayload(reviewID, status, response, reason string) manualreview.ResolvedPayload {
	return manualreview.ResolvedPayload{
		ReviewID:       reviewID,
		Status:         status,
		ResolvedAt:     "2026-05-22T10:00:00.000000+00:00",
		ResponseText:   response,
		RejectReason:   reason,
		ResolverUserID: "alice",
	}
}

// Common case: the chat user captured a pending hold here; the host approves;
// the resolution lands. status_source flips to "queried", response_text is
// populated, host_resolved_at is set, delivery_seq is stored.
func TestApplyHostResolution_UpdatesExistingRow(t *testing.T) {
	a := withLoggedInApp(t, "bob")
	if err := a.RecordSentReview(SentReviewInput{
		ReviewID:     "rid-1",
		EndpointPath: "alice/research-agent",
		EndpointName: "Research Agent",
		PolicyName:   "review-policy",
		Placeholder:  "Held",
	}); err != nil {
		t.Fatalf("record: %v", err)
	}

	applied, err := a.ApplyHostResolution(
		"bob",
		sampleEnvelope("rid-1"),
		samplePayload("rid-1", manualreview.StatusApproved, "the real held answer", ""),
		42,
	)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	if !applied {
		t.Fatal("expected applied=true on first delivery")
	}

	entries, _ := a.GetSentReviews("all")
	if len(entries) != 1 {
		t.Fatalf("got %d entries, want 1", len(entries))
	}
	got := entries[0]
	if got.Status != manualreview.StatusApproved {
		t.Errorf("Status = %q, want approved", got.Status)
	}
	if got.StatusSource != "queried" {
		t.Errorf("StatusSource = %q, want queried", got.StatusSource)
	}
	if got.ResponseText != "the real held answer" {
		t.Errorf("ResponseText = %q", got.ResponseText)
	}
	if got.HostResolvedAt != "2026-05-22T10:00:00.000000+00:00" {
		t.Errorf("HostResolvedAt = %q", got.HostResolvedAt)
	}
	if got.DeliverySeq != 42 {
		t.Errorf("DeliverySeq = %d, want 42", got.DeliverySeq)
	}
}

// A redelivery with an older or equal seq must NOT regress the row.
func TestApplyHostResolution_SeqGuardRejectsOlder(t *testing.T) {
	a := withLoggedInApp(t, "bob")
	_ = a.RecordSentReview(SentReviewInput{ReviewID: "rid-1", EndpointPath: "alice/ep"})

	_, _ = a.ApplyHostResolution("bob", sampleEnvelope("rid-1"),
		samplePayload("rid-1", manualreview.StatusApproved, "good", ""), 100)

	// Same seq — must no-op even with different payload (proves the guard is
	// strict-less-than, not less-than-or-equal-with-overwrite).
	applied, err := a.ApplyHostResolution("bob", sampleEnvelope("rid-1"),
		samplePayload("rid-1", manualreview.StatusRejected, "", "spam"), 100)
	if err != nil {
		t.Fatalf("apply duplicate: %v", err)
	}
	if applied {
		t.Error("expected applied=false on duplicate seq")
	}

	got, _ := a.GetSentReviews("all")
	if got[0].Status != manualreview.StatusApproved {
		t.Errorf("Status regressed: got %q, want approved", got[0].Status)
	}
	if got[0].ResponseText != "good" {
		t.Errorf("ResponseText regressed: %q", got[0].ResponseText)
	}
}

// A later seq must overwrite the row. JetStream replays in sequence order so
// strict-less-than is the only correct guard.
func TestApplyHostResolution_HigherSeqOverwrites(t *testing.T) {
	a := withLoggedInApp(t, "bob")
	_ = a.RecordSentReview(SentReviewInput{ReviewID: "rid-1", EndpointPath: "alice/ep"})

	_, _ = a.ApplyHostResolution("bob", sampleEnvelope("rid-1"),
		samplePayload("rid-1", manualreview.StatusApproved, "first", ""), 10)
	applied, err := a.ApplyHostResolution("bob", sampleEnvelope("rid-1"),
		samplePayload("rid-1", manualreview.StatusRejected, "", "changed mind"), 20)
	if err != nil {
		t.Fatalf("apply newer: %v", err)
	}
	if !applied {
		t.Error("expected applied=true on newer seq")
	}
	got, _ := a.GetSentReviews("all")
	if got[0].Status != manualreview.StatusRejected || got[0].RejectReason != "changed mind" {
		t.Errorf("expected newer state, got %+v", got[0])
	}
}

// A resolution arriving on a device that never saw the original hold must
// still land — synthesized as a "queried"-source row.
func TestApplyHostResolution_SynthesizesRowOnFreshDevice(t *testing.T) {
	a := withLoggedInApp(t, "bob")

	applied, err := a.ApplyHostResolution("bob",
		sampleEnvelope("rid-fresh"),
		samplePayload("rid-fresh", manualreview.StatusApproved, "fresh delivery", ""),
		7,
	)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	if !applied {
		t.Fatal("expected applied=true for synthesized row")
	}
	got, _ := a.GetSentReviews("all")
	if len(got) != 1 {
		t.Fatalf("got %d entries, want 1", len(got))
	}
	row := got[0]
	if row.ReviewID != "rid-fresh" || row.Status != manualreview.StatusApproved {
		t.Errorf("synth row wrong: %+v", row)
	}
	if row.StatusSource != "queried" {
		t.Errorf("synth StatusSource = %q, want queried", row.StatusSource)
	}
	if row.EndpointPath != "alice/research-agent" {
		t.Errorf("EndpointPath = %q, want %q", row.EndpointPath, "alice/research-agent")
	}
	if row.ResponseText != "fresh delivery" {
		t.Errorf("ResponseText = %q", row.ResponseText)
	}
}

// A row already marked status_source='manual' by the user must be flipped to
// 'queried' on host delivery — host wins. (The frontend will surface a toast.)
func TestApplyHostResolution_QueriedOverridesManual(t *testing.T) {
	a := withLoggedInApp(t, "bob")
	_ = a.RecordSentReview(SentReviewInput{ReviewID: "rid-m", EndpointPath: "alice/ep"})
	// User manually marked it approved out of band.
	if err := a.SetSentReviewStatus("rid-m", manualreview.StatusApproved, ""); err != nil {
		t.Fatalf("set manual: %v", err)
	}

	// Host now confirms it was rejected. Queried must win, with the right
	// reject_reason landed.
	applied, err := a.ApplyHostResolution("bob",
		sampleEnvelope("rid-m"),
		samplePayload("rid-m", manualreview.StatusRejected, "", "policy violation"),
		5,
	)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	if !applied {
		t.Error("queried must override manual")
	}
	got, _ := a.GetSentReviews("all")
	if got[0].Status != manualreview.StatusRejected {
		t.Errorf("Status = %q, want rejected (host wins)", got[0].Status)
	}
	if got[0].StatusSource != "queried" {
		t.Errorf("StatusSource = %q, want queried", got[0].StatusSource)
	}
	if got[0].RejectReason != "policy violation" {
		t.Errorf("RejectReason = %q", got[0].RejectReason)
	}
}

// Bad inputs: identity required, review_id consistency, status validation.
func TestApplyHostResolution_ValidatesInputs(t *testing.T) {
	a := withLoggedInApp(t, "bob")

	if _, err := a.ApplyHostResolution("", sampleEnvelope("r"), samplePayload("r", "approved", "", ""), 1); err == nil {
		t.Error("expected error on empty identity")
	}
	// Mismatched review_id between envelope and payload.
	env := sampleEnvelope("env-id")
	payload := samplePayload("payload-id", "approved", "", "")
	if _, err := a.ApplyHostResolution("bob", env, payload, 1); err == nil {
		t.Error("expected error on review_id mismatch")
	}
	// Unsupported status.
	if _, err := a.ApplyHostResolution("bob", sampleEnvelope("r"),
		manualreview.ResolvedPayload{ReviewID: "r", Status: "pending"}, 1); err == nil {
		t.Error("expected error on pending status")
	}
}

// Defensive: an UPDATE for one identity must never modify a row owned by a
// different identity, even when they share a review_id. (Cross-identity
// review_id collision is astronomically unlikely under uuid4 generation, but
// the WHERE-identity guard is the safety net regardless.)
//
// In Phase 2.0, the PRIMARY KEY on review_id (without identity) means a
// cross-identity synth INSERT would normally collide with bob's row. We use
// INSERT OR IGNORE so the path returns applied=false rather than erroring —
// the listener is identity-scoped by design and this code path is not
// normally reachable, so silent skip is the conservative choice.
func TestApplyHostResolution_DoesNotMutateForeignIdentityRow(t *testing.T) {
	a := withLoggedInApp(t, "bob")
	_ = a.RecordSentReview(SentReviewInput{ReviewID: "rid-x", EndpointPath: "alice/ep"})

	applied, err := a.ApplyHostResolution("carol", sampleEnvelope("rid-x"),
		samplePayload("rid-x", manualreview.StatusApproved, "leak?", ""), 1)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	if applied {
		t.Error("cross-identity synth must be a no-op when bob already owns rid-x")
	}

	// bob's row must be unchanged.
	bobsRows, _ := a.GetSentReviews("all")
	if len(bobsRows) != 1 || bobsRows[0].Status != "pending" || bobsRows[0].ResponseText != "" {
		t.Errorf("bob's row was modified by carol's apply: %+v", bobsRows[0])
	}

	// No row got synthesized under carol's identity, either (PK collision).
	db, _ := openSentReviewsDB()
	defer db.Close()
	var n int
	if err := db.QueryRow(`SELECT COUNT(*) FROM sent_reviews WHERE identity = 'carol'`).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 0 {
		t.Errorf("expected 0 carol rows after collision, got %d", n)
	}
}
