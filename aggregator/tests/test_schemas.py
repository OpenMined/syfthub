"""Tests for schema validation."""

import pytest
from pydantic import ValidationError

from aggregator.schemas import ChatRequest, Document, EndpointRef, Message


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
    """Test valid ChatRequest creation with SyftAI-Space format."""
    request = ChatRequest(
        prompt="What is the meaning of life?",
        user_email="user@example.com",
        model=EndpointRef(url="http://localhost:8080", slug="gpt-model"),
        data_sources=[
            EndpointRef(url="http://localhost:8080", slug="ds1", name="Dataset 1"),
            EndpointRef(url="http://localhost:8081", slug="ds2", name="Dataset 2"),
        ],
        top_k=5,
    )
    assert request.prompt == "What is the meaning of life?"
    assert request.user_email == "user@example.com"
    assert request.model.slug == "gpt-model"
    assert len(request.data_sources) == 2
    assert request.data_sources[0].slug == "ds1"
    assert request.top_k == 5
    assert request.stream is False


def test_chat_request_minimal() -> None:
    """Test ChatRequest with minimal fields."""
    request = ChatRequest(
        prompt="Hello",
        user_email="user@example.com",
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
            user_email="user@example.com",
            model=EndpointRef(url="http://localhost:8080", slug="model"),
        )


def test_chat_request_invalid_email_fails() -> None:
    """Test that invalid email is rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(
            prompt="test",
            user_email="not-an-email",
            model=EndpointRef(url="http://localhost:8080", slug="model"),
        )


def test_chat_request_top_k_bounds() -> None:
    """Test top_k validation bounds."""
    model = EndpointRef(url="http://localhost:8080", slug="model")

    # Valid range
    ChatRequest(prompt="test", user_email="user@example.com", model=model, top_k=1)
    ChatRequest(prompt="test", user_email="user@example.com", model=model, top_k=20)

    # Invalid: too low
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", user_email="user@example.com", model=model, top_k=0)

    # Invalid: too high
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", user_email="user@example.com", model=model, top_k=21)


def test_chat_request_temperature_bounds() -> None:
    """Test temperature validation bounds."""
    model = EndpointRef(url="http://localhost:8080", slug="model")

    # Valid range
    ChatRequest(prompt="test", user_email="user@example.com", model=model, temperature=0.0)
    ChatRequest(prompt="test", user_email="user@example.com", model=model, temperature=2.0)

    # Invalid: too low
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", user_email="user@example.com", model=model, temperature=-0.1)

    # Invalid: too high
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", user_email="user@example.com", model=model, temperature=2.1)


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
