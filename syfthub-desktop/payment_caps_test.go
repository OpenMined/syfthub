package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestGetPaymentCaps_DefaultsWhenMissing(t *testing.T) {
	withTempHome(t)
	app := &App{}

	cfg, err := app.GetPaymentCaps()
	if err != nil {
		t.Fatalf("GetPaymentCaps: %v", err)
	}
	if cfg.Defaults.SoftCap != defaultSoftCap {
		t.Errorf("default soft cap = %q, want %q", cfg.Defaults.SoftCap, defaultSoftCap)
	}
	if cfg.Defaults.HardCap != defaultHardCap {
		t.Errorf("default hard cap = %q, want %q", cfg.Defaults.HardCap, defaultHardCap)
	}
	if cfg.Defaults.Currency != pathUSDContractAddress {
		t.Errorf("default currency = %q, want %q", cfg.Defaults.Currency, pathUSDContractAddress)
	}
	if cfg.PerEndpoint == nil {
		t.Error("PerEndpoint should be a non-nil empty map")
	}
	if len(cfg.PerEndpoint) != 0 {
		t.Errorf("PerEndpoint should start empty, got %d entries", len(cfg.PerEndpoint))
	}
}

func TestSetPaymentCap_PersistsAndReloads(t *testing.T) {
	withTempHome(t)
	app := &App{}

	cap := PaymentCap{
		EndpointSlug: "alice/llm",
		SoftCap:      "0.25",
		HardCap:      "2.50",
		Currency:     pathUSDContractAddress,
	}
	if err := app.SetPaymentCap(cap); err != nil {
		t.Fatalf("SetPaymentCap: %v", err)
	}

	// Reload via a fresh-app instance to prove it round-trips on disk.
	app2 := &App{}
	cfg, err := app2.GetPaymentCaps()
	if err != nil {
		t.Fatalf("GetPaymentCaps after set: %v", err)
	}
	got, ok := cfg.PerEndpoint["alice/llm"]
	if !ok {
		t.Fatalf("alice/llm missing from PerEndpoint: %+v", cfg.PerEndpoint)
	}
	if got.SoftCap != "0.25" || got.HardCap != "2.50" {
		t.Errorf("round-trip caps mismatch: %+v", got)
	}
	if got.UpdatedAt == 0 {
		t.Error("UpdatedAt should be set on write")
	}
}

func TestResetPaymentCap_RemovesOverride(t *testing.T) {
	withTempHome(t)
	app := &App{}

	if err := app.SetPaymentCap(PaymentCap{EndpointSlug: "alice/llm", SoftCap: "0.5", HardCap: "5"}); err != nil {
		t.Fatalf("SetPaymentCap: %v", err)
	}
	if err := app.ResetPaymentCap("alice/llm"); err != nil {
		t.Fatalf("ResetPaymentCap: %v", err)
	}
	cfg, err := app.GetPaymentCaps()
	if err != nil {
		t.Fatalf("GetPaymentCaps: %v", err)
	}
	if _, ok := cfg.PerEndpoint["alice/llm"]; ok {
		t.Errorf("override should be gone, still present: %+v", cfg.PerEndpoint)
	}

	// Reset on a slug that was never set is a no-op (no error).
	if err := app.ResetPaymentCap("unknown/endpoint"); err != nil {
		t.Errorf("ResetPaymentCap on missing slug should be no-op: %v", err)
	}
}

func TestSetPaymentCap_RejectsBlankSlug(t *testing.T) {
	withTempHome(t)
	app := &App{}
	if err := app.SetPaymentCap(PaymentCap{EndpointSlug: "  "}); err == nil {
		t.Fatal("expected error for blank slug")
	}
}

func TestSetPaymentCap_RejectsInvalidAmount(t *testing.T) {
	withTempHome(t)
	app := &App{}
	if err := app.SetPaymentCap(PaymentCap{EndpointSlug: "a/b", SoftCap: "not-a-number"}); err == nil {
		t.Fatal("expected error for malformed soft_cap")
	}
	if err := app.SetPaymentCap(PaymentCap{EndpointSlug: "a/b", HardCap: "-1"}); err == nil {
		t.Fatal("expected error for negative hard_cap")
	}
}

