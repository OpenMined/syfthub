"""Tests for peer token creation, validation, and revocation."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from syfthub.auth.peer_tokens import (
    PeerTokenData,
    _generate_peer_channel,
    _generate_peer_token,
    create_peer_token,
    revoke_peer_token,
    validate_peer_token,
)


class TestPeerTokenHelpers:
    """Tests for pure helper functions."""

    def test_generate_peer_channel_format(self):
        """Channel ID starts with 'peer_' and has a hex suffix."""
        channel = _generate_peer_channel()
        assert channel.startswith("peer_")
        assert len(channel) > len("peer_")

    def test_generate_peer_channel_unique(self):
        """Two calls produce different channel IDs."""
        assert _generate_peer_channel() != _generate_peer_channel()

    def test_generate_peer_token_format(self):
        """Token starts with 'pt_'."""
        token = _generate_peer_token()
        assert token.startswith("pt_")
        assert len(token) > len("pt_")

    def test_generate_peer_token_unique(self):
        """Two calls produce different tokens."""
        assert _generate_peer_token() != _generate_peer_token()


class TestCreatePeerToken:
    """Tests for create_peer_token()."""

    @pytest.mark.asyncio
    async def test_create_stores_in_redis_and_returns_data(self):
        """Stores token data in Redis and returns a populated PeerTokenData."""
        redis = AsyncMock()

        mock_settings = AsyncMock()
        mock_settings.peer_token_expire_seconds = 300
        mock_settings.nats_url = "nats://localhost:4222"
        mock_settings.nats_auth_token = "nats-secret"

        with patch("syfthub.auth.peer_tokens.get_settings", return_value=mock_settings):
            result = await create_peer_token(
                user_id=7,
                target_usernames=["alice", "bob"],
                redis=redis,
            )

        assert isinstance(result, PeerTokenData)
        assert result.token.startswith("pt_")
        assert result.peer_channel.startswith("peer_")
        assert result.user_id == 7
        assert result.target_usernames == ["alice", "bob"]
        assert result.expires_in == 300
        assert result.nats_url == "nats://localhost:4222"
        assert result.nats_auth_token == "nats-secret"
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_uses_correct_redis_key(self):
        """Redis key matches the expected 'nats:peer:<token>' pattern."""
        redis = AsyncMock()

        mock_settings = AsyncMock()
        mock_settings.peer_token_expire_seconds = 60
        mock_settings.nats_url = "nats://localhost:4222"
        mock_settings.nats_auth_token = "secret"

        with patch("syfthub.auth.peer_tokens.get_settings", return_value=mock_settings):
            result = await create_peer_token(
                user_id=1,
                target_usernames=["charlie"],
                redis=redis,
            )

        key_used = redis.set.call_args[0][0]
        assert key_used == f"nats:peer:{result.token}"
        assert redis.set.call_args[1]["ex"] == 60


class TestValidatePeerToken:
    """Tests for validate_peer_token()."""

    @pytest.mark.asyncio
    async def test_returns_peer_token_data_when_found(self):
        """Returns populated PeerTokenData for a valid, non-expired token."""
        redis = AsyncMock()
        token_data = {
            "user_id": 3,
            "peer_channel": "peer_abc123",
            "target_usernames": ["dave"],
            "nats_url": "nats://localhost:4222",
            "nats_auth_token": "nats-token",
        }
        redis.get.return_value = json.dumps(token_data)
        redis.ttl.return_value = 250

        result = await validate_peer_token("pt_sometoken", redis)

        assert result is not None
        assert isinstance(result, PeerTokenData)
        assert result.token == "pt_sometoken"
        assert result.user_id == 3
        assert result.peer_channel == "peer_abc123"
        assert result.target_usernames == ["dave"]
        assert result.expires_in == 250

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Returns None when token doesn't exist in Redis."""
        redis = AsyncMock()
        redis.get.return_value = None

        result = await validate_peer_token("pt_expired", redis)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_ttl_expired(self):
        """Returns None when TTL is negative (key about to expire)."""
        redis = AsyncMock()
        token_data = {
            "user_id": 1,
            "peer_channel": "peer_xyz",
            "target_usernames": [],
            "nats_url": "nats://localhost:4222",
            "nats_auth_token": "tok",
        }
        redis.get.return_value = json.dumps(token_data)
        redis.ttl.return_value = -1

        result = await validate_peer_token("pt_expiring", redis)

        assert result is None


class TestRevokePeerToken:
    """Tests for revoke_peer_token()."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self):
        """Returns True when Redis deletes the key (existed)."""
        redis = AsyncMock()
        redis.delete.return_value = 1

        result = await revoke_peer_token("pt_valid", redis)

        assert result is True
        redis.delete.assert_called_once_with("nats:peer:pt_valid")

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        """Returns False when Redis finds nothing to delete."""
        redis = AsyncMock()
        redis.delete.return_value = 0

        result = await revoke_peer_token("pt_missing", redis)

        assert result is False
