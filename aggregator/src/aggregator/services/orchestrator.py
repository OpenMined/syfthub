"""Orchestrator service - coordinates the RAG workflow with SyftAI-Space."""

import json
import logging
import time
from collections.abc import AsyncGenerator

from aggregator.core.config import get_settings
from aggregator.schemas import (
    ChatRequest,
    ChatResponse,
    EndpointRef,
    ResponseMetadata,
    SourceInfo,
    TokenUsage,
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
    Main orchestrator for the RAG workflow with SyftAI-Space.

    This orchestrator is designed for stateless operation - all required
    information (user_email, tenant_name, slug) comes from the ChatRequest.

    Coordinates:
    1. Converting EndpointRefs to ResolvedEndpoints
    2. Parallel retrieval from SyftAI-Space data source endpoints
    3. Prompt construction with retrieved context
    4. Model generation via SyftAI-Space model endpoints
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
        """Convert an EndpointRef from request to internal ResolvedEndpoint.

        Maps the request schema to the internal representation with all
        SyftAI-Space connection details including owner for token lookup.
        """
        # Construct full path as owner/slug for citation format
        if ref.owner_username:
            full_path = f"{ref.owner_username}/{ref.slug}"
        else:
            full_path = ref.slug

        return ResolvedEndpoint(
            path=full_path,  # Full path for citations (e.g., "ionesiotest/general-knowledge")
            url=ref.url,
            slug=ref.slug,
            endpoint_type=endpoint_type,  # type: ignore[arg-type]
            name=ref.name or ref.slug,
            tenant_name=ref.tenant_name,
            owner_username=ref.owner_username,
        )

    async def process_chat(
        self,
        request: ChatRequest,
        user_token: str | None = None,
    ) -> ChatResponse:
        """
        Process a chat request through the full RAG pipeline with SyftAI-Space.

        The request contains all required information for SyftAI-Space:
        - endpoint_tokens: Mapping of owner username to satellite token for auth
        - transaction_tokens: Mapping of owner username to transaction token for billing
        - model.slug, model.tenant_name, model.owner_username: For model endpoint
        - data_sources[]: For data source endpoints

        User identity is derived from the satellite tokens by SyftAI-Space,
        not passed separately in the request.

        Args:
            request: The chat request with all SyftAI-Space connection details
            user_token: Optional user token (deprecated - use endpoint_tokens instead)

        Returns:
            ChatResponse with generated answer and metadata
        """
        _ = user_token  # Deprecated - endpoint_tokens in request is used instead
        total_start = time.perf_counter()

        # Extract token mappings
        endpoint_tokens = request.endpoint_tokens
        transaction_tokens = request.transaction_tokens

        # 1. Convert model EndpointRef to ResolvedEndpoint
        model_endpoint = self._endpoint_ref_to_resolved(request.model, "model")
        logger.info(
            f"Using model: {model_endpoint.name} at {model_endpoint.url}/api/v1/endpoints/{model_endpoint.slug}/query"
        )

        # 2. Convert data source EndpointRefs to ResolvedEndpoints
        data_sources: list[ResolvedEndpoint] = [
            self._endpoint_ref_to_resolved(ds, "data_source")
            for ds in request.data_sources
        ]
        if data_sources:
            logger.info(f"Using {len(data_sources)} data sources")

        # 3. Retrieve context from SyftAI-Space data sources
        retrieval_start = time.perf_counter()
        context = await self.retrieval_service.retrieve(
            data_sources=data_sources,
            query=request.prompt,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            endpoint_tokens=endpoint_tokens,
            transaction_tokens=transaction_tokens,
        )
        retrieval_time_ms = int((time.perf_counter() - retrieval_start) * 1000)

        # 4. Build augmented prompt
        messages = self.prompt_builder.build(
            user_prompt=request.prompt,
            context=context if data_sources else None,
            custom_system_prompt=request.custom_system_prompt,
        )

        # 5. Generate response via SyftAI-Space model endpoint
        generation_start = time.perf_counter()
        try:
            result = await self.generation_service.generate(
                model_endpoint=model_endpoint,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                endpoint_tokens=endpoint_tokens,
                transaction_tokens=transaction_tokens,
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

        # Convert usage dict to TokenUsage if available
        usage = None
        if result.usage:
            usage = TokenUsage(
                prompt_tokens=result.usage.get("prompt_tokens", 0),
                completion_tokens=result.usage.get("completion_tokens", 0),
                total_tokens=result.usage.get("total_tokens", 0),
            )

        return ChatResponse(
            response=result.response,
            sources=sources,
            metadata=ResponseMetadata(
                retrieval_time_ms=retrieval_time_ms,
                generation_time_ms=generation_time_ms,
                total_time_ms=total_time_ms,
            ),
            usage=usage,
        )

    async def process_chat_stream(
        self,
        request: ChatRequest,
        user_token: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Process a chat request with streaming response via SyftAI-Space.

        Yields SSE-formatted events for real-time updates.

        Args:
            request: The chat request with all SyftAI-Space connection details
            user_token: Optional user token (deprecated - use endpoint_tokens instead)

        Yields:
            SSE-formatted event strings
        """
        _ = user_token  # Deprecated - endpoint_tokens in request is used instead
        total_start = time.perf_counter()

        # Extract token mappings
        endpoint_tokens = request.endpoint_tokens
        transaction_tokens = request.transaction_tokens

        # 1. Convert model EndpointRef to ResolvedEndpoint
        model_endpoint = self._endpoint_ref_to_resolved(request.model, "model")
        logger.info(
            f"Streaming with model: {model_endpoint.name} at {model_endpoint.url}/api/v1/endpoints/{model_endpoint.slug}/query"
        )

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
                similarity_threshold=request.similarity_threshold,
                endpoint_tokens=endpoint_tokens,
                transaction_tokens=transaction_tokens,
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
            custom_system_prompt=request.custom_system_prompt,
        )

        # 5. Generation phase with streaming (or non-streaming fallback)
        yield self._sse_event("generation_start", {})

        generation_start = time.perf_counter()
        full_response = []
        usage_data: dict | None = None
        settings = get_settings()

        try:
            # TODO: When SyftAI-Space implements model streaming, set
            # AGGREGATOR_MODEL_STREAMING_ENABLED=true to enable streaming.
            # Currently SyftAI-Space ignores the stream parameter and always
            # returns synchronous JSON, so we use the non-streaming path
            # to avoid the long pause that would occur waiting for SSE.
            if settings.model_streaming_enabled:
                # Streaming mode: yield tokens as they arrive from model
                # Note: Streaming mode doesn't provide usage data
                async for chunk in self.generation_service.generate_stream(
                    model_endpoint=model_endpoint,
                    messages=messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    endpoint_tokens=endpoint_tokens,
                    transaction_tokens=transaction_tokens,
                ):
                    full_response.append(chunk)
                    yield self._sse_event("token", {"content": chunk})
            else:
                # Non-streaming mode: get full response then yield as single token
                # This avoids the UX issue where user sees long pause before tokens
                result = await self.generation_service.generate(
                    model_endpoint=model_endpoint,
                    messages=messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    endpoint_tokens=endpoint_tokens,
                    transaction_tokens=transaction_tokens,
                )
                full_response.append(result.response)
                usage_data = result.usage  # Capture usage from non-streaming response
                yield self._sse_event("token", {"content": result.response})
        except GenerationError as e:
            yield self._sse_event("error", {"message": str(e)})
            return

        generation_time_ms = int((time.perf_counter() - generation_start) * 1000)
        total_time_ms = int((time.perf_counter() - total_start) * 1000)

        # 6. Final event with metadata and usage
        sources = [
            {
                "path": r.endpoint_path,
                "documents_retrieved": len(r.documents),
                "status": r.status,
            }
            for r in retrieval_results
        ]

        done_data: dict = {
            "sources": sources,
            "metadata": {
                "retrieval_time_ms": retrieval_time_ms,
                "generation_time_ms": generation_time_ms,
                "total_time_ms": total_time_ms,
            },
        }

        # Include usage if available (only from non-streaming mode)
        if usage_data:
            done_data["usage"] = usage_data

        yield self._sse_event("done", done_data)

    def _sse_event(self, event_type: str, data: dict) -> str:
        """Format an SSE event."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
