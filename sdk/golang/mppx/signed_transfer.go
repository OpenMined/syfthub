package mppx

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
)

// CredentialTypeSignedTransfer is the `payload.type` value used for an
// off-chain "signed but not broadcast" ERC-20 transfer credential. The
// consumer signs a raw ERC-20 `transfer` transaction and hands the signed
// bytes to the producer. Settlement happens later when the producer
// broadcasts the signed tx via [BroadcastSignedTransfer]. The signed-but-
// unbroadcast nonce slot acts as a natural escrow: until the producer
// broadcasts, the consumer can keep the funds; once broadcast, the nonce
// can no longer be reused for a different transfer.
const CredentialTypeSignedTransfer = "signed_transfer"

// TempoSignedTransferPayload is the payload schema for a `tempo/charge`
// credential of type `"signed_transfer"`. The signed transaction bytes are
// hex-encoded with a `0x` prefix; the verifier MUST be able to recover the
// sender from the signature and match it against `From`.
type TempoSignedTransferPayload struct {
	Type     string `json:"type"`      // always "signed_transfer"
	SignedTx string `json:"signed_tx"` // 0x-prefixed raw signed legacy tx
	From     string `json:"from"`      // EVM address that signed the tx (0x-hex)
	Nonce    uint64 `json:"nonce"`     // tx nonce, echoed for fast freshness lookup
}

// SignSignedTransferCredential signs the on-chain ERC-20 transfer described
// by the challenge but does NOT broadcast it. The signed transaction bytes
// are returned inside the credential's payload so the producer can broadcast
// them later, after the handler has succeeded. This is the "settle on
// success" path used by [`X402PayPerRequestPolicy`].
//
// `rpcURL` is used only to fetch the current nonce and gas price; no
// `eth_sendRawTransaction` call is issued from this function.
//
// On success, the returned Credential's `Source` is populated with the
// payer's `did:pkh` identifier.
func SignSignedTransferCredential(ctx context.Context, ch Challenge, account *Account, rpcURL string) (Credential, error) {
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

	// Gas limit derived via eth_estimateGas (with a 25 % buffer); a static
	// 120k budget previously stranded transfers because Tempo's TIP-20
	// runtime is heavier than a mainnet ERC-20. gasLimitFor falls back to
	// 600k if the estimate RPC fails.
	gasLimit := rpc.gasLimitFor(ctx, from, parsed.Currency, data)
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

	cred := Credential{
		Challenge: ch,
		Payload: TempoSignedTransferPayload{
			Type:     CredentialTypeSignedTransfer,
			SignedTx: "0x" + hex.EncodeToString(rawBytes),
			From:     from.Hex(),
			Nonce:    nonce,
		},
		Source: account.DID(uint64(parsed.ChainID)),
	}
	return cred, nil
}

