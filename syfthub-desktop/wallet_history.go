// Package main provides the SQLite-backed payment history ledger for the
// consumer wallet.
//
// Every credential the desktop signs (WalletPayChallenge) is persisted to a
// local SQLite database so the user can see what they paid for, when, and
// for which endpoint. The producer later reports the on-chain receipt back
// via UpdateSettlement, which flips the row's status from "signed" to
// "settled" or "failed".
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"

	_ "modernc.org/sqlite" // pure-Go SQLite driver, registered as "sqlite"
)

// paymentDBFilename is the filename of the payment ledger inside walletDir().
const paymentDBFilename = "payments.db"

// defaultHistoryLimit / maxHistoryLimit clamp the page size accepted by
// TransactionHistory so the frontend cannot accidentally OOM itself by
// asking for the entire ledger at once.
const (
	defaultHistoryLimit = 50
	maxHistoryLimit     = 500
)

// Valid payment statuses. The enum is intentionally open at the DB layer
// (status is a TEXT column) so future statuses can be added without a
// schema change.
const (
	PaymentStatusSigned    = "signed"
	PaymentStatusBroadcast = "broadcast"
	PaymentStatusSettled   = "settled"
	PaymentStatusFailed    = "failed"
	PaymentStatusRefunded  = "refunded"
)

// PaymentRecord is one row of the payment ledger. Field order matches the
// SQL schema; JSON tags use snake_case for parity with the rest of the
// frontend payloads.
type PaymentRecord struct {
	ID             string `json:"id"`
	TimestampUnix  int64  `json:"timestamp_unix"`
	EndpointOwner  string `json:"endpoint_owner"`
	EndpointSlug   string `json:"endpoint_slug"`
	EndpointLabel  string `json:"endpoint_label,omitempty"`
	Amount         string `json:"amount"`
	Currency       string `json:"currency"`
	ChainID        uint64 `json:"chain_id"`
	ChallengeID    string `json:"challenge_id"`
	CredentialHex  string `json:"credential_hex"`
	TxHash         string `json:"tx_hash,omitempty"`
	Status         string `json:"status"`
	FailureReason  string `json:"failure_reason,omitempty"`
	RequestSummary string `json:"request_summary,omitempty"`
	SettledUnix    int64  `json:"settled_unix,omitempty"`
}

// TransactionFilter is the optional set of WHERE clauses that narrow a
// TransactionHistory query. All zero-valued fields are ignored.
type TransactionFilter struct {
	EndpointSlug string `json:"endpoint_slug,omitempty"`
	Status       string `json:"status,omitempty"`
	SinceUnix    int64  `json:"since_unix,omitempty"`
	UntilUnix    int64  `json:"until_unix,omitempty"`
	Limit        int    `json:"limit,omitempty"`
}

// TransactionPage is the response shape for TransactionHistory: the page of
// matching records plus the total count and aggregate spending totals so the
// frontend can render summary cards without a follow-up query.
type TransactionPage struct {
	Records []PaymentRecord `json:"records"`
	Total   int             `json:"total"`
	Totals  PaymentTotals   `json:"totals"`
}

// PaymentTotals are the three "amount-paid" rollups shown in the history
// view: lifetime, this-month, and this-session (since app start, tracked
// in-memory by sessionStartUnix).
type PaymentTotals struct {
	SpentLifetime string `json:"spent_lifetime"`
	SpentMonth    string `json:"spent_month"`
	SpentSession  string `json:"spent_session"`
}

