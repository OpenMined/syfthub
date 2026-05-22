// Package main provides per-endpoint spend cap persistence for the consumer
// side of the x402 pay-per-request flow.
//
// When the producer signals payment_required for a given endpoint, the
// frontend asks EvaluatePaymentDecision whether to silently auto-pay
// (under the soft cap), toast-and-pay (between soft and hard), or fall back
// to a blocking modal prompt (above hard, or for a currency the user has not
// pre-authorised). Caps are stored in payment_caps.json under the wallet
// directory so they sit next to the private key and payment ledger.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// paymentCapsFilename is the on-disk file name under walletDir() that stores
// the persisted caps configuration.
const paymentCapsFilename = "payment_caps.json"

// Default cap amounts (decimal strings, in pathUSD). These match the values
// quoted in the v2 plan and are intentionally generous for the demo network —
// they should be tightened before mainnet.
const (
	defaultSoftCap = "0.10"
	defaultHardCap = "1.00"
)

// PaymentCap is one record in the caps config. An "effective" cap for an
// endpoint is the per-endpoint entry if present, otherwise the defaults
// merged with the per-endpoint partial overrides — see effectiveCap.
type PaymentCap struct {
	// EndpointSlug is "<owner>/<slug>". Empty when used as the defaults row.
	EndpointSlug string `json:"endpoint_slug"`
	// SoftCap and HardCap are decimal-string amounts (e.g. "0.10", "1.00").
	// Both are interpreted in the same currency as Currency.
	SoftCap string `json:"soft_cap"`
	HardCap string `json:"hard_cap"`
	// Currency is the contract address (or canonical token id) the cap is
	// denominated in. Defaults to the demo pathUSD contract on the Tempo
	// testnet.
	Currency string `json:"currency"`
	// UpdatedAt is unix seconds at the time the entry was last written.
	UpdatedAt int64 `json:"updated_at"`
}

// PaymentCapsConfig is the persisted file shape. PerEndpoint is keyed by
// EndpointSlug ("<owner>/<slug>").
type PaymentCapsConfig struct {
	Defaults    PaymentCap            `json:"defaults"`
	PerEndpoint map[string]PaymentCap `json:"per_endpoint"`
}

// PaymentDecision is the verdict EvaluatePaymentDecision returns.
//
// Action is one of:
//   - "auto_pay"  → silently sign + submit the credential
//   - "toast_pay" → show a non-blocking toast, then sign + submit
//   - "prompt"    → display the blocking modal and let the user choose
type PaymentDecision struct {
	Action       string     `json:"action"`
	EffectiveCap PaymentCap `json:"effective_cap"`
	Reason       string     `json:"reason,omitempty"`
}

// Action constants for PaymentDecision.Action. Exported so the frontend (via
// Wails) can compare against canonical values rather than string literals.
const (
	PaymentDecisionAutoPay  = "auto_pay"
	PaymentDecisionToastPay = "toast_pay"
	PaymentDecisionPrompt   = "prompt"
)

// paymentCapsMu serialises read-modify-write cycles across GetPaymentCaps,
// SetPaymentCap, ResetPaymentCap so two frontend tabs racing on the same
// file cannot drop each other's writes.
var paymentCapsMu sync.Mutex

// paymentCapsPath returns the absolute path to payment_caps.json under the
// wallet directory (~/.syfthub-desktop on Linux/macOS).
func paymentCapsPath() (string, error) {
	dir, err := walletDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, paymentCapsFilename), nil
}

// defaultPaymentCapsConfig returns the canonical starter config: defaults of
// 0.10 soft / 1.00 hard in pathUSD, no per-endpoint overrides.
func defaultPaymentCapsConfig() PaymentCapsConfig {
	return PaymentCapsConfig{
		Defaults: PaymentCap{
			SoftCap:   defaultSoftCap,
			HardCap:   defaultHardCap,
			Currency:  pathUSDContractAddress,
			UpdatedAt: 0,
		},
		PerEndpoint: map[string]PaymentCap{},
	}
}

// loadPaymentCapsLocked reads the on-disk config. Caller must hold
// paymentCapsMu. Missing file returns the defaults config without error.
func loadPaymentCapsLocked() (PaymentCapsConfig, error) {
	path, err := paymentCapsPath()
	if err != nil {
		return defaultPaymentCapsConfig(), err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return defaultPaymentCapsConfig(), nil
		}
		return defaultPaymentCapsConfig(), fmt.Errorf("read payment caps: %w", err)
	}
	cfg := defaultPaymentCapsConfig()
	if err := json.Unmarshal(data, &cfg); err != nil {
		return defaultPaymentCapsConfig(), fmt.Errorf("parse payment caps: %w", err)
	}
	if cfg.PerEndpoint == nil {
		cfg.PerEndpoint = map[string]PaymentCap{}
	}
	// Backfill any unset default fields so callers can rely on a complete row.
	if strings.TrimSpace(cfg.Defaults.SoftCap) == "" {
		cfg.Defaults.SoftCap = defaultSoftCap
	}
	if strings.TrimSpace(cfg.Defaults.HardCap) == "" {
		cfg.Defaults.HardCap = defaultHardCap
	}
	if strings.TrimSpace(cfg.Defaults.Currency) == "" {
		cfg.Defaults.Currency = pathUSDContractAddress
	}
	return cfg, nil
}

