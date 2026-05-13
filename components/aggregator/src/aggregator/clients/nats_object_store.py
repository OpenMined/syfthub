"""NATS JetStream Object Store client for attachment ciphertext.

Each agent session that opts into attachments gets its own Object Store
bucket named `syft-att-{session_id}`. The aggregator pushes ciphertext
blobs (created via aggregator.attachment_crypto.AttachmentEncryptor.encrypt_stream)
into the bucket on upload, and pulls them out again on download.

See docs/architecture/attachments.md for the wire-level contract that
both HOST and aggregator must agree on.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import IO

from aggregator.api.endpoints.agent import get_nats_transport

logger = logging.getLogger(__name__)

ATTACHMENT_BUCKET_PREFIX = "syft-att-"
DEFAULT_BUCKET_TTL_SECONDS = 3600  # 1h — matches Go DefaultAttachmentBucketTTL


def bucket_name_for_session(session_id: str) -> str:
    return f"{ATTACHMENT_BUCKET_PREFIX}{session_id}"


class AttachmentObjectStoreClient:
    """Async wrapper over nats-py's Object Store API.

    Buckets are lazily created on first `put`. Concurrent calls share an
    asyncio.Lock to serialize bucket binding.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._stores: dict = {}  # bucket -> ObjectStore

    async def _get_or_create(self, bucket: str):
        async with self._lock:
            if bucket in self._stores:
                return self._stores[bucket]
            nc = await get_nats_transport()._ensure_connected()
            js = nc.jetstream()
            try:
                obj = await js.object_store(bucket)
            except Exception:
                obj = await js.create_object_store(
                    bucket,
                    description="SyftHub attachment ciphertext (per-session)",
                    ttl=DEFAULT_BUCKET_TTL_SECONDS,
                )
            self._stores[bucket] = obj
            return obj

    async def put(self, bucket: str, key: str, data: bytes) -> None:
        store = await self._get_or_create(bucket)
        await store.put(key, data)

    async def get(self, bucket: str, key: str) -> bytes:
        store = await self._get_or_create(bucket)
        result = await store.get(key)
        # nats-py's ObjectInfo carries the bytes on .data; some versions
        # also support a streaming interface. Handle both.
        if hasattr(result, "data"):
            return bytes(result.data)
        if hasattr(result, "read"):
            return await _read_async_stream(result)
        return bytes(result)

    async def delete_bucket(self, bucket: str) -> None:
        async with self._lock:
            self._stores.pop(bucket, None)
        nc = await get_nats_transport()._ensure_connected()
        js = nc.jetstream()
        try:
            await js.delete_object_store(bucket)
        except Exception:  # pragma: no cover
            logger.debug("delete_object_store %s failed", bucket, exc_info=True)


async def _read_async_stream(stream) -> bytes:
    buf = io.BytesIO()
    while True:
        chunk = await stream.read(64 * 1024)
        if not chunk:
            break
        buf.write(chunk)
    return buf.getvalue()


_singleton: AttachmentObjectStoreClient | None = None


async def get_attachment_object_store() -> AttachmentObjectStoreClient:
    global _singleton
    if _singleton is None:
        _singleton = AttachmentObjectStoreClient()
    return _singleton


def reset_for_tests() -> None:
    """Clear the process-wide Object Store singleton. Tests only."""
    global _singleton
    _singleton = None


# In-memory fallback so unit tests can substitute the singleton without
# spinning up a real NATS server.
class _InMemoryStub:
    def __init__(self) -> None:
        self._blobs: dict[tuple[str, str], bytes] = {}

    async def put(self, bucket: str, key: str, data: bytes) -> None:
        self._blobs[(bucket, key)] = data

    async def get(self, bucket: str, key: str) -> bytes:
        if (bucket, key) not in self._blobs:
            raise KeyError(f"{bucket}/{key}")
        return self._blobs[(bucket, key)]

    async def delete_bucket(self, bucket: str) -> None:
        for k in list(self._blobs.keys()):
            if k[0] == bucket:
                self._blobs.pop(k, None)


def use_in_memory_stub_for_tests() -> _InMemoryStub:
    """Replace the singleton with an in-memory stub. Tests only."""
    global _singleton
    stub = _InMemoryStub()
    _singleton = stub  # type: ignore[assignment]
    return stub


# Suppress unused-import on IO when only used in type hints.
_ = IO[bytes]
