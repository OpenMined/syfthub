"""Attachment crypto — Python mirror of sdk/golang/syfthubapi/transport/attachment_encryptor.go.

See docs/architecture/attachments.md.

Byte-stable interop with the Go implementation is verified via test vectors at
docs/architecture/attachments-vectors.json.
"""

from __future__ import annotations

import hashlib
import secrets
import struct
from typing import IO

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

CHUNK_SIZE = 64 * 1024
TAG_SIZE = 16
BASE_NONCE_SIZE = 8
COUNTER_SIZE = 4
NONCE_SIZE = BASE_NONCE_SIZE + COUNTER_SIZE  # 12

HKDF_INFO = b"syfthub-attachment-v1"


class AttachmentEncryptor:
    """Per-session encryption layer for attachment ciphertext.

    Constructed once per session from the session AES key. Provides:
      - derive_file_kek(file_id): HKDF-Expand(session_key, HKDF_INFO || file_id, 32)
      - wrap_file_key / unwrap_file_key: envelope encryption
      - encrypt_stream / decrypt_stream: chunked AES-256-GCM
    """

    def __init__(self, session_aes_key: bytes) -> None:
        if len(session_aes_key) != 32:
            raise ValueError(f"session AES key must be 32 bytes, got {len(session_aes_key)}")
        self._session_key = bytes(session_aes_key)

    def derive_file_kek(self, file_id: str) -> bytes:
        if not file_id:
            raise ValueError("file_id is required")
        kdf = HKDFExpand(
            algorithm=hashes.SHA256(),
            length=32,
            info=HKDF_INFO + file_id.encode("utf-8"),
        )
        return kdf.derive(self._session_key)

    def wrap_file_key(self, file_id: str, file_key: bytes) -> tuple[bytes, bytes]:
        """Return (ciphertext, nonce) — envelope-encrypts file_key under the KEK."""
        if len(file_key) != 32:
            raise ValueError(f"file_key must be 32 bytes, got {len(file_key)}")
        kek = self.derive_file_kek(file_id)
        nonce = secrets.token_bytes(NONCE_SIZE)
        ct = AESGCM(kek).encrypt(nonce, file_key, file_id.encode("utf-8"))
        return ct, nonce

    def unwrap_file_key(self, file_id: str, ciphertext: bytes, nonce: bytes) -> bytes:
        if len(nonce) != NONCE_SIZE:
            raise ValueError(f"nonce must be {NONCE_SIZE} bytes, got {len(nonce)}")
        kek = self.derive_file_kek(file_id)
        pt = AESGCM(kek).decrypt(nonce, ciphertext, file_id.encode("utf-8"))
        if len(pt) != 32:
            raise ValueError(f"unwrapped key must be 32 bytes, got {len(pt)}")
        return pt

    def encrypt_stream(
        self,
        file_key: bytes,
        base_nonce: bytes,
        file_id: str,
        src: IO[bytes],
        dst: IO[bytes],
    ) -> tuple[int, str]:
        """Encrypt src→dst with chunked AES-256-GCM.

        Returns (plaintext_size, plaintext_sha256_hex).
        """
        if len(file_key) != 32:
            raise ValueError(f"file_key must be 32 bytes, got {len(file_key)}")
        if len(base_nonce) != BASE_NONCE_SIZE:
            raise ValueError(f"base_nonce must be {BASE_NONCE_SIZE} bytes, got {len(base_nonce)}")
        aesgcm = AESGCM(file_key)
        hasher = hashlib.sha256()
        total = 0
        counter = 0
        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
            total += len(chunk)
            nonce = base_nonce + struct.pack(">I", counter)
            aad = file_id.encode("utf-8") + struct.pack(">I", counter)
            ct = aesgcm.encrypt(nonce, chunk, aad)
            dst.write(ct)
            counter += 1
            if len(chunk) < CHUNK_SIZE:
                break
        return total, hasher.hexdigest()

    def decrypt_stream(
        self,
        file_key: bytes,
        base_nonce: bytes,
        file_id: str,
        declared_size: int,
        src: IO[bytes],
        dst: IO[bytes],
    ) -> tuple[int, str]:
        """Decrypt src→dst chunk-by-chunk. Verifies declared_size if non-negative."""
        if len(file_key) != 32:
            raise ValueError(f"file_key must be 32 bytes, got {len(file_key)}")
        if len(base_nonce) != BASE_NONCE_SIZE:
            raise ValueError(f"base_nonce must be {BASE_NONCE_SIZE} bytes, got {len(base_nonce)}")
        aesgcm = AESGCM(file_key)
        hasher = hashlib.sha256()
        ct_chunk_max = CHUNK_SIZE + TAG_SIZE
        total = 0
        counter = 0
        while True:
            chunk = _read_full(src, ct_chunk_max)
            if not chunk:
                break
            if len(chunk) < TAG_SIZE:
                raise ValueError(f"chunk {counter} truncated: {len(chunk)} bytes")
            nonce = base_nonce + struct.pack(">I", counter)
            aad = file_id.encode("utf-8") + struct.pack(">I", counter)
            pt = aesgcm.decrypt(nonce, chunk, aad)
            hasher.update(pt)
            total += len(pt)
            dst.write(pt)
            counter += 1
            if len(chunk) < ct_chunk_max:
                break
        if declared_size >= 0 and total != declared_size:
            raise ValueError(f"plaintext size mismatch: declared {declared_size}, actual {total}")
        return total, hasher.hexdigest()


def _read_full(src: IO[bytes], want: int) -> bytes:
    """Read up to `want` bytes, accumulating across short reads. Returns b"" on EOF."""
    buf = bytearray()
    while len(buf) < want:
        chunk = src.read(want - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def generate_file_key() -> bytes:
    return secrets.token_bytes(32)


def generate_base_nonce() -> bytes:
    return secrets.token_bytes(BASE_NONCE_SIZE)
