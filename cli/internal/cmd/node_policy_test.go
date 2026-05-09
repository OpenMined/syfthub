package cmd

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// validArgs returns a transactionPolicyArgs prefilled with values that pass
// validation. Tests can override individual fields to exercise edge cases
// without re-listing every required flag.
func validArgs() transactionPolicyArgs {
	return transactionPolicyArgs{
		Name:       "paid",
		Recipient:  "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		Amount:     "0.10",
		Currency:   defaultTxCurrency,
		Method:     defaultTxMethod,
		Intent:     defaultTxIntent,
		ChainID:    defaultTxChainID,
		RPCURL:     "https://rpc.tempo.example",
		TTLSeconds: defaultTxTTLSeconds,
	}
}

func TestPolicyAddTransaction_HappyPath(t *testing.T) {
	endpointDir := t.TempDir()

	out, err := runTransactionPolicyAdd(endpointDir, validArgs())
	if err != nil {
		t.Fatalf("expected success, got error: %v", err)
	}

	// Policy YAML exists with expected shape.
	policyPath := filepath.Join(endpointDir, "policy", "transaction.yaml")
	if out.PolicyPath != policyPath {
		t.Errorf("PolicyPath = %q, want %q", out.PolicyPath, policyPath)
	}
	policyBytes, err := os.ReadFile(policyPath)
	if err != nil {
		t.Fatalf("failed to read policy file: %v", err)
	}
	var doc map[string]interface{}
	if err := yaml.Unmarshal(policyBytes, &doc); err != nil {
		t.Fatalf("policy file is not valid YAML: %v", err)
	}
	if doc["type"] != "transaction" {
		t.Errorf("policy type = %v, want %q", doc["type"], "transaction")
	}
	if doc["name"] != "paid" {
		t.Errorf("policy name = %v, want %q", doc["name"], "paid")
	}
	cfg, ok := doc["config"].(map[string]interface{})
	if !ok {
		t.Fatalf("config is not a map: %T", doc["config"])
	}
	if cfg["recipient"] != "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266" {
		t.Errorf("recipient = %v", cfg["recipient"])
	}
	if cfg["chain_id"] != defaultTxChainID {
		t.Errorf("chain_id = %v, want %d", cfg["chain_id"], defaultTxChainID)
	}

	// Secret file exists with mode 0600 and decodable content.
	secretPath := filepath.Join(endpointDir, "policy", ".transaction_secret")
	if out.SecretPath != secretPath {
		t.Errorf("SecretPath = %q, want %q", out.SecretPath, secretPath)
	}
	info, err := os.Stat(secretPath)
	if err != nil {
		t.Fatalf("failed to stat secret: %v", err)
	}
	if mode := info.Mode().Perm(); mode != 0600 {
		t.Errorf("secret file mode = %v, want 0600", mode)
	}
	secretBytes, err := os.ReadFile(secretPath)
	if err != nil {
		t.Fatalf("failed to read secret: %v", err)
	}
	// 32 raw bytes -> base64url ≈ 43 chars (no padding).
	if len(strings.TrimSpace(string(secretBytes))) < 40 {
		t.Errorf("secret length = %d, expected at least 40 base64url chars", len(secretBytes))
	}

	// .gitignore exists and lists the secret.
	if !out.GitignoreUpdated {
		t.Error("expected GitignoreUpdated=true on first run")
	}
	gitignoreBytes, err := os.ReadFile(filepath.Join(endpointDir, ".gitignore"))
	if err != nil {
		t.Fatalf("failed to read .gitignore: %v", err)
	}
	if !strings.Contains(string(gitignoreBytes), "policy/.transaction_secret") {
		t.Errorf(".gitignore missing entry, got:\n%s", string(gitignoreBytes))
	}
}

func TestPolicyAddTransaction_AlreadyExists_NoOverwrite(t *testing.T) {
	endpointDir := t.TempDir()

	// First call seeds the secret.
	out1, err := runTransactionPolicyAdd(endpointDir, validArgs())
	if err != nil {
		t.Fatalf("first add failed: %v", err)
	}
	originalSecret, err := os.ReadFile(out1.SecretPath)
	if err != nil {
		t.Fatalf("failed to read original secret: %v", err)
	}

	// Second call without --force must error and must NOT touch the secret.
	if _, err := runTransactionPolicyAdd(endpointDir, validArgs()); err == nil {
		t.Fatal("expected error on second add without --force, got nil")
	}

	currentSecret, err := os.ReadFile(out1.SecretPath)
	if err != nil {
		t.Fatalf("failed to re-read secret: %v", err)
	}
	if string(currentSecret) != string(originalSecret) {
		t.Error("secret was regenerated despite no --force flag")
	}
}

