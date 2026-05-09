// Package mppx is a Go implementation of the Machine Payments Protocol (MPP)
// client and server primitives, wire-compatible with the TypeScript reference
// implementation `mppx` (https://github.com/openmined/mppx).
//
// MPP is a transport-agnostic application-layer payment protocol. It defines
// four data structures — Challenge, Credential, Receipt and PaymentRequest —
// that are typically carried in HTTP headers (`WWW-Authenticate`,
// `Authorization`, `Payment-Receipt`) but may travel over any transport,
// including pub/sub messages.
//
// This package implements the wire format, the HMAC-SHA256 challenge ID
// binding, and the Tempo blockchain payment method (the on-chain method used
// by the SyftHub transaction policy).
//
// # Wire format
//
// A challenge serialises to:
//
//	Payment id="<base64url-of-HMAC>", realm="<context>", method="tempo",
//	    intent="charge", request="<base64url-JSON>", expires="<ISO8601>"
//
// A credential serialises to:
//
//	Payment <base64url-of-JSON{challenge, payload, source?}>
//
// A receipt serialises to:
//
//	<base64url-of-JSON{method, reference, status, timestamp}>
//
// # Canonical HMAC input
//
// The challenge `id` field is HMAC-SHA256 of the canonical input string
// produced by joining seven positional slots with `|`:
//
//	realm | method | intent | request | expires | digest | opaque
//
// where `request` is the canonical-JSON (RFC 8785) base64url-encoded request
// object and missing optional fields are the empty string. The HMAC binds the
// id to all challenge parameters so that any tampering — by Bob, by the
// transport, or by a man-in-the-middle — invalidates the credential before
// any blockchain call is made.
//
// See [CanonicalFieldOrder] in hmac.go for the joining template.
//
// # Usage
//
// Server side (Alice — challenge generator + credential verifier):
//
//	builder := tempo.NewCharge("0x20c0…", "0xf39F…", 42431).
//	    Amount("1.00").
//	    Decimals(6).
//	    Realm("pubsub://alice/pay")
//	challenge, _ := builder.WithSecretKey([]byte("alice-secret-32")).Build()
//	wwwAuthenticate := mppx.SerializeChallenge(challenge)
//	// … publish wwwAuthenticate to Bob …
//	receipt, err := tempo.VerifyCredential(credential, []byte("alice-secret-32"),
//	    "https://rpc.testnet.tempo.xyz", 5*time.Minute)
//
// Client side (Bob — credential signer):
//
//	challenge, _ := mppx.DeserializeChallenge(wwwAuthenticate)
//	account, _ := mppx.LoadAccount(privateKeyHex)
//	credential, err := tempo.SignCredential(challenge, account,
//	    "https://rpc.testnet.tempo.xyz")
//	authorization := mppx.SerializeCredential(credential)
//
// # Wire compatibility
//
// All serialisation routines aim for byte-identical output with the
// TypeScript `mppx` library, including:
//
//   - Object keys in the request payload are sorted via RFC 8785 canonical
//     JSON before base64url encoding.
//   - Base64 URL encoding is unpadded (no `=`).
//   - HMAC field separator is the literal pipe character `|`; missing
//     optional fields use the empty string but always occupy a slot.
//   - The credential JSON wrapper preserves Go map insertion order for the
//     outer object only; the embedded challenge nests `request` as a base64url
//     string (not the original object) to match TS behaviour.
//
// Conformance is exercised by tests in conformance_test.go using fixtures
// captured from the reference implementation.
package mppx