// savePaymentCapsLocked persists the config atomically: write to a temp file
// in the same directory, then rename over the destination. Caller must hold
// paymentCapsMu.
func savePaymentCapsLocked(cfg PaymentCapsConfig) error {
	path, err := paymentCapsPath()
	if err != nil {
		return err
	}
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("create wallet dir: %w", err)
	}
	if cfg.PerEndpoint == nil {
		cfg.PerEndpoint = map[string]PaymentCap{}
	}
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal payment caps: %w", err)
	}
	tmp := path + ".tmp"
	// Write into a sibling temp file with 0600 perms — this is consumer
	// spending policy, not secret material, but matches wallet.key for
	// principle-of-least-surprise.
	f, err := os.OpenFile(tmp, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		return fmt.Errorf("open payment caps temp: %w", err)
	}
	if _, err := f.Write(data); err != nil {
		_ = f.Close()
		_ = os.Remove(tmp)
		return fmt.Errorf("write payment caps temp: %w", err)
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(tmp)
		return fmt.Errorf("close payment caps temp: %w", err)
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return fmt.Errorf("rename payment caps: %w", err)
	}
	return nil
}

// effectiveCap merges the defaults with a per-endpoint override. The override
// can populate only the fields it wants to change; anything blank falls back
// to defaults so a user who only wants to bump the hard cap doesn't have to
// re-specify currency.
func effectiveCap(defaults PaymentCap, override PaymentCap, slug string) PaymentCap {
	out := PaymentCap{
		EndpointSlug: slug,
		SoftCap:      override.SoftCap,
		HardCap:      override.HardCap,
		Currency:     override.Currency,
		UpdatedAt:    override.UpdatedAt,
	}
	if strings.TrimSpace(out.SoftCap) == "" {
		out.SoftCap = defaults.SoftCap
	}
	if strings.TrimSpace(out.HardCap) == "" {
		out.HardCap = defaults.HardCap
	}
	if strings.TrimSpace(out.Currency) == "" {
		out.Currency = defaults.Currency
	}
	return out
}

// GetPaymentCaps is the Wails-bound read of the persisted config. Returns
// the defaults config (with an empty PerEndpoint map) when the file is
// absent — never an os.ErrNotExist.
func (a *App) GetPaymentCaps() (PaymentCapsConfig, error) {
	paymentCapsMu.Lock()
	defer paymentCapsMu.Unlock()
	return loadPaymentCapsLocked()
}

// SetPaymentCap upserts a per-endpoint cap. The EndpointSlug must be set
// (non-empty after trim); any blank cap field inherits from defaults via
// effectiveCap at evaluation time. Persists atomically.
//
// The parameter name is intentionally `entry` rather than `cap` to avoid
// shadowing the Go builtin and to clarify that this is one ledger entry.
func (a *App) SetPaymentCap(entry PaymentCap) error {
	slug := strings.TrimSpace(entry.EndpointSlug)
	if slug == "" {
		return errors.New("endpoint_slug is required")
	}
	// Sanity: amounts must parse as non-negative decimals when supplied.
	if s := strings.TrimSpace(entry.SoftCap); s != "" {
		if _, err := parseDecimal(s); err != nil {
			return fmt.Errorf("soft_cap: %w", err)
		}
	}
	if s := strings.TrimSpace(entry.HardCap); s != "" {
		if _, err := parseDecimal(s); err != nil {
			return fmt.Errorf("hard_cap: %w", err)
		}
	}
	paymentCapsMu.Lock()
	defer paymentCapsMu.Unlock()

	cfg, err := loadPaymentCapsLocked()
	if err != nil {
		return err
	}
	// Reject soft_cap > hard_cap against the effective row that would result
	// from persisting `entry` — otherwise EvaluatePaymentDecision would
	// auto_pay anything below the inflated soft cap, fully overriding the
	// (lower) hard cap the user intended to enforce.
	eff := effectiveCap(cfg.Defaults, entry, slug)
	softCap, sErr := parseDecimal(eff.SoftCap)
	hardCap, hErr := parseDecimal(eff.HardCap)
	if sErr == nil && hErr == nil && softCap.Cmp(hardCap) > 0 {
		return fmt.Errorf("soft_cap (%s) must be <= hard_cap (%s)", eff.SoftCap, eff.HardCap)
	}
	stored := entry
	stored.EndpointSlug = slug
	stored.UpdatedAt = time.Now().Unix()
	cfg.PerEndpoint[slug] = stored
	return savePaymentCapsLocked(cfg)
}

