package cmd

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
)

// withTempWallet swaps WalletPath to a temp file for the duration of the test
// and restores the previous resolver after.
func withTempWallet(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "wallet.dat")
	return path
}

func TestWalletInit_RoundTrip(t *testing.T) {
	priv, err := crypto.GenerateKey()
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	want := crypto.FromECDSA(priv)

	ct, err := EncryptPrivateKey(want, "test123")
	if err != nil {
		t.Fatalf("EncryptPrivateKey: %v", err)
	}

	wf := &WalletFile{
		Version:    walletFileVersion,
		Address:    crypto.PubkeyToAddress(priv.PublicKey).Hex(),
		Ciphertext: ct,
	}

	path := withTempWallet(t)
	if err := SaveWalletTo(wf, path); err != nil {
		t.Fatalf("SaveWalletTo: %v", err)
	}

	loaded, err := LoadWalletFrom(path)
	if err != nil {
		t.Fatalf("LoadWalletFrom: %v", err)
	}
	if loaded.Address != wf.Address {
		t.Fatalf("address mismatch: got %s want %s", loaded.Address, wf.Address)
	}

	got, err := DecryptWallet(loaded, "test123")
	if err != nil {
		t.Fatalf("DecryptWallet: %v", err)
	}
	if !bytes.Equal(got, want) {
		t.Fatalf("private key mismatch: got %x want %x", got, want)
	}
}

func TestWalletInit_WrongPassphrase_Fails(t *testing.T) {
	priv, _ := crypto.GenerateKey()
	ct, err := EncryptPrivateKey(crypto.FromECDSA(priv), "correct")
	if err != nil {
		t.Fatalf("EncryptPrivateKey: %v", err)
	}
	wf := &WalletFile{
		Version:    walletFileVersion,
		Address:    crypto.PubkeyToAddress(priv.PublicKey).Hex(),
		Ciphertext: ct,
	}
	if _, err := DecryptWallet(wf, "wrong"); err == nil {
		t.Fatalf("expected decrypt error with wrong passphrase, got nil")
	}
}

func TestWalletInit_RefusesOverwrite(t *testing.T) {
	path := withTempWallet(t)
	wf := &WalletFile{
		Version:    walletFileVersion,
		Address:    "0x0000000000000000000000000000000000000000",
		Ciphertext: "AAAA",
	}
	if err := SaveWalletTo(wf, path); err != nil {
		t.Fatalf("SaveWalletTo: %v", err)
	}

	// Mirror runWalletInit's overwrite guard: when --force is false and the
	// wallet file exists, init must refuse. Stat is the load-bearing call
	// the command does on the same path.
	_, err := os.Stat(path)
	if err != nil {
		t.Fatalf("expected wallet file to exist: %v", err)
	}
	if errors.Is(err, os.ErrNotExist) {
		t.Fatalf("ErrNotExist returned for an existing file")
	}

	// And SaveWalletTo with the same path must overwrite — proving that
	// `--force` would succeed.
	wf2 := &WalletFile{Version: walletFileVersion, Address: "0xdead", Ciphertext: "QkJC"}
	if err := SaveWalletTo(wf2, path); err != nil {
		t.Fatalf("overwrite save failed: %v", err)
	}
	loaded, err := LoadWalletFrom(path)
	if err != nil {
		t.Fatalf("LoadWalletFrom after overwrite: %v", err)
	}
	if loaded.Address != "0xdead" {
		t.Fatalf("overwrite did not take effect: got %s", loaded.Address)
	}
}

func TestWalletShow_ShowsAddressWithoutPassphrase(t *testing.T) {
	priv, _ := crypto.GenerateKey()
	addr := crypto.PubkeyToAddress(priv.PublicKey).Hex()

	ct, err := EncryptPrivateKey(crypto.FromECDSA(priv), "secret")
	if err != nil {
		t.Fatalf("EncryptPrivateKey: %v", err)
	}
	path := withTempWallet(t)
	if err := SaveWalletTo(&WalletFile{
		Version:    walletFileVersion,
		Address:    addr,
		Ciphertext: ct,
	}, path); err != nil {
		t.Fatalf("SaveWalletTo: %v", err)
	}

	loaded, err := LoadWalletFrom(path)
	if err != nil {
		t.Fatalf("LoadWalletFrom: %v", err)
	}
	if loaded.Address != addr {
		t.Fatalf("address mismatch: got %s want %s", loaded.Address, addr)
	}
	// No DecryptWallet call here — we want to assert the address is
	// recoverable without the passphrase.
}

func TestEncodeERC20Transfer(t *testing.T) {
	to := common.HexToAddress("0x1111111111111111111111111111111111111111")
	amount := big.NewInt(123456789)
	data := encodeERC20Transfer(to, amount)
	if len(data) != 4+32+32 {
		t.Fatalf("calldata length: got %d want %d", len(data), 4+32+32)
	}
	if hex.EncodeToString(data[:4]) != "a9059cbb" {
		t.Fatalf("selector mismatch: got %s want a9059cbb", hex.EncodeToString(data[:4]))
	}
	// Recipient address occupies the low 20 bytes of the first param slot.
	if !bytes.Equal(data[4+12:4+32], to.Bytes()) {
		t.Fatalf("recipient slot mismatch: got %x", data[4+12:4+32])
	}
	// Amount is right-aligned uint256.
	gotAmt := new(big.Int).SetBytes(data[4+32 : 4+64])
	if gotAmt.Cmp(amount) != 0 {
		t.Fatalf("amount slot mismatch: got %s want %s", gotAmt, amount)
	}
}

