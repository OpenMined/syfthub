"""Tests for the attachments protocol schemas (see docs/architecture/attachments.md)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aggregator.schemas.agent import (
    ATTACHMENT_CAPABILITY,
    ATTACHMENT_HKDF_INFO_V1,
    ATTACHMENT_INLINE_MAX_BYTES,
    AgentAttachmentPayload,
    AttachmentErrorPayload,
    AttachmentInfo,
    AttachmentTransport,
    AttachmentWrappedKey,
    SessionStartPayload,
    UserAttachmentPayload,
)


def test_inline_max_bytes_matches_protocol() -> None:
    assert ATTACHMENT_INLINE_MAX_BYTES == 64 * 1024


def test_capability_string_stable() -> None:
    assert ATTACHMENT_CAPABILITY == "attachments"


def test_hkdf_info_stable() -> None:
    assert ATTACHMENT_HKDF_INFO_V1 == b"syfthub-attachment-v1"


def test_attachment_info_inline_round_trip() -> None:
    info = AttachmentInfo(
        file_id="att-abc",
        name="hello.txt",
        mime="text/plain",
        size_bytes=11,
        plaintext_sha256="deadbeef",
        transport=AttachmentTransport.INLINE,
        inline_data_b64="aGVsbG8gd29ybGQ=",
    )
    raw = info.model_dump_json()
    parsed = AttachmentInfo.model_validate_json(raw)
    assert parsed.file_id == "att-abc"
    assert parsed.transport == AttachmentTransport.INLINE
    assert parsed.inline_data_b64 == "aGVsbG8gd29ybGQ="
    assert parsed.wrapped_key is None


def test_attachment_info_object_store_round_trip() -> None:
    info = AttachmentInfo(
        file_id="att-xyz",
        name="doc.pdf",
        mime="application/pdf",
        size_bytes=2_000_000,
        plaintext_sha256="feedface",
        transport=AttachmentTransport.OBJECT_STORE,
        object_bucket="syft-att-sess-1",
        object_key="att-xyz",
        chunk_size=65536,
        wrapped_key=AttachmentWrappedKey(
            ciphertext="AAAAAA==",
            nonce="BBBBBBBBBBBBBBBBBB==",
            info="syfthub-attachment-v1",
        ),
    )
    raw = info.model_dump_json()
    parsed = AttachmentInfo.model_validate_json(raw)
    assert parsed.wrapped_key is not None
    assert parsed.wrapped_key.info == "syfthub-attachment-v1"
    assert parsed.chunk_size == 65536


def test_attachment_payload_envelopes() -> None:
    info = AttachmentInfo(
        file_id="att-1",
        name="x.bin",
        mime="application/octet-stream",
        size_bytes=10,
        plaintext_sha256="0" * 64,
        transport=AttachmentTransport.INLINE,
        inline_data_b64="AAAAAAAAAAAAAA==",
    )
    user_p = UserAttachmentPayload(attachment=info)
    agent_p = AgentAttachmentPayload(attachment=info)
    assert user_p.attachment.file_id == "att-1"
    assert agent_p.attachment.file_id == "att-1"


def test_session_start_capabilities_default_empty() -> None:
    p = SessionStartPayload(
        prompt="hi",
        endpoint={"owner": "alice", "slug": "code-assistant"},
        satellite_token="t",
    )
    assert p.capabilities == []


def test_session_start_capabilities_round_trip() -> None:
    p = SessionStartPayload(
        prompt="hi",
        endpoint={"owner": "alice", "slug": "code-assistant"},
        satellite_token="t",
        capabilities=["attachments"],
    )
    assert "attachments" in p.capabilities
    raw = p.model_dump_json()
    parsed = SessionStartPayload.model_validate_json(raw)
    assert parsed.capabilities == ["attachments"]


def test_attachment_error_payload_optional_file_id() -> None:
    err = AttachmentErrorPayload(
        code="ATTACHMENT_QUOTA_EXCEEDED",
        message="daily byte cap reached",
    )
    assert err.file_id is None
    assert err.recoverable is False


def test_size_bytes_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        AttachmentInfo(
            file_id="att",
            name="n",
            mime="m",
            size_bytes=-1,
            plaintext_sha256="x",
            transport=AttachmentTransport.INLINE,
        )
