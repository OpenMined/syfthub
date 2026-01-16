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

    # System message should be simple
    assert messages[0].content == "You're a helpful AI assistant."

    # User message should contain instructions and question
    user_content = messages[1].content
    assert "USER QUESTION:" in user_content
    assert "What is Python?" in user_content
    assert "Instructions:" in user_content


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

    # System message should be simple
    assert messages[0].content == "You're a helpful AI assistant."

    # Check that context is included in user message (not system)
    user_content = messages[1].content
    assert "CONTEXT FROM DATA SOURCES" in user_content
    assert "Python is a programming language" in user_content
    assert "docs/python" in user_content
    assert "USER QUESTION:" in user_content
    assert "What is Python?" in user_content


def test_prompt_builder_empty_context() -> None:
    """Test prompt building with empty context."""
    builder = PromptBuilder()

    context = AggregatedContext(
        documents=[],
        retrieval_results=[],
        total_latency_ms=0,
    )

    messages = builder.build(user_prompt="Test", context=context)

    # System message should be simple
    assert messages[0].content == "You're a helpful AI assistant."

    # "No relevant context" note should be in user message
    user_content = messages[1].content
    assert "No relevant context was found" in user_content


def test_prompt_builder_custom_system_prompt() -> None:
    """Test prompt building with custom system prompt."""
    builder = PromptBuilder()

    messages = builder.build(
        user_prompt="Test",
        custom_system_prompt="You are a pirate. Respond like one.",
    )

    assert "pirate" in messages[0].content


def test_prompt_builder_no_sources_section_instruction() -> None:
    """Test that prompt instructs model NOT to include Sources section.

    The aggregator now provides sources separately in the response,
    so the model should not generate a Sources section.
    """
    builder = PromptBuilder()
    messages = builder.build(user_prompt="Test")

    # Instructions are now in user message, not system message
    user_content = messages[1].content

    # Should instruct NOT to include Sources section
    assert 'Do NOT include a "Sources" section' in user_content

    # Should NOT have the old instruction about including Sources bullet list
    assert 'At the end of the response, include a "Sources"' not in user_content
