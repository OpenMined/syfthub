package cmd

import (
	"crypto/aes"
	"crypto/cipher"
	cryptoRand "crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"golang.org/x/crypto/pbkdf2"
	"golang.org/x/term"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
)

// NOTE: We use go-ethereum directly for keypair / address derivation here and
// in the wallet subcommands.
// TODO: replace with `sdk/golang/mppx` once unit 6 lands.

// Default RPC and chain settings for Tempo + PathUSD.
const (
	defaultTempoChainID = int64(42431)
	// defaultPathUSDAddress is the canonical PathUSD ERC-20 contract address
	// used by the transaction policy. Sourced from the design notes
	// (`/home/junior/.claude/plans/nifty-skipping-rainbow.md`).
	defaultPathUSDAddress = "0x20c0000000000000000000000000000000000000"

	// PBKDF2 + AES-GCM parameters for wallet encryption.
	walletPBKDF2Iters  = 100_000
	walletKeyLen       = 32
	walletSaltLen      = 16
	walletNonceLen     = 12
	walletFileVersion  = 1
	walletFileBaseName = "wallet.dat"
)

// walletCmd is the root command for local Tempo wallet management.
var walletCmd = &cobra.Command{
	Use:         "wallet",
	Short:       "Manage your local Tempo wallet",
	Long:        `Generate, inspect, and use a local Tempo wallet for paying transaction-policy endpoints.`,
	Annotations: map[string]string{authExemptKey: "true"},
}

func init() {
	rootCmd.AddCommand(walletCmd)
	walletCmd.AddCommand(walletInitCmd)
	walletCmd.AddCommand(walletShowCmd)
	walletCmd.AddCommand(walletSendCmd)
}

// WalletFile is the on-disk JSON representation of a wallet.
//
// `Address` (public) lets `wallet show` work without prompting for the
// passphrase. `Ciphertext` is the base64 of `salt | nonce | ciphertext_with_tag`
// produced by AES-256-GCM over the raw 32-byte private key.
type WalletFile struct {
	Version    int    `json:"version"`
	Address    string `json:"address"`
	Ciphertext string `json:"ciphertext"`
}

// WalletPath returns the absolute path to the wallet file inside the SyftHub
// config directory.
func WalletPath() string {
	return filepath.Join(nodeconfig.ConfigDir, walletFileBaseName)
}

// LoadWallet reads and parses the wallet JSON from disk.
//
// Returns os.ErrNotExist when the wallet file is missing — callers can use
// `errors.Is(err, os.ErrNotExist)` to detect first-run state.
func LoadWallet() (*WalletFile, error) {
	return LoadWalletFrom(WalletPath())
}

// LoadWalletFrom is LoadWallet with an explicit path (useful for tests).
func LoadWalletFrom(path string) (*WalletFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var wf WalletFile
	if err := json.Unmarshal(data, &wf); err != nil {
		return nil, fmt.Errorf("invalid wallet file: %w", err)
	}
	if wf.Version != walletFileVersion {
		return nil, fmt.Errorf("unsupported wallet version: %d", wf.Version)
	}
	return &wf, nil
}

// SaveWallet writes the wallet JSON to disk with mode 0600.
func SaveWallet(wf *WalletFile) error {
	return SaveWalletTo(wf, WalletPath())
}

// SaveWalletTo is SaveWallet with an explicit path (useful for tests).
func SaveWalletTo(wf *WalletFile, path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return fmt.Errorf("failed to create config directory: %w", err)
	}
	data, err := json.MarshalIndent(wf, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0600)
}

// EncryptPrivateKey produces the base64(salt|nonce|ciphertext) blob expected
// in WalletFile.Ciphertext.
func EncryptPrivateKey(privateKey []byte, passphrase string) (string, error) {
	salt := make([]byte, walletSaltLen)
	if _, err := readRand(salt); err != nil {
		return "", err
	}
	nonce := make([]byte, walletNonceLen)
	if _, err := readRand(nonce); err != nil {
		return "", err
	}
	key := pbkdf2.Key([]byte(passphrase), salt, walletPBKDF2Iters, walletKeyLen, sha256.New)
	gcm, err := newGCM(key)
	if err != nil {
		return "", err
	}
	ct := gcm.Seal(nil, nonce, privateKey, nil)
	blob := append(append(append([]byte{}, salt...), nonce...), ct...)
	return base64.StdEncoding.EncodeToString(blob), nil
}

// DecryptWallet returns the raw private key bytes for the given wallet using
// the supplied passphrase. Wrong passphrases surface as an error from AES-GCM
// authentication.
func DecryptWallet(wf *WalletFile, passphrase string) ([]byte, error) {
	blob, err := base64.StdEncoding.DecodeString(wf.Ciphertext)
	if err != nil {
		return nil, fmt.Errorf("wallet ciphertext is not valid base64: %w", err)
	}
	if len(blob) < walletSaltLen+walletNonceLen+1 {
		return nil, errors.New("wallet ciphertext is truncated")
	}
	salt := blob[:walletSaltLen]
	nonce := blob[walletSaltLen : walletSaltLen+walletNonceLen]
	ct := blob[walletSaltLen+walletNonceLen:]
	key := pbkdf2.Key([]byte(passphrase), salt, walletPBKDF2Iters, walletKeyLen, sha256.New)
	gcm, err := newGCM(key)
	if err != nil {
		return nil, err
	}
	pt, err := gcm.Open(nil, nonce, ct, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt wallet (wrong passphrase?): %w", err)
	}
	return pt, nil
}

// PromptPassphrase reads a passphrase from the controlling terminal without
// echoing characters. The trailing newline that the user pressed is consumed
// for the caller.
func PromptPassphrase(label string) (string, error) {
	if !term.IsTerminal(int(os.Stdin.Fd())) {
		return "", errors.New("passphrase required but stdin is not a terminal")
	}
	fmt.Print(label)
	b, err := term.ReadPassword(int(os.Stdin.Fd()))
	fmt.Println()
	if err != nil {
		return "", fmt.Errorf("failed to read passphrase: %w", err)
	}
	return strings.TrimRight(string(b), "\r\n"), nil
}

// readRand fills b with crypto/rand bytes (indirected so tests can swap it).
var readRand = func(b []byte) (int, error) {
	return cryptoRand.Read(b)
}

// newGCM constructs an AES-256-GCM AEAD from a 32-byte key.
func newGCM(key []byte) (cipher.AEAD, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	return cipher.NewGCM(block)
}
