package cmd

import (
	"bufio"
	"context"
	"crypto/ecdsa"
	"errors"
	"fmt"
	"math/big"
	"os"
	"strings"
	"time"

	"github.com/ethereum/go-ethereum"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethclient"
	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/output"
)

var (
	walletSendCurrency string
	walletSendRPCURL   string
	walletSendChainID  int64
	walletSendJSON     bool
	walletSendYes      bool
)

var walletSendCmd = &cobra.Command{
	Use:   "send <to-address> <amount>",
	Short: "Send PathUSD (or another ERC-20) to an address",
	Long: `Sign and broadcast an ERC-20 transfer from the local wallet.

The amount is in token base units (the ERC-20 ` + "`amount`" + ` argument passed
straight to ` + "`transfer(to, amount)`" + `, no decimals applied). The default
currency is the canonical PathUSD contract used by the transaction policy;
override with --currency for other ERC-20 tokens on the same chain.

This command is interactive: it prompts for the wallet passphrase, then asks
for confirmation before broadcasting. Pass --yes to skip the confirmation.`,
	Annotations: map[string]string{authExemptKey: "true"},
	Args:        cobra.ExactArgs(2),
	RunE:        runWalletSend,
}

func init() {
	walletSendCmd.Flags().StringVar(&walletSendCurrency, "currency", defaultPathUSDAddress,
		"ERC-20 contract address of the token to send")
	walletSendCmd.Flags().StringVar(&walletSendRPCURL, "rpc-url", "", "Tempo RPC URL (required)")
	walletSendCmd.Flags().Int64Var(&walletSendChainID, "chain-id", defaultTempoChainID, "EIP-155 chain ID")
	walletSendCmd.Flags().BoolVar(&walletSendJSON, "json", false, "Output result as JSON")
	walletSendCmd.Flags().BoolVar(&walletSendYes, "yes", false, "Skip the confirmation prompt")
	_ = walletSendCmd.MarkFlagRequired("rpc-url")
}

func runWalletSend(cmd *cobra.Command, args []string) error {
	toArg := strings.TrimSpace(args[0])
	amountArg := strings.TrimSpace(args[1])

	if !common.IsHexAddress(toArg) {
		return output.ReplyError(walletSendJSON, "invalid recipient address: %s", toArg)
	}
	if !common.IsHexAddress(walletSendCurrency) {
		return output.ReplyError(walletSendJSON, "invalid --currency address: %s", walletSendCurrency)
	}
	amount, ok := new(big.Int).SetString(amountArg, 10)
	if !ok || amount.Sign() < 0 {
		return output.ReplyError(walletSendJSON, "invalid amount: %s (expected non-negative integer)", amountArg)
	}

	wf, err := LoadWallet()
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return output.ReplyError(walletSendJSON,
				"no wallet found at %s — run 'syft wallet init'", WalletPath())
		}
		return output.ReplyError(walletSendJSON, "failed to load wallet: %v", err)
	}

	pass, err := PromptPassphrase("Enter passphrase: ")
	if err != nil {
		return output.ReplyError(walletSendJSON, "%v", err)
	}
	privBytes, err := DecryptWallet(wf, pass)
	if err != nil {
		return output.ReplyError(walletSendJSON, "%v", err)
	}
	priv, err := crypto.ToECDSA(privBytes)
	if err != nil {
		return output.ReplyError(walletSendJSON, "wallet contains an invalid key: %v", err)
	}
	from := crypto.PubkeyToAddress(priv.PublicKey)

	if !walletSendYes && !walletSendJSON {
		fmt.Printf("Send %s units of %s to %s from %s? [y/N] ",
			amount.String(), walletSendCurrency, toArg, from.Hex())
		reader := bufio.NewReader(os.Stdin)
		line, _ := reader.ReadString('\n')
		ans := strings.ToLower(strings.TrimSpace(line))
		if ans != "y" && ans != "yes" {
			return output.ReplyError(walletSendJSON, "aborted by user")
		}
	}

	res, err := signAndBroadcastERC20Transfer(cmd.Context(), erc20TransferParams{
		RPCURL:  walletSendRPCURL,
		ChainID: big.NewInt(walletSendChainID),
		PrivKey: priv,
		Token:   common.HexToAddress(walletSendCurrency),
		To:      common.HexToAddress(toArg),
		Amount:  amount,
	})
	if err != nil {
		return output.ReplyError(walletSendJSON, "%v", err)
	}

	if walletSendJSON {
		output.JSON(map[string]any{
			"status":   output.StatusSuccess,
			"tx_hash":  res.TxHash,
			"from":     from.Hex(),
			"to":       toArg,
			"amount":   amount.String(),
			"chain_id": walletSendChainID,
			"mined":    res.Mined,
		})
	} else {
		output.Success("Submitted tx %s", res.TxHash)
		if res.Mined {
			fmt.Println("Receipt confirmed.")
		} else {
			fmt.Println("Receipt not yet available; check the explorer for the tx status.")
		}
	}
	return nil
}

