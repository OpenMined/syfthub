"""Unit tests for NATS tunnel E2E encryption crypto utilities.

Tests cover:
- Key generation
- Request encrypt/decrypt roundtrip (aggregator → space path)
- Response encrypt/decrypt roundtrip (space → aggregator path)
- Wrong-key authentication failures
- Wrong AAD (correlation_id) authentication failures
- Domain separation between request and response keys
- Base64url helpers
"""

from __future__ import annotations

import json
import uuid

import pytest
from cryptography.exceptions import InvalidTag

from aggregator import crypto

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_space_keypair() -> tuple:
    """Return (space_priv, space_pub_b64) for use in tests."""
    space_priv, space_pub_bytes = crypto.generate_keypair()
    space_pub_b64 = crypto._b64url_encode(space_pub_bytes)
    return space_priv, space_pub_b64


def manual_space_decrypt_request(
    enc_info: dict,
    space_priv,
    correlation_id: str,
) -> str:
    """Simulate the Go SDK decrypting a tunnel request."""
    ephemeral_pub_bytes = crypto._b64url_decode(enc_info["ephemeral_public_key"])
    nonce = crypto._b64url_decode(enc_info["nonce"])
    ciphertext = crypto._b64url_decode(enc_info["encrypted_payload"])

    aes_key = crypto.derive_key(space_priv, ephemeral_pub_bytes, crypto.HKDF_REQUEST_INFO)
    return crypto.decrypt_payload(ciphertext, aes_key, nonce, correlation_id.encode()).decode()


def manual_simulate_go_encrypt_response(
    payload_json: str,
    request_ephemeral_priv,
    correlation_id: str,
) -> tuple[dict, str]:
    """Simulate the Go SDK encrypting a tunnel response.

    The Go SDK:
    1. Generates a fresh response ephemeral keypair (resp_priv, resp_pub)
    2. ECDH: X25519(resp_priv, request_ephemeral_pub) = shared_secret
    3. aes_key = HKDF(shared_secret, HKDF_RESPONSE_INFO)
    4. Encrypt payload
    5. Return EncryptionInfo{ephemeral_public_key=resp_pub, nonce} + encrypted_payload

    Here we replicate that logic in Python to produce a ciphertext for
    decrypt_tunnel_response to verify.
    """
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    # Generate response ephemeral keypair (simulating Go's GenerateX25519Keypair)
    resp_priv, resp_pub_bytes = crypto.generate_keypair()

    # ECDH with request ephemeral private key acting as the peer
    request_ephemeral_pub_bytes = request_ephemeral_priv.public_key().public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )
    aes_key = crypto.derive_key(resp_priv, request_ephemeral_pub_bytes, crypto.HKDF_RESPONSE_INFO)
    aad = correlation_id.encode()
    nonce, ciphertext = crypto.encrypt_payload(payload_json.encode(), aes_key, aad)

    enc_info = {
        "algorithm": crypto.ALGORITHM_ID,
        "ephemeral_public_key": crypto._b64url_encode(resp_pub_bytes),
        "nonce": crypto._b64url_encode(nonce),
    }
    return enc_info, crypto._b64url_encode(ciphertext)


# ---------------------------------------------------------------------------
# generate_keypair
# ---------------------------------------------------------------------------


def test_generate_keypair_produces_32_byte_public_key():
    _, pub_bytes = crypto.generate_keypair()
    assert len(pub_bytes) == 32


def test_generate_keypair_produces_unique_keys():
    _, pub1 = crypto.generate_keypair()
    _, pub2 = crypto.generate_keypair()
    assert pub1 != pub2


# ---------------------------------------------------------------------------
# b64url helpers
# ---------------------------------------------------------------------------


def test_b64url_roundtrip():
    data = bytes(range(256))
    assert crypto._b64url_decode(crypto._b64url_encode(data)) == data


def test_b64url_no_padding():
    encoded = crypto._b64url_encode(b"hello")
    assert "=" not in encoded


# ---------------------------------------------------------------------------
# Request encrypt/decrypt roundtrip
# ---------------------------------------------------------------------------


def test_request_encrypt_decrypt_roundtrip():
    """Aggregator encrypts → space decrypts (via manual ECDH replication)."""
    space_priv, space_pub_b64 = make_space_keypair()
    payload = json.dumps({"messages": "find relevant docs", "limit": 5})
    correlation_id = str(uuid.uuid4())

    enc_info, _ = crypto.encrypt_tunnel_request(
        payload_json=payload,
        space_public_key_b64=space_pub_b64,
        correlation_id=correlation_id,
    )

    recovered = manual_space_decrypt_request(enc_info, space_priv, correlation_id)
    assert recovered == payload


def test_request_ciphertext_is_different_each_call():
    """Every call generates a fresh ephemeral key and nonce."""
    _, space_pub_b64 = make_space_keypair()
    payload = '{"messages": "same query"}'
    correlation_id = str(uuid.uuid4())

    enc1, _ = crypto.encrypt_tunnel_request(payload, space_pub_b64, correlation_id)
    enc2, _ = crypto.encrypt_tunnel_request(payload, space_pub_b64, correlation_id)

    assert enc1["ephemeral_public_key"] != enc2["ephemeral_public_key"]
    assert enc1["nonce"] != enc2["nonce"]
    assert enc1["encrypted_payload"] != enc2["encrypted_payload"]


