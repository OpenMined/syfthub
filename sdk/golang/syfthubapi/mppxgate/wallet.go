package mppxgate

import (
	"errors"
	"fmt"
	"os"
	"strings"

	"github.com/openmined/syfthub/sdk/golang/mppx"
)

// LoadLocalWallet reads a hex-encoded secp256k1 private key from keyPath and
// returns the loaded mppx.Account. The file content may include a leading
// "0x" prefix and trailing whitespace/newline; both are tolerated.
//
// The wallet path convention on the desktop app is
// ~/.syfthub-desktop/wallet.key (see U8). The caller resolves the path; this
// helper does not assume a location.
func LoadLocalWallet(keyPath string) (*mppx.Account, error) {
	if keyPath == "" {
		return nil, errors.New("mppxgate: empty wallet key path")
	}
	raw, err := os.ReadFile(keyPath)
	if err != nil {
		return nil, fmt.Errorf("mppxgate: read wallet %q: %w", keyPath, err)
	}
	hex := strings.TrimSpace(string(raw))
	if hex == "" {
		return nil, fmt.Errorf("mppxgate: wallet file %q is empty", keyPath)
	}
	acc, err := mppx.LoadAccount(hex)
	if err != nil {
		return nil, fmt.Errorf("mppxgate: load wallet: %w", err)
	}
	return acc, nil
}

// MustMatchPayTo returns nil iff account.Address().Hex() equals expected
// (case-insensitive). It is the refuse-to-start guard used by the desktop
// app: when the X402 policy's pay_to does not match the wallet that will
// actually settle, every payment would be sent to someone else's address.
// Fail loudly at startup rather than silently leaking funds.
func MustMatchPayTo(account *mppx.Account, expected string) error {
	if account == nil {
		return errors.New("mppxgate: account is nil")
	}
	if expected == "" {
		return errors.New("mppxgate: expected pay_to is empty")
	}
	got := account.Address().Hex()
	if !strings.EqualFold(got, expected) {
		return fmt.Errorf("mppxgate: wallet address %s does not match policy pay_to %s", got, expected)
	}
	return nil
}