// erc20TransferParams bundles the inputs to signAndBroadcastERC20Transfer so
// the helper is easy to mock in tests.
type erc20TransferParams struct {
	RPCURL  string
	ChainID *big.Int
	PrivKey *ecdsa.PrivateKey
	Token   common.Address
	To      common.Address
	Amount  *big.Int
}

// erc20TransferResult is what the wallet send helper returns to the caller.
type erc20TransferResult struct {
	TxHash string
	Mined  bool
}

// signAndBroadcastERC20Transfer builds, signs, and broadcasts an EIP-1559
// `transfer(address,uint256)` call against the given ERC-20 contract. After
// broadcasting it polls for a receipt for up to 60 s; an empty receipt is not
// treated as a failure (the tx may simply not have been mined yet).
//
// Declared as a `var` so tests can swap in an in-process implementation.
var signAndBroadcastERC20Transfer = func(ctx context.Context, p erc20TransferParams) (erc20TransferResult, error) {
	if ctx == nil {
		ctx = context.Background()
	}
	dialCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	client, err := ethclient.DialContext(dialCtx, p.RPCURL)
	if err != nil {
		return erc20TransferResult{}, fmt.Errorf("dial RPC: %w", err)
	}
	defer client.Close()

	from := crypto.PubkeyToAddress(p.PrivKey.PublicKey)
	nonceCtx, cancelNonce := context.WithTimeout(ctx, 10*time.Second)
	defer cancelNonce()
	nonce, err := client.PendingNonceAt(nonceCtx, from)
	if err != nil {
		return erc20TransferResult{}, fmt.Errorf("get nonce: %w", err)
	}

	gasTipCap, err := client.SuggestGasTipCap(ctx)
	if err != nil {
		return erc20TransferResult{}, fmt.Errorf("suggest gas tip: %w", err)
	}
	header, err := client.HeaderByNumber(ctx, nil)
	if err != nil {
		return erc20TransferResult{}, fmt.Errorf("get header: %w", err)
	}
	// EIP-1559: maxFeePerGas = baseFee*2 + tip — gives a safety margin for
	// base-fee fluctuation across one block.
	gasFeeCap := new(big.Int).Add(new(big.Int).Mul(header.BaseFee, big.NewInt(2)), gasTipCap)

	data := encodeERC20Transfer(p.To, p.Amount)

	gasCtx, cancelGas := context.WithTimeout(ctx, 10*time.Second)
	defer cancelGas()
	gas, err := client.EstimateGas(gasCtx, ethereum.CallMsg{
		From:      from,
		To:        &p.Token,
		GasFeeCap: gasFeeCap,
		GasTipCap: gasTipCap,
		Data:      data,
	})
	if err != nil {
		// Fall back to a generous default — Tempo testnets sometimes refuse
		// estimate calls for a fresh contract.
		gas = 80_000
	}

	tx := types.NewTx(&types.DynamicFeeTx{
		ChainID:   p.ChainID,
		Nonce:     nonce,
		GasTipCap: gasTipCap,
		GasFeeCap: gasFeeCap,
		Gas:       gas,
		To:        &p.Token,
		Value:     big.NewInt(0),
		Data:      data,
	})

	signer := types.LatestSignerForChainID(p.ChainID)
	signed, err := types.SignTx(tx, signer, p.PrivKey)
	if err != nil {
		return erc20TransferResult{}, fmt.Errorf("sign tx: %w", err)
	}

	sendCtx, cancelSend := context.WithTimeout(ctx, 15*time.Second)
	defer cancelSend()
	if err := client.SendTransaction(sendCtx, signed); err != nil {
		return erc20TransferResult{}, fmt.Errorf("send tx: %w", err)
	}

	hash := signed.Hash().Hex()
	mined := waitForReceipt(ctx, client, signed.Hash(), 60*time.Second)
	return erc20TransferResult{TxHash: hash, Mined: mined}, nil
}

// waitForReceipt polls TransactionReceipt with simple linear backoff until
// `timeout` elapses. Returns true once a receipt is observed.
func waitForReceipt(ctx context.Context, client *ethclient.Client, hash common.Hash, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	delay := 500 * time.Millisecond
	for time.Now().Before(deadline) {
		rcptCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		_, err := client.TransactionReceipt(rcptCtx, hash)
		cancel()
		if err == nil {
			return true
		}
		select {
		case <-ctx.Done():
			return false
		case <-time.After(delay):
		}
		if delay < 5*time.Second {
			delay += 500 * time.Millisecond
		}
	}
	return false
}

// encodeERC20Transfer builds the calldata for `transfer(address,uint256)`.
//
// Selector: keccak256("transfer(address,uint256)")[:4] = 0xa9059cbb.
func encodeERC20Transfer(to common.Address, amount *big.Int) []byte {
	const selector = "a9059cbb"
	selBytes := common.FromHex(selector)

	out := make([]byte, 0, 4+32+32)
	out = append(out, selBytes...)
	out = append(out, common.LeftPadBytes(to.Bytes(), 32)...)
	out = append(out, common.LeftPadBytes(amount.Bytes(), 32)...)
	return out
}
