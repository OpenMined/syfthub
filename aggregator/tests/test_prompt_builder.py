"""Tests for the prompt builder service."""

from aggregator.schemas import Document
from aggregator.schemas.internal import AggregatedContext, RetrievalResult
from aggregator.services import PromptBuilder


def test_prompt_builder_no_context() -> None:
    """Test prompt building without context."""
    builder = PromptBuilder()
    messages = builder.build(user_prompt="What is Python?")

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert messages[1].content == "What is Python?"


def test_prompt_builder_with_context() -> None:
    """Test prompt building with retrieved context."""
    builder = PromptBuilder()

    # Create mock context
    documents = [
        Document(content="Python is a programming language.", score=0.9),
        Document(content="It was created by Guido van Rossum.", score=0.85),
    ]
    retrieval_results = [
        RetrievalResult(
            endpoint_path="docs/python",
            documents=documents,
            status="success",
            latency_ms=100,
        )
    ]
    context = AggregatedContext(
        documents=documents,
        retrieval_results=retrieval_results,
        total_latency_ms=100,
    )

    messages = builder.build(user_prompt="What is Python?", context=context)

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[1].role == "user"

    # Check that context is included in system message
    system_content = messages[0].content
    assert "CONTEXT FROM DATA SOURCES" in system_content
    assert "Python is a programming language" in system_content
    assert "docs/python" in system_content


def test_prompt_builder_empty_context() -> None:
    """Test prompt building with empty context."""
    builder = PromptBuilder()

    context = AggregatedContext(
        documents=[],
        retrieval_results=[],
        total_latency_ms=0,
    )

    messages = builder.build(user_prompt="Test", context=context)

    system_content = messages[0].content
    assert "No relevant context was found" in system_content


def test_prompt_builder_custom_system_prompt() -> None:
    """Test prompt building with custom system prompt."""
    builder = PromptBuilder()

    messages = builder.build(
        user_prompt="Test",
        custom_system_prompt="You are a pirate. Respond like one.",
    )

    assert "pirate" in messages[0].content
