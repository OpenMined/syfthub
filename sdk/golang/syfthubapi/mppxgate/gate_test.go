package mppxgate

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/core/types"
	"github.com/openmined/syfthub/sdk/golang/mppx"
)

const testPrivKey = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
const testPrivKey2 = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"

// ── Mock RPC ─────────────────────────────────────────────────────────────────

// mockRPC is a tiny JSON-RPC mock copied/adapted from
// mppx/signed_transfer_test.go's signedTransferMockRPC. It is reproduced here
// because that type is package-private in mppx and the gate tests cannot
// import unexported helpers.
type mockRPC struct {
	mu               sync.Mutex
	pendingNonce     uint64
	latestNonce      uint64
	gasPrice         string
	sentRaw          []string
	receiptOverride  map[string]any
	autoMineReceipts bool

	// broadcastDelay, when non-zero, makes eth_sendRawTransaction sleep
	// before responding. Used by the concurrency test to make ordering
	// observable.
	broadcastDelay time.Duration
	broadcastOrder []string
	broadcastSeq   atomic.Int32
}

func newMockRPC() *mockRPC {
	return &mockRPC{
		gasPrice:         "0x3b9aca00",
		autoMineReceipts: true,
		receiptOverride:  map[string]any{},
	}
}

func (m *mockRPC) handle(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	var req map[string]any
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	method, _ := req["method"].(string)
	id := req["id"]
	params, _ := req["params"].([]any)
	respond := func(result any) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"jsonrpc": "2.0", "id": id, "result": result,
		})
	}
	switch method {
	case "eth_getTransactionCount":
		tag, _ := params[1].(string)
		m.mu.Lock()
		n := m.pendingNonce
		if tag == "latest" {
			n = m.latestNonce
		}
		m.mu.Unlock()
		respond("0x" + new(big.Int).SetUint64(n).Text(16))
	case "eth_gasPrice":
		respond(m.gasPrice)
	case "eth_sendRawTransaction":
		if m.broadcastDelay > 0 {
			time.Sleep(m.broadcastDelay)
		}
		raw, _ := params[0].(string)
		m.mu.Lock()
		m.sentRaw = append(m.sentRaw, raw)
		seq := m.broadcastSeq.Add(1)
		m.broadcastOrder = append(m.broadcastOrder, raw[:10]+"#"+itoa(int(seq)))
		m.mu.Unlock()
		rawBytes, _ := hex.DecodeString(strings.TrimPrefix(raw, "0x"))
		var tx types.Transaction
		if err := tx.UnmarshalBinary(rawBytes); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		hash := tx.Hash().Hex()
		m.mu.Lock()
		if _, has := m.receiptOverride[hash]; !has && m.autoMineReceipts {
			m.receiptOverride[hash] = map[string]any{"status": "0x1", "to": tx.To().Hex()}
		}
		m.mu.Unlock()
		respond(hash)
	case "eth_getTransactionReceipt":
		hash, _ := params[0].(string)
		m.mu.Lock()
		r, ok := m.receiptOverride[hash]
		m.mu.Unlock()
		if ok {
			respond(r)
		} else {
			respond(nil)
		}
	default:
		http.Error(w, "unknown method "+method, http.StatusBadRequest)
	}
}

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	var buf [20]byte
	pos := len(buf)
	for i > 0 {
		pos--
		buf[pos] = byte('0' + i%10)
		i /= 10
	}
	return string(buf[pos:])
}

// ── Helpers ──────────────────────────────────────────────────────────────────

func newTestGate(t *testing.T, rpcURL string) (*TempoGate, SecretStore) {
	t.Helper()
	store := NewStaticSecretStore(map[string][]byte{
		"default": []byte("alice-demo-secret-key-32-bytes!!"),
	})
	g, err := NewTempoGate(TempoGateOptions{
		RPCURL:  rpcURL,
		Secrets: store,
	})
	if err != nil {
		t.Fatalf("NewTempoGate: %v", err)
	}
	return g, store
}

func buildSpec() map[string]any {
	return map[string]any{
		specKeyPayTo:         "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		specKeyCurrency:      "0x20c0000000000000000000000000000000000000",
		specKeyDecimals:      6,
		specKeyChainID:       42431,
		specKeyAmount:        "1000000",
		specKeyRealm:         "syfthub:endpoint:alice/foo:x402",
		specKeyExpiresAtISO:  time.Now().Add(5 * time.Minute).UTC().Format(time.RFC3339Nano),
		specKeyHmacSecretKid: "default",
	}
}

