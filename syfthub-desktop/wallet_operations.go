// Package main provides Wails-exposed wallet operations for the consumer side
// of the x402 pay-per-request flow.
//
// The wallet is a local Tempo (EVM) account backed by a single secp256k1
// private key on disk. The private key file is written with 0600 perms and
// lives under the app's per-user wallet directory; it is the signing material
// every payment credential is derived from, so it never leaves the desktop
// process.
package main

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/openmined/syfthub/sdk/golang/mppx"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// Wallet defaults. The Tempo testnet chain id and pathUSD contract are the
// canonical demo values shared with the rest of the x402 stack. The RPC URL
// can be overridden via the SYFTHUB_TEMPO_RPC_URL env var for local nodes or
// alternate networks.
const (
	walletDirName     = ".syfthub-desktop"
	walletKeyFilename = "wallet.key"

	defaultRPCURL  = "https://rpc.testnet.tempo.xyz"
	defaultChainID = uint64(42431)
	walletNetwork  = "tempo-testnet"

	pathUSDContractAddress = "0x20c0000000000000000000000000000000000000"
	pathUSDDecimals        = 6

	rpcEnvVar = "SYFTHUB_TEMPO_RPC_URL"

	// faucetURL is the programmatic Tempo testnet faucet endpoint. A single
	// POST funds the address with 1M each of pathUSD, AlphaUSD, BetaUSD,
	// and ThetaUSD. May be overridden via SYFTHUB_TEMPO_FAUCET_URL for local
	// proxies / alternative testnets.
	faucetURL    = "https://docs.tempo.xyz/api/faucet"
	faucetEnvVar = "SYFTHUB_TEMPO_FAUCET_URL"

	// walletFundTimeout bounds the faucet POST. Funding fans out four
	// transfers server-side, so we allow more headroom than the balance call.
	walletFundTimeout = 30 * time.Second

	// walletBalanceTimeout bounds the JSON-RPC call WalletBalance issues.
	// Tempo testnet has been known to wedge on a slow upstream; this keeps
	// the UI responsive even when the RPC is unhealthy.
	walletBalanceTimeout = 15 * time.Second

	// walletSignTimeout bounds the full SignSignedTransferCredential RPC
	// interaction (nonce + gas price fetches). Longer than the balance
	// timeout because two RPC calls are issued back-to-back and a transient
	// testnet stall on either one would otherwise abort the entire sign.
	walletSignTimeout = 60 * time.Second
)

// erc20BalanceOfSelector is keccak256("balanceOf(address)")[:4]. Computed once
// at package init so each balance query reuses the same 4-byte selector.
var erc20BalanceOfSelector = func() []byte {
	h := crypto.Keccak256([]byte("balanceOf(address)"))
	return h[:4]
}()

// WalletInfo is the snapshot of the on-disk wallet returned to the frontend.
// KeyExists is false when no key file is present yet — the caller should then
// invoke WalletInit to generate one.
type WalletInfo struct {
	Address   string `json:"address"`
	ChainID   uint64 `json:"chain_id"`
	RPCURL    string `json:"rpc_url"`
	Network   string `json:"network"`
	KeyExists bool   `json:"key_exists"`
}

// WalletBalance is the result of querying the pathUSD ERC-20 balance for the
// wallet's address. Amount is a decimal string formatted to pathUSDDecimals
// places so the frontend can display it without doing its own bignum math.
type WalletBalance struct {
	Address  string `json:"address"`
	Amount   string `json:"amount"`
	Currency string `json:"currency"`
	Decimals int    `json:"decimals"`
	AsOfUnix int64  `json:"as_of_unix"`
}

// walletDir resolves the per-user wallet directory (~/.syfthub-desktop on
// Linux/macOS, %USERPROFILE%\.syfthub-desktop on Windows). The directory is
// not created here — callers that write into it (WalletInit) MkdirAll first.
func walletDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("failed to resolve home directory: %w", err)
	}
	return filepath.Join(home, walletDirName), nil
}

// walletKeyPath returns the absolute path of the wallet private key file.
func walletKeyPath() (string, error) {
	dir, err := walletDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, walletKeyFilename), nil
}

