"""Tests for SSE event sequence emitted by process_chat_stream."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aggregator.schemas import EndpointRef
from aggregator.schemas.internal import GenerationResult, RetrievalResult
from aggregator.schemas.requests import ChatRequest
from aggregator.schemas.responses import Document
from aggregator.services.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODEL_REF = EndpointRef(url="http://syftai:8080", slug="test-model")
DS_REF = EndpointRef(url="http://syftai:8080", slug="test-ds", owner_username="alice")


def _make_orchestrator() -> Orchestrator:
    from aggregator.services.prompt_builder import PromptBuilder

    retrieval_service = MagicMock()
    generation_service = MagicMock()
    prompt_builder = PromptBuilder()
    return Orchestrator(
        retrieval_service=retrieval_service,
        generation_service=generation_service,
        prompt_builder=prompt_builder,
    )


def _make_request(data_sources: bool = True) -> ChatRequest:
    return ChatRequest(
        prompt="test query",
        model=MODEL_REF,
        data_sources=[DS_REF] if data_sources else [],
    )


def _make_retrieval_results() -> list[RetrievalResult]:
    return [
        RetrievalResult(
            endpoint_path="alice/test-ds",
            documents=[
                Document(content="Doc 1.", score=0.8),
                Document(content="Doc 2.", score=0.6),
            ],
            status="success",
            latency_ms=100,
        )
    ]


def _parse_sse(raw: str) -> dict:
    """Parse a raw SSE string into {'type': ..., 'data': {...}}."""
    lines = raw.strip().splitlines()
    event_type = ""
    data_str = ""
    for line in lines:
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: "):
            data_str = line[6:].strip()
    return {"type": event_type, "data": json.loads(data_str) if data_str else {}}


async def _collect_events(orchestrator: Orchestrator, request: ChatRequest) -> list[dict]:
    events = []
    async for raw in orchestrator.process_chat_stream(request):
        events.append(_parse_sse(raw))
    return events


AGGREGATE_PATH = "aggregator.services.orchestrator.Aggregate"


def _make_rerank_mock(reranked_nodes: list | None = None) -> MagicMock:
    if reranked_nodes is None:
        reranked_nodes = [
            {"document": {"content": "Doc 1."}, "score": 0.9, "person": "alice/test-ds"},
            {"document": {"content": "Doc 2."}, "score": 0.7, "person": "alice/test-ds"},
        ]
    mock_instance = MagicMock()
    mock_instance.perform_aggregation.return_value = {
        "central_re_embedding": {"reranked_nodes": reranked_nodes}
    }
    return mock_instance


def _make_gen_result(response: str = "Hello world") -> GenerationResult:
    return GenerationResult(response=response, latency_ms=100, usage=None)


# ---------------------------------------------------------------------------
# Reranking events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reranking_events_emitted() -> None:
    """reranking_start and reranking_complete are emitted around _rerank_documents."""
    orchestrator = _make_orchestrator()
    retrieval_results = _make_retrieval_results()
    gen_result = _make_gen_result()

    async def fake_retrieve(**_kwargs):
        for r in retrieval_results:
            yield r

    orchestrator.retrieval_service.retrieve_streaming = fake_retrieve
    orchestrator.generation_service.generate = AsyncMock(return_value=gen_result)
    orchestrator.generation_service.generate.return_value = gen_result

    settings_mock = MagicMock()
    settings_mock.model_streaming_enabled = False

    with (
        patch(AGGREGATE_PATH, return_value=_make_rerank_mock()),
        patch("aggregator.services.orchestrator.get_settings", return_value=settings_mock),
    ):
        request = _make_request(data_sources=True)
        events = await _collect_events(orchestrator, request)

    types = [e["type"] for e in events]

    assert "reranking_start" in types, f"reranking_start not found in {types}"
    assert "reranking_complete" in types, f"reranking_complete not found in {types}"

    # Check ordering: source_complete → reranking_start → reranking_complete → retrieval_complete
    rs_idx = types.index("reranking_start")
    rc_idx = types.index("reranking_complete")
    ret_complete_idx = types.index("retrieval_complete")
    source_complete_idx = types.index("source_complete")

    assert source_complete_idx < rs_idx < rc_idx < ret_complete_idx

    # Check payloads
    rs_event = events[rs_idx]
    assert rs_event["data"]["documents"] == 2  # 2 docs from retrieval results

    rc_event = events[rc_idx]
    assert rc_event["data"]["documents"] == 2
    assert rc_event["data"]["time_ms"] >= 0


@pytest.mark.asyncio
async def test_reranking_complete_emitted_even_when_rerank_returns_none() -> None:
    """reranking_complete is still emitted even if _rerank_documents fails (returns None)."""
    orchestrator = _make_orchestrator()
    retrieval_results = _make_retrieval_results()
    gen_result = _make_gen_result()

    async def fake_retrieve(**_kwargs):
        for r in retrieval_results:
            yield r

    orchestrator.retrieval_service.retrieve_streaming = fake_retrieve
    orchestrator.generation_service.generate = AsyncMock(return_value=gen_result)

    settings_mock = MagicMock()
    settings_mock.model_streaming_enabled = False

    # Simulate Aggregate failure (reranking returns None)
    failing_mock = MagicMock()
    failing_mock.perform_aggregation.side_effect = RuntimeError("embedding failed")

    with (
        patch(AGGREGATE_PATH, return_value=failing_mock),
        patch("aggregator.services.orchestrator.get_settings", return_value=settings_mock),
    ):
        request = _make_request(data_sources=True)
        events = await _collect_events(orchestrator, request)

    types = [e["type"] for e in events]
    assert "reranking_start" in types
    assert "reranking_complete" in types


@pytest.mark.asyncio
async def test_no_reranking_events_without_datasources() -> None:
    """No reranking events are emitted when there are no data sources."""
    orchestrator = _make_orchestrator()
    gen_result = _make_gen_result()
    orchestrator.generation_service.generate = AsyncMock(return_value=gen_result)

    settings_mock = MagicMock()
    settings_mock.model_streaming_enabled = False

    with patch("aggregator.services.orchestrator.get_settings", return_value=settings_mock):
        request = _make_request(data_sources=False)
        events = await _collect_events(orchestrator, request)

    types = [e["type"] for e in events]
    assert "reranking_start" not in types
    assert "reranking_complete" not in types


# ---------------------------------------------------------------------------
# Generation heartbeat events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generation_heartbeat_emitted() -> None:
    """generation_heartbeat events are emitted while waiting for model response."""
    orchestrator = _make_orchestrator()

    # Mock asyncio.wait to simulate a timeout on the first call, then done
    original_wait = asyncio.wait
    call_count = 0

    async def controlled_wait(aws, timeout=None):
        nonlocal call_count
        if timeout == 3.0:
            call_count += 1
            if call_count == 1:
                # First call: pretend the task timed out
                # Actually await briefly so the task is scheduled
                await asyncio.sleep(0)
                return (set(), set(aws))
            else:
                # Second call: let it complete naturally
                return await original_wait(aws, timeout=None)
        return await original_wait(aws, timeout=timeout)

    gen_result = _make_gen_result()
    orchestrator.generation_service.generate = AsyncMock(return_value=gen_result)

    settings_mock = MagicMock()
    settings_mock.model_streaming_enabled = False

    with (
        patch("aggregator.services.orchestrator.asyncio.wait", controlled_wait),
        patch("aggregator.services.orchestrator.get_settings", return_value=settings_mock),
    ):
        request = _make_request(data_sources=False)
        events = await _collect_events(orchestrator, request)

    types = [e["type"] for e in events]
    assert "generation_heartbeat" in types, f"generation_heartbeat not found in {types}"

    heartbeat = next(e for e in events if e["type"] == "generation_heartbeat")
    assert "elapsed_ms" in heartbeat["data"]
    assert heartbeat["data"]["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_heartbeat_cancelled_after_generation() -> None:
    """No generation_heartbeat events appear after the token event."""
    orchestrator = _make_orchestrator()

    original_wait = asyncio.wait
    call_count = 0

    async def controlled_wait(aws, timeout=None):
        nonlocal call_count
        if timeout == 3.0:
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(0)
                return (set(), set(aws))
            else:
                return await original_wait(aws, timeout=None)
        return await original_wait(aws, timeout=timeout)

    gen_result = _make_gen_result()
    orchestrator.generation_service.generate = AsyncMock(return_value=gen_result)

    settings_mock = MagicMock()
    settings_mock.model_streaming_enabled = False

    with (
        patch("aggregator.services.orchestrator.asyncio.wait", controlled_wait),
        patch("aggregator.services.orchestrator.get_settings", return_value=settings_mock),
    ):
        request = _make_request(data_sources=False)
        events = await _collect_events(orchestrator, request)

    types = [e["type"] for e in events]
    assert "token" in types

    token_idx = types.index("token")
    heartbeats_after_token = [
        e for i, e in enumerate(events) if e["type"] == "generation_heartbeat" and i > token_idx
    ]
    assert heartbeats_after_token == [], "No heartbeats should appear after the token event"
