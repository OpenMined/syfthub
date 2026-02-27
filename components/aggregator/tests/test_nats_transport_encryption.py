"""Tests for encrypted NATS transport (aggregator side).

These tests focus on the encryption-related behavior of NATSTransport:
- _build_tunnel_request always produces encrypted messages
- _get_space_public_key fetches and caches keys
- Missing key raises NATSTransportError with ENCRYPTION_KEY_MISSING code
- Decryption failures evict the key cache
- decrypt_tunnel_response is called correctly on valid responses
"""

from __future__ import annotations

import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aggregator import crypto
from aggregator.clients.nats_transport import NATSTransport, NATSTransportError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_space_keypair_b64() -> tuple[object, str]:
    """Return (space_priv, space_pub_b64) for testing."""
    priv, pub_bytes = crypto.generate_keypair()
    pub_b64 = crypto._b64url_encode(pub_bytes)
    return priv, pub_b64


# ---------------------------------------------------------------------------
# _build_tunnel_request — always encrypted
# ---------------------------------------------------------------------------


def test_build_tunnel_request_includes_encryption_info():
    """_build_tunnel_request must always set encryption_info and encrypted_payload."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    _, space_pub_b64 = make_space_keypair_b64()
    peer_channel = str(uuid.uuid4())

    _, message, _ = transport._build_tunnel_request(
        slug="my-endpoint",
        endpoint_type="data_source",
        payload={"messages": "test query", "limit": 5},
        peer_channel=peer_channel,
        space_public_key=space_pub_b64,
    )

    assert "encryption_info" in message
    assert "encrypted_payload" in message
    enc_info = message["encryption_info"]
    assert enc_info["algorithm"] == "X25519-ECDH-AES-256-GCM"
    assert enc_info["ephemeral_public_key"]
    assert enc_info["nonce"]
    assert message["encrypted_payload"]


def test_build_tunnel_request_payload_is_not_plaintext():
    """The message payload field should be None; plaintext is in encrypted_payload."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    _, space_pub_b64 = make_space_keypair_b64()
    peer_channel = str(uuid.uuid4())

    _corr_id, message, _priv = transport._build_tunnel_request(
        slug="ep",
        endpoint_type="model",
        payload={"messages": [{"role": "user", "content": "hello"}]},
        peer_channel=peer_channel,
        space_public_key=space_pub_b64,
    )

    # The plaintext payload must not appear in the message
    assert message.get("payload") is None


def test_build_tunnel_request_encrypted_payload_decryptable():
    """The encrypted_payload in the message can be decrypted by the space."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    space_priv, space_pub_b64 = make_space_keypair_b64()
    peer_channel = str(uuid.uuid4())
    original_payload = {"messages": "find docs", "limit": 10}

    correlation_id, message, _ = transport._build_tunnel_request(
        slug="ep",
        endpoint_type="data_source",
        payload=original_payload,
        peer_channel=peer_channel,
        space_public_key=space_pub_b64,
    )

    enc_info = message["encryption_info"]
    ephemeral_pub_bytes = crypto._b64url_decode(enc_info["ephemeral_public_key"])
    nonce = crypto._b64url_decode(enc_info["nonce"])
    ciphertext = crypto._b64url_decode(message["encrypted_payload"])

    aes_key = crypto.derive_key(space_priv, ephemeral_pub_bytes, crypto.HKDF_REQUEST_INFO)
    plaintext = crypto.decrypt_payload(ciphertext, aes_key, nonce, correlation_id.encode())

    assert json.loads(plaintext.decode()) == original_payload


def test_build_tunnel_request_different_ciphertext_per_call():
    """Two calls with the same payload produce different ciphertexts (ephemeral key)."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    _, space_pub_b64 = make_space_keypair_b64()
    payload = {"messages": "same"}

    _, msg1, _ = transport._build_tunnel_request("ep", "model", payload, "ch", space_pub_b64)
    _, msg2, _ = transport._build_tunnel_request("ep", "model", payload, "ch", space_pub_b64)

    assert msg1["encrypted_payload"] != msg2["encrypted_payload"]
    assert (
        msg1["encryption_info"]["ephemeral_public_key"]
        != msg2["encryption_info"]["ephemeral_public_key"]
    )