// SQL DDL. Kept as constants so tests can exec them against an in-memory
// pool without going through openPaymentsDB.
const (
	paymentsCreateTable = `
CREATE TABLE IF NOT EXISTS payments (
    id              TEXT PRIMARY KEY,
    timestamp_unix  INTEGER NOT NULL,
    endpoint_owner  TEXT NOT NULL,
    endpoint_slug   TEXT NOT NULL,
    endpoint_label  TEXT,
    amount          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    chain_id        INTEGER NOT NULL,
    challenge_id    TEXT NOT NULL,
    credential_hex  TEXT NOT NULL,
    tx_hash         TEXT,
    status          TEXT NOT NULL,
    failure_reason  TEXT,
    request_summary TEXT,
    settled_unix    INTEGER
)`
	paymentsCreateEndpointIdx = `
CREATE INDEX IF NOT EXISTS idx_payments_endpoint
ON payments(endpoint_slug, timestamp_unix DESC)`
	paymentsCreateStatusIdx = `
CREATE INDEX IF NOT EXISTS idx_payments_status
ON payments(status, timestamp_unix DESC)`
)

// paymentsHandle caches the lazily-opened *sql.DB for the ledger. One per
// process. The err field stores any open/migrate failure so subsequent
// callers see the same error rather than retrying with disk I/O.
type paymentsHandle struct {
	db  *sql.DB
	err error
}

// App-scoped lazy SQLite singleton plus the in-memory session start clock
// used by PaymentTotals.SpentSession.
//
// These two pieces of state are intentionally kept as package-level vars
// (not fields on App) because:
//   - tests that exercise the handlers construct &App{} directly and would
//     otherwise need every test to wire a sync.Once+DB themselves
//   - paymentsTestDB lets tests inject an in-memory :memory: pool, which is
//     impossible if the DB lives behind an unexported sync.Once on App
//
// In production, sessionStartUnix is set to time.Now() the first time
// paymentsDB() runs — i.e. on first call to any payments handler. That
// matches the requirement that "session" means "since app start".
var (
	paymentsOnce     sync.Once
	paymentsCache    paymentsHandle
	paymentsTestDB   *sql.DB
	sessionStartOnce sync.Once
	sessionStartUnix int64
)

// initSessionStart captures the per-process clock used for SpentSession
// totals. Called from paymentsDB so the timer starts at first DB access
// (which is the first wallet-aware action the user takes after launch).
func initSessionStart() {
	sessionStartOnce.Do(func() {
		sessionStartUnix = time.Now().Unix()
	})
}

// paymentDBPath resolves the absolute path of the ledger file.
func paymentDBPath() (string, error) {
	dir, err := walletDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, paymentDBFilename), nil
}

// openPaymentsDB opens (or creates) the ledger database, runs the idempotent
// DDL and returns a connection pool. WAL + busy_timeout let the UI thread
// read history while a background WalletPayChallenge inserts a row.
func openPaymentsDB() (*sql.DB, error) {
	path, err := paymentDBPath()
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("create wallet directory: %w", err)
	}
	dsn := "file:" + path + "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open payments db: %w", err)
	}
	db.SetMaxOpenConns(4)
	db.SetMaxIdleConns(2)
	if err := initPaymentsSchema(db); err != nil {
		_ = db.Close()
		return nil, err
	}
	return db, nil
}

// initPaymentsSchema runs the DDL exec sequence. Exported as its own helper
// so tests using an in-memory pool can prime the schema directly.
func initPaymentsSchema(db *sql.DB) error {
	for _, stmt := range []string{
		paymentsCreateTable,
		paymentsCreateEndpointIdx,
		paymentsCreateStatusIdx,
	} {
		if _, err := db.Exec(stmt); err != nil {
			return fmt.Errorf("init payments schema: %w", err)
		}
	}
	return nil
}

// paymentsDB returns the cached *sql.DB, opening on first call. Tests can
// override the pool entirely by setting paymentsTestDB before the first
// call (or by calling resetPaymentsDBForTest in between cases).
func paymentsDB() (*sql.DB, error) {
	initSessionStart()
	if db := paymentsTestDB; db != nil {
		return db, nil
	}
	paymentsOnce.Do(func() {
		db, err := openPaymentsDB()
		paymentsCache = paymentsHandle{db: db, err: err}
	})
	if paymentsCache.err != nil {
		return nil, paymentsCache.err
	}
	if paymentsCache.db == nil {
		return nil, errors.New("payments db unavailable")
	}
	return paymentsCache.db, nil
}