// signTestCredential builds a real signed-transfer credential against the
// given gate+spec, using the test private key.
func signTestCredential(t *testing.T, g *TempoGate, rpcURL string, spec map[string]any, privKey string) string {
	t.Helper()
	resultMeta := map[string]any{}
	if err := g.BuildChallenge(context.Background(), spec, resultMeta); err != nil {
		t.Fatalf("BuildChallenge: %v", err)
	}
	wire, _ := resultMeta[MetaKeyPaymentChallenge].(string)
	ch, err := mppx.DeserializeChallenge(wire)
	if err != nil {
		t.Fatalf("DeserializeChallenge: %v", err)
	}
	acc, err := mppx.LoadAccount(privKey)
	if err != nil {
		t.Fatalf("LoadAccount: %v", err)
	}
	cred, err := mppx.SignSignedTransferCredential(context.Background(), ch, acc, rpcURL)
	if err != nil {
		t.Fatalf("SignSignedTransferCredential: %v", err)
	}
	serialized, err := mppx.SerializeCredential(cred)
	if err != nil {
		t.Fatalf("SerializeCredential: %v", err)
	}
	return serialized
}

// ── BuildChallenge ────────────────────────────────────────────────────────────

func TestBuildChallenge_PopulatesMetadata(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)
	spec := buildSpec()
	meta := map[string]any{}

	if err := g.BuildChallenge(context.Background(), spec, meta); err != nil {
		t.Fatalf("BuildChallenge: %v", err)
	}

	wire, ok := meta[MetaKeyPaymentChallenge].(string)
	if !ok || wire == "" {
		t.Fatalf("payment_challenge missing or empty")
	}
	if !strings.HasPrefix(wire, "Payment ") {
		t.Fatalf("wire should start with Payment scheme: %q", wire)
	}
	// Round-trip: the produced wire must parse back into a challenge
	// that mppx itself accepts.
	if _, err := mppx.DeserializeChallenge(wire); err != nil {
		t.Fatalf("DeserializeChallenge round-trip: %v", err)
	}
	if got, _ := meta[MetaKeyPaymentAmount].(string); got != "1000000" {
		t.Fatalf("payment_amount: %q", got)
	}
	if got, _ := meta[MetaKeyPaymentCurrency].(string); got == "" {
		t.Fatalf("payment_currency missing")
	}
	if got, _ := meta[MetaKeyChallengeID].(string); got == "" {
		t.Fatalf("challenge_id missing")
	}
}

func TestBuildChallenge_MissingSpecField(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)
	spec := buildSpec()
	delete(spec, specKeyAmount)
	if err := g.BuildChallenge(context.Background(), spec, map[string]any{}); err == nil {
		t.Fatal("expected error for missing amount")
	}
}

// ── PreVerify ─────────────────────────────────────────────────────────────────

func TestPreVerify_HappyPath(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)
	spec := buildSpec()
	credential := signTestCredential(t, g, srv.URL, spec, testPrivKey)

	meta := map[string]any{}
	if err := g.PreVerify(context.Background(), credential, meta); err != nil {
		t.Fatalf("PreVerify: %v", err)
	}
	if v, _ := meta[MetaKeyPaymentVerified].(bool); !v {
		t.Fatalf("payment_verified not true: %v", meta[MetaKeyPaymentVerified])
	}
	if id, _ := meta[MetaKeyPaymentChallengeID].(string); id == "" {
		t.Fatalf("payment_challenge_id empty")
	}
	if _, ok := meta[MetaKeyPaymentNonce].(uint64); !ok {
		t.Fatalf("payment_nonce missing or wrong type: %T", meta[MetaKeyPaymentNonce])
	}
	if hexStr, _ := meta[MetaKeyPaymentSignedTxHex].(string); !strings.HasPrefix(hexStr, "0x") {
		t.Fatalf("payment_signed_tx_hex missing or wrong: %q", hexStr)
	}
}

func TestPreVerify_InvalidCredential(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)
	meta := map[string]any{}
	if err := g.PreVerify(context.Background(), "Payment not-base64!!!", meta); err == nil {
		t.Fatal("expected error for invalid credential")
	}
	if _, ok := meta[MetaKeyPaymentVerified]; ok {
		t.Fatal("payment_verified should not be set on error")
	}
}

