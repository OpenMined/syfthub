# NATS Tunnel E2E Encryption

This document describes the end-to-end encryption protocol used for NATS tunneling
in SyftHub. All tunnel communication is encrypted — there is no plaintext fallback.

## Overview

When a client queries a Space via the NATS tunnel (aggregator → space), every
request and response payload is encrypted with a per-request ephemeral key derived
via X25519 ECDH + HKDF-SHA256 + AES-256-GCM. Plaintext requests are rejected by
the space with a `DECRYPTION_FAILED` error.

```
Aggregator                           Space (Go SDK)
──────────                           ─────────────
[startup]                            [startup]
                                     gen X25519 keypair (space_priv, space_pub)
                                     PUT /nats/encryption-key  →  hub stores space_pub

[per request]
GET /nats/encryption-key/{username}  ←  hub returns space_pub
gen ephemeral keypair (eph_priv, eph_pub)
shared = X25519(eph_priv, space_pub)
aes_key = HKDF(shared, REQUEST_INFO)
nonce = random 12 bytes
ct = AES-256-GCM(aes_key, nonce, payload, AAD=corr_id)

publish TunnelRequest {
  encryption_info: {
    algorithm: "X25519-ECDH-AES-256-GCM",
    ephemeral_public_key: b64url(eph_pub),
    nonce: b64url(nonce),
  },
  encrypted_payload: b64url(ct),
}
                                     →  receive TunnelRequest
                                        shared = X25519(space_priv, eph_pub)
                                        aes_key = HKDF(shared, REQUEST_INFO)
                                        plaintext = AES-256-GCM-Decrypt(ct)

                                        gen resp ephemeral (resp_priv, resp_pub)
                                        resp_shared = X25519(resp_priv, eph_pub)
                                        resp_key = HKDF(resp_shared, RESPONSE_INFO)
                                        resp_ct = AES-256-GCM(resp_key, ...)

                                        publish TunnelResponse {
                                          encryption_info: {
                                            ephemeral_public_key: b64url(resp_pub),
                                            nonce: b64url(resp_nonce),
                                          },
                                          encrypted_payload: b64url(resp_ct),
                                        }
←  receive TunnelResponse
   resp_shared = X25519(eph_priv, resp_pub)
   resp_key = HKDF(resp_shared, RESPONSE_INFO)
   plaintext = AES-256-GCM-Decrypt(resp_ct)
```

## Key Exchange Details

| Parameter | Value |
|-----------|-------|
| Key agreement | X25519 ECDH |
| KDF | HKDF-SHA256, 32-byte output |
| Symmetric cipher | AES-256-GCM |
| Nonce size | 12 bytes (random) |
| AAD | UTF-8 bytes of `correlation_id` |
| Request HKDF info | `syfthub-tunnel-request-v1` |
| Response HKDF info | `syfthub-tunnel-response-v1` |
| Algorithm identifier | `X25519-ECDH-AES-256-GCM` |

### Domain Separation

Two distinct HKDF `info` strings ensure that the request AES key and response AES
key are cryptographically independent even when derived from the same ECDH shared
secret. This prevents key reuse across directions.

### Forward Secrecy

A fresh ephemeral keypair is generated for every request (aggregator side) and every
response (space side). Compromise of the space's long-term key does not expose the
content of past requests or responses.

### Authenticated Encryption

`correlation_id` is bound to the ciphertext as GCM additional authenticated data
(AAD). Decryption fails if the correlation_id doesn't match, preventing cross-request
payload substitution.

## Space Key Registration

On startup the Go SDK (`NATSTransport`) generates an X25519 keypair and registers
the public key with the SyftHub backend:

```
PUT /nats/encryption-key
Authorization: Bearer <space-api-key>
Content-Type: application/json

{"encryption_public_key": "<base64url-encoded 32-byte X25519 public key>"}
```

The aggregator fetches this key before sending each request:

```
GET /nats/encryption-key/{username}
Authorization: Bearer <hub-token>
```

The aggregator caches the key in-process (TTL: 300 s by default). If decryption
fails after receiving a response the cache entry is evicted so the next request
re-fetches in case the space restarted and generated a new keypair.

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Space has no registered key | Aggregator raises `ENCRYPTION_KEY_MISSING`; request aborted before NATS publish |
| Request received without `encryption_info` | Space replies with `DECRYPTION_FAILED` error response |
| GCM authentication tag mismatch | Space replies with `DECRYPTION_FAILED` error response |
| Response encryption fails (internal) | Space drops the message; aggregator times out |
| Response missing `encrypted_payload` | Aggregator raises `DECRYPTION_FAILED`; returns error to caller |

## Wire Format

### TunnelRequest (aggregator → space)

```json
{
  "protocol": "syfthub-tunnel/v1",
  "type": "endpoint_request",
  "correlation_id": "<uuid>",
  "reply_to": "<peer_channel_uuid>",
  "endpoint": {"slug": "my-endpoint", "type": "data_source"},
  "encryption_info": {
    "algorithm": "X25519-ECDH-AES-256-GCM",
    "ephemeral_public_key": "<base64url>",
    "nonce": "<base64url 12 bytes>"
  },
  "encrypted_payload": "<base64url ciphertext>"
}
```

The `payload` field is always `null` / absent — the plaintext lives only in
`encrypted_payload`.

### TunnelResponse (space → aggregator)

```json
{
  "protocol": "syfthub-tunnel/v1",
  "type": "endpoint_response",
  "correlation_id": "<uuid>",
  "status": "success",
  "endpoint_slug": "my-endpoint",
  "encryption_info": {
    "algorithm": "X25519-ECDH-AES-256-GCM",
    "ephemeral_public_key": "<base64url>",
    "nonce": "<base64url 12 bytes>"
  },
  "encrypted_payload": "<base64url ciphertext>"
}
```

Even error responses carry `encrypted_payload` (the plaintext is JSON `null`).

## Implementation References

| Component | File |
|-----------|------|
| Python crypto utilities | `components/aggregator/src/aggregator/crypto.py` |
| Python NATS transport (aggregator) | `components/aggregator/src/aggregator/clients/nats_transport.py` |
| Go crypto utilities | `sdk/golang/syfthubapi/transport/crypto.go` |
| Go NATS transport (space) | `sdk/golang/syfthubapi/transport/nats.go` |
| Backend key endpoint | `components/backend/src/syfthub/api/endpoints/nats.py` |
| DB migration | `components/backend/alembic/versions/20260226_000000_add_encryption_public_key.py` |
| Python crypto tests | `components/aggregator/tests/test_crypto.py` |
| Python transport tests | `components/aggregator/tests/test_nats_transport_encryption.py` |
| Go crypto tests | `sdk/golang/syfthubapi/transport/crypto_test.go` |