// resetPaymentsDBForTest clears the cached pool so the next paymentsDB call
// re-opens it. The supplied pool, if non-nil, becomes the override returned
// by paymentsDB until cleared again.
func resetPaymentsDBForTest(override *sql.DB) {
	paymentsOnce = sync.Once{}
	if paymentsCache.db != nil && paymentsCache.db != override {
		_ = paymentsCache.db.Close()
	}
	paymentsCache = paymentsHandle{}
	paymentsTestDB = override
	sessionStartOnce = sync.Once{}
	sessionStartUnix = 0
}

// ── Wails handlers ─────────────────────────────────────────────────────────

// RecordPayment inserts a new payment row. ID and TimestampUnix must be
// pre-populated by the caller (WalletPayChallenge does this); a zero
// TimestampUnix is back-filled with the current time as a safety net.
func (a *App) RecordPayment(rec PaymentRecord) error {
	if rec.ID == "" {
		return errors.New("payment id is required")
	}
	if rec.ChallengeID == "" {
		return errors.New("challenge id is required")
	}
	if rec.Status == "" {
		rec.Status = PaymentStatusSigned
	}
	if rec.TimestampUnix == 0 {
		rec.TimestampUnix = time.Now().Unix()
	}
	db, err := paymentsDB()
	if err != nil {
		return err
	}
	const stmt = `
INSERT INTO payments (
    id, timestamp_unix, endpoint_owner, endpoint_slug, endpoint_label,
    amount, currency, chain_id, challenge_id, credential_hex,
    tx_hash, status, failure_reason, request_summary, settled_unix
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`
	_, err = db.Exec(stmt,
		rec.ID, rec.TimestampUnix, rec.EndpointOwner, rec.EndpointSlug, nullableString(rec.EndpointLabel),
		rec.Amount, rec.Currency, int64(rec.ChainID), rec.ChallengeID, rec.CredentialHex,
		nullableString(rec.TxHash), rec.Status, nullableString(rec.FailureReason), nullableString(rec.RequestSummary), nullableInt64(rec.SettledUnix),
	)
	if err != nil {
		return fmt.Errorf("insert payment: %w", err)
	}
	if a != nil && a.ctx != nil {
		runtime.EventsEmit(a.ctx, "wallet:payment-recorded", rec)
	}
	return nil
}