# ---------------------------------------------------------------------------
# _get_space_public_key — fetching and caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_space_public_key_caches_result():
    """Second call within TTL does not make an HTTP request."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    _, space_pub_b64 = make_space_keypair_b64()
    username = "alice"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"encryption_public_key": space_pub_b64}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        key1 = await transport._get_space_public_key(username)
        key2 = await transport._get_space_public_key(username)

    assert key1 == space_pub_b64
    assert key2 == space_pub_b64
    # Only one HTTP request should have been made (second call used cache)
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_space_public_key_missing_raises():
    """If the space has not registered a key (null response), raise ENCRYPTION_KEY_MISSING."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"encryption_public_key": None}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        with pytest.raises(NATSTransportError) as exc_info:
            await transport._get_space_public_key("bob")

    assert exc_info.value.code == "ENCRYPTION_KEY_MISSING"


@pytest.mark.asyncio
async def test_get_space_public_key_not_found_raises():
    """404 from backend raises ENCRYPTION_KEY_MISSING."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        with pytest.raises(NATSTransportError) as exc_info:
            await transport._get_space_public_key("charlie")

    assert exc_info.value.code == "ENCRYPTION_KEY_MISSING"


# ---------------------------------------------------------------------------
# _evict_key_cache
# ---------------------------------------------------------------------------


def test_evict_key_cache_removes_entry():
    """_evict_key_cache removes the key from the cache."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    username = "dave"
    transport._key_cache[username] = ("some-key-b64", time.monotonic())
    assert username in transport._key_cache

    transport._evict_key_cache(username)
    assert username not in transport._key_cache


def test_evict_key_cache_noop_for_unknown_user():
    """_evict_key_cache on an unknown user does not raise."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )
    transport._evict_key_cache("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# Encrypted response decryption in _send_and_receive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_and_receive_decrypts_response():
    """_send_and_receive calls decrypt_tunnel_response and returns plaintext payload."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    space_priv, space_pub_b64 = make_space_keypair_b64()
    username = "eve"
    slug = "my-model"
    peer_channel = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    # Pre-populate key cache to avoid HTTP call
    transport._key_cache[username] = (space_pub_b64, time.monotonic())

    # Build a realistic encrypted request to get the ephemeral private key
    request_payload = {"messages": [{"role": "user", "content": "hello"}]}
    enc_info, ephemeral_priv = crypto.encrypt_tunnel_request(
        payload_json=json.dumps(request_payload),
        space_public_key_b64=space_pub_b64,
        correlation_id=correlation_id,
    )

    # Simulate the Go space encrypting a response
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    response_payload = {"summary": {"message": {"content": "Hello!"}}}
    resp_ephemeral_priv, resp_ephemeral_pub_bytes = crypto.generate_keypair()
    request_ephemeral_pub_bytes = ephemeral_priv.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )
    aes_key = crypto.derive_key(
        resp_ephemeral_priv, request_ephemeral_pub_bytes, crypto.HKDF_RESPONSE_INFO
    )
    nonce, ciphertext = crypto.encrypt_payload(
        json.dumps(response_payload).encode(), aes_key, correlation_id.encode()
    )
    resp_enc_info = {
        "algorithm": "X25519-ECDH-AES-256-GCM",
        "ephemeral_public_key": crypto._b64url_encode(resp_ephemeral_pub_bytes),
        "nonce": crypto._b64url_encode(nonce),
    }
    resp_encrypted_payload_b64 = crypto._b64url_encode(ciphertext)

    raw_response = {
        "protocol": "syfthub-tunnel/v1",
        "type": "endpoint_response",
        "correlation_id": correlation_id,
        "status": "success",
        "endpoint_slug": slug,
        "encryption_info": resp_enc_info,
        "encrypted_payload": resp_encrypted_payload_b64,
    }

    # Patch _build_tunnel_request to return our controlled correlation_id + ephemeral_priv
    def fake_build(slug, endpoint_type, peer_channel, **_kw):
        msg = {
            "protocol": "syfthub-tunnel/v1",
            "type": "endpoint_request",
            "correlation_id": correlation_id,
            "reply_to": peer_channel,
            "endpoint": {"slug": slug, "type": endpoint_type},
            "payload": None,
            "encryption_info": {
                "algorithm": enc_info["algorithm"],
                "ephemeral_public_key": enc_info["ephemeral_public_key"],
                "nonce": enc_info["nonce"],
            },
            "encrypted_payload": enc_info["encrypted_payload"],
        }
        return correlation_id, msg, ephemeral_priv

    transport._build_tunnel_request = fake_build

    # Mock NATS connection so message is immediately "received"
    async def fake_ensure_connected():
        nc = MagicMock()
        nc.is_connected = True

        async def fake_subscribe(_subject, cb=None):
            # Immediately deliver the raw_response to the callback
            msg = MagicMock()
            msg.data = json.dumps(raw_response).encode()
            assert cb is not None
            await cb(msg)
            sub = MagicMock()
            sub.unsubscribe = AsyncMock()
            return sub

        nc.subscribe = fake_subscribe
        nc.publish = AsyncMock()
        nc.flush = AsyncMock()
        return nc

    transport._ensure_connected = fake_ensure_connected

    result = await transport._send_and_receive(
        target_username=username,
        peer_channel=peer_channel,
        slug=slug,
        endpoint_type="model",
        payload=request_payload,
    )

    assert result["status"] == "success"
    assert result["payload"] == response_payload


