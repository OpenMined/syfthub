package mppx

import (
	"strings"
	"testing"
)

// Well-known Anvil/Hardhat test private key 0 — never use on mainnet.
const testPrivKey = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
const testAddress = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

func TestLoadAccount(t *testing.T) {
	a, err := LoadAccount(testPrivKey)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if got := a.Address().Hex(); !strings.EqualFold(got, testAddress) {
		t.Fatalf("address: got %s want %s", got, testAddress)
	}
}

func TestLoadAccountWithoutPrefix(t *testing.T) {
	a, err := LoadAccount(strings.TrimPrefix(testPrivKey, "0x"))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if !strings.EqualFold(a.Address().Hex(), testAddress) {
		t.Fatalf("address mismatch")
	}
}

func TestLoadAccountRejectsEmpty(t *testing.T) {
	if _, err := LoadAccount(""); err == nil {
		t.Fatal("expected error")
	}
	if _, err := LoadAccount("not-hex"); err == nil {
		t.Fatal("expected error")
	}
}

func TestAccountDID(t *testing.T) {
	a, err := LoadAccount(testPrivKey)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	got := a.DID(42431)
	want := "did:pkh:eip155:42431:" + a.Address().Hex()
	if got != want {
		t.Fatalf("DID: got %q want %q", got, want)
	}
}
