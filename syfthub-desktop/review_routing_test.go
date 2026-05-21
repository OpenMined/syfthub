package main

import (
	"path/filepath"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
)

func newTestRecorder(t *testing.T) manualreview.RoutingRecorder {
	t.Helper()
	dir := t.TempDir()
	r, err := openRoutingRecorder(filepath.Join(dir, "store.db"))
	if err != nil {
		t.Fatalf("open recorder: %v", err)
	}
	t.Cleanup(func() { _ = r.Close() })
	return r
}

func sampleRouting(reviewID string) manualreview.Routing {
	return manualreview.Routing{
		ReviewID:        reviewID,
		CallerUsername:  "bob",
		CallerPubkeyB64: "AAAA",
		InboxSubject:    manualreview.InboxSubjectFor("bob"),
		SessionID:       "sess-1",
		PeerChannel:     "peer-abc",
		CapturedAt:      time.Now().UTC().Format(manualreview.ISOMicroLayout),
	}
}

func TestRouting_RecordAndLoad(t *testing.T) {
	r := newTestRecorder(t)
	row := sampleRouting("rid-1")
	if err := r.Record(row); err != nil {
		t.Fatalf("record: %v", err)
	}
	got, err := r.Load("rid-1")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if got == nil {
		t.Fatal("expected row, got nil")
	}
	if got.CallerUsername != row.CallerUsername || got.CallerPubkeyB64 != row.CallerPubkeyB64 ||
		got.InboxSubject != row.InboxSubject || got.SessionID != row.SessionID ||
		got.PeerChannel != row.PeerChannel {
		t.Errorf("loaded row diverges: %+v vs %+v", got, row)
	}
	if got.DeliveredAt != "" {
		t.Errorf("expected DeliveredAt empty on capture, got %q", got.DeliveredAt)
	}
}

// Capture must be idempotent — a re-emitted pending notice cannot
// silently overwrite the first capture's pubkey/peer_channel.
func TestRouting_RecordIsIdempotentOnReviewID(t *testing.T) {
	r := newTestRecorder(t)
	first := sampleRouting("rid-1")
	if err := r.Record(first); err != nil {
		t.Fatalf("record first: %v", err)
	}

	second := first
	second.CallerPubkeyB64 = "BBBB" // imagine a bogus re-record with a different pubkey
	if err := r.Record(second); err != nil {
		t.Fatalf("record second: %v", err)
	}

	got, err := r.Load("rid-1")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if got.CallerPubkeyB64 != "AAAA" {
		t.Errorf("pubkey overwritten: got %q, want %q (first record wins)", got.CallerPubkeyB64, "AAAA")
	}
}

func TestRouting_LoadMissingReturnsNil(t *testing.T) {
	r := newTestRecorder(t)
	got, err := r.Load("does-not-exist")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if got != nil {
		t.Errorf("expected nil for missing review, got %+v", got)
	}
}

func TestRouting_MarkDeliveredIdempotent(t *testing.T) {
	r := newTestRecorder(t)
	if err := r.Record(sampleRouting("rid-1")); err != nil {
		t.Fatalf("record: %v", err)
	}
	first := "2026-05-22T10:00:00.000000+00:00"
	if err := r.MarkDelivered("rid-1", first); err != nil {
		t.Fatalf("mark first: %v", err)
	}
	// Second mark must NOT overwrite the first timestamp.
	if err := r.MarkDelivered("rid-1", "2026-05-22T11:00:00.000000+00:00"); err != nil {
		t.Fatalf("mark second: %v", err)
	}
	got, _ := r.Load("rid-1")
	if got.DeliveredAt != first {
		t.Errorf("DeliveredAt = %q, want %q (first-write-wins)", got.DeliveredAt, first)
	}
}

func TestRouting_MarkDeliveredMissingErrors(t *testing.T) {
	r := newTestRecorder(t)
	if err := r.MarkDelivered("nope", "2026-05-22T10:00:00.000000+00:00"); err == nil {
		t.Error("expected error marking missing row")
	}
}

func TestRouting_RecordAttemptAndListUndelivered(t *testing.T) {
	r := newTestRecorder(t)
	if err := r.Record(sampleRouting("rid-1")); err != nil {
		t.Fatalf("record: %v", err)
	}
	if err := r.Record(sampleRouting("rid-2")); err != nil {
		t.Fatalf("record: %v", err)
	}
	if err := r.RecordAttempt("rid-1", "2026-05-22T10:00:00.000000+00:00", "nats down"); err != nil {
		t.Fatalf("attempt: %v", err)
	}
	if err := r.MarkDelivered("rid-2", "2026-05-22T10:01:00.000000+00:00"); err != nil {
		t.Fatalf("deliver: %v", err)
	}

	undelivered, err := r.ListUndelivered()
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(undelivered) != 1 || undelivered[0].ReviewID != "rid-1" {
		t.Errorf("ListUndelivered = %+v, want only rid-1", undelivered)
	}
	if undelivered[0].DeliveryAttempts != 1 || undelivered[0].LastError != "nats down" {
		t.Errorf("attempt state not persisted: %+v", undelivered[0])
	}
}

// Two recorders against the same DB file must see each other's writes —
// the capture-path (executor goroutine) and the delivery-path (Wails call)
// run in separate parts of the codebase and may open the file twice.
func TestRouting_CrossHandleVisibility(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "store.db")

	writer, err := openRoutingRecorder(dbPath)
	if err != nil {
		t.Fatalf("open writer: %v", err)
	}
	defer writer.Close()
	if err := writer.Record(sampleRouting("rid-x")); err != nil {
		t.Fatalf("record: %v", err)
	}

	reader, err := openRoutingRecorder(dbPath)
	if err != nil {
		t.Fatalf("open reader: %v", err)
	}
	defer reader.Close()
	got, err := reader.Load("rid-x")
	if err != nil || got == nil {
		t.Fatalf("reader missed row: got=%+v err=%v", got, err)
	}
}