// rpcURL returns the configured Tempo JSON-RPC endpoint. Env override takes
// precedence so a developer can point the desktop at a local Anvil/Hardhat
// node without rebuilding.
func rpcURL() string {
	if v := strings.TrimSpace(os.Getenv(rpcEnvVar)); v != "" {
		return v
	}
	return defaultRPCURL
}

// loadAccountFromFile reads, trims and parses the on-disk private key.
// Returns os.ErrNotExist (wrapped) when the file is missing so callers can
// distinguish "no wallet yet" from "wallet is broken".
func loadAccountFromFile() (*mppx.Account, error) {
	path, err := walletKeyPath()
	if err != nil {
		return nil, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	hexKey := strings.TrimSpace(string(raw))
	if hexKey == "" {
		return nil, errors.New("wallet key file is empty")
	}
	acc, err := mppx.LoadAccount(hexKey)
	if err != nil {
		return nil, fmt.Errorf("invalid wallet key: %w", err)
	}
	return acc, nil
}

// writeAccountToFile persists the private key for a newly generated account
// with 0600 perms. The parent directory is created at 0700 so other users
// cannot list the wallet file by name.
func writeAccountToFile(acc *mppx.Account) error {
	path, err := walletKeyPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("failed to create wallet directory: %w", err)
	}
	hexKey := hex.EncodeToString(crypto.FromECDSA(acc.PrivateKey()))
	// Write via a temp file + rename so a crash mid-write cannot leave a
	// half-formed key around that would later fail to parse. O_EXCL on the
	// temp file guards against two concurrent inits racing on the same path.
	tmpPath := path + ".tmp"
	f, err := os.OpenFile(tmpPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC|os.O_EXCL, 0o600)
	if err != nil {
		// If a stale .tmp exists (previous crash), retry without O_EXCL once.
		if os.IsExist(err) {
			f, err = os.OpenFile(tmpPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
		}
		if err != nil {
			return fmt.Errorf("failed to open wallet key file: %w", err)
		}
	}
	if _, err := f.WriteString(hexKey); err != nil {
		_ = f.Close()
		_ = os.Remove(tmpPath)
		return fmt.Errorf("failed to write wallet key: %w", err)
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return fmt.Errorf("failed to close wallet key file: %w", err)
	}
	if err := os.Rename(tmpPath, path); err != nil {
		_ = os.Remove(tmpPath)
		return fmt.Errorf("failed to install wallet key: %w", err)
	}
	return nil
}

// walletInitMu serialises concurrent WalletInit calls so two frontend tabs
// hitting the binding at the same time cannot both generate a fresh key.
var walletInitMu sync.Mutex

// loadOrGenerateAccount loads the on-disk key, generating a new one if the
// file does not exist. Used by both WalletInit and WalletPayChallenge.
func loadOrGenerateAccount() (*mppx.Account, bool, error) {
	walletInitMu.Lock()
	defer walletInitMu.Unlock()

	acc, err := loadAccountFromFile()
	if err == nil {
		return acc, false, nil
	}
	if !os.IsNotExist(err) {
		return nil, false, err
	}
	pk, genErr := crypto.GenerateKey()
	if genErr != nil {
		return nil, false, fmt.Errorf("failed to generate wallet key: %w", genErr)
	}
	hexKey := hex.EncodeToString(crypto.FromECDSA(pk))
	acc, err = mppx.LoadAccount(hexKey)
	if err != nil {
		return nil, false, fmt.Errorf("failed to load generated key: %w", err)
	}
	if err := writeAccountToFile(acc); err != nil {
		return nil, false, err
	}
	return acc, true, nil
}

// WalletInit returns the wallet's address, generating a new key on disk if
// none exists. Safe to call on every app start — existing keys are loaded
// verbatim, never rotated.
func (a *App) WalletInit() (WalletInfo, error) {
	acc, created, err := loadOrGenerateAccount()
	if err != nil {
		return WalletInfo{}, err
	}
	if a != nil && a.ctx != nil {
		if created {
			runtime.LogInfo(a.ctx, fmt.Sprintf("[wallet] generated new wallet at address %s", acc.Address().Hex()))
		} else {
			runtime.LogDebug(a.ctx, fmt.Sprintf("[wallet] loaded existing wallet at address %s", acc.Address().Hex()))
		}
	}
	return WalletInfo{
		Address:   acc.Address().Hex(),
		ChainID:   defaultChainID,
		RPCURL:    rpcURL(),
		Network:   walletNetwork,
		KeyExists: true,
	}, nil
}

// WalletShow returns the current wallet info WITHOUT generating one. The
// frontend uses this to decide whether to prompt the user to initialize a
// wallet on first launch (KeyExists=false → call WalletInit).
func (a *App) WalletShow() (WalletInfo, error) {
	acc, err := loadAccountFromFile()
	if err != nil {
		if os.IsNotExist(err) {
			return WalletInfo{
				ChainID:   defaultChainID,
				RPCURL:    rpcURL(),
				Network:   walletNetwork,
				KeyExists: false,
			}, nil
		}
		return WalletInfo{}, err
	}
	return WalletInfo{
		Address:   acc.Address().Hex(),
		ChainID:   defaultChainID,
		RPCURL:    rpcURL(),
		Network:   walletNetwork,
		KeyExists: true,
	}, nil
}

// WalletBalance queries the pathUSD ERC-20 balance for the wallet's address
// via eth_call. The amount is returned as a decimal string with pathUSDDecimals
// places of precision so the frontend can render it as-is.
//
// Returns an error wrapping ErrNoWallet when no on-disk key is present; the
// frontend should bounce the user through WalletInit first.
func (a *App) WalletBalance() (WalletBalance, error) {
	acc, err := loadAccountFromFile()
	if err != nil {
		if os.IsNotExist(err) {
			return WalletBalance{}, ErrNoWallet
		}
		return WalletBalance{}, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), walletBalanceTimeout)
	defer cancel()
	raw, err := ethCallBalanceOf(ctx, rpcURL(), pathUSDContractAddress, acc.Address())
	if err != nil {
		return WalletBalance{}, fmt.Errorf("balance query failed: %w", err)
	}
	formatted := formatDecimalAmount(raw, pathUSDDecimals)
	return WalletBalance{
		Address:  acc.Address().Hex(),
		Amount:   formatted,
		Currency: pathUSDContractAddress,
		Decimals: pathUSDDecimals,
		AsOfUnix: time.Now().Unix(),
	}, nil
}

