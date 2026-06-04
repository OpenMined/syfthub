// Package cryptocore consolidates the AES-256-GCM + X25519/HKDF primitives
// shared by every encrypted wire format inside syfthubapi:
//
//   - the v1 ephemeral tunnel scheme (transport/crypto.go)
//   - the v2 identity-keyed agent session scheme (transport/crypto_session.go)
//   - the manual-review resolution scheme (manualreview/cipher.go)
//
// This package is deliberately under sdk/golang/syfthubapi/internal/, which
// means it is import-restricted to packages that live under syfthubapi/. It
// MUST NOT be re-exported. The functions here are intentionally low-level
// and trust their callers — callers are responsible for choosing the right
// HKDF info label (via Domain) and AAD for their scheme.
//
// SECURITY-SENSITIVE — any change to a function here changes wire format
// across multiple schemes. The KAT tests in:
//
//	sdk/golang/syfthubapi/transport/crypto_session_kat_test.go
//	sdk/golang/syfthubapi/manualreview/cipher_kat_test.go
//
// pin the byte-exact wire output and MUST stay green after any edit.
package cryptocore
