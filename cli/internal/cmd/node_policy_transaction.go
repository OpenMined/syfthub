package cmd

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/nodeops"
)

// PolicyTypeTransaction is the type discriminator for on-chain payment policies
// (MPP-over-NATS, Tempo passthrough). When this type is selected on
// `syft node endpoint policy add`, dedicated flags drive the policy YAML and
// an HMAC secret is provisioned alongside it.
const PolicyTypeTransaction = "transaction"

// transactionSecretFilename is the basename of the HMAC secret file written
// inside the endpoint's policy/ directory. It is intentionally dot-prefixed so
// existing tooling treats it as a hidden artifact, and it is added to the
// endpoint's .gitignore on first creation.
const transactionSecretFilename = ".transaction_secret"

// transactionPolicyFilename is the basename of the per-policy YAML emitted by
// the transaction-policy add flow. The plan calls for a per-file layout under
// <endpoint_dir>/policy/, distinct from the legacy single-file policies.yaml.
const transactionPolicyFilename = "transaction.yaml"

// Defaults that match the on-chain Tempo PathUSD configuration documented in
// the unit's plan. Override per-call via the corresponding flags.
const (
	defaultTxCurrency   = "0x20c0000000000000000000000000000000000000"
	defaultTxMethod     = "tempo"
	defaultTxIntent     = "charge"
	defaultTxChainID    = 42431
	defaultTxTTLSeconds = 600
)

// recipientPattern validates a 0x-prefixed Ethereum address (40 hex chars).
var recipientPattern = regexp.MustCompile(`^0x[a-fA-F0-9]{40}$`)

// amountPattern validates a positive decimal expressed as a string. Using a
// regex keeps the dependency surface minimal vs. pulling in a decimal lib.
var amountPattern = regexp.MustCompile(`^\d+(\.\d+)?$`)

// transaction-specific flag values populated by cobra. They live alongside
// `nodePolicyAdd*` so the existing single command can branch on --type.
var (
	nodePolicyAddRecipient  string
	nodePolicyAddAmount     string
	nodePolicyAddCurrency   string
	nodePolicyAddMethod     string
	nodePolicyAddIntent     string
	nodePolicyAddChainID    int64
	nodePolicyAddRPCURL     string
	nodePolicyAddTTLSeconds int
	nodePolicyAddForce      bool
)

// registerTransactionPolicyFlags wires the transaction-only flags onto the
// shared `policy add` cobra command. They are intentionally not marked
// required at the cobra level because non-transaction policy types do not use
// them — validation is deferred to runtime when --type=transaction.
func registerTransactionPolicyFlags(cmd *cobra.Command) {
	cmd.Flags().StringVar(&nodePolicyAddRecipient, "recipient", "", "Payment recipient address (0x-prefixed, transaction policies only)")
	cmd.Flags().StringVar(&nodePolicyAddAmount, "amount", "", "Payment amount as decimal string (transaction policies only)")
	cmd.Flags().StringVar(&nodePolicyAddCurrency, "currency", defaultTxCurrency, "Currency contract address (transaction policies only)")
	cmd.Flags().StringVar(&nodePolicyAddMethod, "method", defaultTxMethod, "Payment method (transaction policies only)")
	cmd.Flags().StringVar(&nodePolicyAddIntent, "intent", defaultTxIntent, "Payment intent (transaction policies only)")
	cmd.Flags().Int64Var(&nodePolicyAddChainID, "chain-id", defaultTxChainID, "Chain ID (transaction policies only)")
	cmd.Flags().StringVar(&nodePolicyAddRPCURL, "rpc-url", "", "RPC URL for the chain (transaction policies only)")
	cmd.Flags().IntVar(&nodePolicyAddTTLSeconds, "ttl-seconds", defaultTxTTLSeconds, "Payment challenge TTL in seconds (transaction policies only)")
	cmd.Flags().BoolVar(&nodePolicyAddForce, "force", false, "Overwrite an existing transaction secret (transaction policies only)")
}

// transactionPolicyArgs is a value-type snapshot of the transaction-only
// flags so the helper is testable without spinning up cobra.
type transactionPolicyArgs struct {
	Name       string
	Recipient  string
	Amount     string
	Currency   string
	Method     string
	Intent     string
	ChainID    int64
	RPCURL     string
	TTLSeconds int
	Force      bool
}

