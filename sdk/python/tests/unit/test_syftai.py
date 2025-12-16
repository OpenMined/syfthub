"""Unit tests for SyftAIResource."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import respx

from syfthub_sdk import SyftHubClient
from syfthub_sdk.exceptions import GenerationError, RetrievalError
from syfthub_sdk.models import Document, EndpointRef, Message
from syfthub_sdk.syftai import SyftAIResource


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def base_url() -> str:
    """Return test base URL."""
    return "https://test.syfthub.com"


@pytest.fixture
def syftai_url() -> str:
    """Return test SyftAI-Space URL."""
    return "http://syftai-space:8080"


@pytest.fixture
def model_endpoint(syftai_url: str) -> EndpointRef:
    """Return a model endpoint reference."""
    return EndpointRef(
        url=syftai_url,
        slug="test-model",
        name="Test Model",
        tenant_name="default",
    )


@pytest.fixture
def data_source_endpoint(syftai_url: str) -> EndpointRef:
    """Return a data source endpoint reference."""
    return EndpointRef(
        url=syftai_url,
        slug="test-docs",
        name="Test Docs",
        tenant_name="default",
    )


# =============================================================================
# SyftAIResource Unit Tests
# =============================================================================


class TestQueryDataSource:
    """Tests for SyftAIResource.query_data_source()."""

    @respx.mock
    def test_query_data_source_success(
        self,
        base_url: str,
        syftai_url: str,
        data_source_endpoint: EndpointRef,
    ) -> None:
        """Test successful data source query."""
        mock_response = {
            "documents": [
                {
                    "content": "Machine learning is a type of AI.",
                    "score": 0.95,
                    "metadata": {"source": "ml-intro.txt"},
                },
                {
                    "content": "Deep learning uses neural networks.",
                    "score": 0.87,
                    "metadata": {"source": "dl-basics.txt"},
                },
            ]
        }

        respx.post(f"{syftai_url}/api/v1/endpoints/test-docs/query").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        client = SyftHubClient(base_url=base_url)

        docs = client.syftai.query_data_source(
            endpoint=data_source_endpoint,
            query="What is machine learning?",
            user_email="test@example.com",
            top_k=5,
        )

        assert len(docs) == 2
        assert all(isinstance(d, Document) for d in docs)
        assert docs[0].content == "Machine learning is a type of AI."
        assert docs[0].score == 0.95
        assert docs[0].metadata["source"] == "ml-intro.txt"

    @respx.mock
    def test_query_data_source_with_tenant_header(
        self,
        base_url: str,
        syftai_url: str,
    ) -> None:
        """Test that X-Tenant-Name header is sent."""
        endpoint = EndpointRef(
            url=syftai_url,
            slug="tenant-docs",
            tenant_name="custom-tenant",
        )

        mock_response = {"documents": []}

        route = respx.post(f"{syftai_url}/api/v1/endpoints/tenant-docs/query").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        client = SyftHubClient(base_url=base_url)

        client.syftai.query_data_source(
            endpoint=endpoint,
            query="test",
            user_email="test@example.com",
        )

        # Verify the header was sent
        assert route.called
        request = route.calls.last.request
        assert request.headers.get("X-Tenant-Name") == "custom-tenant"

    @respx.mock
    def test_query_data_source_empty_results(
        self,
        base_url: str,
        syftai_url: str,
        data_source_endpoint: EndpointRef,
    ) -> None:
        """Test handling of empty results."""
        respx.post(f"{syftai_url}/api/v1/endpoints/test-docs/query").mock(
            return_value=httpx.Response(200, json={"documents": []})
        )

        client = SyftHubClient(base_url=base_url)

        docs = client.syftai.query_data_source(
            endpoint=data_source_endpoint,
            query="obscure query",
            user_email="test@example.com",
        )

        assert docs == []

    @respx.mock
    def test_query_data_source_http_error(
        self,
        base_url: str,
        syftai_url: str,
        data_source_endpoint: EndpointRef,
    ) -> None:
        """Test handling of HTTP errors."""
        respx.post(f"{syftai_url}/api/v1/endpoints/test-docs/query").mock(
            return_value=httpx.Response(
                500,
                json={"detail": "Internal server error"},
            )
        )

        client = SyftHubClient(base_url=base_url)

        with pytest.raises(RetrievalError, match="Internal server error"):
            client.syftai.query_data_source(
                endpoint=data_source_endpoint,
                query="test",
                user_email="test@example.com",
            )

    @respx.mock
    def test_query_data_source_connection_error(
        self,
        base_url: str,
        syftai_url: str,
        data_source_endpoint: EndpointRef,
    ) -> None:
        """Test handling of connection errors."""
        respx.post(f"{syftai_url}/api/v1/endpoints/test-docs/query").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = SyftHubClient(base_url=base_url)

        with pytest.raises(RetrievalError, match="Failed to connect"):
            client.syftai.query_data_source(
                endpoint=data_source_endpoint,
                query="test",
                user_email="test@example.com",
            )


class TestQueryModel:
    """Tests for SyftAIResource.query_model()."""

    @respx.mock
    def test_query_model_success(
        self,
        base_url: str,
        syftai_url: str,
        model_endpoint: EndpointRef,
    ) -> None:
        """Test successful model query."""
        mock_response = {
            "message": {
                "role": "assistant",
                "content": "Hello! How can I help you today?",
            }
        }

        respx.post(f"{syftai_url}/api/v1/endpoints/test-model/query").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        client = SyftHubClient(base_url=base_url)

        messages = [
            Message(role="user", content="Hello!"),
        ]

        response = client.syftai.query_model(
            endpoint=model_endpoint,
            messages=messages,
            user_email="test@example.com",
        )

        assert response == "Hello! How can I help you today?"

    @respx.mock
    def test_query_model_with_system_message(
        self,
        base_url: str,
        syftai_url: str,
        model_endpoint: EndpointRef,
    ) -> None:
        """Test model query with system message."""
        mock_response = {"message": {"content": "I am a helpful assistant."}}

        route = respx.post(f"{syftai_url}/api/v1/endpoints/test-model/query").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        client = SyftHubClient(base_url=base_url)

        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="What are you?"),
        ]

        client.syftai.query_model(
            endpoint=model_endpoint,
            messages=messages,
            user_email="test@example.com",
            max_tokens=512,
            temperature=0.5,
        )

        # Verify request body
        request = route.calls.last.request
        body = json.loads(request.content)
        assert body["max_tokens"] == 512
        assert body["temperature"] == 0.5
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "system"

    @respx.mock
    def test_query_model_http_error(
        self,
        base_url: str,
        syftai_url: str,
        model_endpoint: EndpointRef,
    ) -> None:
        """Test handling of HTTP errors."""
        respx.post(f"{syftai_url}/api/v1/endpoints/test-model/query").mock(
            return_value=httpx.Response(
                429,
                json={"detail": "Rate limit exceeded"},
            )
        )

        client = SyftHubClient(base_url=base_url)

        with pytest.raises(GenerationError, match="Rate limit exceeded"):
            client.syftai.query_model(
                endpoint=model_endpoint,
                messages=[Message(role="user", content="Hi")],
                user_email="test@example.com",
            )

    @respx.mock
    def test_query_model_connection_error(
        self,
        base_url: str,
        syftai_url: str,
        model_endpoint: EndpointRef,
    ) -> None:
        """Test handling of connection errors."""
        respx.post(f"{syftai_url}/api/v1/endpoints/test-model/query").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = SyftHubClient(base_url=base_url)

        with pytest.raises(GenerationError, match="Failed to connect"):
            client.syftai.query_model(
                endpoint=model_endpoint,
                messages=[Message(role="user", content="Hi")],
                user_email="test@example.com",
            )


class TestQueryModelStream:
    """Tests for SyftAIResource.query_model_stream()."""

    @respx.mock
    def test_query_model_stream_success(
        self,
        base_url: str,
        syftai_url: str,
        model_endpoint: EndpointRef,
    ) -> None:
        """Test successful streaming model query."""
        # Create SSE response
        sse_content = (
            'data: {"content": "Hello"}\n\n'
            'data: {"content": " world"}\n\n'
            'data: {"content": "!"}\n\n'
            "data: [DONE]\n\n"
        )

        respx.post(f"{syftai_url}/api/v1/endpoints/test-model/query").mock(
            return_value=httpx.Response(
                200,
                content=sse_content.encode(),
                headers={"content-type": "text/event-stream"},
            )
        )

        client = SyftHubClient(base_url=base_url)

        chunks: list[str] = []
        for chunk in client.syftai.query_model_stream(
            endpoint=model_endpoint,
            messages=[Message(role="user", content="Say hello")],
            user_email="test@example.com",
        ):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello world!"

    @respx.mock
    def test_query_model_stream_openai_format(
        self,
        base_url: str,
        syftai_url: str,
        model_endpoint: EndpointRef,
    ) -> None:
        """Test streaming with OpenAI-style response format."""
        sse_content = (
            'data: {"choices": [{"delta": {"content": "Hi"}}]}\n\n'
            'data: {"choices": [{"delta": {"content": " there"}}]}\n\n'
            "data: [DONE]\n\n"
        )

        respx.post(f"{syftai_url}/api/v1/endpoints/test-model/query").mock(
            return_value=httpx.Response(
                200,
                content=sse_content.encode(),
                headers={"content-type": "text/event-stream"},
            )
        )

        client = SyftHubClient(base_url=base_url)

        chunks: list[str] = []
        for chunk in client.syftai.query_model_stream(
            endpoint=model_endpoint,
            messages=[Message(role="user", content="Hi")],
            user_email="test@example.com",
        ):
            chunks.append(chunk)

        assert "".join(chunks) == "Hi there"

    @respx.mock
    def test_query_model_stream_http_error(
        self,
        base_url: str,
        syftai_url: str,
        model_endpoint: EndpointRef,
    ) -> None:
        """Test handling of HTTP errors in streaming."""
        respx.post(f"{syftai_url}/api/v1/endpoints/test-model/query").mock(
            return_value=httpx.Response(
                503,
                json={"detail": "Service unavailable"},
            )
        )

        client = SyftHubClient(base_url=base_url)

        with pytest.raises(GenerationError, match="Service unavailable"):
            # Need to consume the generator to trigger the error
            list(
                client.syftai.query_model_stream(
                    endpoint=model_endpoint,
                    messages=[Message(role="user", content="Hi")],
                    user_email="test@example.com",
                )
            )


class TestSyftAIResourceIntegration:
    """Integration-style tests for SyftAIResource within SyftHubClient."""

    def test_syftai_resource_accessible_from_client(
        self,
        base_url: str,
    ) -> None:
        """Test that syftai resource is accessible from client."""
        client = SyftHubClient(base_url=base_url)

        assert hasattr(client, "syftai")
        assert isinstance(client.syftai, SyftAIResource)

    def test_syftai_resource_is_cached(
        self,
        base_url: str,
    ) -> None:
        """Test that syftai resource is lazily cached."""
        client = SyftHubClient(base_url=base_url)

        resource1 = client.syftai
        resource2 = client.syftai

        assert resource1 is resource2