// ResetPaymentCap deletes a per-endpoint override so subsequent evaluations
// fall back to the defaults. A non-existent slug is a no-op (not an error).
func (a *App) ResetPaymentCap(endpointSlug string) error {
	slug := strings.TrimSpace(endpointSlug)
	if slug == "" {
		return errors.New("endpoint_slug is required")
	}
	paymentCapsMu.Lock()
	defer paymentCapsMu.Unlock()

	cfg, err := loadPaymentCapsLocked()
	if err != nil {
		return err
	}
	if _, ok := cfg.PerEndpoint[slug]; !ok {
		return nil
	}
	delete(cfg.PerEndpoint, slug)
	return savePaymentCapsLocked(cfg)
}

// EvaluatePaymentDecision is the policy gate called by the frontend when a
// payment_required event arrives. It compares the requested amount + currency
// against the effective cap for endpointSlug and returns one of "auto_pay" /
// "toast_pay" / "prompt".
//
// Rules:
//   - amount unparseable          → prompt (reason: "invalid amount")
//   - currency empty/missing       → prompt (reason: "missing currency")
//   - currency != effective.Currency → prompt (reason: "different currency")
//   - amount <= softCap            → auto_pay
//   - softCap < amount <= hardCap  → toast_pay
//   - amount > hardCap             → prompt (reason: "exceeds hard cap")
func (a *App) EvaluatePaymentDecision(endpointSlug string, amount string, currency string) (PaymentDecision, error) {
	paymentCapsMu.Lock()
	cfg, err := loadPaymentCapsLocked()
	paymentCapsMu.Unlock()
	if err != nil {
		return PaymentDecision{Action: PaymentDecisionPrompt, Reason: "caps load failed"}, err
	}

	slug := strings.TrimSpace(endpointSlug)
	override := cfg.PerEndpoint[slug]
	eff := effectiveCap(cfg.Defaults, override, slug)

	amt, err := parseDecimal(strings.TrimSpace(amount))
	if err != nil {
		return PaymentDecision{Action: PaymentDecisionPrompt, EffectiveCap: eff, Reason: "invalid amount"}, nil
	}

	// Missing currency must NOT auto-pay: the user's cap is denominated
	// against a specific token (eff.Currency), so an unspecified currency
	// could resolve to any on-chain asset. Fall to the modal so the user
	// can review what they are actually paying for.
	trimmedCurrency := strings.TrimSpace(currency)
	if trimmedCurrency == "" {
		return PaymentDecision{Action: PaymentDecisionPrompt, EffectiveCap: eff, Reason: "missing currency"}, nil
	}
	if !strings.EqualFold(trimmedCurrency, eff.Currency) {
		return PaymentDecision{Action: PaymentDecisionPrompt, EffectiveCap: eff, Reason: "different currency"}, nil
	}

	softCap, err := parseDecimal(eff.SoftCap)
	if err != nil {
		return PaymentDecision{Action: PaymentDecisionPrompt, EffectiveCap: eff, Reason: "invalid soft_cap"}, nil
	}
	hardCap, err := parseDecimal(eff.HardCap)
	if err != nil {
		return PaymentDecision{Action: PaymentDecisionPrompt, EffectiveCap: eff, Reason: "invalid hard_cap"}, nil
	}

	if amt.Cmp(softCap) <= 0 {
		return PaymentDecision{Action: PaymentDecisionAutoPay, EffectiveCap: eff}, nil
	}
	if amt.Cmp(hardCap) <= 0 {
		return PaymentDecision{Action: PaymentDecisionToastPay, EffectiveCap: eff}, nil
	}
	return PaymentDecision{Action: PaymentDecisionPrompt, EffectiveCap: eff, Reason: "exceeds hard cap"}, nil
}

// parseDecimal turns a decimal string ("1.23", "0.000005", "10") into a
// big.Rat so comparisons can be exact (no float rounding) across the whole
// pathUSD precision range. Rejects empty / negative / non-numeric input.
func parseDecimal(s string) (*big.Rat, error) {
	t := strings.TrimSpace(s)
	if t == "" {
		return nil, errors.New("empty decimal")
	}
	if strings.HasPrefix(t, "-") {
		return nil, fmt.Errorf("negative decimal not allowed: %q", s)
	}
	r, ok := new(big.Rat).SetString(t)
	if !ok {
		return nil, fmt.Errorf("invalid decimal: %q", s)
	}
	return r, nil
}
