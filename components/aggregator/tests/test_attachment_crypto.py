"""Tests for the aggregator's attachment crypto.

Verifies byte-stable interop with the Go implementation via the vectors at
docs/architecture/attachments-vectors.json.
"""

from __future__ import annotations

import io
import json
import pathlib
import secrets

import pytest
from cryptography.exceptions import InvalidTag

from aggregator.attachment_crypto import (
    BASE_NONCE_SIZE,
    CHUNK_SIZE,
    TAG_SIZE,
    AttachmentEncryptor,
    generate_base_nonce,
    generate_file_key,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
VECTORS_PATH = REPO_ROOT / "docs" / "architecture" / "attachments-vectors.json"


def _load_vectors() -> dict:
    if not VECTORS_PATH.exists():
        pytest.skip(f"vector file not present at {VECTORS_PATH}")
    return json.loads(VECTORS_PATH.read_text())


def test_constants_match_protocol() -> None:
    assert CHUNK_SIZE == 64 * 1024
    assert TAG_SIZE == 16
    assert BASE_NONCE_SIZE == 8


def test_kek_derivation_matches_go_vector() -> None:
    data = _load_vectors()
    vec = next(v for v in data["vectors"] if v["name"] == "kek-derivation-known-file-id")
    session_key = bytes.fromhex(vec["session_key_hex"])
    file_id = vec["file_id"]
    expected = bytes.fromhex(vec["expected_kek_hex"])

    enc = AttachmentEncryptor(session_key)
    got = enc.derive_file_kek(file_id)
    assert got == expected, f"Python KEK does not match Go vector for {file_id}"


def test_stream_encrypt_small_matches_go_vector() -> None:
    data = _load_vectors()
    vec = next(v for v in data["vectors"] if v["name"] == "stream-encrypt-small")
    session_key = bytes.fromhex(vec["session_key_hex"])
    file_key = bytes.fromhex(vec["file_key_hex"])
    base_nonce = bytes.fromhex(vec["base_nonce_hex"])
    plaintext = bytes.fromhex(vec["plaintext_hex"])
    expected_ct = bytes.fromhex(vec["ciphertext_hex"])
    file_id = vec["file_id"]

    enc = AttachmentEncryptor(session_key)
    out = io.BytesIO()
    size, sha = enc.encrypt_stream(file_key, base_nonce, file_id, io.BytesIO(plaintext), out)
    assert size == len(plaintext)
    assert sha == vec["plaintext_sha256"]
    assert out.getvalue() == expected_ct, "Python ciphertext drift vs Go vector"


def test_round_trip_small() -> None:
    session_key = secrets.token_bytes(32)
    enc = AttachmentEncryptor(session_key)
    file_key = generate_file_key()
    base_nonce = generate_base_nonce()
    pt = b"hello world"
    ct = io.BytesIO()
    enc.encrypt_stream(file_key, base_nonce, "att-1", io.BytesIO(pt), ct)
    ct.seek(0)
    out = io.BytesIO()
    size, sha = enc.decrypt_stream(file_key, base_nonce, "att-1", len(pt), ct, out)
    assert size == len(pt)
    assert out.getvalue() == pt


def test_round_trip_multi_chunk() -> None:
    session_key = secrets.token_bytes(32)
    enc = AttachmentEncryptor(session_key)
    file_key = generate_file_key()
    base_nonce = generate_base_nonce()
    pt = secrets.token_bytes(200 * 1024)
    ct = io.BytesIO()
    enc.encrypt_stream(file_key, base_nonce, "att-multi", io.BytesIO(pt), ct)
    ct.seek(0)
    out = io.BytesIO()
    enc.decrypt_stream(file_key, base_nonce, "att-multi", len(pt), ct, out)
    assert out.getvalue() == pt


def test_round_trip_exact_chunk() -> None:
    session_key = secrets.token_bytes(32)
    enc = AttachmentEncryptor(session_key)
    file_key = generate_file_key()
    base_nonce = generate_base_nonce()
    pt = secrets.token_bytes(CHUNK_SIZE)
    ct = io.BytesIO()
    enc.encrypt_stream(file_key, base_nonce, "att-exact", io.BytesIO(pt), ct)
    ct.seek(0)
    out = io.BytesIO()
    enc.decrypt_stream(file_key, base_nonce, "att-exact", len(pt), ct, out)
    assert out.getvalue() == pt


def test_wrap_unwrap_file_key() -> None:
    session_key = secrets.token_bytes(32)
    enc = AttachmentEncryptor(session_key)
    fk = generate_file_key()
    ct, nonce = enc.wrap_file_key("att-w", fk)
    assert enc.unwrap_file_key("att-w", ct, nonce) == fk
    with pytest.raises(InvalidTag):
        enc.unwrap_file_key("att-other", ct, nonce)


def test_invalid_key_length_rejected() -> None:
    with pytest.raises(ValueError):
        AttachmentEncryptor(b"short")


def test_decrypt_tamper_rejected() -> None:
    session_key = secrets.token_bytes(32)
    enc = AttachmentEncryptor(session_key)
    file_key = generate_file_key()
    base_nonce = generate_base_nonce()
    pt = b"sensitive"
    ct = io.BytesIO()
    enc.encrypt_stream(file_key, base_nonce, "att-t", io.BytesIO(pt), ct)
    blob = bytearray(ct.getvalue())
    blob[3] ^= 0xFF
    with pytest.raises(InvalidTag):
        enc.decrypt_stream(
            file_key, base_nonce, "att-t", len(pt), io.BytesIO(bytes(blob)), io.BytesIO()
        )


def test_size_mismatch_rejected() -> None:
    session_key = secrets.token_bytes(32)
    enc = AttachmentEncryptor(session_key)
    file_key = generate_file_key()
    base_nonce = generate_base_nonce()
    ct = io.BytesIO()
    enc.encrypt_stream(file_key, base_nonce, "att-s", io.BytesIO(b"abc"), ct)
    ct.seek(0)
    with pytest.raises(ValueError):
        enc.decrypt_stream(file_key, base_nonce, "att-s", 999, ct, io.BytesIO())
