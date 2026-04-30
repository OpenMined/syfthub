"""Tests for NATS schemas."""

import base64

import pytest
from pydantic import ValidationError

from syfthub.schemas.nats import (
    EncryptionKeyRegisterRequest,
    EncryptionKeyResponse,
    NatsCredentialsResponse,
)


class TestNatsCredentialsResponse:
    def test_creates_with_token(self):
        r = NatsCredentialsResponse(nats_auth_token="mytoken")
        assert r.nats_auth_token == "mytoken"

    def test_requires_token(self):
        with pytest.raises(ValidationError):
            NatsCredentialsResponse()


class TestEncryptionKeyRegisterRequest:
    def _make_valid_key(self) -> str:
        key_bytes = b"\x01" * 32
        return base64.urlsafe_b64encode(key_bytes).rstrip(b"=").decode()

    def test_accepts_valid_x25519_key(self):
        key = self._make_valid_key()
        req = EncryptionKeyRegisterRequest(encryption_public_key=key)
        assert req.encryption_public_key == key

    def test_rejects_empty_key(self):
        with pytest.raises(ValidationError):
            EncryptionKeyRegisterRequest(encryption_public_key="")

    def test_rejects_invalid_base64(self):
        with pytest.raises(ValidationError):
            EncryptionKeyRegisterRequest(encryption_public_key="not!!valid@@base64")

    def test_rejects_wrong_length_key(self):
        short_key = base64.urlsafe_b64encode(b"\x01" * 16).rstrip(b"=").decode()
        with pytest.raises(ValidationError):
            EncryptionKeyRegisterRequest(encryption_public_key=short_key)

    def test_accepts_padded_base64(self):
        key_bytes = b"\x02" * 32
        padded_key = base64.urlsafe_b64encode(key_bytes).decode()
        req = EncryptionKeyRegisterRequest(encryption_public_key=padded_key)
        assert req.encryption_public_key == padded_key


class TestEncryptionKeyResponse:
    def test_creates_with_key(self):
        r = EncryptionKeyResponse(encryption_public_key="somekey")
        assert r.encryption_public_key == "somekey"

    def test_creates_without_key(self):
        r = EncryptionKeyResponse()
        assert r.encryption_public_key is None
