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

func TestParseUnits(t *testing.T) {
	cases := []struct {
		amount   string
		decimals int
		want     string
	}{
		{"1.00", 6, "1000000"},
		{"0.5", 6, "500000"},
		{"123.456789", 6, "123456789"},
		{"1", 0, "1"},
		{"1", 18, "1000000000000000000"},
		{".25", 6, "250000"},
	}
	for _, c := range cases {
		t.Run(c.amount, func(t *testing.T) {
			got, err := parseUnits(c.amount, c.decimals)
			if err != nil {
				t.Fatalf("err: %v", err)
			}
			if got.String() != c.want {
				t.Fatalf("got %s want %s", got.String(), c.want)
			}
		})
	}
}

func TestParseUnitsRejectsTooManyDecimals(t *testing.T) {
	if _, err := parseUnits("1.1234567", 6); err == nil {
		t.Fatal("expected error")
	}
}

func TestEncodeDecodeERC20Transfer(t *testing.T) {
	to := common.HexToAddress("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
	amount := big.NewInt(1000000)
	data := encodeERC20Transfer(to, amount)
	gotTo, gotAmt, err := decodeERC20Transfer("0x" + hex.EncodeToString(data))
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if gotTo != to {
		t.Fatalf("to mismatch: %s vs %s", gotTo.Hex(), to.Hex())
	}
	if gotAmt.Cmp(amount) != 0 {
		t.Fatalf("amount mismatch: %s vs %s", gotAmt.String(), amount.String())
	}
}

func TestChargeBuilder_BuildAndVerify(t *testing.T) {
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch, err := NewCharge(
		"0x20c0000000000000000000000000000000000000",
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("1.00").Decimals(6).Realm("pubsub://alice/pay").
		ExpiresAt(time.Date(2026, 5, 8, 21, 43, 11, 0, time.UTC)).
		WithSecretKey(secret).Build()
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	if ch.ID == "" {
		t.Fatal("expected id to be set")
	}
	if ch.Request["amount"] != "1000000" {
		t.Fatalf("amount not converted: %v", ch.Request["amount"])
	}
	if err := VerifyChallengeID(secret, ch); err != nil {
		t.Fatalf("HMAC verify: %v", err)
	}
}

func TestChargeBuilder_RequiresRealmAndSecret(t *testing.T) {
	if _, err := NewCharge("0x20c0000000000000000000000000000000000000", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266", 42431).
		WithSecretKey([]byte("k")).Build(); err == nil {
		t.Fatal("expected realm error")
	}
	if _, err := NewCharge("0x20c0000000000000000000000000000000000000", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266", 42431).
		Realm("r").Build(); err == nil {
		t.Fatal("expected secret error")
	}
}

// ── Mock RPC ─────────────────────────────────────────────────────────────

type mockRPC struct {
	mu        sync.Mutex
	requests  []map[string]any
	receipts  map[string]any // txHash → receipt JSON
	txByHash  map[string]any
	nonce     uint64
	gasPrice  string
	sentRaw   []string
	autoMined bool
}

func newMockRPC() *mockRPC {
	return &mockRPC{
		receipts:  map[string]any{},
		txByHash:  map[string]any{},
		gasPrice:  "0x3b9aca00", // 1 gwei
		autoMined: true,
	}
}

func (m *mockRPC) handle(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	var req map[string]any
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, err.Error(), 400)
		return
	}
	m.mu.Lock()
	m.requests = append(m.requests, req)
	m.mu.Unlock()
	method, _ := req["method"].(string)
	id, _ := req["id"]

	respond := func(result any) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"jsonrpc": "2.0",
			"id":      id,
			"result":  result,
		})
	}

	switch method {
	case "eth_getTransactionCount":
		respond("0x" + new(big.Int).SetUint64(m.nonce).Text(16))
	case "eth_gasPrice":
		respond(m.gasPrice)
	case "eth_sendRawTransaction":
		params, _ := req["params"].([]any)
		raw, _ := params[0].(string)
		m.mu.Lock()
		m.sentRaw = append(m.sentRaw, raw)
		m.mu.Unlock()
		// Decode and compute the hash to keep test fixtures honest.
		rawBytes, _ := hex.DecodeString(strings.TrimPrefix(raw, "0x"))
		var tx types.Transaction
		if err := tx.UnmarshalBinary(rawBytes); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		hash := tx.Hash().Hex()
		if m.autoMined {
			m.receipts[hash] = map[string]any{"status": "0x1", "to": tx.To().Hex()}
			m.txByHash[hash] = map[string]any{"to": tx.To().Hex(), "input": "0x" + hex.EncodeToString(tx.Data())}
		}
		respond(hash)
	case "eth_getTransactionReceipt":
		params, _ := req["params"].([]any)
		hash, _ := params[0].(string)
		if r, ok := m.receipts[hash]; ok {
			respond(r)
		} else {
			respond(nil)
		}
	case "eth_getTransactionByHash":
		params, _ := req["params"].([]any)
		hash, _ := params[0].(string)
		if t, ok := m.txByHash[hash]; ok {
			respond(t)
		} else {
			respond(nil)
		}
	default:
		http.Error(w, "unknown method "+method, 400)
	}
}

