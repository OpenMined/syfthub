"""Retrieval service for querying data sources in parallel."""

import asyncio
import logging
import time

from aggregator.clients.data_source import DataSourceClient
from aggregator.schemas.internal import AggregatedContext, ResolvedEndpoint, RetrievalResult

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for retrieving context from multiple data sources."""

    def __init__(self, data_source_client: DataSourceClient):
        self.data_source_client = data_source_client

    async def retrieve(
        self,
        data_sources: list[ResolvedEndpoint],
        query: str,
        top_k: int = 5,
    ) -> AggregatedContext:
        """
        Retrieve relevant documents from multiple data sources in parallel.

        Args:
            data_sources: List of resolved data source endpoints
            query: The search query
            top_k: Number of documents to retrieve per source

        Returns:
            AggregatedContext with all documents and retrieval results
        """
        if not data_sources:
            return AggregatedContext(
                documents=[],
                retrieval_results=[],
                total_latency_ms=0,
            )

        start_time = time.perf_counter()

        # Query all data sources in parallel
        tasks = [
            self.data_source_client.query(
                url=ds.url,
                endpoint_path=ds.path,
                query=query,
                top_k=top_k,
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
    ):
        """
        Retrieve from data sources and yield results as they complete.

        This is useful for streaming UX where you want to show progress.

        Args:
            data_sources: List of resolved data source endpoints
            query: The search query
            top_k: Number of documents to retrieve per source

        Yields:
            RetrievalResult for each data source as it completes
        """
        if not data_sources:
            return

        # Create tasks
        tasks = {
            asyncio.create_task(
                self.data_source_client.query(
                    url=ds.url,
                    endpoint_path=ds.path,
                    query=query,
                    top_k=top_k,
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
