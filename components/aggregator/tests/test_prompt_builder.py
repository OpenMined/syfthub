"""Tests for the prompt builder service."""

from aggregator.schemas import Document
from aggregator.schemas.internal import AggregatedContext, RetrievalResult
from aggregator.services import PromptBuilder


def test_prompt_builder_no_context() -> None:
    """Test prompt building without context (no data sources configured).

    When no data sources are configured, the model should act as a normal
    helpful assistant using general knowledge.
    """
    builder = PromptBuilder()
    messages = builder.build(user_prompt="What is Python?")

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[1].role == "user"

    # System message should describe adaptive behavior
    assert "knowledgeable AI assistant" in messages[0].content
    assert "WHEN DOCUMENTS ARE PROVIDED" in messages[0].content
    assert "WHEN NO DOCUMENTS ARE PROVIDED" in messages[0].content

    # User message should contain no-context instructions and question
    user_content = messages[1].content
    assert "USER QUESTION:" in user_content
    assert "What is Python?" in user_content
    # Should instruct model to use general knowledge (not refuse)
    assert "No data sources are configured" in user_content
    assert "general knowledge" in user_content


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

    # System message should describe document-grounded behavior when docs provided
    assert "WHEN DOCUMENTS ARE PROVIDED" in messages[0].content
    assert "Ground your answers in the provided documents" in messages[0].content

    # Check that context is included in user message with XML structure
    user_content = messages[1].content
    assert "<documents>" in user_content
    assert "</documents>" in user_content
    assert "<document index=" in user_content
    assert "<source>docs/python</source>" in user_content
    assert "Python is a programming language" in user_content
    assert "USER QUESTION:" in user_content
    assert "What is Python?" in user_content
    # Check semantic matching guidance is present
    assert "semantically" in user_content.lower()
    assert "Different terminology" in user_content