// WalletPayChallenge signs the supplied wire-format payment_challenge with
// the on-disk wallet and returns the serialized credential ready to ship back
// to the producer. It also persists a "signed" row in the local payment
// ledger so the user can later see (and reconcile) what they paid for.
//
// Wire format: the challenge is a base64url-encoded "Payment …" header value
// as produced by mppx.SerializeChallenge.
func (a *App) WalletPayChallenge(challengeWire string) (string, error) {
	if strings.TrimSpace(challengeWire) == "" {
		return "", errors.New("challenge wire is empty")
	}
	ch, err := mppx.DeserializeChallenge(challengeWire)
	if err != nil {
		return "", fmt.Errorf("invalid challenge: %w", err)
	}
	acc, _, err := loadOrGenerateAccount()
	if err != nil {
		return "", err
	}

	// Bound the RPC interaction (nonce + gas price fetches). The signing
	// itself is local but the two RPC calls inside SignSignedTransferCredential
	// can hang if the upstream is unreachable.
	ctx, cancel := context.WithTimeout(context.Background(), walletSignTimeout)
	defer cancel()

	cred, err := mppx.SignSignedTransferCredential(ctx, ch, acc, rpcURL())
	if err != nil {
		return "", fmt.Errorf("sign challenge: %w", err)
	}
	wire, err := mppx.SerializeCredential(cred)
	if err != nil {
		return "", fmt.Errorf("serialize credential: %w", err)
	}

	// Persist a pending row so the history view immediately reflects the
	// outgoing payment. UpdateSettlement (post-broadcast) will flip status
	// to "settled" or "failed" once the producer reports the receipt.
	rec := buildPendingPaymentRecord(ch, cred, wire)
	if err := a.RecordPayment(rec); err != nil {
		// History is non-fatal — the credential has been signed and the
		// user should still be able to submit it. Log loudly so the
		// discrepancy is visible.
		if a != nil && a.ctx != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("[wallet] failed to record payment %s: %v", rec.ID, err))
		}
	}

	return wire, nil
}

