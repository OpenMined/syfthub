"""
Tests for Pydantic schema validation.

This module tests the request and response schemas used by the SyftAPI framework.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from syfthub_api import (
    DataSourceQueryRequest,
    DataSourceQueryResponse,
    Document,
    EndpointType,
    Message,
    ModelQueryRequest,
    ModelQueryResponse,
    ModelSummary,
    ProviderInfo,
    References,
    ResponseMessage,
    TokenUsage,
)


class TestEndpointType:
    """Tests for the EndpointType enum."""

    def test_data_source_value(self) -> None:
        """Test DATA_SOURCE enum value."""
        assert EndpointType.DATA_SOURCE.value == "data_source"

    def test_model_value(self) -> None:
        """Test MODEL enum value."""
        assert EndpointType.MODEL.value == "model"


class TestDocument:
    """Tests for the Document schema."""

    def test_create_document(self) -> None:
        """Test creating a valid Document."""
        doc = Document(
            document_id="doc-123",
            content="Test content",
            metadata={"key": "value"},
            similarity_score=0.95,
        )
        assert doc.document_id == "doc-123"
        assert doc.content == "Test content"
        assert doc.metadata == {"key": "value"}
        assert doc.similarity_score == 0.95

    def test_document_default_metadata(self) -> None:
        """Test that Document has empty dict as default metadata."""
        doc = Document(
            document_id="doc-123",
            content="Test",
            similarity_score=0.5,
        )
        assert doc.metadata == {}

    def test_document_requires_document_id(self) -> None:
        """Test that Document requires document_id."""
        with pytest.raises(ValidationError):
            Document(content="Test", similarity_score=0.5)  # type: ignore

    def test_document_requires_content(self) -> None:
        """Test that Document requires content."""
        with pytest.raises(ValidationError):
            Document(document_id="doc-123", similarity_score=0.5)  # type: ignore

    def test_document_requires_similarity_score(self) -> None:
        """Test that Document requires similarity_score."""
        with pytest.raises(ValidationError):
            Document(document_id="doc-123", content="Test")  # type: ignore


class TestMessage:
    """Tests for the Message schema."""

    def test_create_user_message(self) -> None:
        """Test creating a user message."""
        msg = Message(role="user", content="Hello!")
        assert msg.role == "user"
        assert msg.content == "Hello!"

    def test_create_assistant_message(self) -> None:
        """Test creating an assistant message."""
        msg = Message(role="assistant", content="Hi there!")
        assert msg.role == "assistant"
        assert msg.content == "Hi there!"

    def test_create_system_message(self) -> None:
        """Test creating a system message."""
        msg = Message(role="system", content="You are helpful.")
        assert msg.role == "system"
        assert msg.content == "You are helpful."

    def test_invalid_role_raises(self) -> None:
        """Test that invalid role raises ValidationError."""
        with pytest.raises(ValidationError):
            Message(role="invalid", content="Test")  # type: ignore


class TestDataSourceQueryRequest:
    """Tests for the DataSourceQueryRequest schema."""

    def test_create_with_defaults(self) -> None:
        """Test creating request with default values."""
        request = DataSourceQueryRequest(messages="search query")
        assert request.messages == "search query"
        assert request.limit == 5
        assert request.similarity_threshold == 0.5
        assert request.include_metadata is True
        assert request.transaction_token is None

    def test_create_with_custom_values(self) -> None:
        """Test creating request with custom values."""
        request = DataSourceQueryRequest(
            messages="search query",
            limit=10,
            similarity_threshold=0.8,
            include_metadata=False,
            transaction_token="token-123",
        )
        assert request.limit == 10
        assert request.similarity_threshold == 0.8
        assert request.include_metadata is False
        assert request.transaction_token == "token-123"


class TestReferences:
    """Tests for the References schema."""

    def test_create_references(self, sample_documents: list[Document]) -> None:
        """Test creating References with documents."""
        refs = References(documents=sample_documents)
        assert len(refs.documents) == 3
        assert refs.provider_info is None
        assert refs.cost is None

    def test_create_references_with_provider_info(self, sample_documents: list[Document]) -> None:
        """Test creating References with provider info."""
        provider = ProviderInfo(provider="openai", model="text-embedding-3-small")
        refs = References(documents=sample_documents, provider_info=provider, cost=0.05)
        assert refs.provider_info is not None
        assert refs.provider_info.provider == "openai"
        assert refs.cost == 0.05


class TestDataSourceQueryResponse:
    """Tests for the DataSourceQueryResponse schema."""

    def test_create_response(self, sample_documents: list[Document]) -> None:
        """Test creating a data source query response."""
        refs = References(documents=sample_documents)
        response = DataSourceQueryResponse(references=refs)
        assert response.summary is None
        assert len(response.references.documents) == 3

    def test_create_response_with_summary(self, sample_documents: list[Document]) -> None:
        """Test creating response with summary."""
        refs = References(documents=sample_documents)
        response = DataSourceQueryResponse(summary="Found 3 relevant documents.", references=refs)
        assert response.summary == "Found 3 relevant documents."


class TestModelQueryRequest:
    """Tests for the ModelQueryRequest schema."""

    def test_create_with_defaults(self, sample_messages: list[Message]) -> None:
        """Test creating request with default values."""
        request = ModelQueryRequest(messages=sample_messages)
        assert len(request.messages) == 4
        assert request.max_tokens == 1024
        assert request.temperature == 0.7
        assert request.stream is False
        assert request.stop_sequences == []
        assert request.transaction_token is None

    def test_create_with_custom_values(self, sample_messages: list[Message]) -> None:
        """Test creating request with custom values."""
        request = ModelQueryRequest(
            messages=sample_messages,
            max_tokens=2048,
            temperature=0.9,
            stream=True,
            stop_sequences=["END", "STOP"],
            transaction_token="token-456",
        )
        assert request.max_tokens == 2048
        assert request.temperature == 0.9
        assert request.stream is True
        assert request.stop_sequences == ["END", "STOP"]
        assert request.transaction_token == "token-456"


class TestResponseMessage:
    """Tests for the ResponseMessage schema."""

    def test_create_response_message(self) -> None:
        """Test creating a response message."""
        msg = ResponseMessage(content="This is the response.")
        assert msg.role == "assistant"  # Default
        assert msg.content == "This is the response."
        assert msg.tokens is None

    def test_create_with_tokens(self) -> None:
        """Test creating response message with token count."""
        msg = ResponseMessage(content="Short response.", tokens=15)
        assert msg.tokens == 15


class TestTokenUsage:
    """Tests for the TokenUsage schema."""

    def test_create_token_usage(self) -> None:
        """Test creating token usage."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150