def test_prompt_builder_empty_context() -> None:
    """Test prompt building with empty context (data sources configured but no docs retrieved).

    When data sources are configured but return no documents, the model should
    use hybrid mode: acknowledge the empty results but can help with general questions.
    """
    builder = PromptBuilder()

    context = AggregatedContext(
        documents=[],
        retrieval_results=[],
        total_latency_ms=0,
    )

    messages = builder.build(user_prompt="Test", context=context)

    # System message should describe adaptive behavior
    assert "knowledgeable AI assistant" in messages[0].content

    # User message should contain empty-context instructions
    user_content = messages[1].content
    assert "did not return any documents" in user_content
    # Should mention the refusal option for document-specific questions
    assert "The provided documents do not contain information" in user_content
    # Should allow helping with general questions
    assert "general" in user_content.lower()


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
    This instruction is only relevant when documents are provided.
    """
    builder = PromptBuilder()

    # Create mock context with documents
    documents = [
        Document(content="Test content", score=0.9),
    ]
    retrieval_results = [
        RetrievalResult(
            endpoint_path="test/source",
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

    messages = builder.build(user_prompt="Test", context=context)

    # Instructions are in user message when documents are provided
    user_content = messages[1].content

    # Should instruct NOT to add Sources section (handled by system)
    assert 'Do NOT add a "Sources" section' in user_content

    # Should NOT have the old instruction about including Sources bullet list
    assert 'At the end of the response, include a "Sources"' not in user_content


def test_prompt_builder_semantic_matching_guidance() -> None:
    """Test that prompt includes semantic matching and inference guidance.

    The improved prompt should guide the model to:
    - Match semantically, not just literally
    - Allow valid inferences from document content
    - Distinguish between inference and hallucination
    """
    builder = PromptBuilder()

    # Create mock context with documents
    documents = [
        Document(content="Revenue data for analysis", score=0.9),
    ]
    retrieval_results = [
        RetrievalResult(
            endpoint_path="test/source",
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

    messages = builder.build(user_prompt="Test", context=context)
    user_content = messages[1].content

    # Should include semantic matching guidance
    assert "semantically" in user_content.lower()
    assert "Different terminology" in user_content

    # Should define valid inference vs hallucination
    assert "VALID INFERENCE" in user_content
    assert "HALLUCINATION" in user_content

    # Should allow logical inferences
    assert "logical inferences" in user_content.lower()


def test_prompt_builder_with_context_dict() -> None:
    """Test that the native citation prompt is built when context_dict is provided."""
    builder = PromptBuilder()

    documents = [Document(content="Python is a programming language.", score=0.9)]
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
    context_dict = {0: "Python is a programming language."}

    messages = builder.build(
        user_prompt="What is Python?",
        context=context,
        context_dict=context_dict,
    )

    assert len(messages) == 2
    user_content = messages[1].content
    # Source should appear with its numbered index
    assert "[0]: Python is a programming language." in user_content
    # Citation format instruction must be present
    assert "[cite:N]" in user_content
    # User question must be embedded
    assert "What is Python?" in user_content
    # Must NOT end with a completion-style suffix
    assert not user_content.rstrip().endswith("Answer:")


def test_prompt_builder_with_multiple_context_dict_sources() -> None:
    """Test that all sources appear in index order in the citation prompt."""
    builder = PromptBuilder()

    documents = [
        Document(content="Doc A content.", score=0.9),
        Document(content="Doc B content.", score=0.8),
        Document(content="Doc C content.", score=0.7),
    ]
    retrieval_results = [
        RetrievalResult(
            endpoint_path="source/a",
            documents=documents,
            status="success",
            latency_ms=50,
        )
    ]
    context = AggregatedContext(
        documents=documents,
        retrieval_results=retrieval_results,
        total_latency_ms=50,
    )
    context_dict = {0: "Doc A content.", 1: "Doc B content.", 2: "Doc C content."}

    messages = builder.build(
        user_prompt="Tell me about the docs.",
        context=context,
        context_dict=context_dict,
    )

    user_content = messages[1].content
    assert "[0]: Doc A content." in user_content
    assert "[1]: Doc B content." in user_content
    assert "[2]: Doc C content." in user_content
    # Sources must appear in index order
    assert user_content.index("[0]:") < user_content.index("[1]:") < user_content.index("[2]:")


def test_prompt_builder_citation_prompt_instructs_prose_not_only_tags() -> None:
    """Test that the citation prompt instructs inline tags, not wrapper-only output."""
    builder = PromptBuilder()

    documents = [Document(content="Some fact.", score=0.9)]
    retrieval_results = [
        RetrievalResult(
            endpoint_path="src/fact",
            documents=documents,
            status="success",
            latency_ms=50,
        )
    ]
    context = AggregatedContext(
        documents=documents,
        retrieval_results=retrieval_results,
        total_latency_ms=50,
    )
    context_dict = {0: "Some fact."}

    messages = builder.build(
        user_prompt="What is the fact?",
        context=context,
        context_dict=context_dict,
    )

    user_content = messages[1].content
    # Must instruct end-of-sentence citation placement
    assert "[cite:N]" in user_content
    # Must not use a completion-style prompt suffix
    assert not user_content.rstrip().endswith("Answer:")


def test_prompt_builder_no_context_dict_uses_xml_prompt() -> None:
    """Test that existing XML prompt is used when context_dict is None (backward compat)."""
    builder = PromptBuilder()

    documents = [Document(content="Python is interpreted.", score=0.9)]
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

    # No context_dict → should use the existing XML format
    messages = builder.build(user_prompt="What is Python?", context=context)

    user_content = messages[1].content
    assert "<documents>" in user_content
    assert "<document index=" in user_content
    assert "Python is interpreted." in user_content
    assert "USER QUESTION:" in user_content


def test_prompt_builder_refusal_as_last_resort() -> None:
    """Test that refusal is positioned as last resort, not default.

    The improved prompt should make refusal step 4 (last resort),
    not emphasize it repeatedly as the primary safe behavior.
    """
    builder = PromptBuilder()

    # Create mock context with documents
    documents = [
        Document(content="Some content", score=0.9),
    ]
    retrieval_results = [
        RetrievalResult(
            endpoint_path="test/source",
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

    messages = builder.build(user_prompt="Test", context=context)
    user_content = messages[1].content

    # Refusal should be positioned as step 4 (last resort)
    assert "4. Only if the documents genuinely lack" in user_content

    # Should NOT have excessive negative framing like the old prompt
    assert "CRITICAL RULES" not in user_content
    assert "EXCLUSIVELY" not in user_content
    # Count of "MUST" should be minimal (only in refusal context)
    must_count = user_content.count("MUST")
    assert must_count <= 1, f"Too many 'MUST' occurrences ({must_count}), reduces flexibility"
