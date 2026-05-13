package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/OpenMined/syfthub/cli/internal/output"
)

// PaymentRequiredEvent mirrors the SSE/WebSocket "payment_required" event
// emitted by the aggregator (unit 10 of the transaction-policy plan,
// nifty-skipping-rainbow.md). All fields are strings to match the wire
// format exactly so that --json mode round-trips losslessly.
type PaymentRequiredEvent struct {
	ChatSessionID string `json:"chat_session_id"`
	EndpointSlug  string `json:"endpoint_slug"`
	Challenge     string `json:"challenge"`
	Amount        string `json:"amount"`
	Currency      string `json:"currency"`
	Recipient     string `json:"recipient"`
	ChallengeID   string `json:"challenge_id"`
	Intent        string `json:"intent"`
	RPCURL        string `json:"rpc_url,omitempty"`
}

// ErrPaymentDeclined is returned by HandlePaymentRequired when the user
// declines the payment prompt. Callers should abort the chat/agent stream.
var ErrPaymentDeclined = errors.New("payment declined by user")

// ── Injected helpers (overridable in tests) ─────────────────────────────────
//
// The real implementations of these helpers live in unit 6 (mppx-go) and
// unit 8 (wallet). Those units are not yet merged on main; the placeholders
// below are stubs that return a clear error. Tests swap them out via the
// package vars so the CLI is fully covered today and the production wiring
// becomes a one-line swap once units 6 + 8 land.

// promptPassphrase reads a passphrase from stdin/tty without echoing.
// TODO: requires unit 8 (wallet) — replace with wallet.PromptPassphrase.
var promptPassphrase = func(prompt string) (string, error) {
	return "", errors.New("wallet passphrase prompt not implemented (requires unit 8)")
}

// loadAndDecryptWallet loads the local wallet file and decrypts the active
// account using the supplied passphrase. Returns an opaque account handle
// that signCredential knows how to use.
//
// TODO: requires unit 8 (wallet) — replace with wallet.LoadWallet +
// wallet.DecryptWallet.
var loadAndDecryptWallet = func(passphrase string) (any, error) {
	return nil, errors.New("wallet loading not implemented (requires unit 8)")
}

// signCredential signs the given challenge with the supplied account and
// broadcasts the resulting credential via the given JSON-RPC URL. Returns
// the credential blob (sent back to the aggregator) and the on-chain tx
// hash for display.
//
// TODO: requires unit 6 (mppx-go) — replace with mppx.tempo.SignCredential.
var signCredential = func(ctx context.Context, challenge string, account any, rpcURL string) (credential string, txHash string, err error) {
	return "", "", errors.New("credential signing not implemented (requires unit 6)")
}

// ── stdin reader (overridable in tests) ─────────────────────────────────────

// readLine reads a single line from the given reader, trimming the trailing
// newline. We use a 1-byte read loop so the function works with both pipes
// (tests) and ttys without a separate bufio.Reader leaking bytes meant for
// the next prompt.
func readLine(r io.Reader) (string, error) {
	var buf bytes.Buffer
	one := make([]byte, 1)
	for {
		n, err := r.Read(one)
		if n > 0 {
			if one[0] == '\n' {
				return strings.TrimRight(buf.String(), "\r"), nil
			}
			buf.WriteByte(one[0])
		}
		if err != nil {
			if err == io.EOF && buf.Len() > 0 {
				return strings.TrimRight(buf.String(), "\r"), nil
			}
			return "", err
		}
	}
}

// ── HTTP submitter (overridable in tests) ───────────────────────────────────

// httpPostCredential POSTs the signed credential to the aggregator's
// /chat/{session_id}/payment endpoint. Overridable for tests.
//
// TODO: requires unit 10 (aggregator endpoint) — once merged the endpoint
// URL and any required headers may need to be revised.
var httpPostCredential = func(ctx context.Context, url, apiToken string, body []byte) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if apiToken != "" {
		req.Header.Set("Authorization", "Bearer "+apiToken)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("aggregator returned %d: %s", resp.StatusCode, strings.TrimSpace(string(b)))
	}
	return nil
}

