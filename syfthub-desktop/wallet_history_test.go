package main

import (
	"database/sql"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

// newTestPaymentsDB returns an in-memory pool with the payments schema and
// installs it as the test override. The test must reset the override in a
// Cleanup; this helper does that automatically.
func newTestPaymentsDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", "file::memory:?cache=shared")
	if err != nil {
		t.Fatalf("open memory db: %v", err)
	}
	if err := initPaymentsSchema(db); err != nil {
		t.Fatalf("schema: %v", err)
	}
	resetPaymentsDBForTest(db)
	t.Cleanup(func() {
		resetPaymentsDBForTest(nil)
		_ = db.Close()
	})
	return db
}

func makeRecord(id, slug, status, amount string, ts int64) PaymentRecord {
	return PaymentRecord{
		ID:            id,
		TimestampUnix: ts,
		EndpointOwner: "alice",
		EndpointSlug:  slug,
		Amount:        amount,
		Currency:      pathUSDContractAddress,
		ChainID:       defaultChainID,
		ChallengeID:   "ch-" + id,
		CredentialHex: "Payment-fake-" + id,
		Status:        status,
	}
}

func TestRecordPaymentRoundTrip(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	rec := makeRecord("a", "bot", PaymentStatusSigned, "1.0", time.Now().Unix())
	if err := a.RecordPayment(rec); err != nil {
		t.Fatalf("record: %v", err)
	}
	page, err := a.TransactionHistory(TransactionFilter{})
	if err != nil {
		t.Fatalf("history: %v", err)
	}
	if page.Total != 1 || len(page.Records) != 1 {
		t.Fatalf("expected 1 row, got total=%d records=%d", page.Total, len(page.Records))
	}
	got := page.Records[0]
	if got.ID != rec.ID || got.EndpointSlug != rec.EndpointSlug {
		t.Fatalf("row mismatch: %+v", got)
	}
}

func TestRecordPayment_RequiresID(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	rec := makeRecord("", "bot", PaymentStatusSigned, "1.0", time.Now().Unix())
	if err := a.RecordPayment(rec); err == nil {
		t.Fatal("expected error on empty id")
	}
}

func TestUpdateSettlement_FlipsStatus(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	rec := makeRecord("a", "bot", PaymentStatusSigned, "1.0", time.Now().Unix())
	if err := a.RecordPayment(rec); err != nil {
		t.Fatalf("record: %v", err)
	}
	settledAt := time.Now().Unix()
	if err := a.UpdateSettlement(rec.ChallengeID, "0xdead", PaymentStatusSettled, "", settledAt); err != nil {
		t.Fatalf("update: %v", err)
	}
	page, err := a.TransactionHistory(TransactionFilter{})
	if err != nil {
		t.Fatalf("history: %v", err)
	}
	got := page.Records[0]
	if got.Status != PaymentStatusSettled {
		t.Fatalf("status = %q", got.Status)
	}
	if got.TxHash != "0xdead" {
		t.Fatalf("tx hash = %q", got.TxHash)
	}
	if got.SettledUnix != settledAt {
		t.Fatalf("settled unix = %d, want %d", got.SettledUnix, settledAt)
	}
}

func TestUpdateSettlement_NoRow(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	err := a.UpdateSettlement("missing", "0xdead", PaymentStatusSettled, "", time.Now().Unix())
	if err == nil {
		t.Fatal("expected error for missing challenge id")
	}
}

func TestTransactionHistory_FilterByStatus(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	now := time.Now().Unix()
	if err := a.RecordPayment(makeRecord("a", "bot", PaymentStatusSigned, "1.0", now)); err != nil {
		t.Fatalf("rec a: %v", err)
	}
	if err := a.RecordPayment(makeRecord("b", "bot", PaymentStatusSettled, "2.0", now+1)); err != nil {
		t.Fatalf("rec b: %v", err)
	}
	if err := a.RecordPayment(makeRecord("c", "bot", PaymentStatusFailed, "3.0", now+2)); err != nil {
		t.Fatalf("rec c: %v", err)
	}
	page, err := a.TransactionHistory(TransactionFilter{Status: PaymentStatusSettled})
	if err != nil {
		t.Fatalf("history: %v", err)
	}
	if page.Total != 1 || page.Records[0].ID != "b" {
		t.Fatalf("expected 1 record id=b, got total=%d records=%v", page.Total, page.Records)
	}
}

