"""Tests for the orchestrator's federated reranking and attribution pipeline."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aggregator.schemas import Document
from aggregator.schemas.internal import AggregatedContext, GenerationResult, RetrievalResult
from aggregator.services.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fed_agg_mock(reranked_nodes: list[dict]) -> ModuleType:
    """Create a mock federated_aggregation module."""
    mock_aggregate_instance = MagicMock()
    mock_aggregate_instance.perform_aggregation.return_value = {
        "central_re_embedding": {"reranked_nodes": reranked_nodes}
    }

    mock_aggregate_cls = MagicMock()
    mock_aggregate_cls.return_value = mock_aggregate_instance
    mock_aggregate_cls.CENTRAL_REEMBEDDING = "central_re_embedding"

    mock_module = MagicMock(spec=ModuleType)
    mock_module.Aggregate = mock_aggregate_cls
    return mock_module  # type: ignore[return-value]


def _make_attribution_mock(profit_share: dict[str, float] | None = None) -> ModuleType:
    """Create a mock attribution module."""
    mock_module = MagicMock(spec=ModuleType)
    return_value = {"profit_share": profit_share} if profit_share is not None else {}
    mock_module.run_llm_attribution_pipeline = MagicMock(return_value=return_value)
    return mock_module  # type: ignore[return-value]


def _make_orchestrator() -> Orchestrator:
    """Create an Orchestrator with mock services."""
    retrieval_service = MagicMock()
    generation_service = MagicMock()

    from aggregator.services.prompt_builder import PromptBuilder

    prompt_builder = PromptBuilder()
    return Orchestrator(
        retrieval_service=retrieval_service,
        generation_service=generation_service,
        prompt_builder=prompt_builder,
    )


def _make_retrieval_results() -> list[RetrievalResult]:
    """Create sample retrieval results from two data sources."""
    return [
        RetrievalResult(
            endpoint_path="alice/docs",
            documents=[
                Document(content="Alice doc 1.", score=0.8),
                Document(content="Alice doc 2.", score=0.6),
            ],
            status="success",
            latency_ms=100,
        ),
        RetrievalResult(
            endpoint_path="bob/data",
            documents=[
                Document(content="Bob doc 1.", score=0.9),
            ],
            status="success",
            latency_ms=80,
        ),
    ]


# ---------------------------------------------------------------------------
# _build_aggregation_input
# ---------------------------------------------------------------------------


def test_build_aggregation_input_transforms_results() -> None:
    """Verify _build_aggregation_input correctly transforms RetrievalResult list."""
    orchestrator = _make_orchestrator()
    results = _make_retrieval_results()

    retrieved_nodes = orchestrator._build_aggregation_input(results)

    assert set(retrieved_nodes.keys()) == {"alice/docs", "bob/data"}
    alice = retrieved_nodes["alice/docs"]
    assert len(alice["sources"]) == 2
    assert alice["sources"][0]["document"]["content"] == "Alice doc 1."
    assert alice["sources"][0]["score"] == 0.8
    assert alice["query_embedding"] is None
    assert alice["embedding_model_name"] is None

    bob = retrieved_nodes["bob/data"]
    assert len(bob["sources"]) == 1
    assert bob["sources"][0]["document"]["content"] == "Bob doc 1."


def test_build_aggregation_input_skips_failed_results() -> None:
    """Verify _build_aggregation_input skips error/timeout/empty results."""
    orchestrator = _make_orchestrator()
    results = [
        RetrievalResult(
            endpoint_path="good/source",
            documents=[Document(content="Good doc.", score=0.9)],
            status="success",
            latency_ms=50,
        ),
        RetrievalResult(
            endpoint_path="error/source",
            documents=[],
            status="error",
            latency_ms=50,
            error_message="Connection refused",
        ),
        RetrievalResult(
            endpoint_path="empty/source",
            documents=[],
            status="success",
            latency_ms=50,
        ),
    ]

    retrieved_nodes = orchestrator._build_aggregation_input(results)

    assert list(retrieved_nodes.keys()) == ["good/source"]


# ---------------------------------------------------------------------------
# _rerank_documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_documents_success() -> None:
    """Verify _rerank_documents returns correctly ordered documents."""
    orchestrator = _make_orchestrator()
    retrieval_results = _make_retrieval_results()

    reranked_nodes = [
        {"document": {"content": "Bob doc 1."}, "score": 0.95, "person": "bob/data"},
        {"document": {"content": "Alice doc 1."}, "score": 0.75, "person": "alice/docs"},
        {"document": {"content": "Alice doc 2."}, "score": 0.50, "person": "alice/docs"},
    ]
    fed_agg_mock = _make_fed_agg_mock(reranked_nodes)

    with patch.dict(
        sys.modules,
        {"federated_aggregation": fed_agg_mock, "federated_aggregation.aggregator": fed_agg_mock},
    ):
        result = await orchestrator._rerank_documents(
            query="test query",
            retrieval_results=retrieval_results,
            top_k=3,
        )

    assert result is not None
    reranked_docs, context_dict, source_index_map = result

    assert len(reranked_docs) == 3
    assert reranked_docs[0].content == "Bob doc 1."
    assert reranked_docs[0].score == 0.95
    assert reranked_docs[1].content == "Alice doc 1."

    assert context_dict == {0: "Bob doc 1.", 1: "Alice doc 1.", 2: "Alice doc 2."}
    assert source_index_map == {0: "bob/data", 1: "alice/docs", 2: "alice/docs"}


@pytest.mark.asyncio
async def test_rerank_documents_failure_returns_none() -> None:
    """Verify _rerank_documents returns None and logs error on exception."""
    orchestrator = _make_orchestrator()
    retrieval_results = _make_retrieval_results()

    failing_mock = MagicMock(spec=ModuleType)
    failing_mock.Aggregate = MagicMock()
    failing_mock.Aggregate.CENTRAL_REEMBEDDING = "central_re_embedding"
    failing_mock.Aggregate.return_value.perform_aggregation.side_effect = RuntimeError(
        "Model download failed"
    )

    with patch.dict(
        sys.modules,
        {"federated_aggregation": failing_mock, "federated_aggregation.aggregator": failing_mock},
    ):
        result = await orchestrator._rerank_documents(
            query="test query",
            retrieval_results=retrieval_results,
            top_k=5,
        )

    assert result is None


@pytest.mark.asyncio
async def test_rerank_documents_empty_input_returns_none() -> None:
    """Verify _rerank_documents returns None without calling perform_aggregation for empty input."""
    orchestrator = _make_orchestrator()

    # All results are failures — _build_aggregation_input will return empty dict
    empty_results = [
        RetrievalResult(
            endpoint_path="source/a",
            documents=[],
            status="error",
            latency_ms=50,
            error_message="Timeout",
        )
    ]

    fed_agg_mock = _make_fed_agg_mock([])

    with patch.dict(
        sys.modules,
        {"federated_aggregation": fed_agg_mock, "federated_aggregation.aggregator": fed_agg_mock},
    ):
        result = await orchestrator._rerank_documents(
            query="test query",
            retrieval_results=empty_results,
            top_k=5,
        )

    assert result is None
    # perform_aggregation should NOT have been called
    fed_agg_mock.Aggregate.return_value.perform_aggregation.assert_not_called()


# ---------------------------------------------------------------------------
# _compute_attribution
# ---------------------------------------------------------------------------


def test_compute_attribution_success() -> None:
    """Verify _compute_attribution normalizes [cite:N] to <cite:[N]> before calling pipeline."""
    source_index_map = {0: "alice/docs", 1: "bob/data"}
    attribution_mock = _make_attribution_mock({"alice/docs": 0.6, "bob/data": 0.4})

    with patch.dict(sys.modules, {"attribution": attribution_mock}):
        result = Orchestrator._compute_attribution(
            "Answer with [cite:0] and [cite:1].", source_index_map
        )

    assert result == {"alice/docs": 0.6, "bob/data": 0.4}
    # The pipeline must receive the normalized <cite:[N]> format, not the raw [cite:N] format
    attribution_mock.run_llm_attribution_pipeline.assert_called_once_with(
        generated_response="Answer with <cite:[0]> and <cite:[1]>.",
        node_map=source_index_map,
    )


def test_compute_attribution_failure_returns_none() -> None:
    """Verify _compute_attribution returns None and logs error on exception."""
    source_index_map = {0: "alice/docs"}

    failing_mock = MagicMock(spec=ModuleType)
    failing_mock.run_llm_attribution_pipeline = MagicMock(
        side_effect=ValueError("DSPy not configured")
    )

    with patch.dict(sys.modules, {"attribution": failing_mock}):
        result = Orchestrator._compute_attribution("Some response.", source_index_map)

    assert result is None


def test_compute_attribution_empty_profit_share() -> None:
    """Verify _compute_attribution returns empty dict when no citations found."""
    source_index_map = {0: "alice/docs"}
    attribution_mock = _make_attribution_mock({})

    with patch.dict(sys.modules, {"attribution": attribution_mock}):
        result = Orchestrator._compute_attribution("Response with no cite tags.", source_index_map)

    assert result == {}


# ---------------------------------------------------------------------------
# process_chat integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_chat_no_datasources_skips_reranking() -> None:
    """Verify reranking and attribution are skipped when no data sources."""
    orchestrator = _make_orchestrator()

    from aggregator.schemas.requests import ChatRequest, EndpointRef

    mock_context = AggregatedContext(documents=[], retrieval_results=[], total_latency_ms=0)
    orchestrator.retrieval_service.retrieve = AsyncMock(return_value=mock_context)
    orchestrator.generation_service.generate = AsyncMock(
        return_value=GenerationResult(response="Hello!", latency_ms=100, usage=None)
    )

    request = ChatRequest(
        prompt="Hello",
        model=EndpointRef(url="http://model", slug="gpt4", owner_username="openai"),
        data_sources=[],  # No data sources
    )

    fed_agg_mock = _make_fed_agg_mock([])
    attribution_mock = _make_attribution_mock({"source": 1.0})

    with patch.dict(
        sys.modules,
        {
            "federated_aggregation": fed_agg_mock,
            "federated_aggregation.aggregator": fed_agg_mock,
            "attribution": attribution_mock,
        },
    ):
        response = await orchestrator.process_chat(request)

    # Neither reranking nor attribution should have been invoked
    fed_agg_mock.Aggregate.return_value.perform_aggregation.assert_not_called()
    attribution_mock.run_llm_attribution_pipeline.assert_not_called()
    assert response.profit_share is None


@pytest.mark.asyncio
async def test_process_chat_empty_documents_skips_reranking() -> None:
    """Verify reranking and attribution are skipped when retrieval returns zero documents."""
    orchestrator = _make_orchestrator()

    from aggregator.schemas.requests import ChatRequest, EndpointRef

    mock_context = AggregatedContext(
        documents=[],
        retrieval_results=[
            RetrievalResult(
                endpoint_path="alice/docs",
                documents=[],
                status="success",
                latency_ms=50,
            )
        ],
        total_latency_ms=50,
    )
    orchestrator.retrieval_service.retrieve = AsyncMock(return_value=mock_context)
    orchestrator.generation_service.generate = AsyncMock(
        return_value=GenerationResult(response="No docs found.", latency_ms=80, usage=None)
    )

    request = ChatRequest(
        prompt="Find something",
        model=EndpointRef(url="http://model", slug="gpt4", owner_username="openai"),
        data_sources=[EndpointRef(url="http://space", slug="docs", owner_username="alice")],
    )

    fed_agg_mock = _make_fed_agg_mock([])
    attribution_mock = _make_attribution_mock({"source": 1.0})

    with patch.dict(
        sys.modules,
        {
            "federated_aggregation": fed_agg_mock,
            "federated_aggregation.aggregator": fed_agg_mock,
            "attribution": attribution_mock,
        },
    ):
        response = await orchestrator.process_chat(request)

    fed_agg_mock.Aggregate.return_value.perform_aggregation.assert_not_called()
    attribution_mock.run_llm_attribution_pipeline.assert_not_called()
    assert response.profit_share is None


@pytest.mark.asyncio
async def test_process_chat_with_reranking_and_attribution() -> None:
    """Integration test: reranking + attribution both succeed, profit_share populated."""
    orchestrator = _make_orchestrator()

    from aggregator.schemas.requests import ChatRequest, EndpointRef

    docs = [Document(content="Doc A.", score=0.7), Document(content="Doc B.", score=0.9)]
    retrieval_result = RetrievalResult(
        endpoint_path="alice/docs",
        documents=docs,
        status="success",
        latency_ms=50,
    )
    mock_context = AggregatedContext(
        documents=docs,
        retrieval_results=[retrieval_result],
        total_latency_ms=50,
    )
    orchestrator.retrieval_service.retrieve = AsyncMock(return_value=mock_context)
    orchestrator.generation_service.generate = AsyncMock(
        return_value=GenerationResult(response="Answer using [cite:0].", latency_ms=200, usage=None)
    )

    request = ChatRequest(
        prompt="What is in Doc A?",
        model=EndpointRef(url="http://model", slug="gpt4", owner_username="openai"),
        data_sources=[EndpointRef(url="http://space", slug="docs", owner_username="alice")],
    )

    reranked = [
        {"document": {"content": "Doc B."}, "score": 0.95, "person": "alice/docs"},
        {"document": {"content": "Doc A."}, "score": 0.65, "person": "alice/docs"},
    ]
    fed_agg_mock = _make_fed_agg_mock(reranked)
    attribution_mock = _make_attribution_mock({"alice/docs": 1.0})

    with patch.dict(
        sys.modules,
        {
            "federated_aggregation": fed_agg_mock,
            "federated_aggregation.aggregator": fed_agg_mock,
            "attribution": attribution_mock,
        },
    ):
        response = await orchestrator.process_chat(request)

    assert response.profit_share == {"alice/docs": 1.0}
    # Response must contain the position-annotated marker, not the raw [cite:0]
    assert response.response is not None
    assert "[cite:0-" in response.response
    # The surrounding prose must be intact
    assert "Answer using" in response.response


# ---------------------------------------------------------------------------
# _annotate_cite_positions
# ---------------------------------------------------------------------------


def test_annotate_cite_positions_single_sentence() -> None:
    """Verify [cite:N] at end of sentence gets annotated with correct span."""
    text = "Python is a language [cite:0]."
    result = Orchestrator._annotate_cite_positions(text)
    # The annotated marker must encode the sentence start (0) and where
    # the citation sits in the clean text (len("Python is a language ") = 21)
    assert "[cite:0-0:21]" in result
    # The surrounding text must be intact
    assert "Python is a language" in result


def test_annotate_cite_positions_multiple_sentences() -> None:
    """Verify each [cite:N] gets the span of its own sentence."""
    text = "First claim [cite:0]. Second claim [cite:1]."
    result = Orchestrator._annotate_cite_positions(text)
    # After stripping raw markers, clean text = "First claim . Second claim ."
    # First sentence starts at 0, marker sits at 12 ("First claim ")
    assert "[cite:0-0:12]" in result
    # Second sentence starts after ". " → position 14, marker at 26
    assert "[cite:1-14:27]" in result


def test_annotate_cite_positions_no_markers_unchanged() -> None:
    """Verify text without [cite:N] is returned as-is."""
    text = "Plain text with no citations."
    assert Orchestrator._annotate_cite_positions(text) == text


def test_annotate_cite_positions_multi_source() -> None:
    """Verify [cite:N,M] multi-source markers are also annotated."""
    text = "A combined claim [cite:0,1]."
    result = Orchestrator._annotate_cite_positions(text)
    assert "[cite:0,1-" in result


# ---------------------------------------------------------------------------
# _strip_cite_tags
# ---------------------------------------------------------------------------


def test_strip_cite_tags_square_bracket_format() -> None:
    """Verify [cite:N] (prompt-native format) markers are removed."""
    result = Orchestrator._strip_cite_tags(
        "Python is interpreted [cite:0]. It is dynamic [cite:1,2]."
    )
    assert result == "Python is interpreted . It is dynamic ."


def test_strip_cite_tags_annotated_format() -> None:
    """Verify position-annotated [cite:N-start:end] markers are also stripped."""
    result = Orchestrator._strip_cite_tags(
        "Python is interpreted [cite:0-0:21]. It is dynamic [cite:1,2-22:35]."
    )
    assert result == "Python is interpreted . It is dynamic ."


def test_strip_cite_tags_legacy_angle_bracket_format() -> None:
    """Verify legacy <cite:[N]> and </cite> formats are also stripped."""
    result = Orchestrator._strip_cite_tags(
        "Python is interpreted <cite:[0]>. It is dynamic <cite:[1,2]>.</cite>"
    )
    assert result == "Python is interpreted . It is dynamic ."


def test_strip_cite_tags_collapses_double_spaces() -> None:
    """Verify extra whitespace left by removed tags is collapsed to single space."""
    result = Orchestrator._strip_cite_tags("Claim  [cite:0-0:5]  rest.")
    assert "  " not in result


def test_strip_cite_tags_no_tags_unchanged() -> None:
    """Verify text without cite tags is returned unchanged."""
    original = "Plain answer with no citations."
    assert Orchestrator._strip_cite_tags(original) == original


def test_strip_cite_tags_all_tags_empty_content() -> None:
    """Verify that a response consisting entirely of cite tags becomes effectively empty."""
    result = Orchestrator._strip_cite_tags("[cite:0][cite:1][cite:3]")
    assert result.strip() == ""