func TestSignCredential_BroadcastsERC20Transfer(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	account, err := LoadAccount(testPrivKey)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch, err := NewCharge(
		"0x20c0000000000000000000000000000000000000",
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("1.00").Decimals(6).Realm("pubsub://alice/pay").
		ExpiresAt(time.Now().Add(5 * time.Minute)).
		WithSecretKey(secret).Build()
	if err != nil {
		t.Fatalf("build: %v", err)
	}

	cred, err := SignCredential(context.Background(), ch, account, srv.URL)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	payload, err := decodeTempoPayload(cred.Payload)
	if err != nil {
		t.Fatalf("decode payload: %v", err)
	}
	if !isHexHash(payload.Signature) {
		t.Fatalf("expected tx hash, got %q", payload.Signature)
	}
	if cred.Source == "" || !strings.HasPrefix(cred.Source, "did:pkh:eip155:42431:") {
		t.Fatalf("missing/invalid source: %q", cred.Source)
	}

	// Confirm the broadcasted raw tx targeted the currency contract with the
	// correct call data.
	if len(mock.sentRaw) != 1 {
		t.Fatalf("expected exactly one broadcast, got %d", len(mock.sentRaw))
	}
	rawBytes, _ := hex.DecodeString(strings.TrimPrefix(mock.sentRaw[0], "0x"))
	var tx types.Transaction
	if err := tx.UnmarshalBinary(rawBytes); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if to := tx.To().Hex(); !strings.EqualFold(to, "0x20c0000000000000000000000000000000000000") {
		t.Fatalf("tx.to %q != currency", to)
	}
	gotTo, gotAmt, err := decodeERC20Transfer("0x" + hex.EncodeToString(tx.Data()))
	if err != nil {
		t.Fatalf("decode call: %v", err)
	}
	if !strings.EqualFold(gotTo.Hex(), "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266") {
		t.Fatalf("recipient: %s", gotTo.Hex())
	}
	if gotAmt.String() != "1000000" {
		t.Fatalf("amount: %s", gotAmt.String())
	}
}

func TestVerifyCredential_HappyPath(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()

	account, _ := LoadAccount(testPrivKey)
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	ch, _ := NewCharge(
		"0x20c0000000000000000000000000000000000000",
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("1.00").Decimals(6).Realm("pubsub://alice/pay").
		ExpiresAt(time.Now().Add(5 * time.Minute)).
		WithSecretKey(secret).Build()

	cred, err := SignCredential(context.Background(), ch, account, srv.URL)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}

	receipt, err := VerifyCredential(context.Background(), cred, secret, srv.URL, time.Minute)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if receipt.Method != "tempo" || receipt.Status != "success" {
		t.Fatalf("bad receipt: %+v", receipt)
	}
}

func TestVerifyCredential_RejectsBadHMAC(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	ch, _ := NewCharge(
		"0x20c0000000000000000000000000000000000000",
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("1.00").Decimals(6).Realm("r").
		ExpiresAt(time.Now().Add(5 * time.Minute)).
		WithSecretKey([]byte("k1")).Build()
	cred, _ := SignCredential(context.Background(), ch, account, srv.URL)

	if _, err := VerifyCredential(context.Background(), cred, []byte("wrong-secret"), srv.URL, time.Minute); err == nil {
		t.Fatal("expected HMAC mismatch")
	}
}

func TestVerifyCredential_RejectsExpired(t *testing.T) {
	mock := newMockRPC()
	srv := httptest.NewServer(http.HandlerFunc(mock.handle))
	defer srv.Close()
	account, _ := LoadAccount(testPrivKey)
	secret := []byte("k1")
	ch, _ := NewCharge(
		"0x20c0000000000000000000000000000000000000",
		"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		42431,
	).Amount("1.00").Decimals(6).Realm("r").
		ExpiresAt(time.Now().Add(-10 * time.Minute)).
		WithSecretKey(secret).Build()
	cred, _ := SignCredential(context.Background(), ch, account, srv.URL)

	if _, err := VerifyCredential(context.Background(), cred, secret, srv.URL, time.Minute); err == nil {
		t.Fatal("expected expiry error")
	}
}