// ── Handler I/O (overridable in tests) ──────────────────────────────────────

var paymentStdin io.Reader = os.Stdin
var paymentStdout io.Writer = os.Stdout

// ── Handler ─────────────────────────────────────────────────────────────────

// HandlePaymentRequired receives a payment_required event, prompts the user
// (or in --json mode emits the structured event), signs a credential via the
// local wallet, and POSTs it back to the aggregator at
// /chat/{chatSessionID}/payment.
//
// In jsonMode the function emits the event payload to stdout via output.JSON
// and returns nil immediately — external tooling is responsible for signing
// and POSTing the credential. The chat stream will block on the aggregator
// until the credential arrives or the aggregator times out.
//
// In interactive mode the function:
//  1. prints the price + recipient and prompts y/N,
//  2. reads the wallet passphrase,
//  3. signs + broadcasts the credential,
//  4. POSTs {challenge_id, credential} to the aggregator.
//
// Returns ErrPaymentDeclined when the user declines so callers can abort
// the stream cleanly.
func HandlePaymentRequired(
	ctx context.Context,
	jsonMode bool,
	aggregatorURL string,
	apiToken string,
	chatSessionID string,
	defaultRPCURL string,
	event PaymentRequiredEvent,
) error {
	// Resolve the chat session id: prefer the caller's value, fall back to
	// the event payload (the aggregator always populates it but the CLI may
	// have a more authoritative id from the request kickoff).
	sessionID := chatSessionID
	if sessionID == "" {
		sessionID = event.ChatSessionID
	}

	if jsonMode {
		output.JSON(map[string]any{
			"event":           "payment_required",
			"chat_session_id": sessionID,
			"endpoint_slug":   event.EndpointSlug,
			"challenge":       event.Challenge,
			"amount":          event.Amount,
			"currency":        event.Currency,
			"recipient":       event.Recipient,
			"challenge_id":    event.ChallengeID,
			"intent":          event.Intent,
			"rpc_url":         event.RPCURL,
		})
		return nil
	}

	// Interactive prompt.
	fmt.Fprintf(paymentStdout,
		"\nEndpoint %s requires payment of %s %s to %s.\nApprove? [y/N]: ",
		event.EndpointSlug, event.Amount, event.Currency, event.Recipient,
	)
	answer, err := readLine(paymentStdin)
	if err != nil {
		return fmt.Errorf("failed to read approval: %w", err)
	}
	answer = strings.TrimSpace(answer)
	if answer != "y" && answer != "Y" {
		fmt.Fprintln(paymentStdout, "Payment declined.")
		return ErrPaymentDeclined
	}

	passphrase, err := promptPassphrase("Wallet passphrase: ")
	if err != nil {
		return fmt.Errorf("failed to read passphrase: %w", err)
	}

	account, err := loadAndDecryptWallet(passphrase)
	if err != nil {
		return fmt.Errorf("failed to unlock wallet: %w", err)
	}

	rpcURL := event.RPCURL
	if rpcURL == "" {
		rpcURL = defaultRPCURL
	}
	if rpcURL == "" {
		return errors.New("no Tempo RPC URL configured (set tempo_rpc_url in settings.json or include rpc_url in the event)")
	}

	fmt.Fprintln(paymentStdout, "Submitting credential…")

	credential, txHash, err := signCredential(ctx, event.Challenge, account, rpcURL)
	if err != nil {
		return fmt.Errorf("failed to sign credential: %w", err)
	}

	body, err := json.Marshal(map[string]string{
		"challenge_id": event.ChallengeID,
		"credential":   credential,
	})
	if err != nil {
		return fmt.Errorf("failed to marshal credential: %w", err)
	}

	url := strings.TrimRight(aggregatorURL, "/") + "/chat/" + sessionID + "/payment"
	if err := httpPostCredential(ctx, url, apiToken, body); err != nil {
		return fmt.Errorf("failed to submit credential: %w", err)
	}

	fmt.Fprintf(paymentStdout, "Payment confirmed — tx %s\n", txHash)
	return nil
}
