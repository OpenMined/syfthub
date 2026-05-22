package mppx

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
)

// signedTransferMockRPC is a tiny JSON-RPC mock tailored to the
// signed-transfer flow. It tracks the "latest" nonce returned by
// `eth_getTransactionCount` (independent of the "pending" nonce returned to
// SignSignedTransferCredential) so freshness can be asserted.
type signedTransferMockRPC struct {
	mu               sync.Mutex
	requests         []map[string]any
	pendingNonce     uint64
	latestNonce      uint64
	gasPrice         string
	sentRaw          []string
	receiptOverride  map[string]any // hash → receipt JSON (overrides auto-mine)
	rejectBroadcast  bool
	autoMineReceipts bool
}

func newSignedTransferMockRPC() *signedTransferMockRPC {
	return &signedTransferMockRPC{
		gasPrice:         "0x3b9aca00", // 1 gwei
		autoMineReceipts: true,
		receiptOverride:  map[string]any{},
	}
}

func (m *signedTransferMockRPC) handle(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	var req map[string]any
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	m.mu.Lock()
	m.requests = append(m.requests, req)
	m.mu.Unlock()
	method, _ := req["method"].(string)
	id := req["id"]
	params, _ := req["params"].([]any)

	respond := func(result any) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"jsonrpc": "2.0",
			"id":      id,
			"result":  result,
		})
	}

	switch method {
	case "eth_getTransactionCount":
		tag, _ := params[1].(string)
		n := m.pendingNonce
		if tag == "latest" {
			n = m.latestNonce
		}
		respond("0x" + new(big.Int).SetUint64(n).Text(16))
	case "eth_gasPrice":
		respond(m.gasPrice)
	case "eth_sendRawTransaction":
		if m.rejectBroadcast {
			_ = json.NewEncoder(w).Encode(map[string]any{
				"jsonrpc": "2.0",
				"id":      id,
				"error":   map[string]any{"code": -32000, "message": "nonce too low"},
			})
			return
		}
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
		hash := tx.Hash().Hex()
		if _, has := m.receiptOverride[hash]; !has && m.autoMineReceipts {
			m.receiptOverride[hash] = map[string]any{"status": "0x1", "to": tx.To().Hex()}
		}
		respond(hash)
	case "eth_getTransactionReceipt":
		hash, _ := params[0].(string)
		if r, ok := m.receiptOverride[hash]; ok {
			respond(r)
		} else {
			respond(nil)
		}
	default:
		http.Error(w, "unknown method "+method, http.StatusBadRequest)
	}
}

// buildChargeChallenge returns a fully-built tempo/charge challenge bound to
// the given secret. Helper used across every test in this file.
func buildChargeChallenge(t *testing.T, secret []byte, expires time.Time) Challenge {
	t.Helper()
	ch, err := NewCharge(
		"0x20c0000000000000000000000000000000000000",
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("1.00").Decimals(6).Realm("pubsub://alice/pay").
		ExpiresAt(expires).WithSecretKey(secret).Build()
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	return ch
}

func TestSignSignedTransferCredential_DoesNotBroadcast(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	account, err := LoadAccount(testPrivKey)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))

	cred, err := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	if len(mock.sentRaw) != 0 {
		t.Fatalf("expected no broadcast, got %d", len(mock.sentRaw))
	}
	payload, err := decodeSignedTransferPayload(cred.Payload)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if payload.Type != CredentialTypeSignedTransfer {
		t.Fatalf("payload.type=%q", payload.Type)
	}
	if !strings.HasPrefix(payload.SignedTx, "0x") || len(payload.SignedTx) < 10 {
		t.Fatalf("signed_tx looks wrong: %q", payload.SignedTx)
	}
	if !strings.EqualFold(payload.From, account.Address().Hex()) {
		t.Fatalf("from %q != account address %q", payload.From, account.Address().Hex())
	}
}

func TestVerifySignedTransferCredential_HappyPath(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))
	cred, err := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}

	parsed, raw, err := VerifySignedTransferCredential(context.Background(), cred, secret, srv.URL, time.Minute)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if parsed.Amount.String() != "1000000" {
		t.Fatalf("amount: %s", parsed.Amount.String())
	}
	if len(raw) == 0 {
		t.Fatal("raw bytes empty")
	}
}

func TestVerifySignedTransferCredential_RejectsBadHMAC(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))
	cred, _ := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)

	if _, _, err := VerifySignedTransferCredential(context.Background(), cred, []byte("wrong-secret"), srv.URL, time.Minute); err == nil {
		t.Fatal("expected HMAC mismatch")
	}
}

func TestVerifySignedTransferCredential_TamperedChallengeFails(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))
	cred, _ := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)

	// Tamper with the recipient on the echoed challenge — HMAC must fail.
	cred.Challenge.Request["recipient"] = "0x1111111111111111111111111111111111111111"
	if _, _, err := VerifySignedTransferCredential(context.Background(), cred, secret, srv.URL, time.Minute); err == nil {
		t.Fatal("expected tamper-detection error")
	}
}

func TestVerifySignedTransferCredential_Expired(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(-1*time.Hour))
	cred, _ := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)

	if _, _, err := VerifySignedTransferCredential(context.Background(), cred, secret, srv.URL, time.Minute); err == nil {
		t.Fatal("expected expiry error")
	}
}

