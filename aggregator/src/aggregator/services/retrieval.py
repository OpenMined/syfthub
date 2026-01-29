"""Retrieval service for querying SyftAI-Space data sources in parallel."""

import asyncio
import logging
import time

from aggregator.clients.data_source import DataSourceClient
from aggregator.clients.tunnel import TunnelClient, extract_tunnel_username, is_tunneled_url
from aggregator.schemas.internal import AggregatedContext, ResolvedEndpoint, RetrievalResult

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for retrieving context from multiple SyftAI-Space data sources.

    Supports both HTTP endpoints and tunneled endpoints (via MQ).
    """

    def __init__(
        self,
        data_source_client: DataSourceClient,
        tunnel_client: TunnelClient | None = None,
    ):
        self.data_source_client = data_source_client
        self.tunnel_client = tunnel_client

    def _get_token_for_endpoint(
        self, endpoint: ResolvedEndpoint, token_mapping: dict[str, str]
    ) -> str | None:
        """Get a token for an endpoint based on its owner username."""
        if endpoint.owner_username and endpoint.owner_username in token_mapping:
            return token_mapping[endpoint.owner_username]
        return None

    async def _query_single_source(
        self,
        ds: ResolvedEndpoint,
        query: str,
        top_k: int,
        similarity_threshold: float,
        endpoint_tokens: dict[str, str],
        transaction_tokens: dict[str, str],
        response_queue_id: str | None,
        response_queue_token: str | None,
    ) -> RetrievalResult:
        """Query a single data source, routing to HTTP or tunnel as appropriate."""
        if is_tunneled_url(ds.url):
            # Tunneled endpoint - use MQ
            if not self.tunnel_client:
                return RetrievalResult(
                    endpoint_path=ds.path,
                    documents=[],
                    status="error",
                    error_message="Tunnel client not configured",
                    latency_ms=0,
                )
            if not response_queue_id or not response_queue_token:
                return RetrievalResult(
                    endpoint_path=ds.path,
                    documents=[],
                    status="error",
                    error_message="Tunneled endpoints require response_queue_id and response_queue_token",
                    latency_ms=0,
                )

            satellite_token = self._get_token_for_endpoint(ds, endpoint_tokens)
            if not satellite_token:
                return RetrievalResult(
                    endpoint_path=ds.path,
                    documents=[],
                    status="error",
                    error_message="Satellite token required for tunneled endpoint",
                    latency_ms=0,
                )

            return await self.tunnel_client.query_data_source(
                target_username=extract_tunnel_username(ds.url),
                endpoint_slug=ds.slug,
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                satellite_token=satellite_token,
                response_queue_id=response_queue_id,
                response_queue_token=response_queue_token,
                endpoint_path=ds.path,
                transaction_token=self._get_token_for_endpoint(ds, transaction_tokens),
            )
        else:
            # HTTP endpoint
            return await self.data_source_client.query(
                url=ds.url,
                slug=ds.slug,
                endpoint_path=ds.path,
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                tenant_name=ds.tenant_name,
                authorization_token=self._get_token_for_endpoint(ds, endpoint_tokens),
                transaction_token=self._get_token_for_endpoint(ds, transaction_tokens),
            )

    async def retrieve(
        self,
        data_sources: list[ResolvedEndpoint],
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
        response_queue_id: str | None = None,
        response_queue_token: str | None = None,
    ) -> AggregatedContext:
        """
        Retrieve relevant documents from multiple SyftAI-Space data sources in parallel.

        Supports both HTTP endpoints and tunneled endpoints (via MQ).
        User identity is derived from satellite tokens by SyftAI-Space.

        Args:
            data_sources: List of resolved data source endpoints
            query: The search query
            top_k: Number of documents to retrieve per source
            similarity_threshold: Minimum similarity score for documents
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            response_queue_id: Reserved queue ID for tunneled responses
            response_queue_token: Token for accessing the reserved queue

        Returns:
            AggregatedContext with all documents and retrieval results
        """
        if not data_sources:
            return AggregatedContext(
                documents=[],
                retrieval_results=[],
                total_latency_ms=0,
            )

        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}
        start_time = time.perf_counter()

        # Query all data sources in parallel
        tasks = [
            self._query_single_source(
                ds=ds,
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                endpoint_tokens=endpoint_tokens,
                transaction_tokens=transaction_tokens,
                response_queue_id=response_queue_id,
                response_queue_token=response_queue_token,
            )
            for ds in data_sources
        ]

        results: list[RetrievalResult] = await asyncio.gather(*tasks, return_exceptions=False)

        total_latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Aggregate all documents, sorted by score
        all_documents = []
        for result in results:
            if result.status == "success":
                all_documents.extend(result.documents)

        # Sort by relevance score (descending)
        all_documents.sort(key=lambda d: d.score, reverse=True)

        # Log summary
        successful = sum(1 for r in results if r.status == "success")
        total_docs = len(all_documents)
        logger.info(
            f"Retrieval complete: {successful}/{len(data_sources)} sources, "
            f"{total_docs} documents, {total_latency_ms}ms"
        )

        return AggregatedContext(
            documents=all_documents,
            retrieval_results=results,
            total_latency_ms=total_latency_ms,
        )

    async def retrieve_streaming(
        self,
        data_sources: list[ResolvedEndpoint],
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
        response_queue_id: str | None = None,
        response_queue_token: str | None = None,
    ):
        """
        Retrieve from SyftAI-Space data sources and yield results as they complete.

        This is useful for streaming UX where you want to show progress.
        Supports both HTTP endpoints and tunneled endpoints (via MQ).
        User identity is derived from satellite tokens by SyftAI-Space.

        Args:
            data_sources: List of resolved data source endpoints
            query: The search query
            top_k: Number of documents to retrieve per source
            similarity_threshold: Minimum similarity score for documents
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            response_queue_id: Reserved queue ID for tunneled responses
            response_queue_token: Token for accessing the reserved queue

        Yields:
            RetrievalResult for each data source as it completes
        """
        if not data_sources:
            return

        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}

        # Create tasks using _query_single_source which handles tunneling
        tasks = {
            asyncio.create_task(
                self._query_single_source(
                    ds=ds,
                    query=query,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                    endpoint_tokens=endpoint_tokens,
                    transaction_tokens=transaction_tokens,
                    response_queue_id=response_queue_id,
                    response_queue_token=response_queue_token,
                )
            ): ds
            for ds in data_sources
        }

        # Yield results as they complete
        pending = set(tasks.keys())
        while pending:
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in done:
                result = await task
                yield result
