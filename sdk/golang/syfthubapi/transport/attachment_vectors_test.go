package transport

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"hash"
	"os"
	"path/filepath"
	"testing"
)

func sha256New() hash.Hash { return sha256.New() }

// TestEmitCrossLanguageVectors writes a JSON file containing test vectors
// the Python aggregator can use to verify byte-stable interop with the Go
// implementation.
//
// The file is committed to repo at docs/architecture/attachments-vectors.json
// so divergence is caught in CI when either side changes.
//
// To regenerate: SYFT_ATT_REGEN_VECTORS=1 go test -run TestEmitCrossLanguageVectors ./...
func TestEmitCrossLanguageVectors(t *testing.T) {
	type vector struct {
		Name            string `json:"name"`
		SessionKeyHex   string `json:"session_key_hex"`
		FileID          string `json:"file_id"`
		ExpectedKEKHex  string `json:"expected_kek_hex"`
		FileKeyHex      string `json:"file_key_hex,omitempty"`
		BaseNonceHex    string `json:"base_nonce_hex,omitempty"`
		PlaintextHex    string `json:"plaintext_hex,omitempty"`
		CiphertextHex   string `json:"ciphertext_hex,omitempty"`
		PlaintextSha256 string `json:"plaintext_sha256,omitempty"`
		Description     string `json:"description"`
		ChunkSize       int    `json:"chunk_size,omitempty"`
		TagSize         int    `json:"tag_size,omitempty"`
		BaseNonceSize   int    `json:"base_nonce_size,omitempty"`
		HKDFInfo        string `json:"hkdf_info,omitempty"`
	}

	// Deterministic inputs so vectors are byte-stable across runs.
	sessKey := mustHex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
	fileKey := mustHex("202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f")
	baseNonce := mustHex("4041424344454647")

	enc, err := NewAttachmentEncryptor(sessKey)
	if err != nil {
		t.Fatal(err)
	}

	// Vector 1: KEK derivation for a known file_id.
	kek1, _ := enc.DeriveFileKEK("att-vec-1")

	// Vector 2: small plaintext round-trip (single chunk).
	pt2 := []byte("hello vector 2")
	var ct2 bytes.Buffer
	if _, _, err := enc.EncryptStream(fileKey, baseNonce, "att-vec-2", bytes.NewReader(pt2), &ct2); err != nil {
		t.Fatal(err)
	}
	pt2sha := sha256Hex(pt2)

	// Vector 3: exactly-one-chunk boundary.
	pt3 := bytes.Repeat([]byte{0xAB}, AttachmentChunkSize)
	var ct3 bytes.Buffer
	if _, _, err := enc.EncryptStream(fileKey, baseNonce, "att-vec-3", bytes.NewReader(pt3), &ct3); err != nil {
		t.Fatal(err)
	}
	pt3sha := sha256Hex(pt3)

	vectors := []vector{
		{
			Name:           "kek-derivation-known-file-id",
			SessionKeyHex:  hex.EncodeToString(sessKey),
			FileID:         "att-vec-1",
			ExpectedKEKHex: hex.EncodeToString(kek1),
			Description:    "HKDF-Expand(session_key, 'syfthub-attachment-v1' || file_id, L=32)",
			HKDFInfo:       "syfthub-attachment-v1",
		},
		{
			Name:            "stream-encrypt-small",
			SessionKeyHex:   hex.EncodeToString(sessKey),
			FileID:          "att-vec-2",
			FileKeyHex:      hex.EncodeToString(fileKey),
			BaseNonceHex:    hex.EncodeToString(baseNonce),
			PlaintextHex:    hex.EncodeToString(pt2),
			CiphertextHex:   hex.EncodeToString(ct2.Bytes()),
			PlaintextSha256: pt2sha,
			Description:     "Single-chunk AES-256-GCM with nonce=base||u32(0), AAD=file_id||u32(0)",
			ChunkSize:       AttachmentChunkSize,
			TagSize:         AttachmentTagSize,
			BaseNonceSize:   AttachmentBaseNonceSize,
		},
		{
			Name:            "stream-encrypt-exact-chunk",
			SessionKeyHex:   hex.EncodeToString(sessKey),
			FileID:          "att-vec-3",
			FileKeyHex:      hex.EncodeToString(fileKey),
			BaseNonceHex:    hex.EncodeToString(baseNonce),
			PlaintextHex:    hex.EncodeToString(pt3[:64]) + "... (64KiB of 0xAB)",
			PlaintextSha256: pt3sha,
			CiphertextHex:   hex.EncodeToString(ct3.Bytes()[:64]) + "... (full ciphertext is " + itoa(ct3.Len()) + " bytes)",
			Description:     "Exactly AttachmentChunkSize plaintext — boundary case for the chunked loop",
			ChunkSize:       AttachmentChunkSize,
			TagSize:         AttachmentTagSize,
			BaseNonceSize:   AttachmentBaseNonceSize,
		},
	}

	repoRoot := findRepoRoot(t)
	out := filepath.Join(repoRoot, "docs", "architecture", "attachments-vectors.json")
	body, err := json.MarshalIndent(map[string]any{
		"version": "v1",
		"vectors": vectors,
		"notes": []string{
			"Vectors are deterministic with the listed session/file/nonce material.",
			"Python aggregator tests should derive the same KEK and produce the same ciphertext.",
			"chunked plaintexts only show a prefix to keep the file small; PR-6 regenerates and checks full byte equality.",
		},
	}, "", "  ")
	if err != nil {
		t.Fatal(err)
	}

	body = append(body, '\n')

	if os.Getenv("SYFT_ATT_REGEN_VECTORS") != "" {
		if err := os.WriteFile(out, body, 0o644); err != nil {
			t.Fatal(err)
		}
		t.Logf("wrote %s", out)
		return
	}

	// In normal CI: assert the committed file is up-to-date (or absent on
	// first run). If absent, write it.
	existing, err := os.ReadFile(out)
	if os.IsNotExist(err) {
		if err := os.WriteFile(out, body, 0o644); err != nil {
			t.Fatal(err)
		}
		t.Logf("wrote initial %s", out)
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(bytes.TrimSpace(existing), bytes.TrimSpace(body)) {
		t.Fatalf("attachments-vectors.json is stale; re-run with SYFT_ATT_REGEN_VECTORS=1")
	}
}

func mustHex(s string) []byte {
	b, err := hex.DecodeString(s)
	if err != nil {
		panic(err)
	}
	return b
}

func sha256Hex(b []byte) string {
	h := sha256Hash(b)
	return hex.EncodeToString(h)
}

func sha256Hash(b []byte) []byte {
	out := make([]byte, 32)
	digest := sha256New()
	digest.Write(b)
	copy(out, digest.Sum(nil))
	return out
}

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	neg := i < 0
	if neg {
		i = -i
	}
	var b [20]byte
	n := len(b)
	for i > 0 {
		n--
		b[n] = byte('0' + i%10)
		i /= 10
	}
	if neg {
		n--
		b[n] = '-'
	}
	return string(b[n:])
}

// findRepoRoot ascends from the test cwd until it finds a directory
// containing a 'docs' subdir.
func findRepoRoot(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for d := wd; d != "/" && d != ""; d = filepath.Dir(d) {
		if _, err := os.Stat(filepath.Join(d, "docs", "architecture")); err == nil {
			return d
		}
	}
	t.Fatalf("could not locate repo root (docs/architecture not found above %s)", wd)
	return ""
}