func TestVerifySignedTransferCredential_WrongCurrency(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")

	// Build challenge for token A, then sign a transfer targeting token B.
	chA := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))
	chB, err := NewCharge(
		"0x1111111111111111111111111111111111111111", // different token
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("1.00").Decimals(6).Realm("pubsub://alice/pay").
		ExpiresAt(time.Now().Add(5 * time.Minute)).WithSecretKey(secret).Build()
	if err != nil {
		t.Fatalf("build B: %v", err)
	}
	credB, err := SignSignedTransferCredential(context.Background(), chB, account, srv.URL)
	if err != nil {
		t.Fatalf("sign B: %v", err)
	}
	// Swap the challenge so the credential's payload targets B but the
	// challenge claims A. We re-sign the challenge swap with the HMAC by
	// using the freshly-built chA (same secret), keeping HMAC valid.
	credB.Challenge = chA

	if _, _, err := VerifySignedTransferCredential(context.Background(), credB, secret, srv.URL, time.Minute); err == nil {
		t.Fatal("expected currency mismatch")
	}
}

func TestVerifySignedTransferCredential_WrongAmount(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")

	chSmall, _ := NewCharge(
		"0x20c0000000000000000000000000000000000000",
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("0.50").Decimals(6).Realm("pubsub://alice/pay").
		ExpiresAt(time.Now().Add(5 * time.Minute)).WithSecretKey(secret).Build()
	chBig, _ := NewCharge(
		"0x20c0000000000000000000000000000000000000",
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("1.00").Decimals(6).Realm("pubsub://alice/pay").
		ExpiresAt(time.Now().Add(5 * time.Minute)).WithSecretKey(secret).Build()
	credBig, err := SignSignedTransferCredential(context.Background(), chBig, account, srv.URL)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	// Swap challenge so request says 0.50 but signed tx pays 1.00.
	credBig.Challenge = chSmall

	if _, _, err := VerifySignedTransferCredential(context.Background(), credBig, secret, srv.URL, time.Minute); err == nil {
		t.Fatal("expected amount mismatch")
	}
}

func TestVerifySignedTransferCredential_SenderMismatch(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))
	cred, _ := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)

	payload := cred.Payload.(TempoSignedTransferPayload)
	payload.From = "0x1111111111111111111111111111111111111111"
	cred.Payload = payload

	if _, _, err := VerifySignedTransferCredential(context.Background(), cred, secret, srv.URL, time.Minute); err == nil {
		t.Fatal("expected sender mismatch")
	}
}

func TestVerifySignedTransferCredential_StaleNonce(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))
	cred, err := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}

	// Advance the on-chain nonce past the tx's nonce — credential is stale.
	mock.latestNonce = cred.Payload.(TempoSignedTransferPayload).Nonce + 1

	if _, _, err := VerifySignedTransferCredential(context.Background(), cred, secret, srv.URL, time.Minute); err == nil {
		t.Fatal("expected stale-nonce error")
	}
}

func TestBroadcastSignedTransfer_HappyPath(t *testing.T) {
	mock := newSignedTransferMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))
	cred, err := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	signedTxHex := cred.Payload.(TempoSignedTransferPayload).SignedTx

	receipt, err := BroadcastSignedTransfer(context.Background(), signedTxHex, srv.URL)
	if err != nil {
		t.Fatalf("broadcast: %v", err)
	}
	if receipt.Method != MethodTempo {
		t.Fatalf("method: %q", receipt.Method)
	}
	if receipt.Status != "success" {
		t.Fatalf("status: %q", receipt.Status)
	}
	if !isHexHash(receipt.Reference) {
		t.Fatalf("reference: %q", receipt.Reference)
	}
	if len(mock.sentRaw) != 1 {
		t.Fatalf("expected one broadcast, got %d", len(mock.sentRaw))
	}
}

func TestBroadcastSignedTransfer_Reverted(t *testing.T) {
	mock := newSignedTransferMockRPC()
	mock.autoMineReceipts = false
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch := buildChargeChallenge(t, secret, time.Now().Add(5*time.Minute))
	cred, err := SignSignedTransferCredential(context.Background(), ch, account, srv.URL)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	signedTxHex := cred.Payload.(TempoSignedTransferPayload).SignedTx

	// Pre-populate a reverted receipt under the tx's hash.
	rawBytes, _ := hex.DecodeString(strings.TrimPrefix(signedTxHex, "0x"))
	var tx types.Transaction
	if err := tx.UnmarshalBinary(rawBytes); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	mock.receiptOverride[tx.Hash().Hex()] = map[string]any{
		"status": "0x0",
		"to":     tx.To().Hex(),
	}

	receipt, err := BroadcastSignedTransfer(context.Background(), signedTxHex, srv.URL)
	if err != nil {
		t.Fatalf("broadcast: %v", err)
	}
	if receipt.Status != "reverted" {
		t.Fatalf("expected reverted, got %q", receipt.Status)
	}
}

// TestDecodeSignedTransferPayload_MapShape ensures payloads round-tripped
// through encoding/json with UseNumber (as DeserializeCredential does) still
// decode correctly.
func TestDecodeSignedTransferPayload_MapShape(t *testing.T) {
	mapPayload := map[string]any{
		"type":      CredentialTypeSignedTransfer,
		"signed_tx": "0xdeadbeef",
		"from":      "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		"nonce":     json.Number("7"),
	}
	got, err := decodeSignedTransferPayload(mapPayload)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got.Type != CredentialTypeSignedTransfer || got.SignedTx != "0xdeadbeef" || got.Nonce != 7 {
		t.Fatalf("bad decode: %+v", got)
	}
	if !common.IsHexAddress(got.From) {
		t.Fatalf("from: %q", got.From)
	}
}
