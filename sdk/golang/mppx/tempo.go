package mppx

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
	"strings"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
)

// MethodTempo is the canonical method name for the Tempo blockchain payment
// method. The corresponding intent for one-shot transfers is "charge".
const (
	MethodTempo  = "tempo"
	IntentCharge = "charge"

	// CredentialTypeTransaction is the `payload.type` value used for an
	// on-chain transaction credential (vs. "hash" or "proof").
	CredentialTypeTransaction = "transaction"
)

// DefaultExpiry is the TTL the TS reference implementation applies to a
// freshly minted challenge when the caller does not specify one.
const DefaultExpiry = 5 * time.Minute

// TempoChargePayload is the payload schema for a `tempo/charge` credential
// of type `"transaction"`. The signature field carries the on-chain
// transaction hash (`0x…`) — Tempo treats inclusion of the hash as proof
// because the verifier can re-fetch the receipt to confirm the transfer.
type TempoChargePayload struct {
	Type      string `json:"type"`      // always "transaction"
	Signature string `json:"signature"` // 0x-prefixed transaction hash (32 bytes)
}

// ChargeBuilder fluently constructs a Tempo `charge` challenge. It is the Go
// equivalent of `mppx.challenge.tempo.charge({...})` from the TS server SDK.
//
// The recipient, currency contract address and chain ID are mandatory. Amount
// defaults to "0", decimals to 6 (pathUSD), realm to the empty string (the
// caller MUST set one), expiry to [DefaultExpiry] from the build time.
type ChargeBuilder struct {
	currency  common.Address
	recipient common.Address
	chainID   int64
	amount    string
	decimals  int
	realm     string
	expires   time.Time
	secretKey []byte

	// Optional methodDetails fields
	memo *common.Hash
}

// NewCharge starts a new ChargeBuilder. `currency` is the ERC-20 token
// contract address (use the pathUSD address `0x20c0…0000` for the standard
// Tempo demo). `recipient` is the EVM address that will receive the funds.
// `chainID` is the EIP-155 chain id (e.g. 42431 for Tempo testnet).
func NewCharge(currency, recipient string, chainID int) *ChargeBuilder {
	return &ChargeBuilder{
		currency:  common.HexToAddress(currency),
		recipient: common.HexToAddress(recipient),
		chainID:   int64(chainID),
		amount:    "0",
		decimals:  6,
	}
}

// Amount sets the human-readable amount (e.g. "1.00") that will be converted
// to the smallest token unit using the configured decimals.
func (b *ChargeBuilder) Amount(amount string) *ChargeBuilder {
	b.amount = amount
	return b
}

// Decimals sets the token decimal precision (default 6, matching pathUSD).
func (b *ChargeBuilder) Decimals(d int) *ChargeBuilder {
	b.decimals = d
	return b
}

// Realm sets the challenge realm (e.g. "pubsub://alice/pay" or a hostname).
func (b *ChargeBuilder) Realm(realm string) *ChargeBuilder {
	b.realm = realm
	return b
}

// ExpiresAt sets the absolute expiry timestamp.
func (b *ChargeBuilder) ExpiresAt(t time.Time) *ChargeBuilder {
	b.expires = t.UTC()
	return b
}

// Memo attaches an optional 32-byte memo to the charge methodDetails.
func (b *ChargeBuilder) Memo(h common.Hash) *ChargeBuilder {
	b.memo = &h
	return b
}

// WithSecretKey configures the HMAC secret used to sign the challenge ID. If
// not set, [Build] returns an error — challenges without an HMAC are not
// useful in practice.
func (b *ChargeBuilder) WithSecretKey(secretKey []byte) *ChargeBuilder {
	b.secretKey = secretKey
	return b
}

