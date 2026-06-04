package cryptocore

import (
	"bytes"
	"crypto/ecdh"
	"strings"
	"testing"
)

func mustKey(t *testing.T, seed []byte) *ecdh.PrivateKey {
	t.Helper()
	k, err := ecdh.X25519().NewPrivateKey(seed)
	if err != nil {
		t.Fatalf("NewPrivateKey: %v", err)
	}
	return k
}

func TestB64URL_RoundTrip(t *testing.T) {
	data := make([]byte, 256)
	for i := range data {
		data[i] = byte(i)
	}
	enc := EncodeB64URL(data)
	if strings.Contains(enc, "=") {
		t.Fatalf("EncodeB64URL produced padding: %q", enc)
	}
	dec, err := DecodeB64URL(enc)
	if err != nil {
		t.Fatalf("DecodeB64URL: %v", err)
	}
	if !bytes.Equal(dec, data) {
		t.Fatal("round-trip mismatch")
	}
}

func TestDecodeB64URLLenient_AcceptsBothEncodings(t *testing.T) {
	data := []byte{0xfb, 0xff}
	noPad := EncodeB64URL(data) // "-_8"
	if _, err := DecodeB64URLLenient(noPad); err != nil {
		t.Errorf("lenient should accept no-padding: %v", err)
	}
	if _, err := DecodeB64URLLenient(noPad + "="); err != nil {
		t.Errorf("lenient should accept padded: %v", err)
	}
	if _, err := DecodeB64URLLenient("!!!"); err == nil {
		t.Error("lenient should reject invalid input")
	}
}

func TestDeriveKey_DomainSeparation(t *testing.T) {
	// Same shared secret, different Domain → different keys.
	a := mustKey(t, bytes.Repeat([]byte{0xaa}, 32))
	b := mustKey(t, bytes.Repeat([]byte{0xbb}, 32))
	domA := NewDomain("dom-a")
	domB := NewDomain("dom-b")

	keyA, err := DeriveKey(a, b.PublicKey().Bytes(), []byte("salt"), domA)
	if err != nil {
		t.Fatalf("DeriveKey A: %v", err)
	}
	keyB, err := DeriveKey(a, b.PublicKey().Bytes(), []byte("salt"), domB)
	if err != nil {
		t.Fatalf("DeriveKey B: %v", err)
	}
	if bytes.Equal(keyA, keyB) {
		t.Fatal("different Domain must produce different keys")
	}
	if len(keyA) != KeySize {
		t.Errorf("key length = %d, want %d", len(keyA), KeySize)
	}
}

func TestDeriveKey_SaltSeparation(t *testing.T) {
	a := mustKey(t, bytes.Repeat([]byte{0xaa}, 32))
	b := mustKey(t, bytes.Repeat([]byte{0xbb}, 32))
	dom := NewDomain("dom")

	keyA, _ := DeriveKey(a, b.PublicKey().Bytes(), []byte("s1"), dom)
	keyB, _ := DeriveKey(a, b.PublicKey().Bytes(), []byte("s2"), dom)
	if bytes.Equal(keyA, keyB) {
		t.Fatal("different salt must produce different keys")
	}
}

func TestDeriveKey_NilSaltIsStable(t *testing.T) {
	// nil salt and empty-bytes salt should both work; nil salt is the
	// v1-tunnel behaviour (zero-filled HashLen salt per RFC 5869).
	a := mustKey(t, bytes.Repeat([]byte{0xaa}, 32))
	b := mustKey(t, bytes.Repeat([]byte{0xbb}, 32))
	dom := NewDomain("d")
	if _, err := DeriveKey(a, b.PublicKey().Bytes(), nil, dom); err != nil {
		t.Errorf("nil salt rejected: %v", err)
	}
}

func TestDeriveKey_RejectsBadPeer(t *testing.T) {
	a := mustKey(t, bytes.Repeat([]byte{0xaa}, 32))
	dom := NewDomain("d")
	if _, err := DeriveKey(a, []byte{1, 2, 3}, nil, dom); err == nil {
		t.Error("expected error for malformed peer pubkey")
	}
}

func TestSealOpen_RoundTrip(t *testing.T) {
	key := bytes.Repeat([]byte{0x77}, KeySize)
	aead, err := NewAESGCM(key)
	if err != nil {
		t.Fatalf("NewAESGCM: %v", err)
	}
	pt := []byte("the quick brown fox")
	aad := []byte("aad-A")
	nonceB64, ctB64, err := Seal(aead, pt, aad)
	if err != nil {
		t.Fatalf("Seal: %v", err)
	}
	got, err := Open(aead, nonceB64, ctB64, aad)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	if !bytes.Equal(got, pt) {
		t.Errorf("decrypted = %q, want %q", got, pt)
	}
}

func TestOpen_RejectsWrongAAD(t *testing.T) {
	key := bytes.Repeat([]byte{0x77}, KeySize)
	aead, _ := NewAESGCM(key)
	n, ct, _ := Seal(aead, []byte("x"), []byte("A"))
	if _, err := Open(aead, n, ct, []byte("B")); err == nil {
		t.Fatal("Open should fail with wrong AAD")
	}
}

func TestOpen_RejectsBadNonceLength(t *testing.T) {
	key := bytes.Repeat([]byte{0x77}, KeySize)
	aead, _ := NewAESGCM(key)
	shortNonce := EncodeB64URL([]byte{1, 2, 3})
	if _, err := Open(aead, shortNonce, "AA", nil); err == nil {
		t.Fatal("Open should reject short nonce")
	}
}

func TestSealWithReader_DeterministicWithFixedNonce(t *testing.T) {
	key := bytes.Repeat([]byte{0x77}, KeySize)
	aead, _ := NewAESGCM(key)
	fixed := bytes.NewReader(bytes.Repeat([]byte{0x33}, NonceSize))
	n1, c1, err := SealWithReader(aead, []byte("hello"), []byte("a"), fixed)
	if err != nil {
		t.Fatalf("SealWithReader: %v", err)
	}
	// Same fixed nonce + same key + same plaintext + same AAD → same ct.
	fixed = bytes.NewReader(bytes.Repeat([]byte{0x33}, NonceSize))
	n2, c2, _ := SealWithReader(aead, []byte("hello"), []byte("a"), fixed)
	if n1 != n2 || c1 != c2 {
		t.Fatalf("deterministic seal mismatch: (%s,%s) vs (%s,%s)", n1, c1, n2, c2)
	}
}

func TestDomain_BytesCopiesLabel(t *testing.T) {
	d := NewDomain("dom-x")
	b := d.Bytes()
	if string(b) != "dom-x" {
		t.Errorf("Bytes = %q, want dom-x", b)
	}
}
