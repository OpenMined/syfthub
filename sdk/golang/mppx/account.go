package mppx

import (
	"crypto/ecdsa"
	"errors"
	"fmt"
	"strings"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"
)

// Account is a thin wrapper around a secp256k1 private key. It is the Go
// equivalent of viem's `PrivateKeyAccount` used by the TypeScript reference
// implementation. Use [LoadAccount] to construct one from a hex-encoded
// private key.
//
// Account is intentionally small: it knows how to expose its EVM address and
// hand its private key to a transaction signer. It does not maintain any
// remote state.
type Account struct {
	privateKey *ecdsa.PrivateKey
	address    common.Address
}

// LoadAccount parses a 32-byte hex-encoded secp256k1 private key (with or
// without a "0x" prefix) and returns an Account. The corresponding EVM
// address is derived once at load time.
func LoadAccount(privateKeyHex string) (*Account, error) {
	if privateKeyHex == "" {
		return nil, errors.New("mppx: empty private key")
	}
	cleaned := strings.TrimPrefix(strings.TrimSpace(privateKeyHex), "0x")
	pk, err := crypto.HexToECDSA(cleaned)
	if err != nil {
		return nil, fmt.Errorf("mppx: invalid private key: %w", err)
	}
	return &Account{
		privateKey: pk,
		address:    crypto.PubkeyToAddress(pk.PublicKey),
	}, nil
}

// Address returns the account's EVM address.
func (a *Account) Address() common.Address { return a.address }

// PrivateKey returns the underlying ecdsa.PrivateKey. Callers MUST treat the
// returned value as sensitive material and avoid persisting or logging it.
func (a *Account) PrivateKey() *ecdsa.PrivateKey { return a.privateKey }

// DID returns the `did:pkh:eip155:<chainId>:<address>` representation of the
// account. This is the canonical `source` field for an MPP credential.
func (a *Account) DID(chainID uint64) string {
	return fmt.Sprintf("did:pkh:eip155:%d:%s", chainID, a.address.Hex())
}
