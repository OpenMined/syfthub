"""Unit tests for ChatResource."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
import respx

from syfthub_sdk import SyftHubClient
from syfthub_sdk.chat import (
    TUNNELING_PREFIX,
    ChatStreamEvent,
    DoneEvent,
    ErrorEvent,
    GenerationStartEvent,
    RetrievalCompleteEvent,
    RetrievalStartEvent,
    SourceCompleteEvent,
    TokenEvent,
)
from syfthub_sdk.exceptions import (
    AggregatorError,
    EndpointResolutionError,
)
from syfthub_sdk.models import (
    AuthTokens,
    ChatResponse,
    Connection,
    EndpointPublic,
    EndpointRef,
    EndpointType,
    PeerTokenResponse,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def base_url() -> str:
    """Return test base URL."""
    return "https://test.syfthub.com"


@pytest.fixture
def aggregator_url(base_url: str) -> str:
    """Return test aggregator URL."""
    return f"{base_url}/aggregator/api/v1"


@pytest.fixture
def fake_tokens() -> AuthTokens:
    """Return fake auth tokens."""
    return AuthTokens(
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
    )


@pytest.fixture
def mock_user_response() -> dict[str, Any]:
    """Return mock user response."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "is_active": True,
        "role": "user",
        "created_at": now,
    }