func TestSetPaymentCap_RejectsSoftAboveHard(t *testing.T) {
	withTempHome(t)
	app := &App{}
	// Explicit inversion: soft above hard must be rejected so
	// EvaluatePaymentDecision can't auto-pay anything below an inflated soft
	// cap and silently bypass the (lower) hard cap.
	if err := app.SetPaymentCap(PaymentCap{
		EndpointSlug: "a/b",
		SoftCap:      "5.00",
		HardCap:      "1.00",
		Currency:     pathUSDContractAddress,
	}); err == nil {
		t.Fatal("expected error for soft > hard")
	}
	// Partial override that inverts against defaults: defaults are
	// soft=0.10/hard=1.00; overriding only soft=2.00 leaves effective
	// hard=1.00, which is also an inversion.
	if err := app.SetPaymentCap(PaymentCap{
		EndpointSlug: "a/b",
		SoftCap:      "2.00",
	}); err == nil {
		t.Fatal("expected error for soft > effective hard (defaults)")
	}
}

func TestEvaluatePaymentDecision_UnderSoftCap(t *testing.T) {
	withTempHome(t)
	app := &App{}
	dec, err := app.EvaluatePaymentDecision("alice/llm", "0.01", pathUSDContractAddress)
	if err != nil {
		t.Fatalf("EvaluatePaymentDecision: %v", err)
	}
	if dec.Action != PaymentDecisionAutoPay {
		t.Errorf("want auto_pay, got %q (reason=%q)", dec.Action, dec.Reason)
	}
	// EffectiveCap should be populated with the defaults inherited via merge.
	if dec.EffectiveCap.SoftCap != defaultSoftCap {
		t.Errorf("effective soft cap should default: %+v", dec.EffectiveCap)
	}
}

func TestEvaluatePaymentDecision_BetweenSoftAndHard(t *testing.T) {
	withTempHome(t)
	app := &App{}
	dec, err := app.EvaluatePaymentDecision("alice/llm", "0.5", pathUSDContractAddress)
	if err != nil {
		t.Fatalf("EvaluatePaymentDecision: %v", err)
	}
	if dec.Action != PaymentDecisionToastPay {
		t.Errorf("want toast_pay, got %q (reason=%q)", dec.Action, dec.Reason)
	}
}

func TestEvaluatePaymentDecision_OverHardCap(t *testing.T) {
	withTempHome(t)
	app := &App{}
	dec, err := app.EvaluatePaymentDecision("alice/llm", "5.0", pathUSDContractAddress)
	if err != nil {
		t.Fatalf("EvaluatePaymentDecision: %v", err)
	}
	if dec.Action != PaymentDecisionPrompt {
		t.Errorf("want prompt, got %q (reason=%q)", dec.Action, dec.Reason)
	}
	if !strings.Contains(dec.Reason, "exceeds hard cap") {
		t.Errorf("expected reason mentioning hard cap, got %q", dec.Reason)
	}
}