func TestPolicyAddTransaction_AlreadyExists_WithForce(t *testing.T) {
	endpointDir := t.TempDir()

	out1, err := runTransactionPolicyAdd(endpointDir, validArgs())
	if err != nil {
		t.Fatalf("first add failed: %v", err)
	}
	originalSecret, err := os.ReadFile(out1.SecretPath)
	if err != nil {
		t.Fatalf("failed to read original secret: %v", err)
	}

	forced := validArgs()
	forced.Force = true
	if _, err := runTransactionPolicyAdd(endpointDir, forced); err != nil {
		t.Fatalf("forced add failed: %v", err)
	}

	currentSecret, err := os.ReadFile(out1.SecretPath)
	if err != nil {
		t.Fatalf("failed to re-read secret: %v", err)
	}
	if string(currentSecret) == string(originalSecret) {
		t.Error("secret was NOT regenerated despite --force")
	}
}

func TestPolicyAddTransaction_InvalidRecipient(t *testing.T) {
	endpointDir := t.TempDir()
	args := validArgs()
	args.Recipient = "not-a-hex-address"

	if _, err := runTransactionPolicyAdd(endpointDir, args); err == nil {
		t.Fatal("expected validation error for invalid recipient, got nil")
	}

	// Nothing should have been written.
	if _, err := os.Stat(filepath.Join(endpointDir, "policy")); !os.IsNotExist(err) {
		t.Errorf("policy/ directory should not exist after validation failure (err=%v)", err)
	}
}

func TestPolicyAddTransaction_GitignoreIdempotent(t *testing.T) {
	endpointDir := t.TempDir()

	if _, err := runTransactionPolicyAdd(endpointDir, validArgs()); err != nil {
		t.Fatalf("first add failed: %v", err)
	}

	// Second call (with --force so the secret regen doesn't error first) must
	// not duplicate the .gitignore entry.
	forced := validArgs()
	forced.Force = true
	out2, err := runTransactionPolicyAdd(endpointDir, forced)
	if err != nil {
		t.Fatalf("forced add failed: %v", err)
	}
	if out2.GitignoreUpdated {
		t.Error("expected GitignoreUpdated=false on second run (entry already present)")
	}

	gitignoreBytes, err := os.ReadFile(filepath.Join(endpointDir, ".gitignore"))
	if err != nil {
		t.Fatalf("failed to read .gitignore: %v", err)
	}
	count := strings.Count(string(gitignoreBytes), "policy/.transaction_secret")
	if count != 1 {
		t.Errorf(".gitignore entry count = %d, want 1; contents:\n%s", count, string(gitignoreBytes))
	}
}

func TestValidateTransactionArgs(t *testing.T) {
	tests := []struct {
		name    string
		mutate  func(*transactionPolicyArgs)
		wantErr bool
	}{
		{"valid", func(a *transactionPolicyArgs) {}, false},
		{"missing name", func(a *transactionPolicyArgs) { a.Name = "" }, true},
		{"missing recipient", func(a *transactionPolicyArgs) { a.Recipient = "" }, true},
		{"short recipient", func(a *transactionPolicyArgs) { a.Recipient = "0xabc" }, true},
		{"non-hex recipient", func(a *transactionPolicyArgs) { a.Recipient = "0xZZZZd6e51aad88F6F4ce6aB8827279cffFb92266" }, true},
		{"missing amount", func(a *transactionPolicyArgs) { a.Amount = "" }, true},
		{"negative amount", func(a *transactionPolicyArgs) { a.Amount = "-1" }, true},
		{"zero amount", func(a *transactionPolicyArgs) { a.Amount = "0" }, true},
		{"zero decimal amount", func(a *transactionPolicyArgs) { a.Amount = "0.00" }, true},
		{"missing rpc url", func(a *transactionPolicyArgs) { a.RPCURL = "" }, true},
		{"http rpc url", func(a *transactionPolicyArgs) { a.RPCURL = "http://rpc.example" }, true},
		{"non-positive ttl", func(a *transactionPolicyArgs) { a.TTLSeconds = 0 }, true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			a := validArgs()
			tt.mutate(&a)
			err := validateTransactionArgs(a)
			if tt.wantErr && err == nil {
				t.Error("expected error, got nil")
			}
			if !tt.wantErr && err != nil {
				t.Errorf("expected nil, got: %v", err)
			}
		})
	}
}
