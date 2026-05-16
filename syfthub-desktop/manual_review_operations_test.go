package main

import (
	"database/sql"
	"os"
	"path/filepath"
	"testing"

	"github.com/openmined/syfthub-desktop-gui/internal/app"
	_ "modernc.org/sqlite"
)

// createManualReviewsTable creates the manual_reviews table with the same
// schema ManualReviewPolicy (policy_manager) uses, in policy/store.db under
// the given endpoint directory. It returns the open database for seeding.
func seedReviewDB(t *testing.T, endpointsPath, slug string) *sql.DB {
	t.Helper()
	policyDir := filepath.Join(endpointsPath, slug, "policy")
	if err := os.MkdirAll(policyDir, 0o755); err != nil {
		t.Fatalf("mkdir policy dir: %v", err)
	}
	db, err := sql.Open("sqlite", "file:"+filepath.Join(policyDir, "store.db"))
	if err != nil {
		t.Fatalf("open store.db: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	_, err = db.Exec(`CREATE TABLE manual_reviews (
		review_id     TEXT PRIMARY KEY,
		policy_name   TEXT NOT NULL,
		user_id       TEXT,
		input         TEXT,
		output        TEXT,
		status        TEXT NOT NULL DEFAULT 'pending',
		pending       INTEGER NOT NULL DEFAULT 1,
		reject_reason TEXT,
		created_at    TEXT NOT NULL,
		resolved_at   TEXT
	)`)
	if err != nil {
		t.Fatalf("create table: %v", err)
	}
	return db
}

func insertReview(t *testing.T, db *sql.DB, id, user, input, output, status string, pending int, reason, created, resolved string) {
	t.Helper()
	_, err := db.Exec(
		`INSERT INTO manual_reviews
			(review_id, policy_name, user_id, input, output, status, pending, reject_reason, created_at, resolved_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		id, "mr", user, input, output, status, pending,
		nullable(reason), created, nullable(resolved),
	)
	if err != nil {
		t.Fatalf("insert review %s: %v", id, err)
	}
}

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func TestGetManualReviews(t *testing.T) {
	tempDir := t.TempDir()
	slug := "agent-ep"
	db := seedReviewDB(t, tempDir, slug)

	// A held model request, still pending.
	insertReview(t, db, "rev-pending", "alice",
		`{"type":"model","query":"summarize the q3 report","messages":[{"role":"user","content":"summarize the q3 report"}]}`,
		`{"response":"Q3 revenue grew 12%."}`,
		"pending", 1, "", "2026-05-16T10:00:00+00:00", "")
	// An approved request.
	insertReview(t, db, "rev-approved", "bob",
		`{"type":"model","query":"hi"}`,
		`{"response":"hello there"}`,
		"approved", 0, "", "2026-05-16T11:00:00+00:00", "2026-05-16T11:05:00+00:00")
	// A rejected request with a reason.
	insertReview(t, db, "rev-rejected", "carol",
		`{"type":"data_source","query":"find policy docs"}`,
		`{"result":[{"document_id":"d1","content":"doc body"}]}`,
		"rejected", 0, "contained PII", "2026-05-16T12:00:00+00:00", "2026-05-16T12:30:00+00:00")

	a := &App{config: &app.Config{EndpointsPath: tempDir}}

	t.Run("all returns every row newest-first", func(t *testing.T) {
		got, err := a.GetManualReviews(slug, "all")
		if err != nil {
			t.Fatalf("GetManualReviews: %v", err)
		}
		if len(got) != 3 {
			t.Fatalf("want 3 entries, got %d", len(got))
		}
		// ORDER BY created_at DESC — rejected (12:00) is newest.
		if got[0].ReviewID != "rev-rejected" || got[2].ReviewID != "rev-pending" {
			t.Errorf("wrong order: %s ... %s", got[0].ReviewID, got[2].ReviewID)
		}
	})

	t.Run("pending filter", func(t *testing.T) {
		got, err := a.GetManualReviews(slug, "pending")
		if err != nil {
			t.Fatalf("GetManualReviews: %v", err)
		}
		if len(got) != 1 || got[0].ReviewID != "rev-pending" {
			t.Fatalf("want only rev-pending, got %+v", got)
		}
		e := got[0]
		if e.Status != "pending" {
			t.Errorf("Status = %q, want pending", e.Status)
		}
		if e.UserID != "alice" {
			t.Errorf("UserID = %q, want alice", e.UserID)
		}
		if e.RequestType != "model" {
			t.Errorf("RequestType = %q, want model", e.RequestType)
		}
		if e.RequestText != "summarize the q3 report" {
			t.Errorf("RequestText = %q", e.RequestText)
		}
		if len(e.RequestMessages) != 1 || e.RequestMessages[0].Role != "user" {
			t.Errorf("RequestMessages not decoded: %+v", e.RequestMessages)
		}
		if e.ResponseText != "Q3 revenue grew 12%." {
			t.Errorf("ResponseText = %q", e.ResponseText)
		}
	})

	t.Run("rejected filter carries reason", func(t *testing.T) {
		got, err := a.GetManualReviews(slug, "rejected")
		if err != nil {
			t.Fatalf("GetManualReviews: %v", err)
		}
		if len(got) != 1 {
			t.Fatalf("want 1 rejected, got %d", len(got))
		}
		e := got[0]
		if e.RejectReason != "contained PII" {
			t.Errorf("RejectReason = %q", e.RejectReason)
		}
		if e.ResolvedAt == "" {
			t.Error("ResolvedAt should be set on a rejected entry")
		}
		// A data_source list output has no "response" key — it falls back to
		// "result" and is pretty-printed rather than dropped.
		if e.ResponseText == "" {
			t.Error("ResponseText should decode the result list")
		}
	})

	t.Run("approved filter", func(t *testing.T) {
		got, err := a.GetManualReviews(slug, "approved")
		if err != nil {
			t.Fatalf("GetManualReviews: %v", err)
		}
		if len(got) != 1 || got[0].ReviewID != "rev-approved" {
			t.Fatalf("want only rev-approved, got %+v", got)
		}
	})
}

func TestGetManualReviewsMissingDatabase(t *testing.T) {
	tempDir := t.TempDir()
	if err := os.MkdirAll(filepath.Join(tempDir, "no-policy-ep"), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	a := &App{config: &app.Config{EndpointsPath: tempDir}}

	got, err := a.GetManualReviews("no-policy-ep", "all")
	if err != nil {
		t.Fatalf("missing store.db should not error: %v", err)
	}
	if len(got) != 0 {
		t.Errorf("want empty slice, got %d entries", len(got))
	}
}

func TestGetManualReviewsMissingTable(t *testing.T) {
	tempDir := t.TempDir()
	slug := "store-no-table"
	policyDir := filepath.Join(tempDir, slug, "policy")
	if err := os.MkdirAll(policyDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	// A store.db that exists but never held a request — no manual_reviews table.
	db, err := sql.Open("sqlite", "file:"+filepath.Join(policyDir, "store.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if _, err := db.Exec("CREATE TABLE policy_store (k TEXT)"); err != nil {
		t.Fatalf("create unrelated table: %v", err)
	}
	db.Close()

	a := &App{config: &app.Config{EndpointsPath: tempDir}}
	got, err := a.GetManualReviews(slug, "all")
	if err != nil {
		t.Fatalf("missing table should not error: %v", err)
	}
	if len(got) != 0 {
		t.Errorf("want empty slice, got %d entries", len(got))
	}
}

func TestResolveManualReview(t *testing.T) {
	tempDir := t.TempDir()
	slug := "agent-ep"
	db := seedReviewDB(t, tempDir, slug)
	insertReview(t, db, "rev-1", "alice",
		`{"type":"model","query":"q1"}`, `{"response":"r1"}`,
		"pending", 1, "", "2026-05-16T10:00:00+00:00", "")
	insertReview(t, db, "rev-2", "bob",
		`{"type":"model","query":"q2"}`, `{"response":"r2"}`,
		"pending", 1, "", "2026-05-16T11:00:00+00:00", "")

	a := &App{config: &app.Config{EndpointsPath: tempDir}}

	t.Run("approve clears pending and leaves reason NULL", func(t *testing.T) {
		if err := a.ApproveManualReview(slug, "rev-1"); err != nil {
			t.Fatalf("ApproveManualReview: %v", err)
		}
		var status string
		var pending int
		var reason, resolvedAt sql.NullString
		if err := db.QueryRow(
			"SELECT status, pending, reject_reason, resolved_at FROM manual_reviews WHERE review_id = ?",
			"rev-1",
		).Scan(&status, &pending, &reason, &resolvedAt); err != nil {
			t.Fatalf("query: %v", err)
		}
		if status != "approved" || pending != 0 {
			t.Errorf("status=%q pending=%d, want approved/0", status, pending)
		}
		if reason.Valid {
			t.Errorf("reject_reason should be NULL on approve, got %q", reason.String)
		}
		if !resolvedAt.Valid || resolvedAt.String == "" {
			t.Error("resolved_at should be set")
		}
	})

	t.Run("reject stores the reason", func(t *testing.T) {
		if err := a.RejectManualReview(slug, "rev-2", "leaked secrets"); err != nil {
			t.Fatalf("RejectManualReview: %v", err)
		}
		var status, reason string
		var pending int
		if err := db.QueryRow(
			"SELECT status, pending, reject_reason FROM manual_reviews WHERE review_id = ?",
			"rev-2",
		).Scan(&status, &pending, &reason); err != nil {
			t.Fatalf("query: %v", err)
		}
		if status != "rejected" || pending != 0 || reason != "leaked secrets" {
			t.Errorf("got status=%q pending=%d reason=%q", status, pending, reason)
		}
	})

	t.Run("unknown review id errors", func(t *testing.T) {
		if err := a.ApproveManualReview(slug, "does-not-exist"); err == nil {
			t.Error("want an error for an unknown review id")
		}
	})

	t.Run("resolved entries leave the pending filter", func(t *testing.T) {
		got, err := a.GetManualReviews(slug, "pending")
		if err != nil {
			t.Fatalf("GetManualReviews: %v", err)
		}
		if len(got) != 0 {
			t.Errorf("want 0 pending after both resolved, got %d", len(got))
		}
	})
}

func TestResolveManualReviewMissingDatabase(t *testing.T) {
	tempDir := t.TempDir()
	if err := os.MkdirAll(filepath.Join(tempDir, "bare-ep"), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	a := &App{config: &app.Config{EndpointsPath: tempDir}}
	if err := a.ApproveManualReview("bare-ep", "rev-x"); err == nil {
		t.Error("want an error when the review database does not exist")
	}
}

func TestDecodeReviewInput(t *testing.T) {
	t.Run("query form", func(t *testing.T) {
		typ, text, msgs := decodeReviewInput(`{"type":"data_source","query":"the query"}`)
		if typ != "data_source" || text != "the query" || msgs != nil {
			t.Errorf("got type=%q text=%q msgs=%v", typ, text, msgs)
		}
	})
	t.Run("messages form joins content", func(t *testing.T) {
		_, text, msgs := decodeReviewInput(
			`{"type":"model","messages":[{"role":"system","content":"be terse"},{"role":"user","content":"hi"}]}`)
		if text != "be terse\nhi" {
			t.Errorf("text = %q", text)
		}
		if len(msgs) != 2 {
			t.Errorf("want 2 messages, got %d", len(msgs))
		}
	})
	t.Run("non-JSON falls through to raw", func(t *testing.T) {
		_, text, _ := decodeReviewInput("not json")
		if text != "not json" {
			t.Errorf("text = %q", text)
		}
	})
	t.Run("empty", func(t *testing.T) {
		typ, text, msgs := decodeReviewInput("")
		if typ != "" || text != "" || msgs != nil {
			t.Errorf("want all zero, got %q %q %v", typ, text, msgs)
		}
	})
}

func TestDecodeReviewOutput(t *testing.T) {
	if got := decodeReviewOutput(`{"response":"hello"}`); got != "hello" {
		t.Errorf("response key: got %q", got)
	}
	if got := decodeReviewOutput(`{"result":"plain"}`); got != "plain" {
		t.Errorf("result key string: got %q", got)
	}
	// Structured result — pretty-printed, not dropped.
	if got := decodeReviewOutput(`{"result":[{"id":1}]}`); got == "" {
		t.Error("structured result should be rendered")
	}
	// No conventional key — whole object is shown.
	if got := decodeReviewOutput(`{"weird":"shape"}`); got == "" {
		t.Error("unconventional object should fall back to whole object")
	}
	if got := decodeReviewOutput(""); got != "" {
		t.Errorf("empty: got %q", got)
	}
}