func TestPreVerify_TamperedCredential(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)
	spec := buildSpec()
	credential := signTestCredential(t, g, srv.URL, spec, testPrivKey)

	// Deserialize, tamper, re-serialize.
	cred, err := mppx.DeserializeCredential(credential)
	if err != nil {
		t.Fatalf("deserialize: %v", err)
	}
	cred.Challenge.Request["recipient"] = "0x1111111111111111111111111111111111111111"
	tampered, err := mppx.SerializeCredential(cred)
	if err != nil {
		t.Fatalf("re-serialize: %v", err)
	}
	if err := g.PreVerify(context.Background(), tampered, map[string]any{}); err == nil {
		t.Fatal("expected HMAC failure")
	}
}

// ── SettleAfterHandler ────────────────────────────────────────────────────────

func TestSettleAfterHandler_Broadcasts(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)
	spec := buildSpec()
	credential := signTestCredential(t, g, srv.URL, spec, testPrivKey)

	meta := map[string]any{}
	if err := g.PreVerify(context.Background(), credential, meta); err != nil {
		t.Fatalf("PreVerify: %v", err)
	}
	if err := g.SettleAfterHandler(context.Background(), meta); err != nil {
		t.Fatalf("SettleAfterHandler: %v", err)
	}
	if got, _ := meta[MetaKeyPaymentStatus].(string); got != "success" {
		t.Fatalf("payment_status: %q", got)
	}
	receipt, ok := meta[MetaKeyPaymentReceipt].(map[string]any)
	if !ok {
		t.Fatalf("payment_receipt missing")
	}
	if ref, _ := receipt["reference"].(string); !strings.HasPrefix(ref, "0x") {
		t.Fatalf("receipt.reference: %v", receipt["reference"])
	}
	if _, ok := meta[MetaKeyPaymentSignedTxHex]; ok {
		t.Fatal("signed_tx should be dropped after broadcast")
	}
	if n := len(mock.sentRaw); n != 1 {
		t.Fatalf("expected 1 broadcast, got %d", n)
	}
}

func TestSettleAfterHandler_NoSignedTxIsNoop(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)
	meta := map[string]any{}
	if err := g.SettleAfterHandler(context.Background(), meta); err != nil {
		t.Fatalf("SettleAfterHandler: %v", err)
	}
	if len(mock.sentRaw) != 0 {
		t.Fatalf("no broadcast expected; got %d", len(mock.sentRaw))
	}
}

// TestSettleAfterHandler_SerializesPerPayer asserts the per-payer broadcast
// mutex actually serialises two simultaneous settles for the same payer.
// With a slow mock RPC, two concurrent settles must finish in
// total ~2 × broadcastDelay (sequential), not ~1× (parallel).
func TestSettleAfterHandler_SerializesPerPayer(t *testing.T) {
	mock := newMockRPC()
	mock.broadcastDelay = 200 * time.Millisecond
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)

	// Build two distinct charges so the signed-tx bytes differ, but both
	// signed by the same payer (testPrivKey) — so they share the same
	// payerMu and must serialise.
	specA := buildSpec()
	specA[specKeyAmount] = "1000000"
	credentialA := signTestCredential(t, g, srv.URL, specA, testPrivKey)

	specB := buildSpec()
	specB[specKeyAmount] = "2000000"
	credentialB := signTestCredential(t, g, srv.URL, specB, testPrivKey)

	metaA := map[string]any{}
	if err := g.PreVerify(context.Background(), credentialA, metaA); err != nil {
		t.Fatalf("PreVerify A: %v", err)
	}
	metaB := map[string]any{}
	if err := g.PreVerify(context.Background(), credentialB, metaB); err != nil {
		t.Fatalf("PreVerify B: %v", err)
	}

	start := time.Now()
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		_ = g.SettleAfterHandler(context.Background(), metaA)
	}()
	go func() {
		defer wg.Done()
		_ = g.SettleAfterHandler(context.Background(), metaB)
	}()
	wg.Wait()
	elapsed := time.Since(start)

	// Sequential ~ 400ms, parallel ~ 200ms. Allow generous slack but
	// require strictly more than 1.5× the delay so the test is not flaky
	// while still catching a missing mutex.
	if elapsed < 300*time.Millisecond {
		t.Fatalf("settles ran in parallel (elapsed=%s), per-payer mutex missing", elapsed)
	}
	if got := len(mock.sentRaw); got != 2 {
		t.Fatalf("expected 2 broadcasts, got %d", got)
	}
}

