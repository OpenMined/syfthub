"""HTTP relay endpoints for the attachments protocol.

CLIENT uploads/downloads attachments via these endpoints (one round trip per
file). The aggregator handles ciphertext encryption (uploads) and decryption
(downloads) using the session-attachment-key shared with the HOST.

Ciphertext blobs live in NATS JetStream Object Store buckets scoped per
session (`syft-att-{session_id}`). Metadata that the aggregator needs at
download time (wrapped key, base nonce, mime, size) lives in an in-process
map keyed by (session_id, file_id) — small and TTL-bounded by session
lifetime.

See docs/architecture/attachments.md.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from aggregator.attachment_crypto import (
    AttachmentEncryptor,
    generate_base_nonce,
    generate_file_key,
)
from aggregator.clients.nats_object_store import AttachmentObjectStoreClient
from aggregator.services.attachment_session_state import (
    MAX_ATTACHMENT_BYTES_PER_FILE,
    registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-attachments"])


@dataclass
class _AttachmentMeta:
    """Per-attachment metadata the aggregator needs at download time."""

    file_id: str
    name: str
    mime: str
    size_bytes: int
    plaintext_sha256: str
    object_bucket: str
    object_key: str
    base_nonce_b64: str
    # wrapped_key bytes are stored here so we don't need to re-publish them
    # on the metadata channel just to satisfy the aggregator-side decrypt.
    wrapped_key_ciphertext: bytes
    wrapped_key_nonce: bytes


class _MetadataStore:
    """In-process map from (session_id, file_id) → metadata."""

    def __init__(self) -> None:
        self._meta: dict[tuple[str, str], _AttachmentMeta] = {}
        self._lock = asyncio.Lock()

    async def put(self, session_id: str, meta: _AttachmentMeta) -> None:
        async with self._lock:
            self._meta[(session_id, meta.file_id)] = meta

    async def get(self, session_id: str, file_id: str) -> _AttachmentMeta | None:
        async with self._lock:
            return self._meta.get((session_id, file_id))

    async def delete_session(self, session_id: str) -> None:
        async with self._lock:
            for key in list(self._meta.keys()):
                if key[0] == session_id:
                    self._meta.pop(key, None)


_metadata = _MetadataStore()


# ObjectStore wiring: lazily initialized JetStream Object Store-backed client
# shared across the relay endpoints. The shared NATSTransport singleton lives
# in aggregator.api.endpoints.agent; we import it indirectly to avoid a hard
# import cycle.
async def _get_object_store() -> AttachmentObjectStoreClient:
    from aggregator.clients.nats_object_store import get_attachment_object_store

    return await get_attachment_object_store()


def bucket_for_session(session_id: str) -> str:
    return f"syft-att-{session_id}"


@router.post("/agent/session/{session_id}/attachment", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    session_id: str,
    file: UploadFile,
) -> dict[str, Any]:
    """Upload an attachment to the session.

    Bytes are encrypted with a fresh per-file AES key, the ciphertext is
    pushed to the session's JetStream Object Store bucket, K is envelope-
    wrapped under the session-attachment-key, and a user.attachment metadata
    event is published to the HOST over NATS.
    """
    sess = registry().get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")

    body = await file.read()
    size = len(body)
    if size == 0:
        raise HTTPException(status_code=400, detail="empty file")
    if size > MAX_ATTACHMENT_BYTES_PER_FILE:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "ATTACHMENT_QUOTA_EXCEEDED",
                "limit_bytes": MAX_ATTACHMENT_BYTES_PER_FILE,
                "actual_bytes": size,
            },
        )

    if not registry().consume_quota(session_id, size):
        raise HTTPException(
            status_code=429,
            detail={"code": "ATTACHMENT_QUOTA_EXCEEDED", "scope": "session"},
        )

    file_id = "att-" + uuid.uuid4().hex
    file_key = generate_file_key()
    base_nonce = generate_base_nonce()
    plaintext_sha = hashlib.sha256(body).hexdigest()

    enc = AttachmentEncryptor(sess.session_attachment_key)
    ct_buf = io.BytesIO()
    enc.encrypt_stream(file_key, base_nonce, file_id, io.BytesIO(body), ct_buf)
    wrapped_ct, wrapped_nonce = enc.wrap_file_key(file_id, file_key)

    bucket = bucket_for_session(session_id)
    object_store = await _get_object_store()
    await object_store.put(bucket, file_id, ct_buf.getvalue())

    name = file.filename or "attachment.bin"
    mime = file.content_type or "application/octet-stream"
    base_nonce_b64 = base64.b64encode(base_nonce).decode()

    await _metadata.put(
        session_id,
        _AttachmentMeta(
            file_id=file_id,
            name=name,
            mime=mime,
            size_bytes=size,
            plaintext_sha256=plaintext_sha,
            object_bucket=bucket,
            object_key=file_id,
            base_nonce_b64=base_nonce_b64,
            wrapped_key_ciphertext=wrapped_ct,
            wrapped_key_nonce=wrapped_nonce,
        ),
    )

    transport = sess.transport
    if transport is None:
        raise HTTPException(status_code=500, detail="session transport missing")

    attachment_info = {
        "file_id": file_id,
        "name": name,
        "mime": mime,
        "size_bytes": size,
        "plaintext_sha256": plaintext_sha,
        "transport": "object_store",
        "object_bucket": bucket,
        "object_key": file_id,
        "chunk_size": 64 * 1024,
        "base_nonce": base_nonce_b64,
        "wrapped_key": {
            "algorithm": "AES-256-GCM",
            "ciphertext": base64.b64encode(wrapped_ct).decode(),
            "nonce": base64.b64encode(wrapped_nonce).decode(),
            "info": "syfthub-attachment-v1",
        },
    }
    await transport.send_to_space(
        {
            "type": "user.attachment",
            "payload": attachment_info,
        }
    )

    return {
        "file_id": file_id,
        "name": name,
        "mime": mime,
        "size_bytes": size,
        "plaintext_sha256": plaintext_sha,
        "transport": "object_store",
    }


@router.get("/agent/session/{session_id}/attachment/{file_id}")
async def download_attachment(session_id: str, file_id: str) -> StreamingResponse:
    """Download a previously-stored attachment.

    Pulls ciphertext from JetStream Object Store, unwraps K under the
    session-attachment-key, decrypts the chunked stream, streams plaintext.
    """
    sess = registry().get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")

    meta = await _metadata.get(session_id, file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="attachment not found")

    object_store = await _get_object_store()
    try:
        ciphertext = await object_store.get(meta.object_bucket, meta.object_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="object-store object missing")

    enc = AttachmentEncryptor(sess.session_attachment_key)
    file_key = enc.unwrap_file_key(file_id, meta.wrapped_key_ciphertext, meta.wrapped_key_nonce)
    base_nonce = base64.b64decode(meta.base_nonce_b64)

    pt_buf = io.BytesIO()
    enc.decrypt_stream(
        file_key,
        base_nonce,
        file_id,
        meta.size_bytes,
        io.BytesIO(ciphertext),
        pt_buf,
    )
    pt_buf.seek(0)
    headers = {
        "Content-Length": str(meta.size_bytes),
        "X-Attachment-Sha256": meta.plaintext_sha256,
    }
    if meta.name:
        headers["Content-Disposition"] = f'attachment; filename="{meta.name}"'
    return StreamingResponse(
        pt_buf,
        media_type=meta.mime,
        headers=headers,
    )


async def record_agent_attachment_metadata(session_id: str, info: dict[str, Any]) -> None:
    """Stash HOST-emitted agent.attachment metadata for later download.

    Called by the session relay (relay_space_to_frontend) when the HOST
    publishes an agent.attachment event with transport=object_store. The
    CLIENT will subsequently issue GET /agent/session/{sid}/attachment/{fid}
    against the aggregator, which uses this stashed metadata to locate the
    ciphertext in Object Store + unwrap the file key.
    """
    if info.get("transport") != "object_store":
        return
    wrapped_key = info.get("wrapped_key") or {}
    try:
        meta = _AttachmentMeta(
            file_id=info["file_id"],
            name=info.get("name", "attachment.bin"),
            mime=info.get("mime", "application/octet-stream"),
            size_bytes=int(info["size_bytes"]),
            plaintext_sha256=info["plaintext_sha256"],
            object_bucket=info["object_bucket"],
            object_key=info["object_key"],
            base_nonce_b64=info["base_nonce"],
            wrapped_key_ciphertext=base64.b64decode(wrapped_key["ciphertext"]),
            wrapped_key_nonce=base64.b64decode(wrapped_key["nonce"]),
        )
    except KeyError as e:
        logger.warning("agent.attachment missing field: %s", e)
        return
    await _metadata.put(session_id, meta)


async def cleanup_session(session_id: str) -> None:
    """Delete attachment metadata + the Object Store bucket for a session.

    Called when the WS session ends. Idempotent; safe to call for sessions
    that never staged any attachments.
    """
    await _metadata.delete_session(session_id)
    try:
        object_store = await _get_object_store()
        await object_store.delete_bucket(bucket_for_session(session_id))
    except Exception:  # pragma: no cover
        logger.debug("cleanup bucket %s failed", session_id, exc_info=True)


def reset_for_tests() -> None:
    """Clear the in-memory metadata map. Tests only."""
    global _metadata
    _metadata = _MetadataStore()
