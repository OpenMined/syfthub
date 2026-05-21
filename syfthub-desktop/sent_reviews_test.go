package main

import (
	"path/filepath"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
	_ "modernc.org/sqlite"
)

// useTempLedger points sentReviewsDBFile at a fresh temp database for the
// duration of one test, restoring the original resolver afterwards.
func useTempLedger(t *testing.T) {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "sent-reviews.db")
	orig := sentReviewsDBFile
	sentReviewsDBFile = func() (string, error) { return dbPath, nil }
	t.Cleanup(func() { sentReviewsDBFile = orig })
}

// sampleInput builds a SentReviewInput with the given review id.
func sampleInput(reviewID string) SentReviewInput {
	return SentReviewInput{
		ReviewID:     reviewID,
		EndpointPath: "alice/qa-agent",
		EndpointName: "QA Agent",
		PolicyName:   "manual_review",
		RequestMessages: []ChatMessage{
			{Role: "user", Content: "summarize the q3 report"},
		},
		Placeholder: "Request submitted to manual review (reference: " + reviewID + ")",
	}
}

func TestRecordAndGetSentReviews(t *testing.T) {
	useTempLedger(t)
	a := &App{username: "bob"}

	if err := a.RecordSentReview(sampleInput("rev-aaa111222333")); err != nil {
		t.Fatalf("RecordSentReview: %v", err)
	}

	got, err := a.GetSentReviews("all")
	if err != nil {
		t.Fatalf("GetSentReviews: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("want 1 entry, got %d", len(got))
	}
	e := got[0]
	if e.ReviewID != "rev-aaa111222333" {
		t.Errorf("ReviewID = %q", e.ReviewID)
	}
	if e.Identity != "bob" {
		t.Errorf("Identity = %q, want bob", e.Identity)
	}
	if e.EndpointOwner != "alice" || e.EndpointSlug != "qa-agent" {
		t.Errorf("endpoint owner/slug = %q/%q, want alice/qa-agent", e.EndpointOwner, e.EndpointSlug)
	}
	if e.EndpointType != "agent" {
		t.Errorf("EndpointType = %q, want agent (default)", e.EndpointType)
	}
	if e.Status != manualreview.StatusPending || e.StatusSource != statusSourceCaptured {
		t.Errorf("status/source = %q/%q, want pending/captured", e.Status, e.StatusSource)
	}
	if e.SubmittedAt == "" {
		t.Error("SubmittedAt should be stamped")
	}
	if len(e.RequestMessages) != 1 || e.RequestMessages[0].Content != "summarize the q3 report" {
		t.Errorf("RequestMessages not round-tripped: %+v", e.RequestMessages)
	}
}

func TestRecordSentReviewIsIdempotent(t *testing.T) {
	useTempLedger(t)
	a := &App{username: "bob"}

	in := sampleInput("rev-dup000000000")
	for i := range 3 {
		if err := a.RecordSentReview(in); err != nil {
			t.Fatalf("RecordSentReview attempt %d: %v", i, err)
		}
	}

	got, err := a.GetSentReviews("all")
	if err != nil {
		t.Fatalf("GetSentReviews: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("re-recording the same review_id must not duplicate; got %d rows", len(got))
	}
}

func TestSentReviewsScopedByIdentity(t *testing.T) {
	useTempLedger(t)

	alice := &App{username: "alice"}
	bob := &App{username: "bob"}
	if err := alice.RecordSentReview(sampleInput("rev-alice0000001")); err != nil {
		t.Fatalf("alice record: %v", err)
	}
	if err := bob.RecordSentReview(sampleInput("rev-bob000000001")); err != nil {
		t.Fatalf("bob record: %v", err)
	}

	aliceGot, err := alice.GetSentReviews("all")
	if err != nil {
		t.Fatalf("alice GetSentReviews: %v", err)
	}
	if len(aliceGot) != 1 || aliceGot[0].ReviewID != "rev-alice0000001" {
		t.Fatalf("alice must see only her own entry, got %+v", aliceGot)
	}
	bobGot, err := bob.GetSentReviews("all")
	if err != nil {
		t.Fatalf("bob GetSentReviews: %v", err)
	}
	if len(bobGot) != 1 || bobGot[0].ReviewID != "rev-bob000000001" {
		t.Fatalf("bob must see only his own entry, got %+v", bobGot)
	}
}

func TestGetSentReviewsStatusFilter(t *testing.T) {
	useTempLedger(t)
	a := &App{username: "bob"}

	for _, id := range []string{"rev-p00000000001", "rev-p00000000002", "rev-r00000000001"} {
		if err := a.RecordSentReview(sampleInput(id)); err != nil {
			t.Fatalf("record %s: %v", id, err)
		}
	}
	if err := a.SetSentReviewStatus("rev-r00000000001", manualreview.StatusRejected, "off topic"); err != nil {
		t.Fatalf("SetSentReviewStatus: %v", err)
	}

	pending, err := a.GetSentReviews("pending")
	if err != nil {
		t.Fatalf("GetSentReviews(pending): %v", err)
	}
	if len(pending) != 2 {
		t.Errorf("want 2 pending, got %d", len(pending))
	}
	rejected, err := a.GetSentReviews("rejected")
	if err != nil {
		t.Fatalf("GetSentReviews(rejected): %v", err)
	}
	if len(rejected) != 1 || rejected[0].ReviewID != "rev-r00000000001" {
		t.Errorf("want only the rejected entry, got %+v", rejected)
	}
}

func TestSetSentReviewStatusManualOverride(t *testing.T) {
	useTempLedger(t)
	a := &App{username: "bob"}

	if err := a.RecordSentReview(sampleInput("rev-app000000001")); err != nil {
		t.Fatalf("record: %v", err)
	}
	if err := a.RecordSentReview(sampleInput("rev-rej000000001")); err != nil {
		t.Fatalf("record: %v", err)
	}

	t.Run("approve stamps manual and clears reason", func(t *testing.T) {
		if err := a.SetSentReviewStatus("rev-app000000001", manualreview.StatusApproved, "ignored"); err != nil {
			t.Fatalf("SetSentReviewStatus: %v", err)
		}
		e := findEntry(t, a, "rev-app000000001")
		if e.Status != manualreview.StatusApproved || e.StatusSource != statusSourceManual {
			t.Errorf("status/source = %q/%q, want approved/manual", e.Status, e.StatusSource)
		}
		if e.RejectReason != "" {
			t.Errorf("RejectReason = %q, want empty on approve", e.RejectReason)
		}
		if e.ResolvedAt == "" {
			t.Error("ResolvedAt should be set")
		}
	})

	t.Run("reject stores the reason", func(t *testing.T) {
		if err := a.SetSentReviewStatus("rev-rej000000001", manualreview.StatusRejected, "contained PII"); err != nil {
			t.Fatalf("SetSentReviewStatus: %v", err)
		}
		e := findEntry(t, a, "rev-rej000000001")
		if e.Status != manualreview.StatusRejected || e.RejectReason != "contained PII" {
			t.Errorf("got status=%q reason=%q", e.Status, e.RejectReason)
		}
	})

	t.Run("invalid status rejected", func(t *testing.T) {
		if err := a.SetSentReviewStatus("rev-app000000001", "pending", ""); err == nil {
			t.Error("want an error for a non-terminal manual status")
		}
	})

	t.Run("unknown review id errors", func(t *testing.T) {
		if err := a.SetSentReviewStatus("rev-does-not-exist", manualreview.StatusApproved, ""); err == nil {
			t.Error("want an error for an unknown review id")
		}
	})
}

func TestSetSentReviewNote(t *testing.T) {
	useTempLedger(t)
	a := &App{username: "bob"}

	if err := a.RecordSentReview(sampleInput("rev-note00000001")); err != nil {
		t.Fatalf("record: %v", err)
	}
	if err := a.SetSentReviewNote("rev-note00000001", "chased this with the owner"); err != nil {
		t.Fatalf("SetSentReviewNote: %v", err)
	}
	if e := findEntry(t, a, "rev-note00000001"); e.UserNote != "chased this with the owner" {
		t.Errorf("UserNote = %q", e.UserNote)
	}
}

func TestSentReviewsNotAuthenticated(t *testing.T) {
	useTempLedger(t)
	a := &App{} // no username

	if err := a.RecordSentReview(sampleInput("rev-anon00000001")); err == nil {
		t.Error("RecordSentReview must error when not authenticated")
	}
	got, err := a.GetSentReviews("all")
	if err != nil {
		t.Fatalf("GetSentReviews should not error when logged out: %v", err)
	}
	if len(got) != 0 {
		t.Errorf("want empty slice when logged out, got %d", len(got))
	}
}

func TestRecordSentReviewRejectsEmptyID(t *testing.T) {
	useTempLedger(t)
	a := &App{username: "bob"}

	in := sampleInput("")
	if err := a.RecordSentReview(in); err == nil {
		t.Error("RecordSentReview must reject an empty review id")
	}
}

// findEntry fetches a single entry by id, failing the test if it is absent.
func findEntry(t *testing.T, a *App, reviewID string) SentReviewEntry {
	t.Helper()
	all, err := a.GetSentReviews("all")
	if err != nil {
		t.Fatalf("GetSentReviews: %v", err)
	}
	for _, e := range all {
		if e.ReviewID == reviewID {
			return e
		}
	}
	t.Fatalf("entry %q not found", reviewID)
	return SentReviewEntry{}
}
