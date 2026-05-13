"""HTTP relay endpoints for the attachments protocol.

CLIENT uploads/downloads attachments via these endpoints (one round trip per
file). The aggregator handles ciphertext encryption (uploads) and decryption
(downloads) using the session-attachment-key shared with the HOST. JetStream
Object Store holds ciphertext blobs scoped per session.

See docs/architecture/attachments.md.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from aggregator.attachment_crypto import (
    AttachmentEncryptor,
    generate_base_nonce,
    generate_file_key,
)
from aggregator.services.attachment_session_state import (
    MAX_ATTACHMENT_BYTES_PER_FILE,
    registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-attachments"])


# In-process map: (session_id, file_id) → AttachmentRecord. PR-6 uses an
# in-memory map; PR-7 persists ciphertext to JetStream Object Store and this
# map only tracks the metadata needed to decrypt on download.
class _InMemoryAttachmentStore:
    def __init__(self) -> None:
        self._blobs: dict[tuple[str, str], bytes] = {}
        self._meta: dict[tuple[str, str], dict[str, Any]] = {}

    def put(self, session_id: str, file_id: str, ciphertext: bytes, meta: dict[str, Any]) -> None:
        self._blobs[(session_id, file_id)] = ciphertext
        self._meta[(session_id, file_id)] = meta

    def get(self, session_id: str, file_id: str) -> tuple[bytes, dict[str, Any]] | None:
        key = (session_id, file_id)
        if key not in self._blobs:
            return None
        return self._blobs[key], self._meta[key]

    def delete_session(self, session_id: str) -> None:
        for key in list(self._blobs.keys()):
            if key[0] == session_id:
                self._blobs.pop(key, None)
                self._meta.pop(key, None)


_store = _InMemoryAttachmentStore()


@router.post("/agent/session/{session_id}/attachment", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    session_id: str,
    request: Request,
    file: UploadFile,
) -> dict[str, Any]:
    """Upload an attachment to the session. Returns the assigned file_id +
    metadata that the CLIENT can echo in subsequent text.

    Bytes are encrypted with a fresh per-file AES key wrapped under the
    session-attachment-key before being stored. The corresponding
    user.attachment metadata event is published to the HOST over NATS.
    """
    sess = registry().get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Read body fully — PR-6 uses an in-memory buffer; PR-7 will stream into
    # JetStream Object Store via piped chunks.
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

    # Stash for the HOST-side download phase (HOST won't download itself in
    # PR-6 because the HOST is the consumer, not the producer; this matters
    # for the reverse direction below).
    _store.put(
        session_id,
        file_id,
        ct_buf.getvalue(),
        {
            "file_id": file_id,
            "name": file.filename or "attachment.bin",
            "mime": file.content_type or "application/octet-stream",
            "size_bytes": size,
            "plaintext_sha256": plaintext_sha,
            "base_nonce_b64": base64.b64encode(base_nonce).decode(),
            "file_key_b64": base64.b64encode(file_key).decode(),
        },
    )

    # Publish the user.attachment metadata event over the encrypted tunnel.
    transport = sess.transport
    if transport is None:
        raise HTTPException(status_code=500, detail="session transport missing")

    attachment_info = {
        "file_id": file_id,
        "name": file.filename or "attachment.bin",
        "mime": file.content_type or "application/octet-stream",
        "size_bytes": size,
        "plaintext_sha256": plaintext_sha,
        "transport": "object_store",
        "object_bucket": f"syft-att-{session_id}",
        "object_key": file_id,
        "chunk_size": 64 * 1024,
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
        "name": attachment_info["name"],
        "mime": attachment_info["mime"],
        "size_bytes": size,
        "plaintext_sha256": plaintext_sha,
        "transport": "object_store",
    }


@router.get("/agent/session/{session_id}/attachment/{file_id}")
async def download_attachment(session_id: str, file_id: str) -> StreamingResponse:
    """Download a previously-stored attachment.

    PR-6: serves agent-emitted attachments that the aggregator decrypted from
    the encrypted event stream. PR-7 will replace the in-memory _store with a
    JetStream Object Store fetch + chunked stream.
    """
    sess = registry().get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")

    got = _store.get(session_id, file_id)
    if got is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    ciphertext, meta = got

    enc = AttachmentEncryptor(sess.session_attachment_key)
    base_nonce = base64.b64decode(meta["base_nonce_b64"])
    file_key = base64.b64decode(meta["file_key_b64"])
    pt_buf = io.BytesIO()
    enc.decrypt_stream(
        file_key,
        base_nonce,
        file_id,
        meta["size_bytes"],
        io.BytesIO(ciphertext),
        pt_buf,
    )

    pt_buf.seek(0)
    headers = {
        "Content-Length": str(meta["size_bytes"]),
        "X-Attachment-Sha256": meta["plaintext_sha256"],
    }
    if meta.get("name"):
        headers["Content-Disposition"] = f'attachment; filename="{meta["name"]}"'
    return StreamingResponse(
        pt_buf,
        media_type=meta.get("mime", "application/octet-stream"),
        headers=headers,
    )


def reset_for_tests() -> None:
    """Clear the in-memory blob store. Tests only."""
    global _store
    _store = _InMemoryAttachmentStore()


def stash_outbound_attachment(
    session_id: str,
    info: dict[str, Any],
    plaintext: bytes,
    file_key: bytes,
    base_nonce: bytes,
) -> None:
    """Store an aggregator-decrypted plaintext blob for HTTP-side serving.

    Called by the session relay when an agent.attachment event arrives over
    the encrypted tunnel — the aggregator decrypts the ciphertext from
    Object Store, runs the SHA-256 check, and stashes the plaintext here so
    the CLIENT can fetch it via GET /agent/session/{sid}/attachment/{fid}.
    """
    file_id = info["file_id"]
    meta = {
        "file_id": file_id,
        "name": info.get("name", "attachment.bin"),
        "mime": info.get("mime", "application/octet-stream"),
        "size_bytes": info["size_bytes"],
        "plaintext_sha256": info["plaintext_sha256"],
        "base_nonce_b64": base64.b64encode(base_nonce).decode(),
        "file_key_b64": base64.b64encode(file_key).decode(),
    }
    enc = AttachmentEncryptor(secrets.token_bytes(32))  # local re-encrypt
    ct = io.BytesIO()
    enc.encrypt_stream(
        secrets.token_bytes(32), generate_base_nonce(), file_id, io.BytesIO(plaintext), ct
    )
    _store.put(session_id, file_id, ct.getvalue(), meta)