// UpdateSettlement updates an existing row identified by challenge_id with
// the broadcast/settlement outcome reported by the producer. Returns an
// error wrapping sql.ErrNoRows when no row matches.
func (a *App) UpdateSettlement(challengeID, txHash, status, failureReason string, settledUnix int64) error {
	if challengeID == "" {
		return errors.New("challenge id is required")
	}
	if status == "" {
		return errors.New("status is required")
	}
	db, err := paymentsDB()
	if err != nil {
		return err
	}
	const stmt = `
UPDATE payments
SET tx_hash = ?, status = ?, failure_reason = ?, settled_unix = ?
WHERE challenge_id = ?`
	res, err := db.Exec(stmt,
		nullableString(txHash),
		status,
		nullableString(failureReason),
		nullableInt64(settledUnix),
		challengeID,
	)
	if err != nil {
		return fmt.Errorf("update settlement: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("update settlement rows: %w", err)
	}
	if n == 0 {
		return fmt.Errorf("no payment found for challenge %s: %w", challengeID, sql.ErrNoRows)
	}
	if a != nil && a.ctx != nil {
		runtime.EventsEmit(a.ctx, "wallet:payment-settled", map[string]any{
			"challenge_id": challengeID,
			"status":       status,
			"tx_hash":      txHash,
		})
	}
	return nil
}

// TransactionHistory returns a page of payment rows matching the filter plus
// the aggregate totals across ALL rows ignoring the limit (so summary cards
// reflect lifetime, not just the current page).
func (a *App) TransactionHistory(filter TransactionFilter) (TransactionPage, error) {
	db, err := paymentsDB()
	if err != nil {
		return TransactionPage{}, err
	}
	limit := filter.Limit
	if limit <= 0 {
		limit = defaultHistoryLimit
	}
	if limit > maxHistoryLimit {
		limit = maxHistoryLimit
	}

	where, args := buildHistoryWhere(filter)

	rowsQuery := "SELECT id, timestamp_unix, endpoint_owner, endpoint_slug, endpoint_label, amount, currency, chain_id, challenge_id, credential_hex, tx_hash, status, failure_reason, request_summary, settled_unix FROM payments " +
		where + " ORDER BY timestamp_unix DESC LIMIT ?"
	queryArgs := append(append([]any{}, args...), limit)

	rows, err := db.Query(rowsQuery, queryArgs...)
	if err != nil {
		return TransactionPage{}, fmt.Errorf("query payments: %w", err)
	}
	defer rows.Close()

	records := make([]PaymentRecord, 0)
	for rows.Next() {
		rec, err := scanPaymentRow(rows)
		if err != nil {
			return TransactionPage{}, err
		}
		records = append(records, rec)
	}
	if err := rows.Err(); err != nil {
		return TransactionPage{}, fmt.Errorf("scan payments: %w", err)
	}

	// Total ignoring limit so the frontend can show "showing X of N".
	var total int
	if err := db.QueryRow("SELECT COUNT(*) FROM payments "+where, args...).Scan(&total); err != nil {
		return TransactionPage{}, fmt.Errorf("count payments: %w", err)
	}

	totals, err := computePaymentTotals(db)
	if err != nil {
		return TransactionPage{}, err
	}

	return TransactionPage{
		Records: records,
		Total:   total,
		Totals:  totals,
	}, nil
}

// TransactionHistoryExportCSV returns the filtered history as a CSV string.
// The frontend offers it as a download — the desktop process does not write
// the file directly because the user may prefer a custom location selected
// via the OS save dialog.
//
// Unlike TransactionHistory, this method does NOT clamp the limit: the
// expected use case is "export everything matching this filter".
func (a *App) TransactionHistoryExportCSV(filter TransactionFilter) (string, error) {
	db, err := paymentsDB()
	if err != nil {
		return "", err
	}
	where, args := buildHistoryWhere(filter)
	q := "SELECT id, timestamp_unix, endpoint_owner, endpoint_slug, endpoint_label, amount, currency, chain_id, challenge_id, credential_hex, tx_hash, status, failure_reason, request_summary, settled_unix FROM payments " +
		where + " ORDER BY timestamp_unix DESC"
	rows, err := db.Query(q, args...)
	if err != nil {
		return "", fmt.Errorf("export query: %w", err)
	}
	defer rows.Close()

	var buf bytes.Buffer
	w := csv.NewWriter(&buf)
	header := []string{
		"id", "timestamp_unix", "endpoint_owner", "endpoint_slug", "endpoint_label",
		"amount", "currency", "chain_id", "challenge_id",
		"tx_hash", "status", "failure_reason", "request_summary", "settled_unix",
	}
	if err := w.Write(header); err != nil {
		return "", fmt.Errorf("csv header: %w", err)
	}
	for rows.Next() {
		rec, err := scanPaymentRow(rows)
		if err != nil {
			return "", err
		}
		row := []string{
			rec.ID,
			strconv.FormatInt(rec.TimestampUnix, 10),
			rec.EndpointOwner,
			rec.EndpointSlug,
			rec.EndpointLabel,
			rec.Amount,
			rec.Currency,
			strconv.FormatUint(rec.ChainID, 10),
			rec.ChallengeID,
			rec.TxHash,
			rec.Status,
			rec.FailureReason,
			rec.RequestSummary,
			settledUnixCSV(rec.SettledUnix),
		}
		if err := w.Write(row); err != nil {
			return "", fmt.Errorf("csv row: %w", err)
		}
	}
	if err := rows.Err(); err != nil {
		return "", fmt.Errorf("csv scan: %w", err)
	}
	w.Flush()
	if err := w.Error(); err != nil {
		return "", fmt.Errorf("csv flush: %w", err)
	}
	return buf.String(), nil
}

// ── internal helpers ───────────────────────────────────────────────────────

// scanPaymentRow centralises the column-order-sensitive Scan call so the row
// reader and the export path stay in sync if a column is ever added.
// Accepts both *sql.Row and *sql.Rows via the package-level rowScanner
// interface (defined in review_routing.go).
func scanPaymentRow(r rowScanner) (PaymentRecord, error) {
	var (
		rec            PaymentRecord
		endpointLabel  sql.NullString
		txHash         sql.NullString
		failureReason  sql.NullString
		requestSummary sql.NullString
		settledUnix    sql.NullInt64
		chainID        int64
	)
	if err := r.Scan(
		&rec.ID, &rec.TimestampUnix, &rec.EndpointOwner, &rec.EndpointSlug,
		&endpointLabel, &rec.Amount, &rec.Currency, &chainID,
		&rec.ChallengeID, &rec.CredentialHex,
		&txHash, &rec.Status, &failureReason, &requestSummary, &settledUnix,
	); err != nil {
		return PaymentRecord{}, fmt.Errorf("scan payment row: %w", err)
	}
	rec.ChainID = uint64(chainID)
	if endpointLabel.Valid {
		rec.EndpointLabel = endpointLabel.String
	}
	if txHash.Valid {
		rec.TxHash = txHash.String
	}
	if failureReason.Valid {
		rec.FailureReason = failureReason.String
	}
	if requestSummary.Valid {
		rec.RequestSummary = requestSummary.String
	}
	if settledUnix.Valid {
		rec.SettledUnix = settledUnix.Int64
	}
	return rec, nil
}

// buildHistoryWhere translates the filter into a parameterised WHERE clause.
// Returns ("", nil) when no fields are set so the caller can concatenate it
// freely without producing a syntax error.
func buildHistoryWhere(f TransactionFilter) (string, []any) {
	var clauses []string
	var args []any
	if f.EndpointSlug != "" {
		clauses = append(clauses, "endpoint_slug = ?")
		args = append(args, f.EndpointSlug)
	}
	if f.Status != "" {
		clauses = append(clauses, "status = ?")
		args = append(args, f.Status)
	}
	if f.SinceUnix > 0 {
		clauses = append(clauses, "timestamp_unix >= ?")
		args = append(args, f.SinceUnix)
	}
	if f.UntilUnix > 0 {
		clauses = append(clauses, "timestamp_unix <= ?")
		args = append(args, f.UntilUnix)
	}
	if len(clauses) == 0 {
		return "", nil
	}
	return "WHERE " + strings.Join(clauses, " AND "), args
}

// computePaymentTotals sums the amount column across three time windows.
// Amounts are stored as decimal strings so we accumulate with big.Float for
// precision; the result is formatted back to a plain decimal string.
//
// Failed and refunded rows are excluded — the user only "spent" funds that
// actually settled or are still in flight.
func computePaymentTotals(db *sql.DB) (PaymentTotals, error) {
	const q = `
SELECT timestamp_unix, amount
FROM payments
WHERE status NOT IN ('failed', 'refunded')`
	rows, err := db.Query(q)
	if err != nil {
		return PaymentTotals{}, fmt.Errorf("totals query: %w", err)
	}
	defer rows.Close()

	now := time.Now()
	monthStart := time.Date(now.Year(), now.Month(), 1, 0, 0, 0, 0, now.Location()).Unix()
	sessionStart := sessionStartUnix

	lifetime := new(big.Float).SetPrec(128)
	month := new(big.Float).SetPrec(128)
	session := new(big.Float).SetPrec(128)

	for rows.Next() {
		var ts int64
		var amount string
		if err := rows.Scan(&ts, &amount); err != nil {
			return PaymentTotals{}, fmt.Errorf("totals scan: %w", err)
		}
		v, ok := new(big.Float).SetPrec(128).SetString(strings.TrimSpace(amount))
		if !ok {
			// Skip rows with un-parseable amounts rather than failing the
			// whole call — totals are advisory.
			continue
		}
		lifetime.Add(lifetime, v)
		if ts >= monthStart {
			month.Add(month, v)
		}
		if sessionStart > 0 && ts >= sessionStart {
			session.Add(session, v)
		}
	}
	if err := rows.Err(); err != nil {
		return PaymentTotals{}, fmt.Errorf("totals iter: %w", err)
	}
	return PaymentTotals{
		SpentLifetime: formatBigFloat(lifetime),
		SpentMonth:    formatBigFloat(month),
		SpentSession:  formatBigFloat(session),
	}, nil
}

// formatBigFloat prints a big.Float with up to 6 fractional digits and
// strips trailing zeros / trailing decimal point so display values are clean
// ("1.5" not "1.500000"). Zero comes back as "0".
func formatBigFloat(f *big.Float) string {
	if f == nil {
		return "0"
	}
	s := f.Text('f', pathUSDDecimals)
	if strings.Contains(s, ".") {
		s = strings.TrimRight(s, "0")
		s = strings.TrimRight(s, ".")
	}
	if s == "" || s == "-" {
		return "0"
	}
	return s
}

// nullableString returns a sql.NullString that is NULL when s is empty.
// Keeps the schema honest: empty TEXT columns are stored as NULL rather
// than empty strings, so callers can use IS NULL in queries if needed.
func nullableString(s string) sql.NullString {
	if s == "" {
		return sql.NullString{}
	}
	return sql.NullString{String: s, Valid: true}
}

// nullableInt64 returns sql.NullInt64{Valid:false} for zero so the
// settled_unix column reads as NULL until UpdateSettlement runs.
func nullableInt64(v int64) sql.NullInt64 {
	if v == 0 {
		return sql.NullInt64{}
	}
	return sql.NullInt64{Int64: v, Valid: true}
}

// settledUnixCSV renders the optional settled_unix column for CSV export.
// Zero (== NULL) becomes the empty string so spreadsheet importers don't
// interpret an artificial epoch timestamp.
func settledUnixCSV(v int64) string {
	if v == 0 {
		return ""
	}
	return strconv.FormatInt(v, 10)
}

// newPaymentID mints a fresh 16-byte hex-encoded random id for a payment
// row. Crypto-quality randomness is not required (the id is local-only) but
// we use crypto/rand via the existing google/uuid dep already in go.mod to
// avoid pulling in math/rand and the noise around seeding it.
func newPaymentID() string {
	var b [16]byte
	if _, err := readRandom(b[:]); err != nil {
		// Last-resort fallback: unique-enough but not random. Should never
		// trigger because crypto/rand on a healthy system does not fail.
		return fmt.Sprintf("pay-%d", time.Now().UnixNano())
	}
	return "pay-" + hex.EncodeToString(b[:])
}

// readRandom is overridable for tests that want deterministic IDs.
var readRandom = cryptoRandRead

// cryptoRandRead is the production implementation — pulled out into a var so
// tests can swap it without importing crypto/rand themselves.
func cryptoRandRead(b []byte) (int, error) {
	return rand.Read(b)
}

// httpEthCall implements ethCallSender against the real network. Lives here
// (next to the other JSON-RPC helpers) so wallet_operations.go does not need
// to import net/http directly.
func httpEthCall(ctx context.Context, rpc, contract, dataHex string) (string, error) {
	body := map[string]any{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  "eth_call",
		"params": []any{
			map[string]any{"to": contract, "data": dataHex},
			"latest",
		},
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, rpc, bytes.NewReader(payload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode/100 != 2 {
		return "", fmt.Errorf("rpc http %d: %s", resp.StatusCode, strings.TrimSpace(string(raw)))
	}
	var out struct {
		Result string         `json:"result"`
		Error  map[string]any `json:"error"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return "", fmt.Errorf("rpc decode: %w", err)
	}
	if out.Error != nil {
		return "", fmt.Errorf("rpc error: %v", out.Error)
	}
	return out.Result, nil
}