// Build produces a fully-formed Challenge, computing the HMAC-bound ID. The
// resulting Challenge is ready to pass to [SerializeChallenge].
func (b *ChargeBuilder) Build() (Challenge, error) {
	if b.realm == "" {
		return Challenge{}, errors.New("mppx/tempo: realm is required")
	}
	if len(b.secretKey) == 0 {
		return Challenge{}, errors.New("mppx/tempo: secretKey is required")
	}
	weiAmount, err := parseUnits(b.amount, b.decimals)
	if err != nil {
		return Challenge{}, fmt.Errorf("mppx/tempo: invalid amount: %w", err)
	}
	request := map[string]any{
		"amount":    weiAmount.String(),
		"currency":  b.currency.Hex(),
		"recipient": b.recipient.Hex(),
	}
	methodDetails := map[string]any{}
	if b.chainID != 0 {
		methodDetails["chainId"] = b.chainID
	}
	if b.memo != nil {
		methodDetails["memo"] = b.memo.Hex()
	}
	if len(methodDetails) > 0 {
		request["methodDetails"] = methodDetails
	}
	expires := b.expires
	if expires.IsZero() {
		expires = time.Now().UTC().Add(DefaultExpiry)
	}
	challenge := Challenge{
		Realm:   b.realm,
		Method:  MethodTempo,
		Intent:  IntentCharge,
		Request: request,
		Expires: expires,
	}
	id, err := ComputeChallengeID(b.secretKey, challenge)
	if err != nil {
		return Challenge{}, err
	}
	challenge.ID = id
	return challenge, nil
}

// SignCredential signs and broadcasts the on-chain ERC-20 transfer described
// by the challenge, then returns a Credential whose Payload contains the
// resulting transaction hash. It is the Go equivalent of
// `mppx.createCredential(fake402)` on the client side.
//
// `rpcURL` is the Tempo JSON-RPC endpoint. The function blocks until the
// transaction is included in a block (success or failure), with a 60s
// default deadline you can override via `ctx`.
//
// On success, the returned Credential's `Source` is populated with the
// payer's `did:pkh` identifier.
func SignCredential(ctx context.Context, ch Challenge, account *Account, rpcURL string) (Credential, error) {
	if account == nil {
		return Credential{}, errors.New("mppx/tempo: account is required")
	}
	if ch.Method != MethodTempo || ch.Intent != IntentCharge {
		return Credential{}, fmt.Errorf("mppx/tempo: unsupported challenge %s/%s", ch.Method, ch.Intent)
	}

	parsed, err := parseChargeRequest(ch.Request)
	if err != nil {
		return Credential{}, err
	}

	chainID := big.NewInt(parsed.ChainID)
	rpc := newRPCClient(rpcURL)

	from := account.Address()
	nonce, err := rpc.getNonce(ctx, from)
	if err != nil {
		return Credential{}, fmt.Errorf("mppx/tempo: get nonce: %w", err)
	}
	gasPrice, err := rpc.getGasPrice(ctx)
	if err != nil {
		return Credential{}, fmt.Errorf("mppx/tempo: get gas price: %w", err)
	}

	data := encodeERC20Transfer(parsed.Recipient, parsed.Amount)

	// Use a legacy tx (type 0). go-ethereum's signer will EIP-155 replay-protect it.
	// Gas limit derived via eth_estimateGas (with a 25 % buffer) so a TIP-20
	// transfer on Tempo doesn't strand on the under-provisioned static budget
	// that mainnet ERC-20 examples use.
	gasLimit, err := rpc.gasLimitFor(ctx, from, parsed.Currency, data)
	if err != nil {
		return Credential{}, err
	}
	tx := types.NewTx(&types.LegacyTx{
		Nonce:    nonce,
		GasPrice: gasPrice,
		Gas:      gasLimit,
		To:       &parsed.Currency,
		Value:    big.NewInt(0),
		Data:     data,
	})
	signer := types.LatestSignerForChainID(chainID)
	signed, err := types.SignTx(tx, signer, account.PrivateKey())
	if err != nil {
		return Credential{}, fmt.Errorf("mppx/tempo: sign tx: %w", err)
	}
	rawBytes, err := signed.MarshalBinary()
	if err != nil {
		return Credential{}, fmt.Errorf("mppx/tempo: marshal tx: %w", err)
	}
	txHash, err := rpc.sendRawTransaction(ctx, rawBytes)
	if err != nil {
		return Credential{}, fmt.Errorf("mppx/tempo: broadcast: %w", err)
	}

	// Wait for receipt — bounded by ctx, capped at 60s.
	deadline, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	if err := rpc.waitForReceipt(deadline, txHash); err != nil {
		return Credential{}, fmt.Errorf("mppx/tempo: wait for receipt: %w", err)
	}

	cred := Credential{
		Challenge: ch,
		Payload: TempoChargePayload{
			Type:      CredentialTypeTransaction,
			Signature: txHash,
		},
		Source: account.DID(uint64(parsed.ChainID)),
	}
	return cred, nil
}

