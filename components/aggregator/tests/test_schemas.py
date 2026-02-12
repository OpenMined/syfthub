"""Tests for schema validation."""

import pytest
from pydantic import ValidationError

from aggregator.schemas import (
    ChatRequest,
    ChatResponse,
    Document,
    DocumentSource,
    EndpointRef,
    Message,
    ResponseMetadata,
    SourceInfo,
)


def test_endpoint_ref_valid() -> None:
    """Test valid EndpointRef creation."""
    ref = EndpointRef(
        url="http://localhost:8080",
        slug="my-endpoint",
        name="My Endpoint",
        tenant_name="acme-corp",
    )
    assert ref.url == "http://localhost:8080"
    assert ref.slug == "my-endpoint"
    assert ref.name == "My Endpoint"
    assert ref.tenant_name == "acme-corp"


def test_endpoint_ref_minimal() -> None:
    """Test EndpointRef with only required fields."""
    ref = EndpointRef(url="http://localhost:8080", slug="my-endpoint")
    assert ref.name == ""
    assert ref.tenant_name is None


def test_chat_request_valid() -> None:
    """Test valid ChatRequest creation with SyftAI-Space format.

    Note: user_email is no longer in the request - identity is derived
    from satellite tokens by SyftAI-Space.
    """
    request = ChatRequest(
        prompt="What is the meaning of life?",
        model=EndpointRef(url="http://localhost:8080", slug="gpt-model"),
        data_sources=[
            EndpointRef(url="http://localhost:8080", slug="ds1", name="Dataset 1"),
            EndpointRef(url="http://localhost:8081", slug="ds2", name="Dataset 2"),
        ],
        top_k=5,
    )
    assert request.prompt == "What is the meaning of life?"
    assert request.model.slug == "gpt-model"
    assert len(request.data_sources) == 2
    assert request.data_sources[0].slug == "ds1"
    assert request.top_k == 5
    assert request.stream is False


def test_chat_request_minimal() -> None:
    """Test ChatRequest with minimal fields."""
    request = ChatRequest(
        prompt="Hello",
        model=EndpointRef(url="http://localhost:8080", slug="model"),
    )
    assert request.data_sources == []
    assert request.top_k == 5  # default
    assert request.stream is False  # default
    assert request.max_tokens == 1024  # default
    assert request.temperature == 0.7  # default
    assert request.similarity_threshold == 0.5  # default


def test_chat_request_empty_prompt_fails() -> None:
    """Test that empty prompt is rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(
            prompt="",
            model=EndpointRef(url="http://localhost:8080", slug="model"),
        )


def test_chat_request_top_k_bounds() -> None:
    """Test top_k validation bounds."""
    model = EndpointRef(url="http://localhost:8080", slug="model")

    # Valid range
    ChatRequest(prompt="test", model=model, top_k=1)
    ChatRequest(prompt="test", model=model, top_k=20)

    # Invalid: too low
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", model=model, top_k=0)

    # Invalid: too high
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", model=model, top_k=21)


def test_chat_request_temperature_bounds() -> None:
    """Test temperature validation bounds."""
    model = EndpointRef(url="http://localhost:8080", slug="model")

    # Valid range
    ChatRequest(prompt="test", model=model, temperature=0.0)
    ChatRequest(prompt="test", model=model, temperature=2.0)

    # Invalid: too low
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", model=model, temperature=-0.1)

    # Invalid: too high
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", model=model, temperature=2.1)


def test_message_roles() -> None:
    """Test Message with different roles."""
    system = Message(role="system", content="You are helpful.")
    user = Message(role="user", content="Hello")
    assistant = Message(role="assistant", content="Hi there!")

    assert system.role == "system"
    assert user.role == "user"
    assert assistant.role == "assistant"


def test_document_defaults() -> None:
    """Test Document default values."""
    doc = Document(content="Some text")
    assert doc.content == "Some text"
    assert doc.score == 0.0
    assert doc.metadata == {}


def test_document_with_metadata() -> None:
    """Test Document with metadata."""
    doc = Document(
        content="Some text",
        score=0.95,
        metadata={"source": "file.txt", "page": 1},
    )
    assert doc.score == 0.95
    assert doc.metadata["source"] == "file.txt"


def test_document_source_valid() -> None:
    """Test valid DocumentSource creation."""
    doc_source = DocumentSource(
        slug="john/salesforce-docs",
        content="Federated search allows organizations to query multiple systems.",
    )
    assert doc_source.slug == "john/salesforce-docs"
    assert "Federated search" in doc_source.content


def test_chat_response_with_new_sources_format() -> None:
    """Test ChatResponse with new sources format (dict of DocumentSource)."""
    response = ChatResponse(
        response="This is the generated response.",
        sources={
            "Federated Search Overview": DocumentSource(
                slug="john/salesforce-docs",
                content="Federated search allows organizations to query multiple systems.",
            ),
            "Security Best Practices": DocumentSource(
                slug="mary/security-wiki",
                content="Federated architectures reduce data duplication risks.",
            ),
        },
        retrieval_info=[
            SourceInfo(
                path="john/salesforce-docs",
                documents_retrieved=1,
                status="success",
            ),
            SourceInfo(
                path="mary/security-wiki",
                documents_retrieved=1,
                status="success",
            ),
        ],
        metadata=ResponseMetadata(
            retrieval_time_ms=150,
            generation_time_ms=500,
            total_time_ms=650,
        ),
    )

    assert response.response == "This is the generated response."
    assert len(response.sources) == 2
    assert "Federated Search Overview" in response.sources
    assert response.sources["Federated Search Overview"].slug == "john/salesforce-docs"
    assert "Federated search" in response.sources["Federated Search Overview"].content
    assert len(response.retrieval_info) == 2
    assert response.retrieval_info[0].path == "john/salesforce-docs"
    assert response.metadata.total_time_ms == 650


def test_chat_response_empty_sources() -> None:
    """Test ChatResponse with no sources (no data sources queried)."""
    response = ChatResponse(
        response="General knowledge response.",
        sources={},
        retrieval_info=[],
        metadata=ResponseMetadata(
            retrieval_time_ms=0,
            generation_time_ms=300,
            total_time_ms=300,
        ),
    )

    assert response.sources == {}
    assert response.retrieval_info == []