func TestTransactionHistory_FilterBySlug(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	now := time.Now().Unix()
	_ = a.RecordPayment(makeRecord("a", "bot", PaymentStatusSigned, "1.0", now))
	_ = a.RecordPayment(makeRecord("b", "weather", PaymentStatusSigned, "2.0", now+1))
	page, err := a.TransactionHistory(TransactionFilter{EndpointSlug: "weather"})
	if err != nil {
		t.Fatalf("history: %v", err)
	}
	if page.Total != 1 || page.Records[0].EndpointSlug != "weather" {
		t.Fatalf("filter mismatch: %+v", page.Records)
	}
}

func TestTransactionHistory_FilterByTimeRange(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	base := int64(1_700_000_000)
	_ = a.RecordPayment(makeRecord("a", "bot", PaymentStatusSigned, "1", base))
	_ = a.RecordPayment(makeRecord("b", "bot", PaymentStatusSigned, "1", base+100))
	_ = a.RecordPayment(makeRecord("c", "bot", PaymentStatusSigned, "1", base+200))
	page, err := a.TransactionHistory(TransactionFilter{SinceUnix: base + 50, UntilUnix: base + 150})
	if err != nil {
		t.Fatalf("history: %v", err)
	}
	if page.Total != 1 || page.Records[0].ID != "b" {
		t.Fatalf("time-range filter mismatch: %+v", page.Records)
	}
}

func TestTransactionHistory_LimitDefault(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	now := time.Now().Unix()
	for i := 0; i < 75; i++ {
		_ = a.RecordPayment(makeRecord(string(rune('a'+i)), "bot", PaymentStatusSigned, "1", now+int64(i)))
	}
	page, err := a.TransactionHistory(TransactionFilter{})
	if err != nil {
		t.Fatalf("history: %v", err)
	}
	if len(page.Records) != defaultHistoryLimit {
		t.Fatalf("expected %d records (default limit), got %d", defaultHistoryLimit, len(page.Records))
	}
	if page.Total != 75 {
		t.Fatalf("expected total=75, got %d", page.Total)
	}
}

func TestTransactionHistory_TotalsExcludeFailed(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	now := time.Now().Unix()
	_ = a.RecordPayment(makeRecord("a", "bot", PaymentStatusSettled, "1.5", now))
	_ = a.RecordPayment(makeRecord("b", "bot", PaymentStatusSigned, "2.25", now))
	_ = a.RecordPayment(makeRecord("c", "bot", PaymentStatusFailed, "100", now))
	page, err := a.TransactionHistory(TransactionFilter{})
	if err != nil {
		t.Fatalf("history: %v", err)
	}
	if page.Totals.SpentLifetime != "3.75" {
		t.Fatalf("lifetime total = %q, want 3.75", page.Totals.SpentLifetime)
	}
	if page.Totals.SpentMonth != "3.75" {
		t.Fatalf("month total = %q, want 3.75", page.Totals.SpentMonth)
	}
}

func TestTransactionHistoryExportCSV(t *testing.T) {
	newTestPaymentsDB(t)
	a := &App{}
	now := time.Now().Unix()
	rec := makeRecord("a", "bot", PaymentStatusSettled, "1.5", now)
	rec.TxHash = "0xabc"
	rec.SettledUnix = now + 10
	if err := a.RecordPayment(rec); err != nil {
		t.Fatalf("record: %v", err)
	}

	csv, err := a.TransactionHistoryExportCSV(TransactionFilter{})
	if err != nil {
		t.Fatalf("export: %v", err)
	}
	lines := strings.Split(strings.TrimSpace(csv), "\n")
	if len(lines) != 2 {
		t.Fatalf("expected header + 1 row, got %d lines: %q", len(lines), csv)
	}
	if !strings.HasPrefix(lines[0], "id,timestamp_unix,") {
		t.Fatalf("unexpected header: %q", lines[0])
	}
	if !strings.Contains(lines[1], "0xabc") {
		t.Fatalf("expected tx hash in row, got %q", lines[1])
	}
	if !strings.Contains(lines[1], PaymentStatusSettled) {
		t.Fatalf("expected status in row, got %q", lines[1])
	}
}

func TestFormatBigFloat_Edges(t *testing.T) {
	// Lifetime aggregator empty → "0".
	newTestPaymentsDB(t)
	a := &App{}
	page, err := a.TransactionHistory(TransactionFilter{})
	if err != nil {
		t.Fatalf("history: %v", err)
	}
	if page.Totals.SpentLifetime != "0" {
		t.Fatalf("empty lifetime = %q, want 0", page.Totals.SpentLifetime)
	}
	if page.Totals.SpentMonth != "0" {
		t.Fatalf("empty month = %q, want 0", page.Totals.SpentMonth)
	}
}
