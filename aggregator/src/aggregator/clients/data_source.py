"""Client for interacting with data source endpoints."""

import logging
import time

import httpx

from aggregator.schemas.internal import RetrievalResult
from aggregator.schemas.requests import QueryRequest
from aggregator.schemas.responses import Document

logger = logging.getLogger(__name__)


class DataSourceClient:
    """Client for querying data source endpoints."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = httpx.Timeout(timeout)

    async def query(
        self,
        url: str,
        endpoint_path: str,
        query: str,
        top_k: int = 5,
    ) -> RetrievalResult:
        """
        Query a data source endpoint for relevant documents.

        Args:
            url: Base URL of the data source
            endpoint_path: Path identifier for logging/tracking
            query: The search query
            top_k: Number of documents to retrieve

        Returns:
            RetrievalResult with documents and status
        """
        start_time = time.perf_counter()

        query_url = f"{url.rstrip('/')}/query"
        request_data = QueryRequest(query=query, top_k=top_k)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    query_url,
                    json=request_data.model_dump(),
                    headers={"Content-Type": "application/json"},
                )

                latency_ms = int((time.perf_counter() - start_time) * 1000)

                if response.status_code != 200:
                    logger.warning(
                        f"Data source query failed: {endpoint_path} "
                        f"status={response.status_code}"
                    )
                    return RetrievalResult(
                        endpoint_path=endpoint_path,
                        documents=[],
                        status="error",
                        error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                        latency_ms=latency_ms,
                    )

                data = response.json()
                documents = self._parse_documents(data)

                logger.info(
                    f"Data source query success: {endpoint_path} "
                    f"docs={len(documents)} latency={latency_ms}ms"
                )

                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=documents,
                    status="success",
                    latency_ms=latency_ms,
                )

            except httpx.TimeoutException:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                logger.warning(f"Data source query timeout: {endpoint_path}")
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="timeout",
                    error_message="Request timed out",
                    latency_ms=latency_ms,
                )

            except httpx.RequestError as e:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                logger.warning(f"Data source query error: {endpoint_path} - {e}")
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="error",
                    error_message=str(e),
                    latency_ms=latency_ms,
                )

            except Exception as e:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                logger.exception(f"Unexpected error querying data source: {endpoint_path}")
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="error",
                    error_message=f"Unexpected error: {e}",
                    latency_ms=latency_ms,
                )

    def _parse_documents(self, data: dict) -> list[Document]:
        """Parse documents from data source response."""
        documents = []
        raw_docs = data.get("documents", [])

        for doc in raw_docs:
            if isinstance(doc, dict):
                documents.append(
                    Document(
                        content=doc.get("content", ""),
                        score=float(doc.get("score", 0.0)),
                        metadata=doc.get("metadata", {}),
                    )
                )
            elif isinstance(doc, str):
                # Handle simple string documents
                documents.append(Document(content=doc, score=0.0, metadata={}))

        return documents