class TestModelSummary:
    """Tests for the ModelSummary schema."""

    def test_create_model_summary(self) -> None:
        """Test creating a model summary."""
        msg = ResponseMessage(content="Response text")
        summary = ModelSummary(
            id="chatcmpl-abc123",
            model="test-model",
            message=msg,
            finish_reason="stop",
        )
        assert summary.id == "chatcmpl-abc123"
        assert summary.model == "test-model"
        assert summary.message.content == "Response text"
        assert summary.finish_reason == "stop"
        assert summary.usage is None

    def test_create_with_usage(self) -> None:
        """Test creating model summary with usage info."""
        msg = ResponseMessage(content="Response")
        usage = TokenUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75)
        summary = ModelSummary(
            id="chatcmpl-xyz789",
            model="test-model",
            message=msg,
            finish_reason="stop",
            usage=usage,
        )
        assert summary.usage is not None
        assert summary.usage.total_tokens == 75


class TestModelQueryResponse:
    """Tests for the ModelQueryResponse schema."""

    def test_create_response(self) -> None:
        """Test creating a model query response."""
        msg = ResponseMessage(content="Generated response")
        summary = ModelSummary(
            id="chatcmpl-123",
            model="test-model",
            message=msg,
            finish_reason="stop",
        )
        response = ModelQueryResponse(summary=summary)
        assert response.summary.id == "chatcmpl-123"
        assert response.summary.message.content == "Generated response"
        assert response.references is None
