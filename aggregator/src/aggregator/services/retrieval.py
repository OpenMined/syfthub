"""Retrieval service for querying SyftAI-Space data sources in parallel."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from aggregator.clients.data_source import DataSourceClient
from aggregator.clients.nats_transport import extract_tunnel_username, is_tunneling_url
from aggregator.schemas.internal import AggregatedContext, ResolvedEndpoint, RetrievalResult

if TYPE_CHECKING:
    from aggregator.clients.nats_transport import NATSTransport

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for retrieving context from multiple SyftAI-Space data sources."""

    def __init__(
        self,
        data_source_client: DataSourceClient,
        nats_transport: NATSTransport | None = None,
    ):
        self.data_source_client = data_source_client
        self.nats_transport = nats_transport

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
        peer_channel: str | None = None,
    ) -> AggregatedContext:
        """
        Retrieve relevant documents from multiple SyftAI-Space data sources in parallel.

        User identity is derived from satellite tokens by SyftAI-Space.

        Args:
            data_sources: List of resolved data source endpoints
            query: The search query
            top_k: Number of documents to retrieve per source
            similarity_threshold: Minimum similarity score for documents
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing

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

        # Query all data sources in parallel (HTTP or NATS)
        tasks = []
        for ds in data_sources:
            if is_tunneling_url(ds.url) and self.nats_transport and peer_channel:
                # Route through NATS for tunneling spaces
                target_username = extract_tunnel_username(ds.url)
                tasks.append(
                    self.nats_transport.query_data_source(
                        target_username=target_username,
                        slug=ds.slug,
                        endpoint_path=ds.path,
                        query=query,
                        peer_channel=peer_channel,
                        top_k=top_k,
                        similarity_threshold=similarity_threshold,
                        transaction_token=self._get_token_for_endpoint(ds, transaction_tokens),
                        satellite_token=self._get_token_for_endpoint(ds, endpoint_tokens),
                    )
                )
            else:
                # Standard HTTP request
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

    async def retrieve_streaming(
        self,
        data_sources: list[ResolvedEndpoint],
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
        peer_channel: str | None = None,
    ) -> AsyncIterator[RetrievalResult]:
        """
        Retrieve from SyftAI-Space data sources and yield results as they complete.

        This is useful for streaming UX where you want to show progress.
        User identity is derived from satellite tokens by SyftAI-Space.

        Args:
            data_sources: List of resolved data source endpoints
            query: The search query
            top_k: Number of documents to retrieve per source
            similarity_threshold: Minimum similarity score for documents
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing

        Yields:
            RetrievalResult for each data source as it completes
        """
        if not data_sources:
            return

        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}

        # Create tasks (HTTP or NATS based on URL)
        tasks = {}
        for ds in data_sources:
            if is_tunneling_url(ds.url) and self.nats_transport and peer_channel:
                target_username = extract_tunnel_username(ds.url)
                task = asyncio.create_task(
                    self.nats_transport.query_data_source(
                        target_username=target_username,
                        slug=ds.slug,
                        endpoint_path=ds.path,
                        query=query,
                        peer_channel=peer_channel,
                        top_k=top_k,
                        similarity_threshold=similarity_threshold,
                        transaction_token=self._get_token_for_endpoint(ds, transaction_tokens),
                        satellite_token=self._get_token_for_endpoint(ds, endpoint_tokens),
                    )
                )
            else:
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