// VerifyCredential runs the full verification chain on a credential:
//
//  1. HMAC re-derivation against `expectedSecret`
//  2. Expiry check (against `time.Now()` ± `clockSkew`)
//  3. Payload schema validation
//  4. On-chain receipt fetch from `rpcURL` (status == 0x1, confirms tx exists)
//  5. Recipient + amount + currency match between challenge.request and the
//     decoded transfer call data
//
// On success it returns a Receipt ready to be serialised back to Bob via
// [SerializeReceipt]. The `clockSkew` parameter allows the verifier to accept
// credentials whose challenge expired up to `clockSkew` ago — useful when the
// signer and verifier clocks drift.
func VerifyCredential(ctx context.Context, c Credential, expectedSecret []byte, rpcURL string, clockSkew time.Duration) (Receipt, error) {
	if c.Challenge.Method != MethodTempo || c.Challenge.Intent != IntentCharge {
		return Receipt{}, fmt.Errorf("mppx/tempo: unsupported credential %s/%s", c.Challenge.Method, c.Challenge.Intent)
	}
	if err := VerifyChallengeID(expectedSecret, c.Challenge); err != nil {
		return Receipt{}, fmt.Errorf("mppx/tempo: %w", err)
	}
	if c.Challenge.HasExpiry() {
		now := time.Now().UTC()
		if now.After(c.Challenge.Expires.Add(clockSkew)) {
			return Receipt{}, fmt.Errorf("mppx/tempo: challenge expired at %s", c.Challenge.Expires.Format(time.RFC3339))
		}
	}
	payload, err := decodeTempoPayload(c.Payload)
	if err != nil {
		return Receipt{}, err
	}
	if payload.Type != CredentialTypeTransaction {
		return Receipt{}, fmt.Errorf("mppx/tempo: unsupported payload type %q", payload.Type)
	}
	if !isHexHash(payload.Signature) {
		return Receipt{}, fmt.Errorf("mppx/tempo: invalid tx hash %q", payload.Signature)
	}

	parsed, err := parseChargeRequest(c.Challenge.Request)
	if err != nil {
		return Receipt{}, err
	}

	rpc := newRPCClient(rpcURL)
	receipt, err := rpc.getTransactionReceipt(ctx, payload.Signature)
	if err != nil {
		return Receipt{}, fmt.Errorf("mppx/tempo: fetch receipt: %w", err)
	}
	if receipt == nil {
		return Receipt{}, errors.New("mppx/tempo: transaction not yet mined")
	}
	if !receipt.successful() {
		return Receipt{}, fmt.Errorf("mppx/tempo: transaction reverted (status %s)", receipt.Status)
	}
	// Confirm the call hit the currency contract.
	if !strings.EqualFold(receipt.To, parsed.Currency.Hex()) {
		return Receipt{}, fmt.Errorf("mppx/tempo: receipt.to %q does not match challenge currency %q", receipt.To, parsed.Currency.Hex())
	}

	// Cross-check recipient + amount via the original tx's input data.
	tx, err := rpc.getTransactionByHash(ctx, payload.Signature)
	if err != nil {
		return Receipt{}, fmt.Errorf("mppx/tempo: fetch tx: %w", err)
	}
	if tx == nil {
		return Receipt{}, errors.New("mppx/tempo: transaction not found")
	}
	wantRecipient, wantAmount, err := decodeERC20Transfer(tx.Input)
	if err != nil {
		return Receipt{}, fmt.Errorf("mppx/tempo: decode transfer: %w", err)
	}
	if wantRecipient != parsed.Recipient {
		return Receipt{}, fmt.Errorf("mppx/tempo: tx recipient %s does not match challenge %s", wantRecipient.Hex(), parsed.Recipient.Hex())
	}
	if wantAmount.Cmp(parsed.Amount) != 0 {
		return Receipt{}, fmt.Errorf("mppx/tempo: tx amount %s does not match challenge %s", wantAmount.String(), parsed.Amount.String())
	}

	return Receipt{
		Method:    MethodTempo,
		Reference: payload.Signature,
		Status:    "success",
		Timestamp: time.Now().UTC(),
	}, nil
}

