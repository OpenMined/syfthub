"""Tests for aggregator services with tunneling support."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from aggregator.clients.tunnel import TunnelClient
from aggregator.schemas.internal import ResolvedEndpoint, RetrievalResult
from aggregator.schemas.responses import Document
from aggregator.services.generation import GenerationError, GenerationService
from aggregator.services.retrieval import RetrievalService


class TestRetrievalServiceTunneling:
    """Tests for RetrievalService with tunneling support."""

    @pytest.fixture
    def mock_data_source_client(self):
        """Create a mock DataSourceClient."""
        client = AsyncMock()
        client.query = AsyncMock(
            return_value=RetrievalResult(
                endpoint_path="test/endpoint",
                documents=[Document(content="HTTP result", score=0.9)],
                status="success",
                latency_ms=100,
            )
        )
        return client

    @pytest.fixture
    def mock_tunnel_client(self):
        """Create a mock TunnelClient."""
        client = AsyncMock(spec=TunnelClient)
        client.query_data_source = AsyncMock(
            return_value=RetrievalResult(
                endpoint_path="tunnel/endpoint",
                documents=[Document(content="Tunnel result", score=0.85)],
                status="success",
                latency_ms=150,
            )
        )
        return client

    @pytest.fixture
    def retrieval_service(self, mock_data_source_client, mock_tunnel_client):
        """Create a RetrievalService with mocked clients."""
        return RetrievalService(mock_data_source_client, mock_tunnel_client)

    @pytest.fixture
    def http_endpoint(self):
        """Create an HTTP endpoint."""
        return ResolvedEndpoint(
            path="owner/http-ds",
            url="http://localhost:8080",
            slug="http-ds",
            endpoint_type="data_source",
            name="HTTP Data Source",
            owner_username="owner",
        )

    @pytest.fixture
    def tunnel_endpoint(self):
        """Create a tunneled endpoint."""
        return ResolvedEndpoint(
            path="alice/tunnel-ds",
            url="tunneling:alice",
            slug="tunnel-ds",
            endpoint_type="data_source",
            name="Tunneled Data Source",
            owner_username="alice",
        )

    @pytest.mark.asyncio
    async def test_retrieve_http_endpoint(
        self, retrieval_service, mock_data_source_client, http_endpoint
    ):
        """Test retrieval from HTTP endpoint."""
        result = await retrieval_service.retrieve(
            data_sources=[http_endpoint],
            query="test query",
            top_k=5,
            similarity_threshold=0.5,
            endpoint_tokens={"owner": "token"},
        )

        assert len(result.documents) == 1
        assert result.documents[0].content == "HTTP result"
        mock_data_source_client.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_tunneled_endpoint(
        self, retrieval_service, mock_tunnel_client, tunnel_endpoint
    ):
        """Test retrieval from tunneled endpoint."""
        result = await retrieval_service.retrieve(
            data_sources=[tunnel_endpoint],
            query="test query",
            top_k=5,
            similarity_threshold=0.5,
            endpoint_tokens={"alice": "sat_token_alice"},
            response_queue_id="rq_test123",
            response_queue_token="queue_token",
        )

        assert len(result.documents) == 1
        assert result.documents[0].content == "Tunnel result"
        mock_tunnel_client.query_data_source.assert_called_once()

        # Verify tunnel client was called with correct params
        call_kwargs = mock_tunnel_client.query_data_source.call_args.kwargs
        assert call_kwargs["target_username"] == "alice"
        assert call_kwargs["endpoint_slug"] == "tunnel-ds"
        assert call_kwargs["satellite_token"] == "sat_token_alice"
        assert call_kwargs["response_queue_id"] == "rq_test123"

    @pytest.mark.asyncio
    async def test_retrieve_mixed_endpoints(
        self,
        retrieval_service,
        mock_data_source_client,
        mock_tunnel_client,
        http_endpoint,
        tunnel_endpoint,
    ):
        """Test retrieval from both HTTP and tunneled endpoints."""
        result = await retrieval_service.retrieve(
            data_sources=[http_endpoint, tunnel_endpoint],
            query="test query",
            top_k=5,
            similarity_threshold=0.5,
            endpoint_tokens={"owner": "token1", "alice": "sat_token_alice"},
            response_queue_id="rq_mixed",
            response_queue_token="mixed_token",
        )

        # Should have results from both endpoints
        assert len(result.documents) == 2
        mock_data_source_client.query.assert_called_once()
        mock_tunnel_client.query_data_source.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_tunneled_missing_queue_credentials(
        self, retrieval_service, tunnel_endpoint
    ):
        """Test retrieval from tunneled endpoint without queue credentials."""
        result = await retrieval_service.retrieve(
            data_sources=[tunnel_endpoint],
            query="test query",
            endpoint_tokens={"alice": "token"},
            # Missing response_queue_id and response_queue_token
        )

        # Should return error result
        assert result.retrieval_results[0].status == "error"
        assert "require" in result.retrieval_results[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_retrieve_tunneled_missing_satellite_token(
        self, retrieval_service, tunnel_endpoint
    ):
        """Test retrieval from tunneled endpoint without satellite token."""
        result = await retrieval_service.retrieve(
            data_sources=[tunnel_endpoint],
            query="test query",
            endpoint_tokens={},  # No token for alice
            response_queue_id="rq_test",
            response_queue_token="token",
        )

        # Should return error result
        assert result.retrieval_results[0].status == "error"
        assert "token" in result.retrieval_results[0].error_message.lower()


class TestGenerationServiceTunneling:
    """Tests for GenerationService with tunneling support."""

    @pytest.fixture
    def mock_model_client(self):
        """Create a mock ModelClient."""
        from aggregator.schemas.internal import GenerationResult

        client = AsyncMock()
        client.chat = AsyncMock(
            return_value=GenerationResult(
                response="HTTP response",
                latency_ms=200,
                usage={"prompt_tokens": 10, "completion_tokens": 20},
            )
        )
        return client

    @pytest.fixture
    def mock_tunnel_client(self):
        """Create a mock TunnelClient."""
        from aggregator.schemas.internal import GenerationResult

        client = AsyncMock(spec=TunnelClient)
        client.query_model = AsyncMock(
            return_value=GenerationResult(
                response="Tunnel response",
                latency_ms=300,
            )
        )
        return client

    @pytest.fixture
    def generation_service(self, mock_model_client, mock_tunnel_client):
        """Create a GenerationService with mocked clients."""
        return GenerationService(mock_model_client, mock_tunnel_client)

    @pytest.fixture
    def http_model_endpoint(self):
        """Create an HTTP model endpoint."""
        return ResolvedEndpoint(
            path="owner/http-model",
            url="http://localhost:8080",
            slug="http-model",
            endpoint_type="model",
            name="HTTP Model",
            owner_username="owner",
        )

    @pytest.fixture
    def tunnel_model_endpoint(self):
        """Create a tunneled model endpoint."""
        return ResolvedEndpoint(
            path="bob/tunnel-model",
            url="tunneling:bob",
            slug="tunnel-model",
            endpoint_type="model",
            name="Tunneled Model",
            owner_username="bob",
        )

    @pytest.mark.asyncio
    async def test_generate_http_endpoint(
        self, generation_service, mock_model_client, http_model_endpoint
    ):
        """Test generation from HTTP endpoint."""
        from aggregator.schemas.requests import Message

        messages = [Message(role="user", content="Hello")]

        result = await generation_service.generate(
            model_endpoint=http_model_endpoint,
            messages=messages,
            max_tokens=100,
            temperature=0.7,
            endpoint_tokens={"owner": "token"},
        )

        assert result.response == "HTTP response"
        mock_model_client.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_tunneled_endpoint(
        self, generation_service, mock_tunnel_client, tunnel_model_endpoint
    ):
        """Test generation from tunneled endpoint."""
        from aggregator.schemas.requests import Message

        messages = [Message(role="user", content="Hello")]

        result = await generation_service.generate(
            model_endpoint=tunnel_model_endpoint,
            messages=messages,
            max_tokens=100,
            temperature=0.7,
            endpoint_tokens={"bob": "sat_token_bob"},
            response_queue_id="rq_model",
            response_queue_token="model_token",
        )

        assert result.response == "Tunnel response"
        mock_tunnel_client.query_model.assert_called_once()

        # Verify tunnel client was called with correct params
        call_kwargs = mock_tunnel_client.query_model.call_args.kwargs
        assert call_kwargs["target_username"] == "bob"
        assert call_kwargs["endpoint_slug"] == "tunnel-model"
        assert call_kwargs["satellite_token"] == "sat_token_bob"

    @pytest.mark.asyncio
    async def test_generate_tunneled_missing_credentials_raises(
        self, generation_service, tunnel_model_endpoint
    ):
        """Test generation from tunneled endpoint without credentials raises error."""
        from aggregator.schemas.requests import Message

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(GenerationError) as exc_info:
            await generation_service.generate(
                model_endpoint=tunnel_model_endpoint,
                messages=messages,
                endpoint_tokens={"bob": "token"},
                # Missing queue credentials
            )

        assert "require" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_generate_stream_tunneled_raises(
        self, generation_service, tunnel_model_endpoint
    ):
        """Test streaming from tunneled endpoint raises error (not supported)."""
        from aggregator.schemas.requests import Message

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(GenerationError) as exc_info:
            async for _ in generation_service.generate_stream(
                model_endpoint=tunnel_model_endpoint,
                messages=messages,
                endpoint_tokens={"bob": "token"},
                response_queue_id="rq_test",
                response_queue_token="token",
            ):
                pass

        assert "streaming" in str(exc_info.value).lower()
        assert "not" in str(exc_info.value).lower()


class TestServiceTokenLookup:
    """Tests for token lookup functionality in services."""

    def test_get_token_for_endpoint_found(self):
        """Test token lookup when owner is in mapping."""
        from aggregator.services.retrieval import RetrievalService

        service = RetrievalService(MagicMock(), MagicMock())
        endpoint = ResolvedEndpoint(
            path="alice/ds",
            url="tunneling:alice",
            slug="ds",
            endpoint_type="data_source",
            owner_username="alice",
        )
        token_mapping = {"alice": "alice_token", "bob": "bob_token"}

        token = service._get_token_for_endpoint(endpoint, token_mapping)
        assert token == "alice_token"

    def test_get_token_for_endpoint_not_found(self):
        """Test token lookup when owner not in mapping."""
        from aggregator.services.retrieval import RetrievalService

        service = RetrievalService(MagicMock(), MagicMock())
        endpoint = ResolvedEndpoint(
            path="charlie/ds",
            url="tunneling:charlie",
            slug="ds",
            endpoint_type="data_source",
            owner_username="charlie",
        )
        token_mapping = {"alice": "alice_token"}

        token = service._get_token_for_endpoint(endpoint, token_mapping)
        assert token is None

    def test_get_token_for_endpoint_no_owner(self):
        """Test token lookup when endpoint has no owner."""
        from aggregator.services.retrieval import RetrievalService

        service = RetrievalService(MagicMock(), MagicMock())
        endpoint = ResolvedEndpoint(
            path="ds",
            url="http://localhost:8080",
            slug="ds",
            endpoint_type="data_source",
            owner_username=None,
        )
        token_mapping = {"alice": "alice_token"}

        token = service._get_token_for_endpoint(endpoint, token_mapping)
        assert token is None
