"""Orchestrator service - coordinates the RAG workflow."""

import json
import logging
import time
from collections.abc import AsyncGenerator

from aggregator.schemas import (
    ChatRequest,
    ChatResponse,
    EndpointRef,
    ResponseMetadata,
    SourceInfo,
)
from aggregator.schemas.internal import ResolvedEndpoint
from aggregator.services.generation import GenerationError, GenerationService
from aggregator.services.prompt_builder import PromptBuilder
from aggregator.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """Error in orchestration."""

    pass


class Orchestrator:
    """
    Main orchestrator for the RAG workflow.

    Coordinates:
    1. Direct endpoint access via URLs (no resolution needed)
    2. Parallel retrieval from data sources
    3. Prompt construction with context
    4. Model generation
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        generation_service: GenerationService,
        prompt_builder: PromptBuilder,
    ):
        self.retrieval_service = retrieval_service
        self.generation_service = generation_service
        self.prompt_builder = prompt_builder

    def _endpoint_ref_to_resolved(
        self, ref: EndpointRef, endpoint_type: str
    ) -> ResolvedEndpoint:
        """Convert an EndpointRef from request to internal ResolvedEndpoint."""
        return ResolvedEndpoint(
            path=ref.name or "unknown",
            url=ref.url,
            endpoint_type=endpoint_type,  # type: ignore[arg-type]
            name=ref.name or "Unnamed Endpoint",
        )

    async def process_chat(
        self,
        request: ChatRequest,
        user_token: str | None = None,
    ) -> ChatResponse:
        """
        Process a chat request through the full RAG pipeline.

        Args:
            request: The chat request (contains URLs directly)
            user_token: Optional user token (unused - kept for API compatibility)

        Returns:
            ChatResponse with generated answer and metadata
        """
        _ = user_token  # Unused - URLs are provided directly in request
        total_start = time.perf_counter()

        # 1. Convert model EndpointRef to ResolvedEndpoint (no resolution needed)
        model_endpoint = self._endpoint_ref_to_resolved(request.model, "model")
        logger.info(f"Using model: {model_endpoint.name} at {model_endpoint.url}")

        # 2. Convert data source EndpointRefs to ResolvedEndpoints
        data_sources: list[ResolvedEndpoint] = [
            self._endpoint_ref_to_resolved(ds, "data_source")
            for ds in request.data_sources
        ]
        if data_sources:
            logger.info(f"Using {len(data_sources)} data sources")

        # 3. Retrieve context from data sources
        retrieval_start = time.perf_counter()
        context = await self.retrieval_service.retrieve(
            data_sources=data_sources,
            query=request.prompt,
            top_k=request.top_k,
        )
        retrieval_time_ms = int((time.perf_counter() - retrieval_start) * 1000)

        # 4. Build augmented prompt
        messages = self.prompt_builder.build(
            user_prompt=request.prompt,
            context=context if data_sources else None,
        )

        # 5. Generate response
        generation_start = time.perf_counter()
        try:
            result = await self.generation_service.generate(
                model_url=model_endpoint.url,
                messages=messages,
            )
        except GenerationError as e:
            raise OrchestratorError(f"Generation failed: {e}") from e
        generation_time_ms = int((time.perf_counter() - generation_start) * 1000)

        # 6. Build response
        total_time_ms = int((time.perf_counter() - total_start) * 1000)

        sources = [
            SourceInfo(
                path=r.endpoint_path,
                documents_retrieved=len(r.documents),
                status=r.status,
                error_message=r.error_message,
            )
            for r in context.retrieval_results
        ]

        return ChatResponse(
            response=result.response,
            sources=sources,
            metadata=ResponseMetadata(
                retrieval_time_ms=retrieval_time_ms,
                generation_time_ms=generation_time_ms,
                total_time_ms=total_time_ms,
            ),
        )

    async def process_chat_stream(
        self,
        request: ChatRequest,
        user_token: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Process a chat request with streaming response.

        Yields SSE-formatted events for real-time updates.

        Args:
            request: The chat request (contains URLs directly)
            user_token: Optional user token (unused - kept for API compatibility)

        Yields:
            SSE-formatted event strings
        """
        _ = user_token  # Unused - URLs are provided directly in request
        total_start = time.perf_counter()

        # 1. Convert model EndpointRef to ResolvedEndpoint (no resolution needed)
        model_endpoint = self._endpoint_ref_to_resolved(request.model, "model")
        logger.info(f"Streaming with model: {model_endpoint.name} at {model_endpoint.url}")

        # 2. Convert data source EndpointRefs to ResolvedEndpoints
        data_sources: list[ResolvedEndpoint] = [
            self._endpoint_ref_to_resolved(ds, "data_source")
            for ds in request.data_sources
        ]

        # 3. Retrieval phase with progress events
        yield self._sse_event(
            "retrieval_start",
            {"sources": len(data_sources)},
        )

        retrieval_start = time.perf_counter()
        retrieval_results = []

        if data_sources:
            async for result in self.retrieval_service.retrieve_streaming(
                data_sources=data_sources,
                query=request.prompt,
                top_k=request.top_k,
            ):
                retrieval_results.append(result)
                yield self._sse_event(
                    "source_complete",
                    {
                        "path": result.endpoint_path,
                        "status": result.status,
                        "documents": len(result.documents),
                    },
                )

        retrieval_time_ms = int((time.perf_counter() - retrieval_start) * 1000)

        # Aggregate documents
        all_documents = []
        for r in retrieval_results:
            if r.status == "success":
                all_documents.extend(r.documents)
        all_documents.sort(key=lambda d: d.score, reverse=True)

        yield self._sse_event(
            "retrieval_complete",
            {
                "total_documents": len(all_documents),
                "time_ms": retrieval_time_ms,
            },
        )

        # 4. Build prompt with context
        from aggregator.schemas.internal import AggregatedContext

        context = AggregatedContext(
            documents=all_documents,
            retrieval_results=retrieval_results,
            total_latency_ms=retrieval_time_ms,
        )

        messages = self.prompt_builder.build(
            user_prompt=request.prompt,
            context=context if data_sources else None,
        )

        # 5. Generation phase with streaming
        yield self._sse_event("generation_start", {})

        generation_start = time.perf_counter()
        full_response = []

        try:
            async for chunk in self.generation_service.generate_stream(
                model_url=model_endpoint.url,
                messages=messages,
            ):
                full_response.append(chunk)
                yield self._sse_event("token", {"content": chunk})
        except GenerationError as e:
            yield self._sse_event("error", {"message": str(e)})
            return

        generation_time_ms = int((time.perf_counter() - generation_start) * 1000)
        total_time_ms = int((time.perf_counter() - total_start) * 1000)

        # 6. Final event with metadata
        sources = [
            {
                "path": r.endpoint_path,
                "documents_retrieved": len(r.documents),
                "status": r.status,
            }
            for r in retrieval_results
        ]

        yield self._sse_event(
            "done",
            {
                "sources": sources,
                "metadata": {
                    "retrieval_time_ms": retrieval_time_ms,
                    "generation_time_ms": generation_time_ms,
                    "total_time_ms": total_time_ms,
                },
            },
        )

    def _sse_event(self, event_type: str, data: dict) -> str:
        """Format an SSE event."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