// parsedCharge is the typed projection of a tempo/charge request payload.
type parsedCharge struct {
	Amount    *big.Int
	Currency  common.Address
	Recipient common.Address
	ChainID   int64
}

func parseChargeRequest(req map[string]any) (parsedCharge, error) {
	var out parsedCharge
	amountStr, ok := req["amount"].(string)
	if !ok {
		// json.Number after DecodeRequest
		if n, isNum := req["amount"].(json.Number); isNum {
			amountStr = n.String()
		} else {
			return out, errors.New("mppx/tempo: request.amount missing or not a string")
		}
	}
	amount, ok := new(big.Int).SetString(amountStr, 10)
	if !ok {
		return out, fmt.Errorf("mppx/tempo: invalid amount %q", amountStr)
	}
	out.Amount = amount

	currencyStr, ok := req["currency"].(string)
	if !ok {
		return out, errors.New("mppx/tempo: request.currency missing or not a string")
	}
	out.Currency = common.HexToAddress(currencyStr)

	recipientStr, ok := req["recipient"].(string)
	if !ok {
		return out, errors.New("mppx/tempo: request.recipient missing or not a string")
	}
	out.Recipient = common.HexToAddress(recipientStr)

	if md, ok := req["methodDetails"].(map[string]any); ok {
		switch v := md["chainId"].(type) {
		case json.Number:
			n, err := v.Int64()
			if err == nil {
				out.ChainID = n
			}
		case float64:
			out.ChainID = int64(v)
		case int:
			out.ChainID = int64(v)
		case int64:
			out.ChainID = v
		case string:
			n, ok := new(big.Int).SetString(v, 10)
			if ok {
				out.ChainID = n.Int64()
			}
		}
	}
	return out, nil
}

// decodeTempoPayload normalises any of the shapes a payload might arrive in
// (typed struct, map[string]any with json.Number values, *TempoChargePayload).
func decodeTempoPayload(p any) (TempoChargePayload, error) {
	switch v := p.(type) {
	case TempoChargePayload:
		return v, nil
	case *TempoChargePayload:
		if v == nil {
			return TempoChargePayload{}, errors.New("mppx/tempo: nil payload")
		}
		return *v, nil
	case map[string]any:
		out := TempoChargePayload{}
		if t, ok := v["type"].(string); ok {
			out.Type = t
		}
		if s, ok := v["signature"].(string); ok {
			out.Signature = s
		}
		if out.Type == "" || out.Signature == "" {
			return out, errors.New("mppx/tempo: payload missing type or signature")
		}
		return out, nil
	}
	// Last resort: re-encode and decode.
	raw, err := json.Marshal(p)
	if err != nil {
		return TempoChargePayload{}, fmt.Errorf("mppx/tempo: invalid payload: %w", err)
	}
	var out TempoChargePayload
	if err := json.Unmarshal(raw, &out); err != nil {
		return out, fmt.Errorf("mppx/tempo: invalid payload: %w", err)
	}
	if out.Type == "" || out.Signature == "" {
		return out, errors.New("mppx/tempo: payload missing type or signature")
	}
	return out, nil
}

