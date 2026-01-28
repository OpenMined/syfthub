"""Retrieval service for querying SyftAI-Space data sources in parallel."""

import asyncio
import logging
import time
from typing import Any

from aggregator.clients.data_source import DataSourceClient
from aggregator.clients.tunnel import TunnelClient, extract_tunnel_username, is_tunneled_url
from aggregator.schemas.internal import AggregatedContext, ResolvedEndpoint, RetrievalResult

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for retrieving context from multiple SyftAI-Space data sources."""

    def __init__(self, data_source_client: DataSourceClient):
        self.data_source_client = data_source_client

    def _get_token_for_endpoint(
        self, endpoint: ResolvedEndpoint, token_mapping: dict[str, str]
    ) -> str | None:
        """Get a token for an endpoint based on its owner username."""
        if endpoint.owner_username and endpoint.owner_username in token_mapping:
            return token_mapping[endpoint.owner_username]
        return None

    async def retrieve(
        self,
        data_sources: list[ResolvedEndpoint],
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
        tunnel_client: TunnelClient | None = None,
    ) -> AggregatedContext:
        """
        Retrieve relevant documents from multiple SyftAI-Space data sources in parallel.

        User identity is derived from satellite tokens by SyftAI-Space.
        Supports both HTTP endpoints and tunneled endpoints (via MQ).

        Args:
            data_sources: List of resolved data source endpoints
            query: The search query
            top_k: Number of documents to retrieve per source
            similarity_threshold: Minimum similarity score for documents
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            tunnel_client: TunnelClient for querying tunneled endpoints (required if any endpoint is tunneled)

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

        # Create tasks for all data sources (both HTTP and tunneled)
        tasks = []
        for ds in data_sources:
            if is_tunneled_url(ds.url):
                # Tunneled endpoint - use TunnelClient
                if tunnel_client is None:
                    # Return error result for this endpoint
                    tasks.append(
                        self._create_error_result(
                            ds.path,
                            "Tunneled endpoint requires response_queue credentials",
                        )
                    )
                else:
                    target_username = extract_tunnel_username(ds.url)
                    tasks.append(
                        tunnel_client.query_data_source(
                            target_username=target_username,
                            slug=ds.slug,
                            endpoint_path=ds.path,
                            query=query,
                            top_k=top_k,
                            similarity_threshold=similarity_threshold,
                            transaction_token=self._get_token_for_endpoint(ds, transaction_tokens),
                        )
                    )
            else:
                # HTTP endpoint - use DataSourceClient
                tasks.append(
                    self.data_source_client.query(
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
                )

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

    async def _create_error_result(self, endpoint_path: str, error_message: str) -> RetrievalResult:
        """Create an error result for an endpoint."""
        return RetrievalResult(
            endpoint_path=endpoint_path,
            documents=[],
            status="error",
            error_message=error_message,
            latency_ms=0,
        )

    async def retrieve_streaming(
        self,
        data_sources: list[ResolvedEndpoint],
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
        tunnel_client: TunnelClient | None = None,
    ):
        """
        Retrieve from SyftAI-Space data sources and yield results as they complete.

        This is useful for streaming UX where you want to show progress.
        User identity is derived from satellite tokens by SyftAI-Space.
        Supports both HTTP endpoints and tunneled endpoints (via MQ).

        Args:
            data_sources: List of resolved data source endpoints
            query: The search query
            top_k: Number of documents to retrieve per source
            similarity_threshold: Minimum similarity score for documents
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            tunnel_client: TunnelClient for querying tunneled endpoints (required if any endpoint is tunneled)

        Yields:
            RetrievalResult for each data source as it completes
        """
        if not data_sources:
            return

        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}

        # Create tasks for all data sources (both HTTP and tunneled)
        tasks = {}
        for ds in data_sources:
            if is_tunneled_url(ds.url):
                # Tunneled endpoint - use TunnelClient
                if tunnel_client is None:
                    # Create error task for this endpoint
                    task = asyncio.create_task(
                        self._create_error_result(
                            ds.path,
                            "Tunneled endpoint requires response_queue credentials",
                        )
                    )
                else:
                    target_username = extract_tunnel_username(ds.url)
                    task = asyncio.create_task(
                        tunnel_client.query_data_source(
                            target_username=target_username,
                            slug=ds.slug,
                            endpoint_path=ds.path,
                            query=query,
                            top_k=top_k,
                            similarity_threshold=similarity_threshold,
                            transaction_token=self._get_token_for_endpoint(ds, transaction_tokens),
                        )
                    )
            else:
                # HTTP endpoint - use DataSourceClient
                task = asyncio.create_task(
                    self.data_source_client.query(
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
                )
            tasks[task] = ds

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
