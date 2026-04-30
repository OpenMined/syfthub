"""Tests for Redis client utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import syfthub.core.redis_client as redis_module


@pytest.fixture(autouse=True)
def reset_redis_singleton():
    """Reset module-level Redis singleton between tests."""
    redis_module._redis_client = None
    yield
    redis_module._redis_client = None


class TestGetRedisClient:
    @pytest.mark.asyncio
    async def test_creates_client_when_none(self):
        mock_client = MagicMock()
        with patch("syfthub.core.redis_client.Redis") as mock_redis_cls:
            mock_redis_cls.from_url.return_value = mock_client
            with patch("syfthub.core.redis_client.get_settings") as mock_get_settings:
                mock_settings = MagicMock()
                mock_settings.redis_url = "redis://localhost:6379"
                mock_get_settings.return_value = mock_settings

                result = await redis_module.get_redis_client()

                assert result is mock_client
                mock_redis_cls.from_url.assert_called_once_with(
                    "redis://localhost:6379",
                    decode_responses=True,
                )

    @pytest.mark.asyncio
    async def test_returns_cached_client(self):
        mock_client = MagicMock()
        redis_module._redis_client = mock_client

        with patch("syfthub.core.redis_client.Redis") as mock_redis_cls:
            result = await redis_module.get_redis_client()
            assert result is mock_client
            mock_redis_cls.from_url.assert_not_called()


class TestCloseRedisClient:
    @pytest.mark.asyncio
    async def test_closes_and_clears_client(self):
        mock_client = AsyncMock()
        redis_module._redis_client = mock_client

        await redis_module.close_redis_client()

        mock_client.close.assert_called_once()
        assert redis_module._redis_client is None

    @pytest.mark.asyncio
    async def test_noop_when_client_is_none(self):
        redis_module._redis_client = None
        await redis_module.close_redis_client()
        assert redis_module._redis_client is None


class TestCheckRedisHealth:
    @pytest.mark.asyncio
    async def test_returns_true_when_ping_succeeds(self):
        mock_client = AsyncMock()
        mock_client.ping.return_value = True

        with patch(
            "syfthub.core.redis_client.get_redis_client",
            new=AsyncMock(return_value=mock_client),
        ):
            result = await redis_module.check_redis_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_ping_raises(self):
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("connection refused")

        with patch(
            "syfthub.core.redis_client.get_redis_client",
            new=AsyncMock(return_value=mock_client),
        ):
            result = await redis_module.check_redis_health()
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_get_client_raises(self):
        async def raise_error():
            raise Exception("cannot connect")

        with patch("syfthub.core.redis_client.get_redis_client", new=raise_error):
            result = await redis_module.check_redis_health()
            assert result is False
