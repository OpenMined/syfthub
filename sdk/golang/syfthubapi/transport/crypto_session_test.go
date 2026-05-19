package transport

import (
	"bytes"
	"crypto/ecdh"
	"testing"
)

// newTestIdentity returns a fresh X25519 identity keypair and its base64url
// public key, as the v2 agent session crypto expects.
func newTestIdentity(t *testing.T) (*ecdh.PrivateKey, string) {
	t.Helper()
	k, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("GenerateX25519Keypair: %v", err)
	}
	return k, b64urlEncode(k.PublicKey().Bytes())
}

func TestSessionCipher_RoundTrip(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	hostKey, hostPub := newTestIdentity(t)
	const sid = "session-abc-123"

	client, err := NewSessionCipher(clientKey, hostPub, sid)
	if err != nil {
		t.Fatalf("client cipher: %v", err)
	}
	host, err := NewSessionCipher(hostKey, clientPub, sid)
	if err != nil {
		t.Fatalf("host cipher: %v", err)
	}

	// Request direction: client encrypts, host decrypts.
	req := []byte(`{"prompt":"hello world"}`)
	nonce, ct, err := client.EncryptRequest(req, "corr-1")
	if err != nil {
		t.Fatalf("EncryptRequest: %v", err)
	}
	got, err := host.DecryptRequest(nonce, ct, "corr-1")
	if err != nil {
		t.Fatalf("DecryptRequest: %v", err)
	}
	if !bytes.Equal(got, req) {
		t.Fatalf("request round-trip mismatch: got %q want %q", got, req)
	}

	// Response direction: host encrypts, client decrypts.
	resp := []byte(`{"event_type":"agent.message","data":{}}`)
	nonce, ct, err = host.EncryptResponse(resp, sid+"-7")
	if err != nil {
		t.Fatalf("EncryptResponse: %v", err)
	}
	got, err = client.DecryptResponse(nonce, ct, sid+"-7")
	if err != nil {
		t.Fatalf("DecryptResponse: %v", err)
	}
	if !bytes.Equal(got, resp) {
		t.Fatalf("response round-trip mismatch: got %q want %q", got, resp)
	}
}

func TestSessionCipher_SessionIsolation(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	hostKey, hostPub := newTestIdentity(t)

	c1, err := NewSessionCipher(clientKey, hostPub, "session-1")
	if err != nil {
		t.Fatal(err)
	}
	h2, err := NewSessionCipher(hostKey, clientPub, "session-2")
	if err != nil {
		t.Fatal(err)
	}

	nonce, ct, err := c1.EncryptRequest([]byte("secret"), "c")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := h2.DecryptRequest(nonce, ct, "c"); err == nil {
		t.Fatal("ciphertext from session-1 decrypted under session-2 keys")
	}
}

func TestSessionCipher_DirectionSeparation(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	hostKey, hostPub := newTestIdentity(t)
	const sid = "s"

	client, err := NewSessionCipher(clientKey, hostPub, sid)
	if err != nil {
		t.Fatal(err)
	}
	host, err := NewSessionCipher(hostKey, clientPub, sid)
	if err != nil {
		t.Fatal(err)
	}

	nonce, ct, err := client.EncryptRequest([]byte("x"), "c")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := host.DecryptResponse(nonce, ct, "c"); err == nil {
		t.Fatal("request ciphertext decrypted as a response — direction keys not separated")
	}
}

func TestSessionCipher_AADBinding(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	hostKey, hostPub := newTestIdentity(t)
	const sid = "s"

	client, err := NewSessionCipher(clientKey, hostPub, sid)
	if err != nil {
		t.Fatal(err)
	}
	host, err := NewSessionCipher(hostKey, clientPub, sid)
	if err != nil {
		t.Fatal(err)
	}

	nonce, ct, err := client.EncryptRequest([]byte("x"), "corr-A")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := host.DecryptRequest(nonce, ct, "corr-B"); err == nil {
		t.Fatal("decrypt succeeded with a different correlation id — AAD not bound")
	}
}

func TestSessionCipher_Tamper(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	hostKey, hostPub := newTestIdentity(t)
	const sid = "s"

	client, err := NewSessionCipher(clientKey, hostPub, sid)
	if err != nil {
		t.Fatal(err)
	}
	host, err := NewSessionCipher(hostKey, clientPub, sid)
	if err != nil {
		t.Fatal(err)
	}

	nonce, ct, err := client.EncryptRequest([]byte("important payload"), "c")
	if err != nil {
		t.Fatal(err)
	}
	raw, err := b64urlDecode(ct)
	if err != nil {
		t.Fatal(err)
	}
	raw[0] ^= 0xff
	if _, err := host.DecryptRequest(nonce, b64urlEncode(raw), "c"); err == nil {
		t.Fatal("tampered ciphertext authenticated successfully")
	}
}

func TestSessionCipher_WrongPeer(t *testing.T) {
	clientKey, clientPub := newTestIdentity(t)
	_, hostPub := newTestIdentity(t)
	eveKey, _ := newTestIdentity(t)
	const sid = "s"

	client, err := NewSessionCipher(clientKey, hostPub, sid)
	if err != nil {
		t.Fatal(err)
	}
	nonce, ct, err := client.EncryptRequest([]byte("private"), "c")
	if err != nil {
		t.Fatal(err)
	}

	// Eve pairs her own key with the client's public key — a different
	// shared secret than (client, host).
	eve, err := NewSessionCipher(eveKey, clientPub, sid)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := eve.DecryptRequest(nonce, ct, "c"); err == nil {
		t.Fatal("an eavesdropper decrypted the message")
	}
}

func TestNewSessionCipher_Errors(t *testing.T) {
	key, pub := newTestIdentity(t)

	if _, err := NewSessionCipher(nil, pub, "s"); err == nil {
		t.Error("expected error for nil identity key")
	}
	if _, err := NewSessionCipher(key, pub, ""); err == nil {
		t.Error("expected error for empty session id")
	}
	if _, err := NewSessionCipher(key, "not valid base64!!", "s"); err == nil {
		t.Error("expected error for malformed peer public key")
	}
}
