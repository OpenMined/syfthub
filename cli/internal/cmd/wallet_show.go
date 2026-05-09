package cmd

import (
	"context"
	"errors"
	"fmt"
	"math/big"
	"os"
	"time"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/ethclient"
	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/output"
)

var (
	walletShowBalance bool
	walletShowRPCURL  string
	walletShowJSON    bool
)

var walletShowCmd = &cobra.Command{
	Use:   "show",
	Short: "Print the local wallet address (and optional balance)",
	Long: `Display the public address of the local Tempo wallet.

The address is stored in plaintext alongside the encrypted private key, so
this command does NOT prompt for the passphrase. Pass --balance with --rpc-url
to additionally query the chain for the native-token balance (read-only RPC,
still no passphrase required).`,
	Annotations: map[string]string{authExemptKey: "true"},
	RunE:        runWalletShow,
}

func init() {
	walletShowCmd.Flags().BoolVar(&walletShowBalance, "balance", false, "Query the chain for the wallet balance")
	walletShowCmd.Flags().StringVar(&walletShowRPCURL, "rpc-url", "", "Tempo RPC URL (required with --balance)")
	walletShowCmd.Flags().BoolVar(&walletShowJSON, "json", false, "Output result as JSON")
}

func runWalletShow(cmd *cobra.Command, args []string) error {
	wf, err := LoadWallet()
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return output.ReplyError(walletShowJSON,
				"no wallet found at %s — run 'syft wallet init'", WalletPath())
		}
		return output.ReplyError(walletShowJSON, "failed to load wallet: %v", err)
	}

	result := map[string]any{
		"status":  output.StatusSuccess,
		"address": wf.Address,
		"path":    WalletPath(),
	}

	if walletShowBalance {
		if walletShowRPCURL == "" {
			return output.ReplyError(walletShowJSON, "--balance requires --rpc-url")
		}
		bal, err := fetchNativeBalance(cmd.Context(), walletShowRPCURL, wf.Address)
		if err != nil {
			return output.ReplyError(walletShowJSON, "failed to fetch balance: %v", err)
		}
		result["balance_wei"] = bal.String()
	}

	if walletShowJSON {
		output.JSON(result)
		return nil
	}

	fmt.Printf("Address: %s\n", wf.Address)
	output.Dim.Print("Path:    ")
	fmt.Println(WalletPath())
	if walletShowBalance {
		output.Dim.Print("Balance: ")
		fmt.Printf("%s wei\n", result["balance_wei"])
	}
	return nil
}

// fetchNativeBalance queries the given RPC for the wallet's native-token
// balance. Used only by `show --balance`; it does NOT need the passphrase
// because eth_getBalance is read-only.
func fetchNativeBalance(ctx context.Context, rpcURL, address string) (*big.Int, error) {
	if ctx == nil {
		ctx = context.Background()
	}
	dialCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	client, err := ethclient.DialContext(dialCtx, rpcURL)
	if err != nil {
		return nil, fmt.Errorf("dial RPC: %w", err)
	}
	defer client.Close()

	callCtx, cancelCall := context.WithTimeout(ctx, 10*time.Second)
	defer cancelCall()

	bal, err := client.BalanceAt(callCtx, common.HexToAddress(address), nil)
	if err != nil {
		return nil, fmt.Errorf("eth_getBalance: %w", err)
	}
	return bal, nil
}
