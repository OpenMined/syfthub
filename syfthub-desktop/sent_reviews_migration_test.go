package main

import (
	"database/sql"
	"os"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

// migrateFromV1Schema simulates a Phase 1 install: the table exists without
// host_resolved_at or delivery_seq, PRAGMA user_version is 0.
func writeV1SentReviewsDB(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	db, err := sql.Open("sqlite", "file:"+path+"?_pragma=journal_mode(WAL)")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()
	if _, err := db.Exec(`CREATE TABLE sent_reviews (
		review_id        TEXT PRIMARY KEY,
		identity         TEXT NOT NULL,
		endpoint_path    TEXT NOT NULL,
		endpoint_owner   TEXT,
		endpoint_slug    TEXT,
		endpoint_name    TEXT,
		endpoint_type    TEXT NOT NULL DEFAULT 'agent',
		policy_name      TEXT,
		request_messages TEXT,
		placeholder      TEXT,
		submitted_at     TEXT NOT NULL,
		status           TEXT NOT NULL DEFAULT 'pending',
		status_source    TEXT NOT NULL DEFAULT 'captured',
		resolved_at      TEXT,
		reject_reason    TEXT,
		response_text    TEXT,
		user_note        TEXT
	)`); err != nil {
		t.Fatalf("create v1: %v", err)
	}
	if _, err := db.Exec(
		`INSERT INTO sent_reviews
		   (review_id, identity, endpoint_path, submitted_at)
		 VALUES ('rid-old', 'alice', 'alice/ep', '2026-01-01T00:00:00.000000+00:00')`,
	); err != nil {
		t.Fatalf("seed: %v", err)
	}
	if _, err := db.Exec("PRAGMA user_version = 0"); err != nil {
		t.Fatalf("set version: %v", err)
	}
}

// A Phase 1 ledger opened by Phase 2.0 code must (a) acquire the two new
// columns, (b) keep the existing row intact, and (c) end at version 2.
func TestMigrateSentReviewsSchema_UpgradesV1ToV2InPlace(t *testing.T) {
	withTempSettingsDir(t)
	path, _ := sentReviewsDBFile()
	writeV1SentReviewsDB(t, path)

	db, err := openSentReviewsDB()
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()

	var version int
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		t.Fatalf("read version: %v", err)
	}
	if version != sentReviewsSchemaVersion {
		t.Errorf("user_version = %d, want %d", version, sentReviewsSchemaVersion)
	}

	if exists, _ := columnExists(db, "sent_reviews", "host_resolved_at"); !exists {
		t.Error("host_resolved_at column missing after migration")
	}
	if exists, _ := columnExists(db, "sent_reviews", "delivery_seq"); !exists {
		t.Error("delivery_seq column missing after migration")
	}

	// The existing row's old fields must be untouched and the new fields
	// default to NULL.
	var rid string
	var hostResolvedAt sql.NullString
	var deliverySeq sql.NullInt64
	err = db.QueryRow(
		`SELECT review_id, host_resolved_at, delivery_seq FROM sent_reviews WHERE review_id = ?`,
		"rid-old",
	).Scan(&rid, &hostResolvedAt, &deliverySeq)
	if err != nil {
		t.Fatalf("read row: %v", err)
	}
	if hostResolvedAt.Valid || deliverySeq.Valid {
		t.Errorf("expected new columns NULL on legacy row, got host=%v seq=%v", hostResolvedAt, deliverySeq)
	}
}

// A fresh install (no pre-existing DB) must also end at version 2 with
// every column present. CREATE TABLE handles the columns; the migration
// just stamps the version.
func TestMigrateSentReviewsSchema_FreshInstallStampsVersion(t *testing.T) {
	withTempSettingsDir(t)
	db, err := openSentReviewsDB()
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()
	var version int
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		t.Fatalf("read version: %v", err)
	}
	if version != sentReviewsSchemaVersion {
		t.Errorf("user_version = %d, want %d", version, sentReviewsSchemaVersion)
	}
}

// Opening twice (second time = the migration has already run) must be a no-op.
func TestMigrateSentReviewsSchema_IdempotentSecondOpen(t *testing.T) {
	dir := withTempSettingsDir(t)
	_ = filepath.Base(dir)

	db1, err := openSentReviewsDB()
	if err != nil {
		t.Fatalf("first open: %v", err)
	}
	db1.Close()

	db2, err := openSentReviewsDB()
	if err != nil {
		t.Fatalf("second open: %v", err)
	}
	defer db2.Close()
	var version int
	if err := db2.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		t.Fatalf("read version: %v", err)
	}
	if version != sentReviewsSchemaVersion {
		t.Errorf("user_version after second open = %d, want %d", version, sentReviewsSchemaVersion)
	}
}
