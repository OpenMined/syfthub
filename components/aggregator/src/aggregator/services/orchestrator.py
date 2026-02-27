"""Orchestrator service - coordinates the RAG workflow with SyftAI-Space."""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from federated_aggregation.aggregator import Aggregate

from aggregator.core.config import get_settings
from aggregator.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentSource,
    EndpointRef,
    ResponseMetadata,
    SourceInfo,
    TokenUsage,
)
from aggregator.schemas.internal import AggregatedContext, ResolvedEndpoint, RetrievalResult
from aggregator.schemas.responses import Document
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

    def _endpoint_ref_to_resolved(self, ref: EndpointRef, endpoint_type: str) -> ResolvedEndpoint:
        """Convert an EndpointRef from request to internal ResolvedEndpoint.

        Maps the request schema to the internal representation with all
        SyftAI-Space connection details including owner for token lookup.
        """
        # Construct full path as owner/slug for citation format
        full_path = f"{ref.owner_username}/{ref.slug}" if ref.owner_username else ref.slug

        return ResolvedEndpoint(
            path=full_path,  # Full path for citations (e.g., "ionesiotest/general-knowledge")
            url=ref.url,
            slug=ref.slug,
            endpoint_type=endpoint_type,
            name=ref.name or ref.slug,
            tenant_name=ref.tenant_name,
            owner_username=ref.owner_username,
        )

    def _build_document_sources(self, context: AggregatedContext) -> dict[str, DocumentSource]:
        """Build document sources dict from retrieval results.

        Returns a dict mapping document title to DocumentSource (slug + content).
        Handles title collisions by appending numeric suffix.

        Args:
            context: Aggregated context containing retrieval results

        Returns:
            Dict mapping document titles to DocumentSource objects
        """
        sources: dict[str, DocumentSource] = {}
        title_counts: dict[str, int] = {}

        for result in context.retrieval_results:
            if result.status != "success":
                continue

            endpoint_path = result.endpoint_path  # e.g., "john/salesforce-docs"

            for doc in result.documents:
                # Extract title with fallback
                title = (
                    doc.metadata.get("title")
                    or doc.metadata.get("document_title")
                    or f"Document from {endpoint_path}"
                )

                # Handle title collisions by appending numeric suffix
                if title in title_counts:
                    title_counts[title] += 1
                    unique_title = f"{title} ({title_counts[title]})"
                else:
                    title_counts[title] = 1
                    unique_title = title

                sources[unique_title] = DocumentSource(
                    slug=endpoint_path,
                    content=doc.content,
                )

        return sources

    @staticmethod
    def _build_aggregation_input(
        retrieval_results: list[RetrievalResult],
    ) -> dict[str, dict[str, Any]]:
        """Build input dict for federated_aggregation from retrieval results.

        Only includes successful retrieval results with documents.

        Returns:
            Dict mapping endpoint_path to source structure expected by
            Aggregate.perform_aggregation with CENTRAL_REEMBEDDING.
        """
        retrieved_nodes: dict[str, dict[str, Any]] = {}
        for result in retrieval_results:
            if result.status != "success" or not result.documents:
                continue
            retrieved_nodes[result.endpoint_path] = {
                "sources": [
                    {"document": {"content": doc.content}, "score": doc.score}
                    for doc in result.documents
                ],
                # Placeholder embeddings required by flatten_query_result; overwritten by CENTRAL_REEMBEDDING
                "document_embeddings": [[] for _ in result.documents],
                "query_embedding": None,
                "embedding_model_name": None,
                "similarity_metric": None,
            }
        return retrieved_nodes

    async def _rerank_documents(
        self,
        query: str,
        retrieval_results: list[RetrievalResult],
        top_k: int,
    ) -> tuple[list[Document], dict[int, str], dict[int, str]] | None:
        """Rerank documents using CENTRAL_REEMBEDDING.

        Re-embeds all retrieved documents into a uniform embedding space so
        cross-source scores are directly comparable.

        Returns:
            Tuple of (reranked_documents, context_dict, source_index_map)
            or None if reranking fails or no documents to rerank.
        """
        retrieved_nodes = self._build_aggregation_input(retrieval_results)
        if not retrieved_nodes:
            return None

        rerank_start = time.perf_counter()
        try:
            aggregator = Aggregate()
            results = await asyncio.to_thread(
                aggregator.perform_aggregation,
                query=query,
                retrieved_nodes=retrieved_nodes,
                method=Aggregate.CENTRAL_REEMBEDDING,
                top_k=top_k,
                model_name="BAAI/bge-base-en-v1.5",
                device="cpu",
            )
        except Exception:
            logger.error("Reranking failed, falling back to raw score sort", exc_info=True)
            return None

        rerank_ms = int((time.perf_counter() - rerank_start) * 1000)
        logger.info(f"Reranking (CENTRAL_REEMBEDDING) completed in {rerank_ms}ms")

        reranked_nodes = results["central_re_embedding"]["reranked_nodes"]

        reranked_docs: list[Document] = []
        context_dict: dict[int, str] = {}
        source_index_map: dict[int, str] = {}

        for i, node in enumerate(reranked_nodes, start=1):
            content = node["document"]["content"]
            score = node.get("score", 0.0)
            source = node.get("person", f"source_{i}")

            reranked_docs.append(Document(content=content, score=score))
            context_dict[i] = content
            source_index_map[i] = source

        return reranked_docs, context_dict, source_index_map

    @staticmethod
    def _compute_attribution(
        response: str,
        source_index_map: dict[int, str],
    ) -> dict[str, float] | None:
        """Compute profit share via LLM attribution pipeline.

        Parses <cite:[N]> tags from the generated response and computes a
        normalized fractional contribution per source.

        Returns:
            profit_share dict mapping owner/slug to fraction (0-1),
            or None if attribution fails.
        """
        try:
            from attribution import run_llm_attribution_pipeline  # noqa: PLC0415

            # Normalize [cite:N], [cite:N,M], and [cite:N-start:end] to <cite:[N]>
            # so aggregate_server_citations can parse them with its existing regex.
            # The position suffix (-start:end) is stripped; only source indices are kept.
            normalized = re.sub(
                r"\[cite:([\d,]+)(?:-\d+:\d+)?\]",
                lambda m: f"<cite:[{m.group(1)}]>",
                response,
            )
            contribution_info = run_llm_attribution_pipeline(
                generated_response=normalized,
                node_map=source_index_map,
            )
            profit_share: dict[str, float] = contribution_info.get("profit_share", {})
            return profit_share
        except Exception:
            logger.error("Attribution pipeline failed", exc_info=True)
            return None

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
        peer_channel = request.peer_channel

        # 1. Convert model EndpointRef to ResolvedEndpoint
        model_endpoint = self._endpoint_ref_to_resolved(request.model, "model")
        logger.info(
            f"Using model: {model_endpoint.name} at {model_endpoint.url}/api/v1/endpoints/{model_endpoint.slug}/query"
        )

        # 2. Convert data source EndpointRefs to ResolvedEndpoints
        data_sources: list[ResolvedEndpoint] = [
            self._endpoint_ref_to_resolved(ds, "data_source") for ds in request.data_sources
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
            peer_channel=peer_channel,
        )
        retrieval_time_ms = int((time.perf_counter() - retrieval_start) * 1000)

        # 3b. Rerank documents using federated aggregation (CENTRAL_REEMBEDDING)
        context_dict: dict[int, str] | None = None
        source_index_map: dict[int, str] | None = None

        if data_sources and context.documents:
            rerank_result = await self._rerank_documents(
                query=request.prompt,
                retrieval_results=context.retrieval_results,
                top_k=request.top_k,
            )
            if rerank_result is not None:
                reranked_docs, context_dict, source_index_map = rerank_result
                context.documents = reranked_docs

        # 4. Build augmented prompt
        messages = self.prompt_builder.build(
            user_prompt=request.prompt,
            context=context if data_sources else None,
            custom_system_prompt=request.custom_system_prompt,
            history=request.messages or None,
            context_dict=context_dict,
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
                peer_channel=peer_channel,
            )
        except GenerationError as e:
            raise OrchestratorError(f"Generation failed: {e}") from e
        generation_time_ms = int((time.perf_counter() - generation_start) * 1000)

        # 5b. Annotate, attribute, and enrich the response
        profit_share: dict[str, float] | None = None
        display_response = result.response
        if source_index_map:
            # Inject character-span info: [cite:N] → [cite:N-start:end]
            annotated = self._annotate_cite_positions(result.response)
            profit_share = self._compute_attribution(annotated, source_index_map)
            # Expose the position-annotated response so consumers can highlight cited spans
            display_response = annotated

        # 6. Build response
        total_time_ms = int((time.perf_counter() - total_start) * 1000)

        # Build retrieval info (metadata about each data source retrieval)
        retrieval_info = [
            SourceInfo(
                path=r.endpoint_path,
                documents_retrieved=len(r.documents),
                status=r.status,
                error_message=r.error_message,
            )
            for r in context.retrieval_results
        ]

        # Build document sources dict (title -> {slug, content})
        document_sources = self._build_document_sources(context)

        # Convert usage dict to TokenUsage if available
        usage = None
        if result.usage:
            usage = TokenUsage(
                prompt_tokens=result.usage.get("prompt_tokens", 0),
                completion_tokens=result.usage.get("completion_tokens", 0),
                total_tokens=result.usage.get("total_tokens", 0),
            )

        return ChatResponse(
            response=display_response,
            sources=document_sources,
            retrieval_info=retrieval_info,
            metadata=ResponseMetadata(
                retrieval_time_ms=retrieval_time_ms,
                generation_time_ms=generation_time_ms,
                total_time_ms=total_time_ms,
            ),
            usage=usage,
            profit_share=profit_share,
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
        peer_channel = request.peer_channel

        # 1. Convert model EndpointRef to ResolvedEndpoint
        model_endpoint = self._endpoint_ref_to_resolved(request.model, "model")
        logger.info(
            f"Streaming with model: {model_endpoint.name} at {model_endpoint.url}/api/v1/endpoints/{model_endpoint.slug}/query"
        )

        # 2. Convert data source EndpointRefs to ResolvedEndpoints
        data_sources: list[ResolvedEndpoint] = [
            self._endpoint_ref_to_resolved(ds, "data_source") for ds in request.data_sources
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
                peer_channel=peer_channel,
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

        # Aggregate documents (raw sort as baseline / fallback)
        all_documents = []
        for r in retrieval_results:
            if r.status == "success":
                all_documents.extend(r.documents)
        all_documents.sort(key=lambda d: d.score, reverse=True)

        # Rerank using federated aggregation (CENTRAL_REEMBEDDING)
        context_dict: dict[int, str] | None = None
        source_index_map: dict[int, str] | None = None

        if data_sources and all_documents:
            yield self._sse_event("reranking_start", {"documents": len(all_documents)})
            rerank_start = time.perf_counter()
            rerank_result = await self._rerank_documents(
                query=request.prompt,
                retrieval_results=retrieval_results,
                top_k=request.top_k,
            )
            rerank_time_ms = int((time.perf_counter() - rerank_start) * 1000)
            if rerank_result is not None:
                reranked_docs, context_dict, source_index_map = rerank_result
                all_documents = reranked_docs
            yield self._sse_event(
                "reranking_complete", {"documents": len(all_documents), "time_ms": rerank_time_ms}
            )

        yield self._sse_event(
            "retrieval_complete",
            {
                "total_documents": len(all_documents),
                "time_ms": retrieval_time_ms,
            },
        )

        # 4. Build prompt with context
        context = AggregatedContext(
            documents=all_documents,
            retrieval_results=retrieval_results,
            total_latency_ms=retrieval_time_ms,
        )

        messages = self.prompt_builder.build(
            user_prompt=request.prompt,
            context=context if data_sources else None,
            custom_system_prompt=request.custom_system_prompt,
            history=request.messages or None,
            context_dict=context_dict,
        )

        # 5. Generation phase with streaming (or non-streaming fallback)
        yield self._sse_event("generation_start", {})

        generation_start = time.perf_counter()
        full_response = []
        usage_data: dict[str, Any] | None = None
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
                # Non-streaming mode: get full response then yield as single token.
                # Emit periodic heartbeat events so the frontend can show elapsed time.
                gen_start = time.monotonic()
                gen_task = asyncio.create_task(
                    self.generation_service.generate(
                        model_endpoint=model_endpoint,
                        messages=messages,
                        max_tokens=request.max_tokens,
                        temperature=request.temperature,
                        endpoint_tokens=endpoint_tokens,
                        transaction_tokens=transaction_tokens,
                        peer_channel=peer_channel,
                    )
                )
                try:
                    while True:
                        done, _ = await asyncio.wait({gen_task}, timeout=3.0)
                        if done:
                            gen_result = gen_task.result()
                            break
                        elapsed_ms = int((time.monotonic() - gen_start) * 1000)
                        yield self._sse_event("generation_heartbeat", {"elapsed_ms": elapsed_ms})
                finally:
                    if not gen_task.done():
                        gen_task.cancel()
                full_response.append(gen_result.response)
                usage_data = gen_result.usage  # Capture usage from non-streaming response
                yield self._sse_event("token", {"content": gen_result.response})
        except GenerationError as e:
            yield self._sse_event("error", {"message": str(e)})
            return

        generation_time_ms = int((time.perf_counter() - generation_start) * 1000)
        total_time_ms = int((time.perf_counter() - total_start) * 1000)

        # 5b. Annotate, attribute, and enrich the full assembled response.
        # Streamed chunks already went to the client as raw [cite:N]; the done event
        # carries the position-annotated version so frontends can replace/highlight.
        profit_share: dict[str, float] | None = None
        annotated_response: str | None = None
        if source_index_map:
            full_response_text = "".join(full_response)
            annotated_response = self._annotate_cite_positions(full_response_text)
            profit_share = self._compute_attribution(annotated_response, source_index_map)

        # 6. Final event with metadata and usage
        # Build retrieval info (metadata about each data source retrieval)
        retrieval_info = [
            {
                "path": r.endpoint_path,
                "documents_retrieved": len(r.documents),
                "status": r.status,
            }
            for r in retrieval_results
        ]

        # Build document sources dict (title -> {slug, content})
        # Convert DocumentSource objects to dicts for JSON serialization
        document_sources = {
            title: {"slug": doc_source.slug, "content": doc_source.content}
            for title, doc_source in self._build_document_sources(context).items()
        }

        done_data: dict[str, Any] = {
            "sources": document_sources,
            "retrieval_info": retrieval_info,
            "metadata": {
                "retrieval_time_ms": retrieval_time_ms,
                "generation_time_ms": generation_time_ms,
                "total_time_ms": total_time_ms,
            },
        }

        # Include usage if available (only from non-streaming mode)
        if usage_data:
            done_data["usage"] = usage_data

        # Include profit share and position-annotated response if attribution ran
        if profit_share is not None:
            done_data["profit_share"] = profit_share
        if annotated_response is not None:
            done_data["response"] = annotated_response

        yield self._sse_event("done", done_data)

    @staticmethod
    def _annotate_cite_positions(text: str) -> str:
        """Enrich [cite:N] end-of-sentence markers with character span information.

        Converts [cite:N] → [cite:N-start:end] where start:end are the character
        positions of the attributed sentence in the CLEAN (marker-free) response.

        This allows consumers to extract the exact cited span via clean_text[start:end]
        without any further parsing of the surrounding text.

        Algorithm:
        1. Strip all raw [cite:N] markers to build a clean response, tracking
           where each marker sat in the clean string.
        2. For each marker position, walk backwards to find the sentence boundary
           (last '.', '!', '?', or newline), giving the sentence start.
        3. Re-insert annotated [cite:N-start:end] markers from right to left
           (so earlier insertions don't shift positions of later ones).
        """
        raw_pattern = re.compile(r"\[cite:([\d,]+)\]")
        matches = list(raw_pattern.finditer(text))
        if not matches:
            return text

        # Build clean text and collect (clean_pos, indices) for each marker
        clean_parts: list[str] = []
        prev_end = 0
        clean_offset = 0
        marker_info: list[tuple[int, str]] = []  # (position_in_clean, cite_indices)

        for m in matches:
            segment = text[prev_end : m.start()]
            clean_parts.append(segment)
            clean_offset += len(segment)
            marker_info.append((clean_offset, m.group(1)))
            prev_end = m.end()

        clean_parts.append(text[prev_end:])
        clean_text = "".join(clean_parts)

        def _sentence_start(s: str, end: int) -> int:
            """Return the index of the first character of the sentence ending at `end`."""
            for i in range(end - 1, -1, -1):
                if s[i] in ".!?\n":
                    start = i + 1
                    # Skip leading whitespace
                    while start < end and s[start] in " \t":
                        start += 1
                    return start
            return 0

        # Build annotated markers and insert right-to-left into clean_text
        result = clean_text
        insertions = []
        for clean_pos, indices in marker_info:
            start = _sentence_start(clean_text, clean_pos)
            insertions.append((clean_pos, f"[cite:{indices}-{start}:{clean_pos}]"))

        for clean_pos, annotated in reversed(insertions):
            result = result[:clean_pos] + annotated + result[clean_pos:]

        return result

    @staticmethod
    def _strip_cite_tags(text: str) -> str:
        """Remove attribution citation markers from response text.

        Handles all formats:
        - [cite:N] / [cite:N,M]          — raw prompt-native format
        - [cite:N-start:end]             — position-annotated format
        - <cite:[N]> / </cite>           — legacy angle-bracket format

        Collapses any extra whitespace left behind after tag removal.
        """
        # Strip [cite:...] in any form (raw, annotated, multi-source)
        stripped = re.sub(r"\[cite:[^\]]+\]", "", text)
        # Strip any residual angle-bracket variants
        stripped = re.sub(r"</?cite[^>]*>", "", stripped)
        return re.sub(r"  +", " ", stripped)

    def _sse_event(self, event_type: str, data: dict[str, Any]) -> str:
        """Format an SSE event."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
