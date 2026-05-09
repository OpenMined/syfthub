package cmd

import (
	"errors"
	"fmt"
	"os"

	"github.com/ethereum/go-ethereum/crypto"
	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/output"
)

var (
	walletInitForce bool
	walletInitJSON  bool
)

var walletInitCmd = &cobra.Command{
	Use:   "init",
	Short: "Generate a new local Tempo wallet",
	Long: `Generate a fresh secp256k1 keypair, encrypt the private key with a
passphrase you provide, and write the wallet to ~/.config/syfthub/wallet.dat.

The public address is stored in plaintext alongside the encrypted private key
so 'wallet show' does not require the passphrase. The passphrase itself is
NEVER stored — losing it means losing access to any funds at this address.`,
	Annotations: map[string]string{authExemptKey: "true"},
	RunE:        runWalletInit,
}

func init() {
	walletInitCmd.Flags().BoolVar(&walletInitForce, "force", false, "Overwrite an existing wallet file")
	walletInitCmd.Flags().BoolVar(&walletInitJSON, "json", false, "Output result as JSON")
}

func runWalletInit(cmd *cobra.Command, args []string) error {
	path := WalletPath()

	if !walletInitForce {
		if _, err := os.Stat(path); err == nil {
			return output.ReplyError(walletInitJSON,
				"wallet already exists at %s (use --force to overwrite)", path)
		} else if !errors.Is(err, os.ErrNotExist) {
			return output.ReplyError(walletInitJSON, "failed to stat wallet: %v", err)
		}
	}

	// Prompt + confirm passphrase. Empty passphrases are rejected — the
	// underlying PBKDF2 + AES-GCM would technically still work, but a wallet
	// with no passphrase is indistinguishable from a plaintext key file.
	pass, err := PromptPassphrase("Enter passphrase: ")
	if err != nil {
		return output.ReplyError(walletInitJSON, "%v", err)
	}
	if pass == "" {
		return output.ReplyError(walletInitJSON, "passphrase must not be empty")
	}
	confirm, err := PromptPassphrase("Confirm passphrase: ")
	if err != nil {
		return output.ReplyError(walletInitJSON, "%v", err)
	}
	if pass != confirm {
		return output.ReplyError(walletInitJSON, "passphrases do not match")
	}

	// TODO: replace with mppx.GenerateKey() once unit 6 lands.
	priv, err := crypto.GenerateKey()
	if err != nil {
		return output.ReplyError(walletInitJSON, "failed to generate key: %v", err)
	}
	privBytes := crypto.FromECDSA(priv)
	address := crypto.PubkeyToAddress(priv.PublicKey).Hex()

	ciphertext, err := EncryptPrivateKey(privBytes, pass)
	if err != nil {
		return output.ReplyError(walletInitJSON, "failed to encrypt private key: %v", err)
	}

	wf := &WalletFile{
		Version:    walletFileVersion,
		Address:    address,
		Ciphertext: ciphertext,
	}
	if err := SaveWallet(wf); err != nil {
		return output.ReplyError(walletInitJSON, "failed to write wallet: %v", err)
	}

	if walletInitJSON {
		output.JSON(map[string]any{
			"status":  output.StatusSuccess,
			"address": address,
			"path":    path,
		})
	} else {
		output.Success("Wallet created at %s", path)
		fmt.Printf("Address: %s\n", address)
		output.Warning("Keep your passphrase safe — losing it means losing your funds.")
	}
	return nil
}
