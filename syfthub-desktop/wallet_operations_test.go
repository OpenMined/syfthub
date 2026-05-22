package main

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
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/core/types"
	"github.com/openmined/syfthub/sdk/golang/mppx"
)

// withTempHome redirects os.UserHomeDir() at the env-var level so wallet
// files land in a t.TempDir(). On Windows this would need USERPROFILE — we
// skip Windows in the build matrix for these tests.
func withTempHome(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	if runtime.GOOS == "windows" {
		t.Skip("home redirect only validated on unix-like OSes")
	}
	t.Setenv("HOME", dir)
	return dir
}

func TestWalletInit_GeneratesKeyWith0600Perms(t *testing.T) {
	home := withTempHome(t)
	a := &App{}
	info, err := a.WalletInit()
	if err != nil {
		t.Fatalf("WalletInit: %v", err)
	}
	if !info.KeyExists {
		t.Fatalf("expected KeyExists=true after init")
	}
	if info.Address == "" {
		t.Fatalf("expected non-empty address")
	}
	if info.ChainID != defaultChainID {
		t.Fatalf("ChainID = %d, want %d", info.ChainID, defaultChainID)
	}

	keyFile := filepath.Join(home, walletDirName, walletKeyFilename)
	st, err := os.Stat(keyFile)
	if err != nil {
		t.Fatalf("stat key file: %v", err)
	}
	if mode := st.Mode().Perm(); mode != 0o600 {
		t.Fatalf("key file mode = %o, want 0600", mode)
	}
}

func TestWalletInit_ReloadReturnsSameAddress(t *testing.T) {
	withTempHome(t)
	a := &App{}

	first, err := a.WalletInit()
	if err != nil {
		t.Fatalf("WalletInit #1: %v", err)
	}
	second, err := a.WalletInit()
	if err != nil {
		t.Fatalf("WalletInit #2: %v", err)
	}
	if first.Address != second.Address {
		t.Fatalf("address rotated: %s -> %s", first.Address, second.Address)
	}

	show, err := a.WalletShow()
	if err != nil {
		t.Fatalf("WalletShow: %v", err)
	}
	if !show.KeyExists {
		t.Fatalf("expected KeyExists=true on show after init")
	}
	if show.Address != first.Address {
		t.Fatalf("WalletShow address mismatch: %s vs %s", show.Address, first.Address)
	}
}

func TestWalletShow_NoKey(t *testing.T) {
	withTempHome(t)
	a := &App{}
	info, err := a.WalletShow()
	if err != nil {
		t.Fatalf("WalletShow no key: %v", err)
	}
	if info.KeyExists {
		t.Fatalf("expected KeyExists=false on fresh dir")
	}
	if info.Address != "" {
		t.Fatalf("expected empty address; got %q", info.Address)
	}
	if info.Network != walletNetwork {
		t.Fatalf("Network = %q, want %q", info.Network, walletNetwork)
	}
}

func TestRPCURL_EnvOverride(t *testing.T) {
	t.Setenv(rpcEnvVar, "http://localhost:8545")
	if got := rpcURL(); got != "http://localhost:8545" {
		t.Fatalf("rpcURL = %q, want override", got)
	}
	t.Setenv(rpcEnvVar, "")
	if got := rpcURL(); got != defaultRPCURL {
		t.Fatalf("rpcURL = %q, want default", got)
	}
}

func TestFormatDecimalAmount(t *testing.T) {
	cases := []struct {
		raw      string
		decimals int
		want     string
	}{
		{"1000000", 6, "1"},
		{"1234567", 6, "1.234567"},
		{"100", 6, "0.0001"},
		{"0", 6, "0"},
		{"500000", 6, "0.5"},
		{"", 6, ""}, // pass-through on parse failure
	}
	for _, tc := range cases {
		got := formatDecimalAmount(tc.raw, tc.decimals)
		if got != tc.want {
			t.Errorf("formatDecimalAmount(%q, %d) = %q, want %q", tc.raw, tc.decimals, got, tc.want)
		}
	}
}

func TestParseRealmEndpoint(t *testing.T) {
	cases := []struct {
		realm string
		owner string
		slug  string
	}{
		{"alice/bot", "alice", "bot"},
		{"pubsub://alice/bot", "alice", "bot"},
		{"alice", "alice", ""},
		{"", "", ""},
	}
	for _, tc := range cases {
		o, s := parseRealmEndpoint(tc.realm)
		if o != tc.owner || s != tc.slug {
			t.Errorf("parseRealmEndpoint(%q) = (%q, %q), want (%q, %q)", tc.realm, o, s, tc.owner, tc.slug)
		}
	}
}

// rpcMock mimics the subset of JSON-RPC needed by SignSignedTransferCredential.
type rpcMock struct {
	mu       sync.Mutex
	sentRaw  []string
	gasPrice string
}

func newRPCMock() *rpcMock { return &rpcMock{gasPrice: "0x3b9aca00"} }