// ── ERC-20 transfer encoding ──────────────────────────────────────────────

// erc20TransferSelector is keccak256("transfer(address,uint256)")[:4].
var erc20TransferSelector = computeSelector("transfer(address,uint256)")

func computeSelector(sig string) []byte {
	h := crypto.Keccak256([]byte(sig))
	return h[:4]
}

// encodeERC20Transfer builds the call data for `transfer(to, amount)`.
func encodeERC20Transfer(to common.Address, amount *big.Int) []byte {
	data := make([]byte, 4+32+32)
	copy(data[:4], erc20TransferSelector)
	copy(data[4+12:4+32], to.Bytes())
	amtBytes := amount.Bytes()
	copy(data[4+32+(32-len(amtBytes)):], amtBytes)
	return data
}

// decodeERC20Transfer parses a `transfer(address,uint256)` call data string
// (`0x…` hex). It returns the recipient address and amount.
func decodeERC20Transfer(input string) (common.Address, *big.Int, error) {
	raw, err := hex.DecodeString(strings.TrimPrefix(input, "0x"))
	if err != nil {
		return common.Address{}, nil, fmt.Errorf("invalid hex: %w", err)
	}
	if len(raw) < 4+32+32 {
		return common.Address{}, nil, fmt.Errorf("input too short: %d bytes", len(raw))
	}
	if !bytes.Equal(raw[:4], erc20TransferSelector) {
		return common.Address{}, nil, fmt.Errorf("not an ERC-20 transfer (selector %x)", raw[:4])
	}
	to := common.BytesToAddress(raw[4+12 : 4+32])
	amount := new(big.Int).SetBytes(raw[4+32 : 4+32+32])
	return to, amount, nil
}

// parseUnits converts a decimal string like "1.00" into the smallest unit
// amount given the token's decimal precision. It mirrors viem's parseUnits.
func parseUnits(amount string, decimals int) (*big.Int, error) {
	if decimals < 0 {
		return nil, fmt.Errorf("invalid decimals: %d", decimals)
	}
	parts := strings.SplitN(amount, ".", 2)
	whole := strings.TrimSpace(parts[0])
	frac := ""
	if len(parts) == 2 {
		frac = parts[1]
	}
	if whole == "" {
		whole = "0"
	}
	if len(frac) > decimals {
		return nil, fmt.Errorf("too many fractional digits (%d > %d)", len(frac), decimals)
	}
	frac = frac + strings.Repeat("0", decimals-len(frac))
	combined := whole + frac
	combined = strings.TrimLeft(combined, "0")
	if combined == "" {
		combined = "0"
	}
	v, ok := new(big.Int).SetString(combined, 10)
	if !ok {
		return nil, fmt.Errorf("invalid amount %q", amount)
	}
	return v, nil
}

func isHexHash(s string) bool {
	if !strings.HasPrefix(s, "0x") {
		return false
	}
	if len(s) != 2+64 {
		return false
	}
	_, err := hex.DecodeString(s[2:])
	return err == nil
}

// ── JSON-RPC client ───────────────────────────────────────────────────────

type rpcClient struct {
	url    string
	http   *http.Client
	nextID int
}

func newRPCClient(url string) *rpcClient {
	return &rpcClient{
		url:  url,
		http: &http.Client{Timeout: 30 * time.Second},
	}
}

type rpcRequest struct {
	JSONRPC string `json:"jsonrpc"`
	Method  string `json:"method"`
	Params  []any  `json:"params"`
	ID      int    `json:"id"`
}

type rpcResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	Result  json.RawMessage `json:"result"`
	Error   *rpcError       `json:"error,omitempty"`
	ID      int             `json:"id"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

func (e *rpcError) Error() string {
	return fmt.Sprintf("rpc error %d: %s", e.Code, e.Message)
}

func (c *rpcClient) call(ctx context.Context, method string, params []any) (json.RawMessage, error) {
	c.nextID++
	body, err := json.Marshal(rpcRequest{JSONRPC: "2.0", Method: method, Params: params, ID: c.nextID})
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("rpc http %d: %s", resp.StatusCode, strings.TrimSpace(string(raw)))
	}
	var r rpcResponse
	if err := json.Unmarshal(raw, &r); err != nil {
		return nil, fmt.Errorf("rpc decode: %w", err)
	}
	if r.Error != nil {
		return nil, r.Error
	}
	return r.Result, nil
}

func (c *rpcClient) getNonce(ctx context.Context, addr common.Address) (uint64, error) {
	raw, err := c.call(ctx, "eth_getTransactionCount", []any{addr.Hex(), "pending"})
	if err != nil {
		return 0, err
	}
	var hexStr string
	if err := json.Unmarshal(raw, &hexStr); err != nil {
		return 0, err
	}
	return parseHexUint64(hexStr)
}

func (c *rpcClient) getGasPrice(ctx context.Context) (*big.Int, error) {
	raw, err := c.call(ctx, "eth_gasPrice", []any{})
	if err != nil {
		return nil, err
	}
	var hexStr string
	if err := json.Unmarshal(raw, &hexStr); err != nil {
		return nil, err
	}
	return parseHexBig(hexStr)
}

// estimateGas asks the RPC how much gas a `transfer(to, amount)` ERC-20
// call would actually consume. Tempo's TIP-20 implementation runs notably
// heavier than mainnet ERC-20 (uninitialised-account detection, settlement
// hooks); a static budget pinned to mainnet-style numbers will under-shoot.
// Callers should apply a buffer on top of this estimate so a block-time
// gas-cost bump does not strand the tx.
//
// `from` is the signer (so the node sees the right msg.sender); `to` is
// the ERC-20 contract; `data` is the transfer call data already produced
// by encodeERC20Transfer.
func (c *rpcClient) estimateGas(ctx context.Context, from, to common.Address, data []byte) (uint64, error) {
	call := map[string]string{
		"from": from.Hex(),
		"to":   to.Hex(),
		"data": "0x" + hex.EncodeToString(data),
	}
	raw, err := c.call(ctx, "eth_estimateGas", []any{call, "latest"})
	if err != nil {
		return 0, err
	}
	var hexStr string
	if err := json.Unmarshal(raw, &hexStr); err != nil {
		return 0, err
	}
	return parseHexUint64(hexStr)
}

// gasLimitFor returns a safe gas limit for the supplied ERC-20 transfer.
// It tries eth_estimateGas first and adds a 25 % buffer, falling back to
// a generous static budget if the estimate fails — Tempo's RPC has been
// observed to reject estimate calls under load. The fallback (600k) is
// ~5x the mainnet ERC-20 baseline and ~2x the worst case observed on
// Tempo testnet so a noisy block still settles.
//
// The sanity ceiling (gasLimitCeiling) is enforced AGAINST THE PADDED value
// only: if the unpadded RPC estimate already exceeds the ceiling, the
// estimate itself is returned rather than the ceiling so the broadcast does
// not silently strand at out-of-gas below the RPC's own number. An estimate
// that big is also a strong "something is wrong" signal; surface it via a
// caller-handled error so the user can be told instead of getting their
// transaction silently reverted on-chain.
func (c *rpcClient) gasLimitFor(ctx context.Context, from, to common.Address, data []byte) (uint64, error) {
	est, err := c.estimateGas(ctx, from, to, data)
	if err != nil || est == 0 {
		return fallbackGasLimit, nil
	}
	if est > gasLimitCeiling {
		return 0, fmt.Errorf(
			"mppx/tempo: eth_estimateGas returned %d, above the %d sanity ceiling — refusing to sign a tx the caller likely cannot afford",
			est, gasLimitCeiling,
		)
	}
	// 25 % padding — keep it integer-friendly so the encoded hex is short.
	padded := est + est/4
	if padded < est { // overflow guard, theoretical
		return fallbackGasLimit, nil
	}
	if padded > gasLimitCeiling {
		// Padded value would exceed the ceiling but the estimate itself
		// is below it: cap the padded value at the ceiling so we still
		// stay above the unpadded estimate.
		return gasLimitCeiling, nil
	}
	return padded, nil
}

// gasLimitCeiling is the maximum gas limit gasLimitFor will silently apply.
// 5,000,000 is well above the ~272k cost observed for a TIP-20 transfer on
// Tempo testnet but well below the per-tx ceiling, so it absorbs both a
// fat padding factor and the heavier paths (uninitialised-account
// detection, settlement hooks) without giving a runaway estimate room to
// drain the wallet.
const gasLimitCeiling uint64 = 5_000_000

// fallbackGasLimit is used when eth_estimateGas fails or returns zero.
// 600,000 is well above the ~272k cost observed for a TIP-20 transfer on
// Tempo testnet and well under the per-tx ceiling; it is intentionally
// generous because under-estimating strands the credential entirely.
const fallbackGasLimit uint64 = 600_000

func (c *rpcClient) sendRawTransaction(ctx context.Context, rawTx []byte) (string, error) {
	raw, err := c.call(ctx, "eth_sendRawTransaction", []any{"0x" + hex.EncodeToString(rawTx)})
	if err != nil {
		return "", err
	}
	var hash string
	if err := json.Unmarshal(raw, &hash); err != nil {
		return "", err
	}
	return hash, nil
}

type rpcReceipt struct {
	Status string `json:"status"` // "0x1" success, "0x0" reverted
	To     string `json:"to"`
}

func (r *rpcReceipt) successful() bool { return r.Status == "0x1" }

func (c *rpcClient) getTransactionReceipt(ctx context.Context, hash string) (*rpcReceipt, error) {
	raw, err := c.call(ctx, "eth_getTransactionReceipt", []any{hash})
	if err != nil {
		return nil, err
	}
	if len(raw) == 0 || string(raw) == "null" {
		return nil, nil
	}
	var r rpcReceipt
	if err := json.Unmarshal(raw, &r); err != nil {
		return nil, err
	}
	return &r, nil
}

type rpcTx struct {
	Input string `json:"input"`
	To    string `json:"to"`
}

func (c *rpcClient) getTransactionByHash(ctx context.Context, hash string) (*rpcTx, error) {
	raw, err := c.call(ctx, "eth_getTransactionByHash", []any{hash})
	if err != nil {
		return nil, err
	}
	if len(raw) == 0 || string(raw) == "null" {
		return nil, nil
	}
	var t rpcTx
	if err := json.Unmarshal(raw, &t); err != nil {
		return nil, err
	}
	return &t, nil
}

func (c *rpcClient) waitForReceipt(ctx context.Context, hash string) error {
	backoff := 500 * time.Millisecond
	for {
		r, err := c.getTransactionReceipt(ctx, hash)
		if err != nil {
			return err
		}
		if r != nil {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(backoff):
		}
		if backoff < 4*time.Second {
			backoff *= 2
		}
	}
}

func parseHexUint64(s string) (uint64, error) {
	s = strings.TrimPrefix(s, "0x")
	if s == "" {
		return 0, nil
	}
	b, ok := new(big.Int).SetString(s, 16)
	if !ok {
		return 0, fmt.Errorf("invalid hex %q", s)
	}
	return b.Uint64(), nil
}

func parseHexBig(s string) (*big.Int, error) {
	s = strings.TrimPrefix(s, "0x")
	if s == "" {
		return big.NewInt(0), nil
	}
	b, ok := new(big.Int).SetString(s, 16)
	if !ok {
		return nil, fmt.Errorf("invalid hex %q", s)
	}
	return b, nil
}