// validateTransactionArgs enforces the per-flag invariants documented in the
// plan: recipient must be a 0x address, amount a positive decimal, rpc-url a
// well-formed https URL. Returns a user-facing error message on the first
// violation; callers print it via output.ReplyErrorSoft.
func validateTransactionArgs(a transactionPolicyArgs) error {
	if a.Name == "" {
		return fmt.Errorf("--name is required")
	}
	if a.Recipient == "" {
		return fmt.Errorf("--recipient is required for transaction policies")
	}
	if !recipientPattern.MatchString(a.Recipient) {
		return fmt.Errorf("--recipient must be a 0x-prefixed Ethereum address (got %q)", a.Recipient)
	}
	if a.Amount == "" {
		return fmt.Errorf("--amount is required for transaction policies")
	}
	if !amountPattern.MatchString(a.Amount) {
		return fmt.Errorf("--amount must be a positive decimal (got %q)", a.Amount)
	}
	// Reject "0" / "0.0" / "0.00..." — the regex permits them but a zero
	// payment is meaningless and almost certainly a user mistake.
	if isZeroAmount(a.Amount) {
		return fmt.Errorf("--amount must be greater than zero (got %q)", a.Amount)
	}
	if a.RPCURL == "" {
		return fmt.Errorf("--rpc-url is required for transaction policies")
	}
	parsed, err := url.Parse(a.RPCURL)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" {
		return fmt.Errorf("--rpc-url must be an https:// URL (got %q)", a.RPCURL)
	}
	if a.TTLSeconds <= 0 {
		return fmt.Errorf("--ttl-seconds must be positive (got %d)", a.TTLSeconds)
	}
	return nil
}

// isZeroAmount returns true if the decimal string represents zero. Cheaper
// than parsing and avoids pulling in math/big for a one-shot check.
func isZeroAmount(s string) bool {
	for _, r := range s {
		if r != '0' && r != '.' {
			return false
		}
	}
	return true
}

// transactionPolicyOutcome captures the side effects of a successful
// transaction-policy add for both human and JSON output paths.
type transactionPolicyOutcome struct {
	PolicyPath       string
	SecretPath       string
	GitignoreUpdated bool
}

// runTransactionPolicyAdd performs the full per-endpoint side effect set:
//  1. Write policy/transaction.yaml with the validated config.
//  2. Generate (or refuse to overwrite) the .transaction_secret file.
//  3. Append the secret path to the endpoint's .gitignore.
//
// It is decoupled from cobra so tests can drive it directly with a tmp dir.
func runTransactionPolicyAdd(endpointDir string, a transactionPolicyArgs) (*transactionPolicyOutcome, error) {
	if err := validateTransactionArgs(a); err != nil {
		return nil, err
	}

	if _, err := os.Stat(endpointDir); os.IsNotExist(err) {
		return nil, fmt.Errorf("endpoint directory does not exist: %s", endpointDir)
	}

	policyDir := filepath.Join(endpointDir, "policy")
	if err := os.MkdirAll(policyDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create policy directory: %w", err)
	}

	policyPath := filepath.Join(policyDir, transactionPolicyFilename)
	if err := writeTransactionPolicyYAML(policyPath, a); err != nil {
		return nil, err
	}

	secretPath := filepath.Join(policyDir, transactionSecretFilename)
	if err := generateTransactionSecret(secretPath, a.Force); err != nil {
		return nil, err
	}

	gitignorePath := filepath.Join(endpointDir, ".gitignore")
	gitignoreUpdated, err := ensureGitignoreEntry(gitignorePath, "policy/"+transactionSecretFilename)
	if err != nil {
		return nil, err
	}

	return &transactionPolicyOutcome{
		PolicyPath:       policyPath,
		SecretPath:       secretPath,
		GitignoreUpdated: gitignoreUpdated,
	}, nil
}

// writeTransactionPolicyYAML serialises the policy to disk in the per-policy
// file layout. Reuses nodeops.Policy so the on-disk shape stays consistent
// with the legacy policies.yaml entries and a future nodeops.SavePolicy that
// supports per-file layout becomes a drop-in replacement.
func writeTransactionPolicyYAML(path string, a transactionPolicyArgs) error {
	policy := nodeops.Policy{
		Name: a.Name,
		Type: PolicyTypeTransaction,
		Config: map[string]interface{}{
			"recipient":   a.Recipient,
			"amount":      a.Amount,
			"currency":    a.Currency,
			"method":      a.Method,
			"intent":      a.Intent,
			"chain_id":    a.ChainID,
			"rpc_url":     a.RPCURL,
			"ttl_seconds": a.TTLSeconds,
		},
	}

	content, err := yaml.Marshal(&policy)
	if err != nil {
		return fmt.Errorf("failed to marshal transaction policy: %w", err)
	}

	if err := os.WriteFile(path, content, 0644); err != nil {
		return fmt.Errorf("failed to write transaction policy: %w", err)
	}
	return nil
}