func TestEvaluatePaymentDecision_DifferentCurrency(t *testing.T) {
	withTempHome(t)
	app := &App{}
	dec, err := app.EvaluatePaymentDecision("alice/llm", "0.01", "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
	if err != nil {
		t.Fatalf("EvaluatePaymentDecision: %v", err)
	}
	if dec.Action != PaymentDecisionPrompt {
		t.Errorf("want prompt for currency mismatch, got %q", dec.Action)
	}
	if dec.Reason != "different currency" {
		t.Errorf("want reason 'different currency', got %q", dec.Reason)
	}
}

func TestEvaluatePaymentDecision_EmptyCurrencyFallsToPrompt(t *testing.T) {
	// Empty currency must NOT auto-pay against the user's pathUSD cap —
	// the on-chain asset is unknown, so the modal must surface for review.
	withTempHome(t)
	app := &App{}
	dec, err := app.EvaluatePaymentDecision("alice/llm", "0.01", "")
	if err != nil {
		t.Fatalf("EvaluatePaymentDecision: %v", err)
	}
	if dec.Action != PaymentDecisionPrompt {
		t.Errorf("want prompt for missing currency, got %q", dec.Action)
	}
	if dec.Reason != "missing currency" {
		t.Errorf("want reason 'missing currency', got %q", dec.Reason)
	}
}

func TestEvaluatePaymentDecision_PerEndpointOverrideBeatsDefaults(t *testing.T) {
	withTempHome(t)
	app := &App{}

	// Bump the soft cap for one endpoint so 0.5 should auto-pay even though
	// the default soft cap is 0.10.
	if err := app.SetPaymentCap(PaymentCap{
		EndpointSlug: "alice/llm",
		SoftCap:      "1.00",
		HardCap:      "10.00",
		Currency:     pathUSDContractAddress,
	}); err != nil {
		t.Fatalf("SetPaymentCap: %v", err)
	}

	dec, err := app.EvaluatePaymentDecision("alice/llm", "0.5", pathUSDContractAddress)
	if err != nil {
		t.Fatalf("EvaluatePaymentDecision: %v", err)
	}
	if dec.Action != PaymentDecisionAutoPay {
		t.Errorf("override should auto-pay 0.5 under 1.00 soft cap, got %q", dec.Action)
	}
	// A different endpoint (no override) must still use defaults.
	dec2, err := app.EvaluatePaymentDecision("bob/llm", "0.5", pathUSDContractAddress)
	if err != nil {
		t.Fatalf("EvaluatePaymentDecision: %v", err)
	}
	if dec2.Action != PaymentDecisionToastPay {
		t.Errorf("bob/llm with defaults: want toast_pay for 0.5, got %q", dec2.Action)
	}
}

func TestEvaluatePaymentDecision_InvalidAmountFallsToPrompt(t *testing.T) {
	withTempHome(t)
	app := &App{}
	dec, err := app.EvaluatePaymentDecision("alice/llm", "abc", pathUSDContractAddress)
	if err != nil {
		t.Fatalf("EvaluatePaymentDecision: %v", err)
	}
	if dec.Action != PaymentDecisionPrompt {
		t.Errorf("unparseable amount must prompt, got %q", dec.Action)
	}
	if dec.Reason != "invalid amount" {
		t.Errorf("want reason 'invalid amount', got %q", dec.Reason)
	}
}

func TestSavePaymentCaps_AtomicRename_DoesNotCorruptExisting(t *testing.T) {
	home := withTempHome(t)
	app := &App{}

	// Write a known-good config.
	if err := app.SetPaymentCap(PaymentCap{EndpointSlug: "alice/llm", SoftCap: "0.50", HardCap: "5.00"}); err != nil {
		t.Fatalf("SetPaymentCap: %v", err)
	}
	path := filepath.Join(home, walletDirName, paymentCapsFilename)
	original, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read original: %v", err)
	}

	// Drop a stale .tmp sibling that a previous crash might have left behind.
	// SetPaymentCap must still succeed (the temp file is overwritten by
	// O_CREATE|O_TRUNC) and the original config must remain valid afterwards.
	if err := os.WriteFile(path+".tmp", []byte("partial garbage"), 0o600); err != nil {
		t.Fatalf("seed stale tmp: %v", err)
	}
	if err := app.SetPaymentCap(PaymentCap{EndpointSlug: "alice/llm", SoftCap: "0.60", HardCap: "6.00"}); err != nil {
		t.Fatalf("SetPaymentCap with stale tmp: %v", err)
	}

	// The original file must still be readable as valid JSON (rename is atomic).
	after, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read after second write: %v", err)
	}
	var cfg PaymentCapsConfig
	if err := json.Unmarshal(after, &cfg); err != nil {
		t.Fatalf("post-write config is not valid JSON: %v\n%s", err, string(after))
	}
	// And the value must reflect the latest write — not the original or the
	// garbage we seeded.
	if got := cfg.PerEndpoint["alice/llm"].SoftCap; got != "0.60" {
		t.Errorf("expected updated soft cap 0.60, got %q (original was %q)", got, string(original))
	}
	// Stale .tmp has been cleaned up by the rename.
	if _, err := os.Stat(path + ".tmp"); !os.IsNotExist(err) {
		t.Errorf("stale .tmp file should be gone after atomic write, stat err=%v", err)
	}
}

func TestEffectiveCap_PartialOverrideMergesDefaults(t *testing.T) {
	defaults := PaymentCap{SoftCap: "0.10", HardCap: "1.00", Currency: pathUSDContractAddress}
	// Override only bumps the hard cap; soft cap + currency should fall back.
	override := PaymentCap{HardCap: "5.00"}
	got := effectiveCap(defaults, override, "alice/llm")
	if got.SoftCap != "0.10" {
		t.Errorf("soft cap should fall back to defaults, got %q", got.SoftCap)
	}
	if got.HardCap != "5.00" {
		t.Errorf("hard cap should use override, got %q", got.HardCap)
	}
	if got.Currency != pathUSDContractAddress {
		t.Errorf("currency should fall back to defaults, got %q", got.Currency)
	}
	if got.EndpointSlug != "alice/llm" {
		t.Errorf("slug should be propagated, got %q", got.EndpointSlug)
	}
}