func (m *rpcMock) handle(w http.ResponseWriter, r *http.Request) {
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
		_ = json.NewEncoder(w).Encode(map[string]any{"jsonrpc": "2.0", "id": id, "result": result})
	}
	switch method {
	case "eth_getTransactionCount":
		respond("0x0")
	case "eth_gasPrice":
		respond(m.gasPrice)
	case "eth_sendRawTransaction":
		raw, _ := params[0].(string)
		m.mu.Lock()
		m.sentRaw = append(m.sentRaw, raw)
		m.mu.Unlock()
		rawBytes, _ := hex.DecodeString(strings.TrimPrefix(raw, "0x"))
		var tx types.Transaction
		if err := tx.UnmarshalBinary(rawBytes); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		respond(tx.Hash().Hex())
	case "eth_call":
		// Return a 32-byte balance of 5 pathUSD (5 * 10^6 = 5_000_000 = 0x4c4b40)
		respond("0x" + leftPadHex("4c4b40", 64))
	default:
		http.Error(w, "unknown method "+method, http.StatusBadRequest)
	}
}

func leftPadHex(s string, width int) string {
	if len(s) >= width {
		return s
	}
	return strings.Repeat("0", width-len(s)) + s
}

func TestWalletPayChallenge_RoundTrip(t *testing.T) {
	withTempHome(t)

	mock := newRPCMock()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	t.Setenv(rpcEnvVar, srv.URL)

	// Use an isolated payments DB so RecordPayment in the handler can succeed.
	resetPaymentsDBForTest(nil)
	t.Cleanup(func() { resetPaymentsDBForTest(nil) })

	a := &App{}

	// Build a challenge with a known secret so we can verify the credential.
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch, err := mppx.NewCharge(
		pathUSDContractAddress,
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		int(defaultChainID),
	).Amount("1.00").Decimals(pathUSDDecimals).Realm("alice/bot").
		ExpiresAt(time.Now().Add(5 * time.Minute)).WithSecretKey(secret).Build()
	if err != nil {
		t.Fatalf("build challenge: %v", err)
	}
	wireChallenge, err := mppx.SerializeChallenge(ch)
	if err != nil {
		t.Fatalf("serialize challenge: %v", err)
	}

	credWire, err := a.WalletPayChallenge(wireChallenge, "1.00", pathUSDContractAddress)
	if err != nil {
		t.Fatalf("WalletPayChallenge: %v", err)
	}
	if credWire == "" {
		t.Fatal("empty credential")
	}

	// Deserialize the credential and verify HMAC matches.
	cred, err := mppx.DeserializeCredential(credWire)
	if err != nil {
		t.Fatalf("deserialize credential: %v", err)
	}
	if cred.Challenge.ID != ch.ID {
		t.Fatalf("challenge id mismatch: %s vs %s", cred.Challenge.ID, ch.ID)
	}
	parsed, _, err := mppx.VerifySignedTransferCredential(context.Background(), cred, secret, srv.URL, time.Minute)
	if err != nil {
		t.Fatalf("verify credential: %v", err)
	}
	if parsed.Amount.Cmp(big.NewInt(1_000_000)) != 0 {
		t.Fatalf("amount: %s", parsed.Amount.String())
	}

	// A pending payment row should now exist.
	page, err := a.TransactionHistory(TransactionFilter{})
	if err != nil {
		t.Fatalf("TransactionHistory: %v", err)
	}
	if page.Total != 1 {
		t.Fatalf("expected 1 history row, got %d", page.Total)
	}
	if page.Records[0].ChallengeID != ch.ID {
		t.Fatalf("history row challenge id mismatch")
	}
	if page.Records[0].Status != PaymentStatusSigned {
		t.Fatalf("history row status = %q, want signed", page.Records[0].Status)
	}
}

func TestWalletPayChallenge_RejectsEmpty(t *testing.T) {
	withTempHome(t)
	resetPaymentsDBForTest(nil)
	t.Cleanup(func() { resetPaymentsDBForTest(nil) })
	a := &App{}
	if _, err := a.WalletPayChallenge("", "", ""); err == nil {
		t.Fatal("expected error on empty challenge")
	}
	if _, err := a.WalletPayChallenge("not a real challenge", "", ""); err == nil {
		t.Fatal("expected error on garbage challenge")
	}
}

func TestWalletBalance_ParsesEthCallResult(t *testing.T) {
	withTempHome(t)
	mock := newRPCMock()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	t.Setenv(rpcEnvVar, srv.URL)

	a := &App{}
	if _, err := a.WalletInit(); err != nil {
		t.Fatalf("WalletInit: %v", err)
	}

	bal, err := a.WalletBalance()
	if err != nil {
		t.Fatalf("WalletBalance: %v", err)
	}
	if bal.Currency != pathUSDContractAddress {
		t.Fatalf("currency = %q", bal.Currency)
	}
	if bal.Decimals != pathUSDDecimals {
		t.Fatalf("decimals = %d", bal.Decimals)
	}
	if bal.Amount != "5" {
		t.Fatalf("amount = %q, want 5 (5,000,000 with 6 decimals)", bal.Amount)
	}
	if bal.AsOfUnix == 0 {
		t.Fatalf("AsOfUnix not set")
	}
}

func TestWalletBalance_ErrorsWhenNoKey(t *testing.T) {
	withTempHome(t)
	a := &App{}
	if _, err := a.WalletBalance(); err == nil {
		t.Fatal("expected error when wallet not initialised")
	}
}
