// genkey generates a fresh Ed25519 keypair for signing the auto-update
// manifest. Intended to be run once, by a maintainer, during the
// Phase 5 bootstrap (see RELEASING.md).
//
//	go run ./cmd/genkey > /tmp/keys
//	# Copy the PUBLIC PEM into internal/updater/embed/manifest_pubkey.pem
//	# Set the PRIVATE PEM as a GitHub secret named DESKTOP_MANIFEST_SIGNING_KEY
//
// The private key never lives in the repo. Re-running this tool produces
// a new keypair; once a public key is committed and clients ship with it,
// rotating the private key requires shipping a new client release with
// the updated public key.
package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"os"
)

func main() {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		fmt.Fprintln(os.Stderr, "genkey:", err)
		os.Exit(1)
	}

	pubDER, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		fmt.Fprintln(os.Stderr, "marshal public key:", err)
		os.Exit(1)
	}
	privDER, err := x509.MarshalPKCS8PrivateKey(priv)
	if err != nil {
		fmt.Fprintln(os.Stderr, "marshal private key:", err)
		os.Exit(1)
	}

	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: privDER})

	fmt.Println("# === PUBLIC KEY ===")
	fmt.Println("# Commit this to internal/updater/embed/manifest_pubkey.pem")
	fmt.Print(string(pubPEM))
	fmt.Println()
	fmt.Println("# === PRIVATE KEY ===")
	fmt.Println("# Set as GitHub secret DESKTOP_MANIFEST_SIGNING_KEY (or PEM file path)")
	fmt.Println("# NEVER commit this to the repo")
	fmt.Print(string(privPEM))
}