@pytest.fixture
def mock_endpoint_public() -> dict[str, Any]:
    """Return mock public endpoint response."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "name": "Test Model",
        "slug": "test-model",
        "type": "model",
        "owner_username": "alice",
        "description": "A test model",
        "version": "1.0.0",
        "stars_count": 10,
        "created_at": now,
        "updated_at": now,
        "connect": [
            {
                "type": "syftai",
                "enabled": True,
                "description": "SyftAI Space connection",
                "config": {
                    "url": "http://syftai:8080",
                    "tenant_name": "default",
                },
            }
        ],
    }


@pytest.fixture
def mock_chat_response() -> dict[str, Any]:
    """Return mock chat response."""
    return {
        "response": "Machine learning is a subset of AI that enables systems to learn from data.",
        "retrieval_info": [
            {
                "path": "alice/docs",
                "documents_retrieved": 3,
                "status": "success",
            }
        ],
        "metadata": {
            "retrieval_time_ms": 150,
            "generation_time_ms": 500,
            "total_time_ms": 650,
        },
    }


@pytest.fixture
def mock_satellite_token_response() -> dict[str, Any]:
    """Return mock satellite token response."""
    return {
        "target_token": "fake-satellite-token-for-alice",
        "expires_in": 3600,
    }


# =============================================================================
# ChatResource Unit Tests
# =============================================================================


class TestChatComplete:
    """Tests for ChatResource.complete()."""

    @respx.mock
    def test_complete_with_string_endpoints(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
        mock_endpoint_public: dict[str, Any],
        mock_chat_response: dict[str, Any],
        mock_satellite_token_response: dict[str, Any],
    ) -> None:
        """Test chat completion with string endpoint references."""
        # Mock satellite token endpoint (for owner "alice")
        respx.get(f"{base_url}/api/v1/token").mock(
            return_value=httpx.Response(200, json=mock_satellite_token_response)
        )

        # Mock hub browse endpoint (hub.get uses browse to find endpoints)
        model_response = {**mock_endpoint_public}
        ds_response = {**mock_endpoint_public, "slug": "docs", "type": "data_source"}
        respx.get(f"{base_url}/api/v1/endpoints/public").mock(
            return_value=httpx.Response(200, json=[model_response, ds_response])
        )

        # Mock aggregator chat endpoint
        respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(200, json=mock_chat_response)
        )

        client = SyftHubClient(base_url=base_url)
        # Set tokens to simulate authenticated state
        client._http.set_tokens(fake_tokens)

        response = client.chat.complete(
            prompt="What is machine learning?",
            model="alice/test-model",
            data_sources=["alice/docs"],
        )

        assert isinstance(response, ChatResponse)
        assert "machine learning" in response.response.lower()
        assert len(response.retrieval_info) == 1
        assert response.retrieval_info[0].path == "alice/docs"
        assert response.metadata.total_time_ms == 650

    @respx.mock
    def test_complete_with_endpoint_ref(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
        mock_chat_response: dict[str, Any],
        mock_satellite_token_response: dict[str, Any],
    ) -> None:
        """Test chat completion with EndpointRef objects.

        Note: When using EndpointRef with owner_username, satellite tokens
        are fetched. Without owner_username, no tokens are fetched.
        """
        # Mock satellite token endpoint (for owner "alice")
        respx.get(f"{base_url}/api/v1/token").mock(
            return_value=httpx.Response(200, json=mock_satellite_token_response)
        )

        respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(200, json=mock_chat_response)
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        model_ref = EndpointRef(
            url="http://syftai:8080",
            slug="test-model",
            name="Test Model",
            owner_username="alice",  # Include owner for satellite token
        )

        response = client.chat.complete(
            prompt="What is ML?",
            model=model_ref,
        )

        assert isinstance(response, ChatResponse)

    @respx.mock
    def test_complete_aggregator_error(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
    ) -> None:
        """Test handling of aggregator errors."""
        respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(
                500,
                json={"message": "Internal server error"},
            )
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        # EndpointRef without owner_username means no satellite tokens are fetched
        model_ref = EndpointRef(url="http://syftai:8080", slug="model")

        with pytest.raises(AggregatorError, match="Internal server error"):
            client.chat.complete(prompt="Hello", model=model_ref)

    @respx.mock
    def test_complete_endpoint_resolution_error(
        self,
        base_url: str,
        fake_tokens: AuthTokens,
    ) -> None:
        """Test handling of endpoint resolution errors."""
        respx.get(f"{base_url}/alice/nonexistent").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        with pytest.raises(EndpointResolutionError, match="Failed to fetch"):
            client.chat.complete(
                prompt="Hello",
                model="alice/nonexistent",
            )


class TestChatStream:
    """Tests for ChatResource.stream()."""

    @respx.mock
    def test_stream_parses_events(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
    ) -> None:
        """Test that stream() parses SSE events correctly."""
        # Create SSE response
        sse_content = (
            'event: retrieval_start\ndata: {"sources": 2}\n\n'
            'event: source_complete\ndata: {"path": "alice/docs", "status": "success", "documents": 3}\n\n'
            'event: retrieval_complete\ndata: {"total_documents": 3, "time_ms": 150}\n\n'
            "event: generation_start\ndata: {}\n\n"
            'event: token\ndata: {"content": "Hello "}\n\n'
            'event: token\ndata: {"content": "world!"}\n\n'
            'event: done\ndata: {"sources": [], "metadata": {"retrieval_time_ms": 150, "generation_time_ms": 200, "total_time_ms": 350}}\n\n'
        )

        respx.post(f"{aggregator_url}/chat/stream").mock(
            return_value=httpx.Response(
                200,
                content=sse_content.encode(),
                headers={"content-type": "text/event-stream"},
            )
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        # EndpointRef without owner_username means no satellite tokens are fetched
        model_ref = EndpointRef(url="http://syftai:8080", slug="model")

        events: list[ChatStreamEvent] = []
        for event in client.chat.stream(prompt="Hello", model=model_ref):
            events.append(event)

        # Verify event sequence
        assert len(events) >= 5

        # Check specific events
        assert any(isinstance(e, RetrievalStartEvent) for e in events)
        assert any(isinstance(e, SourceCompleteEvent) for e in events)
        assert any(isinstance(e, RetrievalCompleteEvent) for e in events)
        assert any(isinstance(e, GenerationStartEvent) for e in events)
        assert any(isinstance(e, TokenEvent) for e in events)
        assert any(isinstance(e, DoneEvent) for e in events)

        # Check token content
        tokens = [e for e in events if isinstance(e, TokenEvent)]
        full_response = "".join(t.content for t in tokens)
        assert full_response == "Hello world!"

    @respx.mock
    def test_stream_error_event(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
    ) -> None:
        """Test that stream() handles error events."""
        sse_content = 'event: error\ndata: {"message": "Model unavailable"}\n\n'

        respx.post(f"{aggregator_url}/chat/stream").mock(
            return_value=httpx.Response(
                200,
                content=sse_content.encode(),
                headers={"content-type": "text/event-stream"},
            )
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        # EndpointRef without owner_username means no satellite tokens are fetched
        model_ref = EndpointRef(url="http://syftai:8080", slug="model")

        events = list(client.chat.stream(prompt="Hello", model=model_ref))

        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert events[0].message == "Model unavailable"


class TestEndpointResolution:
    """Tests for endpoint resolution logic."""

    @respx.mock
    def test_resolve_string_path(
        self,
        base_url: str,
        mock_endpoint_public: dict[str, Any],
    ) -> None:
        """Test resolving string path to EndpointRef with owner_username."""
        # Mock hub browse endpoint (hub.get uses browse to find endpoints)
        respx.get(f"{base_url}/api/v1/endpoints/public").mock(
            return_value=httpx.Response(200, json=[mock_endpoint_public])
        )

        client = SyftHubClient(base_url=base_url)

        # Access the private method for testing
        ref = client.chat._resolve_endpoint_ref("alice/test-model")

        assert isinstance(ref, EndpointRef)
        assert ref.url == "http://syftai:8080"
        assert ref.slug == "test-model"
        assert ref.tenant_name == "default"
        assert (
            ref.owner_username == "alice"
        )  # Verify owner is captured for satellite token

    def test_resolve_endpoint_ref_passthrough(
        self,
        base_url: str,
    ) -> None:
        """Test that EndpointRef objects pass through unchanged."""
        client = SyftHubClient(base_url=base_url)

        original = EndpointRef(
            url="http://custom:8080",
            slug="custom-model",
            name="Custom",
            tenant_name="tenant1",
        )

        resolved = client.chat._resolve_endpoint_ref(original)

        assert resolved is original

    def test_resolve_endpoint_public(
        self,
        base_url: str,
    ) -> None:
        """Test resolving EndpointPublic to EndpointRef with owner_username."""
        client = SyftHubClient(base_url=base_url)

        now = datetime.now(timezone.utc)

        # Create mock EndpointPublic
        ep = EndpointPublic(
            name="Test Model",
            slug="test-model",
            type=EndpointType.MODEL,
            owner_username="alice",
            stars_count=5,
            created_at=now,
            updated_at=now,
            connect=[
                Connection(
                    type="syftai",
                    enabled=True,
                    config={"url": "http://space:8080"},
                )
            ],
        )

        resolved = client.chat._resolve_endpoint_ref(ep)

        assert isinstance(resolved, EndpointRef)
        assert resolved.url == "http://space:8080"
        assert resolved.slug == "test-model"
        assert (
            resolved.owner_username == "alice"
        )  # Verify owner is captured for satellite token

    def test_resolve_endpoint_no_url_raises(
        self,
        base_url: str,
    ) -> None:
        """Test that endpoint without URL raises error."""
        client = SyftHubClient(base_url=base_url)

        now = datetime.now(timezone.utc)

        ep = EndpointPublic(
            name="No URL Model",
            slug="no-url",
            type=EndpointType.MODEL,
            owner_username="alice",
            stars_count=0,
            created_at=now,
            updated_at=now,
            connect=[
                Connection(
                    type="syftai",
                    enabled=True,
                    config={},  # No URL
                )
            ],
        )

        with pytest.raises(EndpointResolutionError, match="no connection with URL"):
            client.chat._resolve_endpoint_ref(ep)

    def test_resolve_model_data_source_as_model(
        self,
        base_url: str,
    ) -> None:
        """Test that model_data_source endpoints can be used as models."""
        client = SyftHubClient(base_url=base_url)
        now = datetime.now(timezone.utc)

        ep = EndpointPublic(
            name="Combo Endpoint",
            slug="combo-endpoint",
            type=EndpointType.MODEL_DATA_SOURCE,
            owner_username="alice",
            stars_count=0,
            created_at=now,
            updated_at=now,
            connect=[
                Connection(
                    type="syftai",
                    enabled=True,
                    config={"url": "http://space:8080"},
                )
            ],
        )

        resolved = client.chat._resolve_endpoint_ref(ep, expected_type="model")

        assert isinstance(resolved, EndpointRef)
        assert resolved.slug == "combo-endpoint"

    def test_resolve_model_data_source_as_data_source(
        self,
        base_url: str,
    ) -> None:
        """Test that model_data_source endpoints can be used as data sources."""
        client = SyftHubClient(base_url=base_url)
        now = datetime.now(timezone.utc)

        ep = EndpointPublic(
            name="Combo Endpoint",
            slug="combo-endpoint",
            type=EndpointType.MODEL_DATA_SOURCE,
            owner_username="alice",
            stars_count=0,
            created_at=now,
            updated_at=now,
            connect=[
                Connection(
                    type="syftai",
                    enabled=True,
                    config={"url": "http://space:8080"},
                )
            ],
        )

        resolved = client.chat._resolve_endpoint_ref(ep, expected_type="data_source")

        assert isinstance(resolved, EndpointRef)
        assert resolved.slug == "combo-endpoint"

    def test_resolve_wrong_type_raises(
        self,
        base_url: str,
    ) -> None:
        """Test that using a data_source endpoint as a model raises ValueError."""
        client = SyftHubClient(base_url=base_url)
        now = datetime.now(timezone.utc)

        ep = EndpointPublic(
            name="Data Only",
            slug="data-only",
            type=EndpointType.DATA_SOURCE,
            owner_username="alice",
            stars_count=0,
            created_at=now,
            updated_at=now,
            connect=[
                Connection(
                    type="syftai",
                    enabled=True,
                    config={"url": "http://space:8080"},
                )
            ],
        )

        with pytest.raises(ValueError, match="Expected endpoint type 'model'"):
            client.chat._resolve_endpoint_ref(ep, expected_type="model")


class TestGetAvailableEndpoints:
    """Tests for get_available_models() and get_available_data_sources()."""

    @respx.mock
    def test_get_available_models(
        self,
        base_url: str,
        mock_endpoint_public: dict[str, Any],
    ) -> None:
        """Test getting available models."""
        # Create multiple endpoints
        endpoints = [
            {**mock_endpoint_public, "slug": "model-1", "type": "model"},
            {**mock_endpoint_public, "slug": "model-2", "type": "model"},
            {**mock_endpoint_public, "slug": "datasource-1", "type": "data_source"},
        ]

        # hub.browse() uses /api/v1/endpoints/public
        respx.get(f"{base_url}/api/v1/endpoints/public").mock(
            return_value=httpx.Response(200, json=endpoints)
        )

        client = SyftHubClient(base_url=base_url)

        # get_available_models returns a generator, convert to list
        models = list(client.chat.get_available_models(limit=10))

        # Should only return models with URLs
        assert len(models) == 2
        for m in models:
            assert m.type == EndpointType.MODEL

    @respx.mock
    def test_get_available_data_sources(
        self,
        base_url: str,
        mock_endpoint_public: dict[str, Any],
    ) -> None:
        """Test getting available data sources."""
        endpoints = [
            {**mock_endpoint_public, "slug": "ds-1", "type": "data_source"},
            {**mock_endpoint_public, "slug": "model-1", "type": "model"},
        ]

        # hub.browse() uses /api/v1/endpoints/public
        respx.get(f"{base_url}/api/v1/endpoints/public").mock(
            return_value=httpx.Response(200, json=endpoints)
        )

        client = SyftHubClient(base_url=base_url)

        # get_available_data_sources returns a generator, convert to list
        sources = list(client.chat.get_available_data_sources(limit=10))

        assert len(sources) == 1
        assert sources[0].type == EndpointType.DATA_SOURCE


class TestTunnelingDetection:
    """Tests for tunneling endpoint detection and peer token auto-fetch."""

    def test_collect_tunneling_usernames_with_tunneling_model(
        self,
        base_url: str,
    ) -> None:
        """Test that tunneling model URLs are detected."""
        client = SyftHubClient(base_url=base_url)

        model_ref = EndpointRef(url="tunneling:alice", slug="model")
        ds_refs = [EndpointRef(url="http://normal:8080", slug="docs")]

        usernames = client.chat._collect_tunneling_usernames(model_ref, ds_refs)
        assert usernames == ["alice"]

    def test_collect_tunneling_usernames_with_tunneling_datasource(
        self,
        base_url: str,
    ) -> None:
        """Test that tunneling data source URLs are detected."""
        client = SyftHubClient(base_url=base_url)

        model_ref = EndpointRef(url="http://normal:8080", slug="model")
        ds_refs = [
            EndpointRef(url="tunneling:bob", slug="docs"),
            EndpointRef(url="tunneling:carol", slug="data"),
        ]

        usernames = client.chat._collect_tunneling_usernames(model_ref, ds_refs)
        assert set(usernames) == {"bob", "carol"}

    def test_collect_tunneling_usernames_no_tunneling(
        self,
        base_url: str,
    ) -> None:
        """Test that non-tunneling URLs return empty list."""
        client = SyftHubClient(base_url=base_url)

        model_ref = EndpointRef(url="http://normal:8080", slug="model")
        ds_refs = [EndpointRef(url="http://also-normal:8080", slug="docs")]

        usernames = client.chat._collect_tunneling_usernames(model_ref, ds_refs)
        assert usernames == []

    def test_tunneling_prefix_constant(self) -> None:
        """Test that the tunneling prefix constant is correct."""
        assert TUNNELING_PREFIX == "tunneling:"

    @respx.mock
    def test_complete_with_tunneling_endpoints_fetches_peer_token(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
        mock_chat_response: dict[str, Any],
    ) -> None:
        """Test that complete() auto-fetches peer token for tunneling endpoints."""
        mock_peer_token_response = {
            "peer_token": "pt_test123",
            "peer_channel": "peer_abc",
            "expires_in": 120,
            "nats_url": "ws://localhost:8080/nats",
        }

        respx.post(f"{base_url}/api/v1/peer-token").mock(
            return_value=httpx.Response(200, json=mock_peer_token_response)
        )

        respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(200, json=mock_chat_response)
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        model_ref = EndpointRef(
            url="tunneling:alice",
            slug="test-model",
            owner_username="alice",
        )

        response = client.chat.complete(
            prompt="Hello via tunnel",
            model=model_ref,
        )

        assert isinstance(response, ChatResponse)

        # Verify peer-token was called
        peer_token_call = respx.calls.last
        assert peer_token_call is not None

    def test_peer_token_response_model(self) -> None:
        """Test PeerTokenResponse model validation."""
        response = PeerTokenResponse(
            peer_token="pt_abc123",
            peer_channel="peer_def456",
            expires_in=120,
            nats_url="ws://localhost:8080/nats",
        )
        assert response.peer_token == "pt_abc123"
        assert response.peer_channel == "peer_def456"
        assert response.expires_in == 120
        assert response.nats_url == "ws://localhost:8080/nats"
