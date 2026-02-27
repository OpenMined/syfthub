"""NATS transport for communicating with tunneling SyftAI Spaces.

When a SyftAI Space registers with a `tunneling:<username>` domain,
it connects to the platform via NATS pub/sub instead of HTTP. This
transport sends requests to those spaces and collects responses.

Subject namespace:
- `syfthub.spaces.{username}` — space listens here for incoming requests
- `syfthub.peer.{peer_channel}` — aggregator subscribes here for replies

Message format: syfthub-tunnel/v1 protocol with mandatory E2E encryption.
All payloads are encrypted using X25519 ECDH + AES-256-GCM (see aggregator/crypto.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx
import nats
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from nats.aio.client import Client as NATSClient

from aggregator import crypto
from aggregator.core.config import get_settings
from aggregator.schemas.internal import GenerationResult, RetrievalResult
from aggregator.schemas.responses import Document

logger = logging.getLogger(__name__)

TUNNEL_PROTOCOL_VERSION = "syfthub-tunnel/v1"
TUNNELING_PREFIX = "tunneling:"

# Key cache TTL in seconds — refresh the cached public key after this interval
_KEY_CACHE_TTL = 300.0


def is_tunneling_url(url: str) -> bool:
    """Check if a URL is a tunneling URL."""
    return url.startswith(TUNNELING_PREFIX)


def extract_tunnel_username(url: str) -> str:
    """Extract the username from a tunneling URL."""
    return url[len(TUNNELING_PREFIX) :]


class NATSTransportError(Exception):
    """Error during NATS transport communication."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class NATSTransport:
    """Transport for sending requests to tunneling spaces via NATS.

    This client connects to NATS and implements the syfthub-tunnel/v1
    protocol with mandatory E2E encryption for all request/response payloads.
    """

    def __init__(
        self,
        nats_url: str | None = None,
        nats_auth_token: str | None = None,
        backend_url: str | None = None,
        default_timeout: float = 30.0,
    ):
        settings = get_settings()
        self._nats_url = nats_url or settings.nats_url
        self._nats_auth_token = nats_auth_token or settings.nats_auth_token
        self._backend_url = (backend_url or settings.syfthub_url).rstrip("/")
        self._default_timeout = default_timeout
        self._nc: NATSClient | None = None
        self._lock = asyncio.Lock()
        # Key cache: username -> (public_key_b64, fetched_at_timestamp)
        self._key_cache: dict[str, tuple[str, float]] = {}

    async def _ensure_connected(self) -> NATSClient:
        """Ensure we have an active NATS connection."""
        if self._nc is not None and self._nc.is_connected:
            return self._nc

        async with self._lock:
            # Double-check after acquiring lock
            if self._nc is not None and self._nc.is_connected:
                return self._nc

            logger.info(f"Connecting to NATS at {self._nats_url}")
            self._nc = await nats.connect(
                self._nats_url,
                token=self._nats_auth_token,
                name="syfthub-aggregator",
            )
            return self._nc

    async def close(self) -> None:
        """Close the NATS connection."""
        if self._nc is not None and self._nc.is_connected:
            await self._nc.close()
            self._nc = None

    async def _get_space_public_key(self, username: str) -> str:
        """Fetch and cache the X25519 public key for a tunneling space.

        Calls GET {backend_url}/api/v1/nats/encryption-key/{username}.
        Result is cached for _KEY_CACHE_TTL seconds.

        Args:
            username: The tunneling space's username.

        Returns:
            Base64url-encoded X25519 public key.

        Raises:
            NATSTransportError: If the key cannot be retrieved or is not registered.
        """
        now = time.monotonic()
        cached = self._key_cache.get(username)
        if cached is not None:
            key_b64, fetched_at = cached
            if now - fetched_at < _KEY_CACHE_TTL:
                return key_b64

        url = f"{self._backend_url}/api/v1/nats/encryption-key/{username}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            raise NATSTransportError(
                f"Failed to fetch encryption key for {username}: {exc}",
                code="ENCRYPTION_KEY_FETCH_FAILED",
            ) from exc

        if resp.status_code == 404:
            raise NATSTransportError(
                f"Space '{username}' not found or has not registered an encryption key",
                code="ENCRYPTION_KEY_MISSING",
            )
        if resp.status_code != 200:
            raise NATSTransportError(
                f"Unexpected response fetching encryption key for {username}: HTTP {resp.status_code}",
                code="ENCRYPTION_KEY_FETCH_FAILED",
            )

        data = resp.json()
        raw_key = data.get("encryption_public_key")
        if not raw_key:
            raise NATSTransportError(
                f"Space '{username}' has not registered an encryption key. "
                "The space must call PUT /api/v1/nats/encryption-key on startup.",
                code="ENCRYPTION_KEY_MISSING",
            )

        key_b64 = str(raw_key)
        # Cache the key
        self._key_cache[username] = (key_b64, now)
        return key_b64

    def _evict_key_cache(self, username: str) -> None:
        """Evict a cached key (called after decryption failure to force re-fetch)."""
        self._key_cache.pop(username, None)

    def _build_tunnel_request(
        self,
        slug: str,
        endpoint_type: str,
        payload: dict[str, Any],
        peer_channel: str,
        space_public_key: str,
        timeout_ms: int = 30000,
        satellite_token: str | None = None,
    ) -> tuple[str, dict[str, Any], X25519PrivateKey]:
        """Build a syfthub-tunnel/v1 encrypted request message.

        Generates a fresh ephemeral X25519 keypair, encrypts the payload,
        and returns the request dict alongside the ephemeral private key
        (needed to decrypt the response).

        Args:
            slug: Endpoint slug.
            endpoint_type: "model" or "data_source".
            payload: Plaintext request payload dict.
            peer_channel: Reply channel identifier (no "syfthub.peer." prefix).
            space_public_key: Base64url-encoded X25519 public key of the target space.
            timeout_ms: Request timeout in milliseconds.
            satellite_token: Optional RS256 satellite token for authentication.

        Returns:
            Tuple of (correlation_id, message_dict, ephemeral_private_key).
            The caller must retain the ephemeral_private_key to decrypt the response.
        """
        correlation_id = str(uuid.uuid4())
        payload_json = json.dumps(payload)

        encryption_info, ephemeral_priv = crypto.encrypt_tunnel_request(
            payload_json=payload_json,
            space_public_key_b64=space_public_key,
            correlation_id=correlation_id,
        )

        message: dict[str, Any] = {
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_request",
            "correlation_id": correlation_id,
            "reply_to": peer_channel,
            "endpoint": {
                "slug": slug,
                "type": endpoint_type,
            },
            "payload": None,
            "timeout_ms": timeout_ms,
            "encryption_info": {
                "algorithm": encryption_info["algorithm"],
                "ephemeral_public_key": encryption_info["ephemeral_public_key"],
                "nonce": encryption_info["nonce"],
            },
            "encrypted_payload": encryption_info["encrypted_payload"],
        }
        if satellite_token:
            message["satellite_token"] = satellite_token

        return correlation_id, message, ephemeral_priv

    async def _send_and_receive(
        self,
        target_username: str,
        peer_channel: str,
        slug: str,
        endpoint_type: str,
        payload: dict[str, Any],
        timeout: float | None = None,
        satellite_token: str | None = None,
    ) -> dict[str, Any]:
        """Send an encrypted tunnel request and wait for the encrypted response.

        Fetches the target space's public key (with cache), encrypts the request,
        sends via NATS, waits for the response, and decrypts it.

        Args:
            target_username: Username of the tunneling space.
            peer_channel: Unique peer channel for receiving the reply.
            slug: Endpoint slug.
            endpoint_type: "model" or "data_source".
            payload: Plaintext request payload.
            timeout: Timeout in seconds (defaults to self._default_timeout).
            satellite_token: Optional satellite token for authenticated endpoints.

        Returns:
            The decrypted, parsed TunnelResponse dict (with plaintext payload).

        Raises:
            NATSTransportError: On timeout, connection failure, encryption error,
                or error response.
        """
        timeout = timeout or self._default_timeout
        timeout_ms = int(timeout * 1000)

        # Fetch the space's encryption public key (raises on missing key)
        space_public_key = await self._get_space_public_key(target_username)

        nc = await self._ensure_connected()

        # Build the encrypted request message; retain ephemeral_priv for response decryption
        correlation_id, request_msg, ephemeral_priv = self._build_tunnel_request(
            slug=slug,
            endpoint_type=endpoint_type,
            payload=payload,
            peer_channel=peer_channel,
            space_public_key=space_public_key,
            timeout_ms=timeout_ms,
            satellite_token=satellite_token,
        )

        # Subscribe to reply channel BEFORE publishing (prevents race condition)
        reply_subject = f"syfthub.peer.{peer_channel}"
        response_future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()

        async def message_handler(msg: Any) -> None:
            try:
                data = json.loads(msg.data.decode())
                if data.get("correlation_id") == correlation_id and not response_future.done():
                    response_future.set_result(data)
            except Exception as exc:
                if not response_future.done():
                    response_future.set_exception(exc)

        sub = await nc.subscribe(reply_subject, cb=message_handler)

        try:
            publish_subject = f"syfthub.spaces.{target_username}"
            await nc.publish(publish_subject, json.dumps(request_msg).encode())
            await nc.flush()

            logger.info(
                f"Published encrypted tunnel request to {publish_subject} "
                f"(correlation_id={correlation_id}, slug={slug})"
            )

            # Wait for response with timeout
            raw_response = await asyncio.wait_for(response_future, timeout=timeout)

        except TimeoutError:
            raise NATSTransportError(
                f"Timeout waiting for response from {target_username}/{slug} after {timeout}s",
                code="TIMEOUT",
            )
        finally:
            await sub.unsubscribe()

        # Decrypt the response payload
        enc_info = raw_response.get("encryption_info")
        encrypted_payload_b64 = raw_response.get("encrypted_payload")

        if not enc_info or not encrypted_payload_b64:
            raise NATSTransportError(
                f"Response from {target_username}/{slug} is missing encryption_info "
                "or encrypted_payload. Space may be running an old SDK version.",
                code="DECRYPTION_FAILED",
            )

        try:
            decrypted_json = crypto.decrypt_tunnel_response(
                encrypted_payload_b64=encrypted_payload_b64,
                encryption_info=enc_info,
                ephemeral_private_key=ephemeral_priv,
                correlation_id=correlation_id,
            )
        except crypto.InvalidTag as exc:
            # Evict cached key in case it was rotated; caller may retry once
            self._evict_key_cache(target_username)
            raise NATSTransportError(
                f"Response decryption failed for {target_username}/{slug}: "
                "GCM authentication tag mismatch. Possible key rotation — cached key evicted.",
                code="DECRYPTION_FAILED",
            ) from exc

        # Replace encrypted fields with decrypted payload in the response dict
        raw_response = dict(raw_response)
        raw_response["payload"] = json.loads(decrypted_json)
        return raw_response

    async def query_data_source(
        self,
        target_username: str,
        slug: str,
        endpoint_path: str,
        query: str,
        peer_channel: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        transaction_token: str | None = None,
        satellite_token: str | None = None,
        timeout: float | None = None,
    ) -> RetrievalResult:
        """Query a tunneling data source endpoint via NATS.

        Args:
            target_username: Username of the tunneling space.
            slug: Endpoint slug.
            endpoint_path: Full path for logging/citations.
            query: Search query.
            peer_channel: Peer channel for the reply.
            top_k: Number of documents to retrieve.
            similarity_threshold: Minimum similarity score.
            transaction_token: Optional billing token.
            satellite_token: Optional satellite token for authenticated endpoints.
            timeout: Timeout in seconds.

        Returns:
            RetrievalResult with documents and status.
        """
        start_time = time.perf_counter()

        payload: dict[str, Any] = {
            "messages": query,
            "limit": top_k,
            "similarity_threshold": similarity_threshold,
            "include_metadata": True,
        }
        if transaction_token:
            payload["transaction_token"] = transaction_token

        try:
            response = await self._send_and_receive(
                target_username=target_username,
                peer_channel=peer_channel,
                slug=slug,
                endpoint_type="data_source",
                payload=payload,
                timeout=timeout,
                satellite_token=satellite_token,
            )

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if response.get("status") == "error":
                error = response.get("error", {})
                error_msg = error.get("message", "Unknown tunnel error")
                logger.warning(
                    f"Tunnel data source query failed: {error_msg}",
                    extra={"endpoint_path": endpoint_path},
                )
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="error",
                    error_message=error_msg,
                    latency_ms=latency_ms,
                )

            # Parse response payload (same format as HTTP response)
            resp_payload = response.get("payload", {})
            documents = self._parse_data_source_response(resp_payload)

            logger.info(
                f"Tunnel data source query complete: {len(documents)} documents, {latency_ms}ms",
                extra={"endpoint_path": endpoint_path},
            )

            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=documents,
                status="success",
                latency_ms=latency_ms,
            )

        except NATSTransportError as exc:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning(
                f"Tunnel transport error for data source {endpoint_path}: {exc}",
            )
            status = "timeout" if exc.code == "TIMEOUT" else "error"
            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=[],
                status=status,
                error_message=str(exc),
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception(
                f"Unexpected error querying tunnel data source {endpoint_path}: {exc}",
            )
            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=[],
                status="error",
                error_message=f"Unexpected error: {exc}",
                latency_ms=latency_ms,
            )

    async def query_model(
        self,
        target_username: str,
        slug: str,
        messages: list[dict[str, str]],
        peer_channel: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        transaction_token: str | None = None,
        satellite_token: str | None = None,
        timeout: float | None = None,
    ) -> GenerationResult:
        """Query a tunneling model endpoint via NATS.

        Args:
            target_username: Username of the tunneling space.
            slug: Endpoint slug.
            messages: List of conversation messages.
            peer_channel: Peer channel for the reply.
            max_tokens: Maximum tokens to generate.
            temperature: Temperature for generation.
            transaction_token: Optional billing token.
            satellite_token: Optional satellite token for authenticated endpoints.
            timeout: Timeout in seconds.

        Returns:
            GenerationResult with response and metadata.

        Raises:
            NATSTransportError: On failure.
        """
        start_time = time.perf_counter()

        payload: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "stop_sequences": [],
        }
        if transaction_token:
            payload["transaction_token"] = transaction_token

        try:
            response = await self._send_and_receive(
                target_username=target_username,
                peer_channel=peer_channel,
                slug=slug,
                endpoint_type="model",
                payload=payload,
                timeout=timeout,
                satellite_token=satellite_token,
            )

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if response.get("status") == "error":
                error = response.get("error", {})
                error_msg = error.get("message", "Unknown tunnel error")
                raise NATSTransportError(error_msg, code=error.get("code"))

            # Parse response payload (same format as HTTP response)
            resp_payload = response.get("payload", {})
            response_text, usage = self._parse_model_response(resp_payload)

            logger.info(f"Tunnel model query complete: {latency_ms}ms")

            return GenerationResult(
                response=response_text,
                latency_ms=latency_ms,
                usage=usage,
            )

        except NATSTransportError:
            raise
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            raise NATSTransportError(f"Unexpected error: {exc}") from exc

    def _parse_data_source_response(self, data: dict[str, Any]) -> list[Document]:
        """Parse documents from tunnel response payload.

        The payload matches the SyftAI-Space QueryEndpointResponse format.
        """
        documents: list[Document] = []
        references = data.get("references")
        if not references:
            return documents

        raw_docs = references.get("documents", [])
        for doc in raw_docs:
            if isinstance(doc, dict):
                documents.append(
                    Document(
                        content=doc.get("content", ""),
                        score=float(doc.get("similarity_score", 0.0)),
                        metadata=doc.get("metadata", {}),
                    )
                )
        return documents

    def _parse_model_response(self, data: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        """Parse model response from tunnel response payload.

        Returns:
            Tuple of (response_text, usage_dict).
        """
        summary = data.get("summary")
        if not summary:
            return "", None

        message = summary.get("message", {})
        if isinstance(message, dict):
            response_text = message.get("content", "")
        elif isinstance(message, str):
            response_text = message
        else:
            response_text = ""

        usage = summary.get("usage")
        if usage:
            usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        return response_text, usage
