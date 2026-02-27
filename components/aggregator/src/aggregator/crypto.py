"""Cryptographic utilities for NATS tunnel E2E encryption.

Implements X25519 ECDH key agreement + AES-256-GCM symmetric encryption with
HKDF-SHA256 key derivation. Each tunnel request uses a fresh ephemeral keypair
(forward secrecy). The GCM AAD is bound to the correlation_id to prevent
cross-request replay attacks.

Protocol:
  Sender (aggregator):
    1. Generate ephemeral X25519 keypair (priv_e, pub_e)
    2. shared_secret = X25519(priv_e, space_long_term_pub)
    3. aes_key = HKDF-SHA256(shared_secret, salt="", info=HKDF_REQUEST_INFO, len=32)
    4. nonce = os.urandom(12)
    5. ciphertext = AES-256-GCM(aes_key, nonce, plaintext, aad=correlation_id.encode())
    6. Transmit: (pub_e, nonce, ciphertext) as base64url + correlation_id

  Receiver (Go SDK space):
    1. shared_secret = X25519(space_priv, pub_e)
    2. aes_key = HKDF-SHA256(shared_secret, same info/salt, len=32)
    3. plaintext = AES-256-GCM-Decrypt(aes_key, nonce, ciphertext, aad=correlation_id.encode())

Response uses HKDF_RESPONSE_INFO so request/response keys are always distinct.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

# Domain-separation labels for HKDF; distinct info ensures request/response keys differ
# even if the same ECDH shared secret were somehow reused.
HKDF_REQUEST_INFO: bytes = b"syfthub-tunnel-request-v1"
HKDF_RESPONSE_INFO: bytes = b"syfthub-tunnel-response-v1"
HKDF_SALT: bytes = b""  # Empty salt — HKDF handles this per RFC 5869
NONCE_SIZE: int = 12  # 96-bit nonce for AES-256-GCM

ALGORITHM_ID: str = "X25519-ECDH-AES-256-GCM"


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    """Decode base64url string (with or without padding) to bytes."""
    padded = s + "=" * (4 - len(s) % 4) if len(s) % 4 else s
    return base64.urlsafe_b64decode(padded)


def generate_keypair() -> tuple[X25519PrivateKey, bytes]:
    """Generate a fresh X25519 keypair.

    Returns:
        Tuple of (private_key, public_key_raw_bytes).
    """
    private_key = X25519PrivateKey.generate()
    public_key_bytes = private_key.public_key().public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )
    return private_key, public_key_bytes


def derive_key(
    private_key: X25519PrivateKey,
    peer_public_key_bytes: bytes,
    info: bytes,
) -> bytes:
    """Perform X25519 ECDH and derive a 32-byte AES key via HKDF-SHA256.

    Args:
        private_key: Our X25519 private key.
        peer_public_key_bytes: Peer's raw X25519 public key (32 bytes).
        info: HKDF domain-separation label (HKDF_REQUEST_INFO or HKDF_RESPONSE_INFO).

    Returns:
        32-byte AES key.
    """
    peer_pub = X25519PublicKey.from_public_bytes(peer_public_key_bytes)
    shared_secret = private_key.exchange(peer_pub)
    return HKDF(
        algorithm=SHA256(),
        length=32,
        salt=HKDF_SALT if HKDF_SALT else None,
        info=info,
    ).derive(shared_secret)


def encrypt_payload(
    plaintext: bytes,
    aes_key: bytes,
    aad: bytes,
) -> tuple[bytes, bytes]:
    """Encrypt bytes with AES-256-GCM.

    Args:
        plaintext: Bytes to encrypt.
        aes_key: 32-byte AES key.
        aad: Additional authenticated data (not encrypted, but authenticated).

    Returns:
        Tuple of (nonce, ciphertext_with_gcm_tag).
    """
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ciphertext


def decrypt_payload(
    ciphertext_with_tag: bytes,
    aes_key: bytes,
    nonce: bytes,
    aad: bytes,
) -> bytes:
    """Decrypt AES-256-GCM ciphertext.

    Args:
        ciphertext_with_tag: Ciphertext concatenated with 16-byte GCM tag.
        aes_key: 32-byte AES key.
        nonce: 12-byte nonce used during encryption.
        aad: Additional authenticated data (must match what was used to encrypt).

    Returns:
        Decrypted plaintext bytes.

    Raises:
        InvalidTag: If decryption fails (wrong key, wrong aad, or tampered data).
    """
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, ciphertext_with_tag, aad)


def encrypt_tunnel_request(
    payload_json: str,
    space_public_key_b64: str,
    correlation_id: str,
) -> tuple[dict[str, str], X25519PrivateKey]:
    """Encrypt a tunnel request payload for a target space.

    Generates a fresh ephemeral keypair, performs ECDH with the space's
    long-term public key, derives an AES key, and encrypts the payload.
    The caller must retain the returned ephemeral private key to decrypt
    the response (which will be encrypted with the same ephemeral public key
    as the ECDH peer).

    Args:
        payload_json: JSON-serialized request payload string.
        space_public_key_b64: Base64url-encoded X25519 public key of the space.
        correlation_id: Unique request ID — bound to GCM tag to prevent replay.

    Returns:
        Tuple of:
          - encryption_info dict: {algorithm, ephemeral_public_key, nonce}
          - ephemeral_private_key: Retain this to decrypt the response.
    """
    space_pub_bytes = _b64url_decode(space_public_key_b64)
    ephemeral_priv, ephemeral_pub_bytes = generate_keypair()

    aes_key = derive_key(ephemeral_priv, space_pub_bytes, HKDF_REQUEST_INFO)
    aad = correlation_id.encode()
    nonce, ciphertext = encrypt_payload(payload_json.encode(), aes_key, aad)

    encryption_info = {
        "algorithm": ALGORITHM_ID,
        "ephemeral_public_key": _b64url_encode(ephemeral_pub_bytes),
        "nonce": _b64url_encode(nonce),
        "encrypted_payload": _b64url_encode(ciphertext),
    }
    return encryption_info, ephemeral_priv


def decrypt_tunnel_response(
    encrypted_payload_b64: str,
    encryption_info: dict[str, str],
    ephemeral_private_key: X25519PrivateKey,
    correlation_id: str,
) -> str:
    """Decrypt a tunnel response payload.

    The Go SDK encrypts responses using the aggregator's ephemeral public key
    (from the request's encryption_info) as the ECDH peer. We recover the
    shared secret using our ephemeral private key and the response's ephemeral
    public key.

    Args:
        encrypted_payload_b64: Base64url-encoded ciphertext+tag.
        encryption_info: Dict containing response's ephemeral_public_key and nonce.
        ephemeral_private_key: The ephemeral private key used to send the request.
        correlation_id: Must match what was used when encrypting (AAD check).

    Returns:
        Decrypted JSON string.

    Raises:
        InvalidTag: If decryption fails.
        KeyError: If encryption_info is missing required fields.
    """
    resp_ephemeral_pub_bytes = _b64url_decode(encryption_info["ephemeral_public_key"])
    nonce = _b64url_decode(encryption_info["nonce"])
    ciphertext = _b64url_decode(encrypted_payload_b64)

    aes_key = derive_key(ephemeral_private_key, resp_ephemeral_pub_bytes, HKDF_RESPONSE_INFO)
    aad = correlation_id.encode()
    plaintext = decrypt_payload(ciphertext, aes_key, nonce, aad)
    return plaintext.decode()


__all__ = [
    "ALGORITHM_ID",
    "HKDF_REQUEST_INFO",
    "HKDF_RESPONSE_INFO",
    "NONCE_SIZE",
    "InvalidTag",
    "generate_keypair",
    "derive_key",
    "encrypt_payload",
    "decrypt_payload",
    "encrypt_tunnel_request",
    "decrypt_tunnel_response",
]