// FundResult is the outcome of a faucet request. Hashes are the on-chain
// transaction hashes for each asset the faucet sent (typically pathUSD,
// AlphaUSD, BetaUSD, ThetaUSD — one per asset, in the order the faucet
// returned them). The explorer link prefix is shared with the rest of the
// app: ExplorerTxPrefix in the frontend.
type FundResult struct {
	Address   string   `json:"address"`
	Hashes    []string `json:"hashes"`
	Network   string   `json:"network"`
	FaucetURL string   `json:"faucet_url"`
}

// faucetResponse is the JSON shape returned by the Tempo testnet faucet:
//
//	{"data":[{"hash":"0x..."},{"hash":"0x..."},...],"error":null}
//
// `error` is non-empty on rate-limit or invalid-address failures.
type faucetResponse struct {
	Data  []faucetHash `json:"data"`
	Error any          `json:"error"`
}

type faucetHash struct {
	Hash string `json:"hash"`
}

// faucetURLFor returns the faucet endpoint, allowing an env override for
// local proxies or alternative testnets.
func faucetURLFor() string {
	if v := strings.TrimSpace(os.Getenv(faucetEnvVar)); v != "" {
		return v
	}
	return faucetURL
}

// WalletFund requests testnet funding for the local wallet from the Tempo
// faucet. Returns the transaction hashes the faucet broadcast — the user can
// open each in the explorer to confirm receipt. The balance will visibly
// update on the next WalletBalance call once the txs are mined.
//
// Returns ErrNoWallet when no on-disk key exists; the frontend should bounce
// the user through WalletInit first. Surfaces the faucet's `error` field
// verbatim when funding fails (typically a rate-limit message).
func (a *App) WalletFund() (FundResult, error) {
	acc, err := loadAccountFromFile()
	if err != nil {
		if os.IsNotExist(err) {
			return FundResult{}, ErrNoWallet
		}
		return FundResult{}, err
	}

	// Tempo's faucet expects the address lowercase; mixed-case sometimes
	// returns a generic 400.
	address := strings.ToLower(acc.Address().Hex())
	body, err := json.Marshal(map[string]string{"address": address})
	if err != nil {
		return FundResult{}, fmt.Errorf("encode faucet request: %w", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), walletFundTimeout)
	defer cancel()
	url := faucetURLFor()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return FundResult{}, fmt.Errorf("build faucet request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return FundResult{}, fmt.Errorf("faucet request failed: %w", err)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	if err != nil {
		return FundResult{}, fmt.Errorf("read faucet response: %w", err)
	}

	if resp.StatusCode/100 != 2 {
		return FundResult{}, fmt.Errorf("faucet returned HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(raw)))
	}

	var parsed faucetResponse
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return FundResult{}, fmt.Errorf("decode faucet response: %w (body: %s)", err, strings.TrimSpace(string(raw)))
	}
	if parsed.Error != nil && fmt.Sprint(parsed.Error) != "" && fmt.Sprint(parsed.Error) != "<nil>" {
		return FundResult{}, fmt.Errorf("faucet error: %v", parsed.Error)
	}
	if len(parsed.Data) == 0 {
		return FundResult{}, errors.New("faucet returned no transaction hashes")
	}

	hashes := make([]string, 0, len(parsed.Data))
	for _, h := range parsed.Data {
		if h.Hash != "" {
			hashes = append(hashes, h.Hash)
		}
	}

	return FundResult{
		Address:   address,
		Hashes:    hashes,
		Network:   walletNetwork,
		FaucetURL: url,
	}, nil
}

// ErrNoWallet is returned by balance/show paths when no on-disk wallet
// exists. The frontend should redirect the user through WalletInit.
var ErrNoWallet = errors.New("wallet not initialised — call WalletInit first")

// ── helpers ────────────────────────────────────────────────────────────────

