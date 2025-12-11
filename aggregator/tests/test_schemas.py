"""Tests for schema validation."""

import pytest
from pydantic import ValidationError

from aggregator.schemas import ChatRequest, Document, Message


def test_chat_request_valid() -> None:
    """Test valid ChatRequest creation."""
    request = ChatRequest(
        prompt="What is the meaning of life?",
        model="owner/model-slug",
        data_sources=["owner/ds1", "owner/ds2"],
        top_k=5,
    )
    assert request.prompt == "What is the meaning of life?"
    assert request.model == "owner/model-slug"
    assert len(request.data_sources) == 2
    assert request.top_k == 5
    assert request.stream is False


def test_chat_request_minimal() -> None:
    """Test ChatRequest with minimal fields."""
    request = ChatRequest(
        prompt="Hello",
        model="owner/model",
    )
    assert request.data_sources == []
    assert request.top_k == 5  # default
    assert request.stream is False  # default


def test_chat_request_empty_prompt_fails() -> None:
    """Test that empty prompt is rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(prompt="", model="owner/model")


def test_chat_request_top_k_bounds() -> None:
    """Test top_k validation bounds."""
    # Valid range
    ChatRequest(prompt="test", model="owner/model", top_k=1)
    ChatRequest(prompt="test", model="owner/model", top_k=20)

    # Invalid: too low
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", model="owner/model", top_k=0)

    # Invalid: too high
    with pytest.raises(ValidationError):
        ChatRequest(prompt="test", model="owner/model", top_k=21)


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