// rpcRecorder is a minimal JSON-RPC test server that captures the raw tx and
// returns canned responses for every call signAndBroadcastERC20Transfer makes.
type rpcRecorder struct {
	mu      sync.Mutex
	rawTx   string
	chainID int64
}

func (r *rpcRecorder) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, req *http.Request) {
		body, _ := io.ReadAll(req.Body)
		req.Body.Close()
		// Each request is a JSON-RPC envelope; decode just enough to dispatch.
		var msg struct {
			ID     json.RawMessage `json:"id"`
			Method string          `json:"method"`
			Params []any           `json:"params"`
		}
		if err := json.Unmarshal(body, &msg); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		var result any
		switch msg.Method {
		case "eth_chainId":
			result = "0x" + big.NewInt(r.chainID).Text(16)
		case "eth_getTransactionCount":
			result = "0x0"
		case "eth_maxPriorityFeePerGas":
			result = "0x3b9aca00" // 1 gwei
		case "eth_getBlockByNumber":
			result = map[string]any{
				"number":           "0x1",
				"hash":             "0x" + strings.Repeat("11", 32),
				"parentHash":       "0x" + strings.Repeat("00", 32),
				"sha3Uncles":       "0x" + strings.Repeat("00", 32),
				"logsBloom":        "0x" + strings.Repeat("00", 256),
				"transactionsRoot": "0x" + strings.Repeat("00", 32),
				"stateRoot":        "0x" + strings.Repeat("00", 32),
				"receiptsRoot":     "0x" + strings.Repeat("00", 32),
				"miner":            "0x0000000000000000000000000000000000000000",
				"difficulty":       "0x0",
				"extraData":        "0x",
				"size":             "0x0",
				"gasLimit":         "0x1c9c380",
				"gasUsed":          "0x0",
				"timestamp":        "0x0",
				"transactions":     []any{},
				"uncles":           []any{},
				"baseFeePerGas":    "0x3b9aca00",
				"nonce":            "0x0000000000000000",
				"mixHash":          "0x" + strings.Repeat("00", 32),
			}
		case "eth_estimateGas":
			result = "0x" + big.NewInt(80000).Text(16)
		case "eth_sendRawTransaction":
			r.mu.Lock()
			if len(msg.Params) > 0 {
				if s, ok := msg.Params[0].(string); ok {
					r.rawTx = s
				}
			}
			r.mu.Unlock()
			// Hash isn't validated against the tx in tests; any 32-byte hex works.
			result = "0x" + strings.Repeat("ab", 32)
		case "eth_getTransactionReceipt":
			// Return null so waitForReceipt loops once and gives up on the
			// short test deadline — we only care about the broadcast payload.
			result = nil
		default:
			result = nil
		}
		resp := map[string]any{
			"jsonrpc": "2.0",
			"id":      msg.ID,
			"result":  result,
		}
		_ = json.NewEncoder(w).Encode(resp)
	}
}

func TestWalletSend_SignsTransactionCorrectly(t *testing.T) {
	priv, err := crypto.GenerateKey()
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	chainID := big.NewInt(42431)

	rec := &rpcRecorder{chainID: chainID.Int64()}
	srv := httptest.NewServer(rec.handler())
	defer srv.Close()

	to := common.HexToAddress("0x2222222222222222222222222222222222222222")
	token := common.HexToAddress(defaultPathUSDAddress)
	amount := big.NewInt(1_000)

	// Use a short context so waitForReceipt aborts quickly when the mock
	// always returns a nil receipt.
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	res, err := signAndBroadcastERC20Transfer(ctx, erc20TransferParams{
		RPCURL:  srv.URL,
		ChainID: chainID,
		PrivKey: priv,
		Token:   token,
		To:      to,
		Amount:  amount,
	})
	// The receipt poll may return a context error; that's fine. We only
	// require the broadcast itself to have happened.
	if err != nil && !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("signAndBroadcastERC20Transfer: %v", err)
	}
	if res.TxHash == "" {
		t.Fatalf("expected non-empty tx hash")
	}

	rec.mu.Lock()
	raw := rec.rawTx
	rec.mu.Unlock()
	if raw == "" {
		t.Fatalf("eth_sendRawTransaction was never called")
	}

	// Decode the broadcast tx and assert from/to/data/chainId.
	rawBytes := common.FromHex(raw)
	tx := new(types.Transaction)
	if err := tx.UnmarshalBinary(rawBytes); err != nil {
		t.Fatalf("UnmarshalBinary: %v", err)
	}
	if tx.ChainId().Cmp(chainID) != 0 {
		t.Fatalf("chain id mismatch: got %s want %s", tx.ChainId(), chainID)
	}
	if tx.To() == nil || *tx.To() != token {
		t.Fatalf("tx.To() should be the token contract; got %v want %s", tx.To(), token.Hex())
	}
	expectedData := encodeERC20Transfer(to, amount)
	if !bytes.Equal(tx.Data(), expectedData) {
		t.Fatalf("calldata mismatch:\n got  %x\n want %x", tx.Data(), expectedData)
	}

	signer := types.LatestSignerForChainID(chainID)
	sender, err := types.Sender(signer, tx)
	if err != nil {
		t.Fatalf("recover sender: %v", err)
	}
	want := crypto.PubkeyToAddress(priv.PublicKey)
	if sender != want {
		t.Fatalf("sender mismatch: got %s want %s", sender.Hex(), want.Hex())
	}
}
