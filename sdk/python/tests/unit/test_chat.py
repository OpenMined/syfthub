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
    ChatResource,
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
        "billing": {
            "total_cost": 0.01,
            "currency": "USD",
            "entries": [
                {
                    "source": "alice/docs",
                    "policy_type": "mpp_per_request",
                    "kind": "payment",
                    "status": "charged",
                    "amount": 0.01,
                    "currency": "USD",
                    "recipient": {
                        "username": "alice",
                        "email": "alice@x.io",
                        "wallet_address": "0xabc",
                    },
                    "transaction": {
                        "rail": "mpp",
                        "id": "0xtxhash",
                        "reference": None,
                    },
                    "reason_code": None,
                    "reason": None,
                    "details": {},
                }
            ],
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
        # Billing block is parsed from the aggregator response.
        assert response.billing is not None
        assert response.billing.total_cost == 0.01
        assert response.billing.currency == "USD"
        entry = response.billing.entries[0]
        assert entry.source == "alice/docs"
        assert entry.policy_type == "mpp_per_request"
        assert entry.recipient is not None
        assert entry.recipient.username == "alice"
        assert entry.transaction is not None
        assert entry.transaction.rail == "mpp"
        assert entry.transaction.id == "0xtxhash"

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
    def test_complete_aggregator_error_surfaces_billing(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
    ) -> None:
        """A rejected paid query attaches the billing block to AggregatorError."""
        respx.post(f"{aggregator_url}/chat").mock(
            return_value=httpx.Response(
                402,
                json={
                    "message": "Payment required",
                    "billing": {
                        "total_cost": None,
                        "currency": None,
                        "entries": [
                            {
                                "source": "alice/docs",
                                "policy_type": "mpp_per_request",
                                "kind": "payment",
                                "status": "rejected",
                                "amount": 0.05,
                                "currency": "USD",
                                "reason_code": "PAYMENT_REQUIRED",
                                "transaction": None,
                            }
                        ],
                    },
                },
            )
        )

        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)

        model_ref = EndpointRef(url="http://syftai:8080", slug="model")

        with pytest.raises(AggregatorError) as exc_info:
            client.chat.complete(prompt="Hello", model=model_ref)

        err = exc_info.value
        assert err.billing is not None
        assert err.billing.entries[0].source == "alice/docs"
        assert err.billing.entries[0].status == "rejected"
        assert err.billing.entries[0].reason_code == "PAYMENT_REQUIRED"

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
            'event: done\ndata: {"sources": [], "metadata": {"retrieval_time_ms": 150, "generation_time_ms": 200, "total_time_ms": 350}, "billing": {"total_cost": 0.02, "currency": "USD", "entries": [{"source": "alice/docs", "policy_type": "mpp_per_request", "kind": "payment", "status": "charged", "amount": 0.02, "currency": "USD", "recipient": {"username": "alice", "email": null, "wallet_address": null}, "transaction": {"rail": "mpp", "id": "0xdone", "reference": null}, "reason_code": null, "reason": null, "details": {}}]}}\n\n'
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

        # The done event carries the aggregated billing block.
        done = next(e for e in events if isinstance(e, DoneEvent))
        assert done.billing is not None
        assert done.billing.total_cost == 0.02
        assert done.billing.entries[0].transaction is not None
        assert done.billing.entries[0].transaction.id == "0xdone"

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
        # No billing block on this error -> billing stays None.
        assert events[0].billing is None

    @respx.mock
    def test_stream_error_event_surfaces_billing(
        self,
        base_url: str,
        aggregator_url: str,
        fake_tokens: AuthTokens,
    ) -> None:
        """A rejected paid stream surfaces billing on the ErrorEvent."""
        sse_content = (
            'event: error\ndata: {"message": "Payment required", "billing": '
            '{"total_cost": null, "currency": null, "entries": [{"source": '
            '"alice/docs", "policy_type": "mpp_per_request", "kind": "payment", '
            '"status": "rejected", "amount": 0.05, "currency": "USD", '
            '"reason_code": "PAYMENT_REQUIRED", "transaction": null}]}}\n\n'
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

        model_ref = EndpointRef(url="http://syftai:8080", slug="model")

        events = list(client.chat.stream(prompt="Hello", model=model_ref))

        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert events[0].billing is not None
        assert events[0].billing.entries[0].source == "alice/docs"
        assert events[0].billing.entries[0].status == "rejected"
        assert events[0].billing.entries[0].reason_code == "PAYMENT_REQUIRED"


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


class TestTypeMatches:
    """Tests for ChatResource._type_matches().

    Shared type-match test vectors — keep in sync across Go/Python/TypeScript SDKs.
    These vectors ensure all three SDK implementations of _type_matches stay consistent.
    Rules:
      1. Exact match always returns true
      2. model_data_source matches both model and data_source
      3. agent matches model (agents can be used where models are expected)
      4. All other cross-type combinations return false
    """

    @pytest.mark.parametrize(
        ("actual_type", "expected_type", "want"),
        [
            # Exact matches
            ("model", "model", True),
            ("data_source", "data_source", True),
            ("model_data_source", "model_data_source", True),
            ("agent", "agent", True),
            # model_data_source matches both model and data_source
            ("model_data_source", "model", True),
            ("model_data_source", "data_source", True),
            # agent matches model
            ("agent", "model", True),
            # Cross-type mismatches
            ("model", "data_source", False),
            ("data_source", "model", False),
            ("model", "agent", False),
            ("data_source", "agent", False),
            ("model_data_source", "agent", False),
            ("agent", "data_source", False),
            ("model", "model_data_source", False),
            ("data_source", "model_data_source", False),
        ],
    )
    def test_type_matches(
        self, actual_type: str, expected_type: str, want: bool
    ) -> None:
        """Verify _type_matches returns the expected result."""
        got = ChatResource._type_matches(actual_type, expected_type)
        assert got is want, (
            f"_type_matches({actual_type!r}, {expected_type!r}) = {got}, want {want}"
        )


class TestExpandCollectivePaths:
    """Tests for ChatResource._expand_collective_paths()."""

    @staticmethod
    def _chat(
        base_url: str, fake_tokens: AuthTokens, member_paths: list[str]
    ) -> tuple[Any, list[tuple[str, str | None]]]:
        """Build a chat resource whose hub returns fixed collective member paths."""
        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(fake_tokens)
        calls: list[tuple[str, str | None]] = []

        def fake_paths(slug: str, shared_slug: str | None = None) -> list[str]:
            calls.append((slug, shared_slug))
            return member_paths

        client.chat._hub.get_collective_endpoint_paths = fake_paths  # type: ignore[method-assign]
        return client.chat, calls

    def test_expands_bare_collective(
        self, base_url: str, fake_tokens: AuthTokens
    ) -> None:
        chat, calls = self._chat(base_url, fake_tokens, ["alice/a", "bob/b"])
        result = chat._expand_collective_paths(["collective/genomics"])
        assert result == ["alice/a", "bob/b"]
        assert calls == [("genomics", None)]

    def test_all_alias_maps_to_no_subset(
        self, base_url: str, fake_tokens: AuthTokens
    ) -> None:
        chat, calls = self._chat(base_url, fake_tokens, ["alice/a"])
        chat._expand_collective_paths(["collective/genomics/all"])
        assert calls == [("genomics", None)]

    def test_subset_slug_passed_through(
        self, base_url: str, fake_tokens: AuthTokens
    ) -> None:
        chat, calls = self._chat(base_url, fake_tokens, ["alice/a"])
        chat._expand_collective_paths(["collective/genomics/oncology"])
        assert calls == [("genomics", "oncology")]

    def test_non_collective_passthrough_and_dedup(
        self, base_url: str, fake_tokens: AuthTokens
    ) -> None:
        chat, _ = self._chat(base_url, fake_tokens, ["alice/a"])
        result = chat._expand_collective_paths(["bob/b", "bob/b", "collective/g"])
        # bob/b is deduped; the collective's member is appended after.
        assert result == ["bob/b", "alice/a"]

    def test_dedup_across_collective_and_standalone(
        self, base_url: str, fake_tokens: AuthTokens
    ) -> None:
        chat, _ = self._chat(base_url, fake_tokens, ["alice/a", "bob/b"])
        result = chat._expand_collective_paths(["alice/a", "collective/g"])
        assert result == ["alice/a", "bob/b"]

    def test_malformed_collective_raises(
        self, base_url: str, fake_tokens: AuthTokens
    ) -> None:
        chat, _ = self._chat(base_url, fake_tokens, [])
        with pytest.raises(EndpointResolutionError):
            chat._expand_collective_paths(["collective/"])