// VerifySignedTransferCredential runs the full off-chain verification chain
// on a signed-transfer credential. Unlike [VerifyCredential], it does NOT
// require the transaction to be on-chain — it verifies the credential's
// integrity, recovers the signer, decodes the embedded ERC-20 transfer call,
// and confirms the tx's nonce slot has not already been consumed.
//
// The returned raw bytes are the signed transaction ready to be passed to
// [BroadcastSignedTransfer] once the handler succeeds. The returned
// parsedCharge gives the caller the typed projection of the challenge
// request (amount, currency, recipient, chain id).
func VerifySignedTransferCredential(ctx context.Context, c Credential, expectedSecret []byte, rpcURL string, clockSkew time.Duration) (parsedCharge, []byte, error) {
	if c.Challenge.Method != MethodTempo || c.Challenge.Intent != IntentCharge {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: unsupported credential %s/%s", c.Challenge.Method, c.Challenge.Intent)
	}
	if err := VerifyChallengeID(expectedSecret, c.Challenge); err != nil {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: %w", err)
	}
	if c.Challenge.HasExpiry() {
		now := time.Now().UTC()
		if now.After(c.Challenge.Expires.Add(clockSkew)) {
			return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: challenge expired at %s", c.Challenge.Expires.Format(time.RFC3339))
		}
	}

	payload, err := decodeSignedTransferPayload(c.Payload)
	if err != nil {
		return parsedCharge{}, nil, err
	}
	if payload.Type != CredentialTypeSignedTransfer {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: unsupported payload type %q", payload.Type)
	}

	parsed, err := parseChargeRequest(c.Challenge.Request)
	if err != nil {
		return parsedCharge{}, nil, err
	}

	rawBytes, err := hex.DecodeString(strings.TrimPrefix(payload.SignedTx, "0x"))
	if err != nil {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: invalid signed_tx hex: %w", err)
	}
	var tx types.Transaction
	if err := tx.UnmarshalBinary(rawBytes); err != nil {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: unmarshal signed tx: %w", err)
	}

	chainID := big.NewInt(parsed.ChainID)
	signer := types.LatestSignerForChainID(chainID)
	recovered, err := types.Sender(signer, &tx)
	if err != nil {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: recover sender: %w", err)
	}
	if !strings.EqualFold(recovered.Hex(), payload.From) {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: recovered sender %s does not match payload.from %s", recovered.Hex(), payload.From)
	}

	if tx.To() == nil {
		return parsedCharge{}, nil, errors.New("mppx/tempo: signed tx has no recipient (contract creation)")
	}
	if !strings.EqualFold(tx.To().Hex(), parsed.Currency.Hex()) {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: tx.to %s does not match challenge currency %s", tx.To().Hex(), parsed.Currency.Hex())
	}

	gotRecipient, gotAmount, err := decodeERC20Transfer("0x" + hex.EncodeToString(tx.Data()))
	if err != nil {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: decode transfer: %w", err)
	}
	if gotRecipient != parsed.Recipient {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: tx recipient %s does not match challenge %s", gotRecipient.Hex(), parsed.Recipient.Hex())
	}
	if gotAmount.Cmp(parsed.Amount) != 0 {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: tx amount %s does not match challenge %s", gotAmount.String(), parsed.Amount.String())
	}

	// Nonce-freshness check: the signer's current on-chain nonce must be <=
	// the tx's nonce. Otherwise the nonce slot was already consumed by some
	// other transaction and broadcasting this one would fail with "nonce
	// too low".
	rpc := newRPCClient(rpcURL)
	currentNonce, err := rpc.getLatestNonce(ctx, recovered)
	if err != nil {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: nonce check: %w", err)
	}
	if currentNonce > tx.Nonce() {
		return parsedCharge{}, nil, fmt.Errorf("mppx/tempo: stale nonce (current=%d, tx=%d)", currentNonce, tx.Nonce())
	}

	return parsed, rawBytes, nil
}

// BroadcastSignedTransfer broadcasts a previously signed ERC-20 transfer to
// the network and waits for the receipt. It is intended to run AFTER a
// handler has succeeded — settle-on-success — so that the consumer only
// pays when value was actually delivered.
//
// The returned Receipt's Status is "success" when the transaction was mined
// with status `0x1`, or "reverted" when mined with status `0x0`. The
// Reference field carries the on-chain transaction hash.
func BroadcastSignedTransfer(ctx context.Context, signedTxHex string, rpcURL string) (Receipt, error) {
	rawBytes, err := hex.DecodeString(strings.TrimPrefix(signedTxHex, "0x"))
	if err != nil {
		return Receipt{}, fmt.Errorf("mppx/tempo: invalid signed_tx hex: %w", err)
	}
	rpc := newRPCClient(rpcURL)
	txHash, err := rpc.sendRawTransaction(ctx, rawBytes)
	if err != nil {
		return Receipt{}, fmt.Errorf("mppx/tempo: broadcast: %w", err)
	}
	deadline, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	if err := rpc.waitForReceipt(deadline, txHash); err != nil {
		return Receipt{}, fmt.Errorf("mppx/tempo: wait for receipt: %w", err)
	}
	receipt, err := rpc.getTransactionReceipt(ctx, txHash)
	if err != nil {
		return Receipt{}, fmt.Errorf("mppx/tempo: fetch receipt: %w", err)
	}
	status := "reverted"
	if receipt != nil && receipt.successful() {
		status = "success"
	}
	return Receipt{
		Method:    MethodTempo,
		Reference: txHash,
		Status:    status,
		Timestamp: time.Now().UTC(),
	}, nil
}