// buildPendingPaymentRecord extracts the audit fields (endpoint owner/slug,
// amount, currency, chain id) from the credential's challenge and assembles
// a PaymentRecord suitable for the initial "signed" insert.
func buildPendingPaymentRecord(ch mppx.Challenge, cred mppx.Credential, wire string) PaymentRecord {
	owner, slug := parseRealmEndpoint(ch.Realm)
	amount := ""
	currency := ""
	chainID := defaultChainID
	if ch.Request != nil {
		if v, ok := ch.Request["amount"].(string); ok {
			amount = formatDecimalAmount(v, pathUSDDecimals)
		}
		if v, ok := ch.Request["currency"].(string); ok {
			currency = v
		}
		if md, ok := ch.Request["methodDetails"].(map[string]any); ok {
			switch n := md["chainId"].(type) {
			case float64:
				chainID = uint64(n)
			case int:
				chainID = uint64(n)
			case int64:
				if n > 0 {
					chainID = uint64(n)
				}
			case string:
				if i, ok := new(big.Int).SetString(n, 10); ok {
					chainID = i.Uint64()
				}
			}
		}
	}
	_ = cred
	return PaymentRecord{
		ID:            newPaymentID(),
		TimestampUnix: time.Now().Unix(),
		EndpointOwner: owner,
		EndpointSlug:  slug,
		Amount:        amount,
		Currency:      currency,
		ChainID:       chainID,
		ChallengeID:   ch.ID,
		CredentialHex: wire,
		Status:        "signed",
	}
}

// parseRealmEndpoint best-effort splits an MPP realm string into an owner +
// slug pair. The convention used by the desktop is "owner/slug" or
// "pubsub://owner/slug"; we strip the scheme prefix and any leading slash.
// Returns empty strings when the realm does not parse — history rows still
// insert; they just lack endpoint metadata.
func parseRealmEndpoint(realm string) (owner, slug string) {
	r := realm
	if i := strings.Index(r, "://"); i != -1 {
		r = r[i+3:]
	}
	r = strings.TrimPrefix(r, "/")
	parts := strings.SplitN(r, "/", 2)
	if len(parts) == 2 {
		return parts[0], parts[1]
	}
	if len(parts) == 1 {
		return parts[0], ""
	}
	return "", ""
}

// formatDecimalAmount converts a base-10 integer string (e.g. "1234567")
// representing an amount in the smallest unit of a token into a decimal
// string formatted with `decimals` fractional digits (e.g. "1.234567").
//
// Returns the original string on any parse failure so the caller still has
// some signal rather than an empty cell in the UI.
func formatDecimalAmount(raw string, decimals int) string {
	if decimals < 0 {
		return raw
	}
	v, ok := new(big.Int).SetString(strings.TrimSpace(raw), 10)
	if !ok {
		return raw
	}
	sign := ""
	if v.Sign() < 0 {
		sign = "-"
		v = new(big.Int).Neg(v)
	}
	s := v.String()
	if decimals == 0 {
		return sign + s
	}
	if len(s) <= decimals {
		s = strings.Repeat("0", decimals-len(s)+1) + s
	}
	cut := len(s) - decimals
	whole := s[:cut]
	frac := strings.TrimRight(s[cut:], "0")
	if frac == "" {
		return sign + whole
	}
	return sign + whole + "." + frac
}

// ethCallBalanceOf issues an eth_call against the ERC-20 contract and parses
// the 32-byte uint256 return value into a decimal string.
func ethCallBalanceOf(ctx context.Context, rpc string, contract string, holder common.Address) (string, error) {
	data := make([]byte, 4+32)
	copy(data[:4], erc20BalanceOfSelector)
	copy(data[4+12:], holder.Bytes())
	dataHex := "0x" + hex.EncodeToString(data)

	hexResult, err := ethCall(ctx, rpc, contract, dataHex)
	if err != nil {
		return "", err
	}
	hexResult = strings.TrimPrefix(strings.TrimSpace(hexResult), "0x")
	if hexResult == "" {
		return "0", nil
	}
	v, ok := new(big.Int).SetString(hexResult, 16)
	if !ok {
		return "", fmt.Errorf("invalid hex result %q", hexResult)
	}
	return v.String(), nil
}

// ethCallSender is overridable from tests so they can avoid spinning up an
// httptest server inside formatDecimalAmount round-trip tests.
var ethCallSender = httpEthCall

// ethCall sends a single eth_call to the configured RPC. It is a thin wrapper
// around ethCallSender so tests can stub the transport.
func ethCall(ctx context.Context, rpc, contract, dataHex string) (string, error) {
	return ethCallSender(ctx, rpc, contract, dataHex)
}