// TestSettleAfterHandler_DistinctPayersParallel asserts the per-payer mutex
// does NOT serialise across distinct payers — two payers should settle
// concurrently.
func TestSettleAfterHandler_DistinctPayersParallel(t *testing.T) {
	mock := newMockRPC()
	mock.broadcastDelay = 200 * time.Millisecond
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	g, _ := newTestGate(t, srv.URL)
	spec := buildSpec()

	credA := signTestCredential(t, g, srv.URL, spec, testPrivKey)
	credB := signTestCredential(t, g, srv.URL, spec, testPrivKey2)

	metaA := map[string]any{}
	_ = g.PreVerify(context.Background(), credA, metaA)
	metaB := map[string]any{}
	_ = g.PreVerify(context.Background(), credB, metaB)

	start := time.Now()
	var wg sync.WaitGroup
	wg.Add(2)
	go func() { defer wg.Done(); _ = g.SettleAfterHandler(context.Background(), metaA) }()
	go func() { defer wg.Done(); _ = g.SettleAfterHandler(context.Background(), metaB) }()
	wg.Wait()
	elapsed := time.Since(start)

	// Distinct payers should overlap; total should be under 1.8x the delay.
	if elapsed > 350*time.Millisecond {
		t.Fatalf("distinct-payer settles serialised (elapsed=%s) — over-locking", elapsed)
	}
}

// ── FileSecretStore ──────────────────────────────────────────────────────────

func TestFileSecretStore_RoundTrip(t *testing.T) {
	dir := t.TempDir()
	store := NewFileSecretStore(dir)

	first, err := store.Get("default")
	if err != nil {
		t.Fatalf("first Get: %v", err)
	}
	if len(first) != 32 {
		t.Fatalf("expected 32 bytes, got %d", len(first))
	}
	second, err := store.Get("default")
	if err != nil {
		t.Fatalf("second Get: %v", err)
	}
	if string(first) != string(second) {
		t.Fatalf("secrets differ between Gets")
	}
	// File perms must be 0600.
	info, err := os.Stat(filepath.Join(dir, "default.key"))
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Fatalf("file perm: %o (want 0600)", perm)
	}
}

func TestFileSecretStore_DistinctKids(t *testing.T) {
	dir := t.TempDir()
	store := NewFileSecretStore(dir)

	a, err := store.Get("kid-a")
	if err != nil {
		t.Fatalf("kid-a: %v", err)
	}
	b, err := store.Get("kid-b")
	if err != nil {
		t.Fatalf("kid-b: %v", err)
	}
	if string(a) == string(b) {
		t.Fatal("two kids returned same secret")
	}
}

func TestFileSecretStore_RejectsBadKid(t *testing.T) {
	store := NewFileSecretStore(t.TempDir())
	for _, bad := range []string{"", "..", ".", "a/b", "a\\b"} {
		if _, err := store.Get(bad); err == nil {
			t.Errorf("expected error for kid %q", bad)
		}
	}
}

// ── Wallet ───────────────────────────────────────────────────────────────────

func TestLoadLocalWallet_RoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "wallet.key")
	if err := os.WriteFile(path, []byte(testPrivKey+"\n"), 0o600); err != nil {
		t.Fatalf("write: %v", err)
	}
	acc, err := LoadLocalWallet(path)
	if err != nil {
		t.Fatalf("LoadLocalWallet: %v", err)
	}
	want := "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
	if !strings.EqualFold(acc.Address().Hex(), want) {
		t.Fatalf("address: %s want %s", acc.Address().Hex(), want)
	}
}

func TestLoadLocalWallet_MissingFile(t *testing.T) {
	if _, err := LoadLocalWallet(filepath.Join(t.TempDir(), "missing.key")); err == nil {
		t.Fatal("expected error for missing file")
	}
}

func TestMustMatchPayTo(t *testing.T) {
	acc, err := mppx.LoadAccount(testPrivKey)
	if err != nil {
		t.Fatalf("LoadAccount: %v", err)
	}
	addr := acc.Address().Hex()

	if err := MustMatchPayTo(acc, addr); err != nil {
		t.Fatalf("exact match: %v", err)
	}
	if err := MustMatchPayTo(acc, strings.ToLower(addr)); err != nil {
		t.Fatalf("case-insensitive: %v", err)
	}
	if err := MustMatchPayTo(acc, "0x0000000000000000000000000000000000000000"); err == nil {
		t.Fatal("expected mismatch")
	}
	if err := MustMatchPayTo(nil, addr); err == nil {
		t.Fatal("expected nil-account error")
	}
	if err := MustMatchPayTo(acc, ""); err == nil {
		t.Fatal("expected empty-expected error")
	}
}