// decodeSignedTransferPayload normalises a credential payload into a
// [TempoSignedTransferPayload]. It mirrors the shape-tolerance of
// [decodeTempoPayload]: typed struct, pointer, map[string]any from a
// `encoding/json` decoder using UseNumber, or a re-encodable any.
func decodeSignedTransferPayload(p any) (TempoSignedTransferPayload, error) {
	switch v := p.(type) {
	case TempoSignedTransferPayload:
		if err := validateSignedTransferPayload(v); err != nil {
			return v, err
		}
		return v, nil
	case *TempoSignedTransferPayload:
		if v == nil {
			return TempoSignedTransferPayload{}, errors.New("mppx/tempo: nil payload")
		}
		if err := validateSignedTransferPayload(*v); err != nil {
			return *v, err
		}
		return *v, nil
	case map[string]any:
		out := TempoSignedTransferPayload{}
		if t, ok := v["type"].(string); ok {
			out.Type = t
		}
		if s, ok := v["signed_tx"].(string); ok {
			out.SignedTx = s
		}
		if f, ok := v["from"].(string); ok {
			out.From = f
		}
		switch n := v["nonce"].(type) {
		case json.Number:
			i, err := n.Int64()
			if err != nil {
				return out, fmt.Errorf("mppx/tempo: invalid nonce: %w", err)
			}
			if i < 0 {
				return out, fmt.Errorf("mppx/tempo: negative nonce %d", i)
			}
			out.Nonce = uint64(i)
		case float64:
			if n < 0 {
				return out, fmt.Errorf("mppx/tempo: negative nonce %v", n)
			}
			out.Nonce = uint64(n)
		case int:
			if n < 0 {
				return out, fmt.Errorf("mppx/tempo: negative nonce %d", n)
			}
			out.Nonce = uint64(n)
		case int64:
			if n < 0 {
				return out, fmt.Errorf("mppx/tempo: negative nonce %d", n)
			}
			out.Nonce = uint64(n)
		case uint64:
			out.Nonce = n
		case string:
			i, ok := new(big.Int).SetString(n, 10)
			if !ok {
				return out, fmt.Errorf("mppx/tempo: invalid nonce %q", n)
			}
			out.Nonce = i.Uint64()
		}
		if err := validateSignedTransferPayload(out); err != nil {
			return out, err
		}
		return out, nil
	}
	raw, err := json.Marshal(p)
	if err != nil {
		return TempoSignedTransferPayload{}, fmt.Errorf("mppx/tempo: invalid payload: %w", err)
	}
	var out TempoSignedTransferPayload
	if err := json.Unmarshal(raw, &out); err != nil {
		return out, fmt.Errorf("mppx/tempo: invalid payload: %w", err)
	}
	if err := validateSignedTransferPayload(out); err != nil {
		return out, err
	}
	return out, nil
}

func validateSignedTransferPayload(p TempoSignedTransferPayload) error {
	if p.Type == "" {
		return errors.New("mppx/tempo: payload missing type")
	}
	if p.SignedTx == "" {
		return errors.New("mppx/tempo: payload missing signed_tx")
	}
	if p.From == "" {
		return errors.New("mppx/tempo: payload missing from")
	}
	return nil
}

// getLatestNonce reports the signer's current confirmed nonce on the
// "latest" block. It is used as the freshness oracle for a signed-transfer
// credential: if the on-chain nonce has already advanced past the tx's
// nonce, the credential is stale.
func (c *rpcClient) getLatestNonce(ctx context.Context, addr common.Address) (uint64, error) {
	raw, err := c.call(ctx, "eth_getTransactionCount", []any{addr.Hex(), "latest"})
	if err != nil {
		return 0, err
	}
	var hexStr string
	if err := json.Unmarshal(raw, &hexStr); err != nil {
		return 0, err
	}
	return parseHexUint64(hexStr)
}