def test_request_decrypt_wrong_key_raises():
    """Decrypting with a different space key raises InvalidTag."""
    _, space_pub_b64 = make_space_keypair()
    wrong_priv, _ = crypto.generate_keypair()  # different key

    payload = '{"messages": "secret"}'
    correlation_id = str(uuid.uuid4())

    enc_info, _ = crypto.encrypt_tunnel_request(payload, space_pub_b64, correlation_id)

    with pytest.raises(InvalidTag):
        manual_space_decrypt_request(enc_info, wrong_priv, correlation_id)


def test_request_decrypt_wrong_correlation_id_raises():
    """Decrypting with the wrong correlation_id (wrong AAD) raises InvalidTag."""
    space_priv, space_pub_b64 = make_space_keypair()
    payload = '{"messages": "secret"}'
    correlation_id = str(uuid.uuid4())

    enc_info, _ = crypto.encrypt_tunnel_request(payload, space_pub_b64, correlation_id)

    with pytest.raises(InvalidTag):
        manual_space_decrypt_request(enc_info, space_priv, "wrong-correlation-id")


# ---------------------------------------------------------------------------
# Response encrypt/decrypt roundtrip
# ---------------------------------------------------------------------------


def test_response_encrypt_decrypt_roundtrip():
    """Space (Go) encrypts response → aggregator decrypts (Python decrypt_tunnel_response)."""
    _, space_pub_b64 = make_space_keypair()
    payload = json.dumps({"summary": {"message": {"content": "Here are results..."}}})
    correlation_id = str(uuid.uuid4())

    # Aggregator sends a request; retain ephemeral_priv for response decryption
    _, ephemeral_priv = crypto.encrypt_tunnel_request(
        payload_json='{"messages": "query"}',
        space_public_key_b64=space_pub_b64,
        correlation_id=correlation_id,
    )

    # Space (Go) encrypts the response — simulated here with manual_simulate_go_encrypt_response
    enc_info, enc_payload_b64 = manual_simulate_go_encrypt_response(
        payload_json=payload,
        request_ephemeral_priv=ephemeral_priv,
        correlation_id=correlation_id,
    )

    # Aggregator decrypts
    recovered_json = crypto.decrypt_tunnel_response(
        encrypted_payload_b64=enc_payload_b64,
        encryption_info=enc_info,
        ephemeral_private_key=ephemeral_priv,
        correlation_id=correlation_id,
    )
    assert json.loads(recovered_json) == json.loads(payload)


def test_response_decrypt_wrong_correlation_id_raises():
    """Decrypting a response with wrong correlation_id raises InvalidTag."""
    _, space_pub_b64 = make_space_keypair()
    correlation_id = str(uuid.uuid4())

    _, ephemeral_priv = crypto.encrypt_tunnel_request(
        payload_json='{"q": "x"}',
        space_public_key_b64=space_pub_b64,
        correlation_id=correlation_id,
    )

    enc_info, enc_payload_b64 = manual_simulate_go_encrypt_response(
        payload_json='{"ok": true}',
        request_ephemeral_priv=ephemeral_priv,
        correlation_id=correlation_id,
    )

    with pytest.raises(InvalidTag):
        crypto.decrypt_tunnel_response(
            encrypted_payload_b64=enc_payload_b64,
            encryption_info=enc_info,
            ephemeral_private_key=ephemeral_priv,
            correlation_id="wrong-correlation-id",
        )


# ---------------------------------------------------------------------------
# Domain separation
# ---------------------------------------------------------------------------


def test_domain_separation_request_vs_response_keys_differ():
    """The same ECDH shared secret yields different keys for request vs response.

    If domain separation were absent, the request and response would use the
    same AES key — which would be a security flaw.
    """
    _, space_pub_b64 = make_space_keypair()
    space_pub_bytes = crypto._b64url_decode(space_pub_b64)

    ephemeral_priv, _ = crypto.generate_keypair()

    # Both sides compute the ECDH shared secret
    request_key = crypto.derive_key(ephemeral_priv, space_pub_bytes, crypto.HKDF_REQUEST_INFO)
    response_key = crypto.derive_key(ephemeral_priv, space_pub_bytes, crypto.HKDF_RESPONSE_INFO)

    assert request_key != response_key, "Request and response keys must be distinct"


# ---------------------------------------------------------------------------
# Low-level encrypt/decrypt
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_payload_roundtrip():
    import os

    key = os.urandom(32)
    plaintext = b"hello, world!"
    aad = b"some-request-id"

    nonce, ciphertext = crypto.encrypt_payload(plaintext, key, aad)
    recovered = crypto.decrypt_payload(ciphertext, key, nonce, aad)
    assert recovered == plaintext


def test_encrypt_decrypt_payload_wrong_aad_raises():
    import os

    key = os.urandom(32)
    plaintext = b"confidential"
    nonce, ciphertext = crypto.encrypt_payload(plaintext, key, b"correct-aad")

    with pytest.raises(InvalidTag):
        crypto.decrypt_payload(ciphertext, key, nonce, b"wrong-aad")


def test_nonce_size_is_12():
    assert crypto.NONCE_SIZE == 12