// generateTransactionSecret writes 32 random bytes (base64url-encoded) to path
// with mode 0600. Without force, O_EXCL ensures we never silently overwrite an
// existing secret — overwriting would invalidate in-flight payment challenges.
func generateTransactionSecret(path string, force bool) error {
	buf := make([]byte, 32)
	if _, err := rand.Read(buf); err != nil {
		return fmt.Errorf("failed to generate random bytes: %w", err)
	}
	encoded := base64.RawURLEncoding.EncodeToString(buf)

	flags := os.O_WRONLY | os.O_CREATE | os.O_TRUNC
	if !force {
		flags |= os.O_EXCL
	}
	f, err := os.OpenFile(path, flags, 0600)
	if err != nil {
		if os.IsExist(err) {
			return fmt.Errorf("transaction secret already exists at %s; pass --force to regenerate (this will invalidate in-flight payment challenges)", path)
		}
		return fmt.Errorf("failed to open transaction secret: %w", err)
	}
	defer f.Close()

	if _, err := f.Write([]byte(encoded)); err != nil {
		return fmt.Errorf("failed to write transaction secret: %w", err)
	}
	return nil
}

// ensureGitignoreEntry idempotently appends entry to the .gitignore at path.
// Creates the file if missing. Returns true iff the file was modified (or
// created), so callers can report it in the JSON envelope.
func ensureGitignoreEntry(path, entry string) (bool, error) {
	existing, err := os.ReadFile(path)
	if err != nil && !os.IsNotExist(err) {
		return false, fmt.Errorf("failed to read .gitignore: %w", err)
	}

	if err == nil {
		// Idempotency: skip if a matching line is already present (any of
		// the lines, not just whole-file substring, to avoid false positives
		// from comments).
		for _, line := range strings.Split(string(existing), "\n") {
			if strings.TrimSpace(line) == entry {
				return false, nil
			}
		}
	}

	var buf strings.Builder
	if len(existing) > 0 {
		buf.Write(existing)
		if !strings.HasSuffix(string(existing), "\n") {
			buf.WriteString("\n")
		}
	}
	buf.WriteString(entry)
	buf.WriteString("\n")

	if err := os.WriteFile(path, []byte(buf.String()), 0644); err != nil {
		return false, fmt.Errorf("failed to write .gitignore: %w", err)
	}
	return true, nil
}

// printTransactionPolicySuccess emits the human-readable warning + tip block
// described in the plan. Kept here (vs. inlined in runNodePolicyAdd) so the
// JSON branch can share the outcome type without duplicating any text.
func printTransactionPolicySuccess(slug string, out *transactionPolicyOutcome) {
	output.Success("Added transaction policy to endpoint '%s'.", slug)
	fmt.Printf("  Policy file: %s\n", out.PolicyPath)
	fmt.Println()

	absSecret, err := filepath.Abs(out.SecretPath)
	if err != nil {
		absSecret = out.SecretPath
	}
	output.Yellow.Println("⚠  WARNING: A new HMAC secret was generated at:")
	fmt.Printf("     %s\n", absSecret)
	output.Yellow.Println("   DO NOT COMMIT THIS FILE.")
	if out.GitignoreUpdated {
		fmt.Println("   It has been added to your endpoint's .gitignore.")
	} else {
		fmt.Println("   It is already covered by your endpoint's .gitignore.")
	}
	fmt.Println("   Losing this secret invalidates all in-flight payment challenges.")
	fmt.Println()

	output.Info("Tip: paid endpoints benefit from container mode (~10x faster policy hot path).")
	fmt.Println("     Add `runtime: { mode: container }` to your README.md frontmatter.")
}

// transactionArgsFromFlags snapshots the cobra flag globals into a value type
// so RunE stays narrow and tests can build args without touching the globals.
func transactionArgsFromFlags() transactionPolicyArgs {
	return transactionPolicyArgs{
		Name:       nodePolicyAddName,
		Recipient:  nodePolicyAddRecipient,
		Amount:     nodePolicyAddAmount,
		Currency:   nodePolicyAddCurrency,
		Method:     nodePolicyAddMethod,
		Intent:     nodePolicyAddIntent,
		ChainID:    nodePolicyAddChainID,
		RPCURL:     nodePolicyAddRPCURL,
		TTLSeconds: nodePolicyAddTTLSeconds,
		Force:      nodePolicyAddForce,
	}
}

// resolveTransactionEndpointDir centralises the cfg.EndpointsPath/<slug> join
// so the cobra handler in node_policy.go stays free of nodeconfig coupling
// for the transaction branch.
func resolveTransactionEndpointDir(slug string) string {
	cfg := nodeconfig.Load()
	return filepath.Join(cfg.EndpointsPath, slug)
}
