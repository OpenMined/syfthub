package updater

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// withTestPubKey temporarily replaces the embedded public key with one
// generated for this test. Returns the matching private key so the
// caller can sign payloads.
func withTestPubKey(t *testing.T) ed25519.PrivateKey {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, _ := x509.MarshalPKIXPublicKey(pub)
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})

	orig := embeddedPubKeyPEM
	embeddedPubKeyPEM = pemBytes
	t.Cleanup(func() { embeddedPubKeyPEM = orig })
	return priv
}

func TestPubKeyPlaceholderReturnsNil(t *testing.T) {
	// The repo ships with a placeholder — verify pubKey() returns (nil, nil).
	pk, err := pubKey()
	if err != nil {
		t.Fatalf("placeholder pubKey: %v", err)
	}
	if pk != nil {
		t.Error("expected nil pubKey for placeholder PEM")
	}
}

func TestVerifyManifestUnsignedLenient(t *testing.T) {
	// Lenient mode (default): missing signature is OK.
	if err := verifyManifest([]byte("body"), nil); err != nil {
		t.Errorf("verifyManifest with no sig in lenient mode: %v", err)
	}
}

func TestVerifyManifestUnsignedStrict(t *testing.T) {
	t.Setenv(RequireSigEnv, "1")
	err := verifyManifest([]byte("body"), nil)
	if !errors.Is(err, ErrSignatureRequired) {
		t.Errorf("strict mode no-sig: want ErrSignatureRequired, got %v", err)
	}
}

func TestVerifyManifestValidSignature(t *testing.T) {
	priv := withTestPubKey(t)
	body := []byte(`{"schema_version":1}`)
	sig := ed25519.Sign(priv, body)
	if err := verifyManifest(body, sig); err != nil {
		t.Errorf("valid sig: %v", err)
	}
}

func TestVerifyManifestInvalidSignature(t *testing.T) {
	_ = withTestPubKey(t)
	body := []byte("body")
	bogusSig := make([]byte, ed25519.SignatureSize) // all zeros
	if err := verifyManifest(body, bogusSig); !errors.Is(err, ErrSignatureInvalid) {
		t.Errorf("bogus sig: want ErrSignatureInvalid, got %v", err)
	}
}

func TestVerifyManifestTamperedBody(t *testing.T) {
	priv := withTestPubKey(t)
	body := []byte(`{"schema_version":1}`)
	sig := ed25519.Sign(priv, body)
	tampered := []byte(`{"schema_version":2}`)
	if err := verifyManifest(tampered, sig); !errors.Is(err, ErrSignatureInvalid) {
		t.Errorf("tampered body: want ErrSignatureInvalid, got %v", err)
	}
}

func TestFetchSignatureMissingIs404(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()
	sig, err := fetchSignature(srv.Client(), srv.URL+"/manifest.json")
	if err != nil {
		t.Errorf("fetchSignature 404: %v", err)
	}
	if sig != nil {
		t.Errorf("expected nil sig for 404")
	}
}

func TestFetchSignatureRawBytes(t *testing.T) {
	rawSig := make([]byte, ed25519.SignatureSize)
	for i := range rawSig {
		rawSig[i] = byte(i)
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(rawSig)
	}))
	defer srv.Close()
	sig, err := fetchSignature(srv.Client(), srv.URL+"/manifest.json")
	if err != nil {
		t.Errorf("fetchSignature raw: %v", err)
	}
	if len(sig) != ed25519.SignatureSize {
		t.Errorf("got %d bytes, want %d", len(sig), ed25519.SignatureSize)
	}
}

func TestDecodeSignatureBase64(t *testing.T) {
	priv := withTestPubKey(t)
	rawSig := ed25519.Sign(priv, []byte("payload"))
	encoded := []byte(base64.StdEncoding.EncodeToString(rawSig))
	got, err := decodeSignature(encoded)
	if err != nil {
		t.Fatalf("decodeSignature(base64): %v", err)
	}
	if string(got) != string(rawSig) {
		t.Errorf("decoded sig mismatch")
	}
}

// Sanity check: end-to-end FetchManifest with signature verification.
func TestFetchManifestSignedHappyPath(t *testing.T) {
	priv := withTestPubKey(t)
	m := makeManifest("0.2.0", "0.1.0", []string{"linux/amd64"})
	body, _ := json.Marshal(m)
	sig := ed25519.Sign(priv, body)

	mux := http.NewServeMux()
	mux.HandleFunc("/manifest.json", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(body)
	})
	mux.HandleFunc("/manifest.json.sig", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(sig)
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	got, err := FetchManifest(srv.Client(), srv.URL+"/manifest.json")
	if err != nil {
		t.Fatalf("FetchManifest: %v", err)
	}
	if got.Version != m.Version {
		t.Errorf("got version %q, want %q", got.Version, m.Version)
	}
}

func TestFetchManifestSignedTampered(t *testing.T) {
	priv := withTestPubKey(t)
	m := makeManifest("0.2.0", "0.1.0", []string{"linux/amd64"})
	body, _ := json.Marshal(m)
	sig := ed25519.Sign(priv, body)
	// Tamper with the served body.
	tampered := []byte(strings.Replace(string(body), "0.2.0", "0.9.9", 1))

	mux := http.NewServeMux()
	mux.HandleFunc("/manifest.json", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(tampered)
	})
	mux.HandleFunc("/manifest.json.sig", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(sig)
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	_, err := FetchManifest(srv.Client(), srv.URL+"/manifest.json")
	if !errors.Is(err, ErrSignatureInvalid) {
		t.Errorf("tampered manifest: want ErrSignatureInvalid, got %v", err)
	}
}