@pytest.mark.asyncio
async def test_send_and_receive_raises_on_missing_encrypted_payload():
    """If response lacks encrypted_payload, raise NATSTransportError(DECRYPTION_FAILED)."""
    transport = NATSTransport(
        nats_url="nats://localhost:4222",
        nats_auth_token="tok",
        backend_url="http://localhost:8000",
    )

    _, space_pub_b64 = make_space_keypair_b64()
    username = "frank"
    peer_channel = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    transport._key_cache[username] = (space_pub_b64, time.monotonic())

    _, ephemeral_priv = crypto.encrypt_tunnel_request(
        payload_json='{"messages":"q"}',
        space_public_key_b64=space_pub_b64,
        correlation_id=correlation_id,
    )

    def fake_build(**_kw):
        return correlation_id, {}, ephemeral_priv

    transport._build_tunnel_request = fake_build

    # Response missing encrypted_payload (old SDK / bug)
    raw_response = {
        "protocol": "syfthub-tunnel/v1",
        "correlation_id": correlation_id,
        "status": "success",
        # No encryption_info, no encrypted_payload
    }

    async def fake_ensure_connected():
        nc = MagicMock()
        nc.is_connected = True

        async def fake_subscribe(_subject, cb=None):
            msg = MagicMock()
            msg.data = json.dumps(raw_response).encode()
            assert cb is not None
            await cb(msg)
            sub = MagicMock()
            sub.unsubscribe = AsyncMock()
            return sub

        nc.subscribe = fake_subscribe
        nc.publish = AsyncMock()
        nc.flush = AsyncMock()
        return nc

    transport._ensure_connected = fake_ensure_connected

    with pytest.raises(NATSTransportError) as exc_info:
        await transport._send_and_receive(
            target_username=username,
            peer_channel=peer_channel,
            slug="ep",
            endpoint_type="model",
            payload={"messages": [{"role": "user", "content": "q"}]},
        )

    assert exc_info.value.code == "DECRYPTION_FAILED"
