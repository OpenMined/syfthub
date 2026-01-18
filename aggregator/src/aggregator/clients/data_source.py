"""Client for interacting with SyftAI-Space data source endpoints."""

import time
from typing import Any

import httpx

from aggregator.observability import get_correlation_id, get_logger
from aggregator.observability.constants import CORRELATION_ID_HEADER, LogEvents
from aggregator.schemas.internal import RetrievalResult
from aggregator.schemas.responses import Document

logger = get_logger(__name__)


class DataSourceClient:
    """Client for querying SyftAI-Space data source endpoints.

    This client is adapted to work with SyftAI-Space's unified endpoint API:
    POST /api/v1/endpoints/{slug}/query

    The endpoint must be configured with response_type that includes "raw"
    (either "raw" or "both") to return document references.
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = httpx.Timeout(timeout)

    async def query(
        self,
        url: str,
        slug: str,
        endpoint_path: str,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        tenant_name: str | None = None,
        authorization_token: str | None = None,
        transaction_token: str | None = None,
    ) -> RetrievalResult:
        """
        Query a SyftAI-Space endpoint for relevant documents.

        User identity is derived from the satellite token by SyftAI-Space.

        Args:
            url: Base URL of the SyftAI-Space instance
            slug: Endpoint slug for the API path
            endpoint_path: Path identifier for logging/tracking
            query: The search query
            top_k: Number of documents to retrieve (maps to 'limit')
            similarity_threshold: Minimum similarity score for documents
            tenant_name: Tenant name for X-Tenant-Name header (optional)
            authorization_token: Satellite token for Authorization header (optional)
            transaction_token: Transaction token for billing authorization (optional)

        Returns:
            RetrievalResult with documents and status
        """
        start_time = time.perf_counter()

        # Build SyftAI-Space endpoint URL
        query_url = f"{url.rstrip('/')}/api/v1/endpoints/{slug}/query"

        # Build SyftAI-Space compatible request body
        # SyftAI-Space accepts messages as a string for simple queries
        # User identity is derived from the satellite token, not the request body
        request_data: dict[str, Any] = {
            "messages": query,  # String is accepted by SyftAI-Space
            "limit": top_k,
            "similarity_threshold": similarity_threshold,
            "include_metadata": True,
        }

        # Include transaction token in payload for billing authorization
        if transaction_token:
            request_data["transaction_token"] = transaction_token

        # Build headers with correlation ID for request tracing
        headers: dict[str, str] = {"Content-Type": "application/json"}
        correlation_id = get_correlation_id()
        if correlation_id:
            headers[CORRELATION_ID_HEADER] = correlation_id
        if tenant_name:
            headers["X-Tenant-Name"] = tenant_name
        if authorization_token:
            headers["Authorization"] = f"Bearer {authorization_token}"

        logger.debug(
            LogEvents.DATA_SOURCE_QUERY_STARTED,
            endpoint_path=endpoint_path,
            query_url=query_url,
            top_k=top_k,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    query_url,
                    json=request_data,
                    headers=headers,
                )

                latency_ms = int((time.perf_counter() - start_time) * 1000)

                if response.status_code == 403:
                    error_detail = self._extract_error_detail(response)
                    logger.warning(
                        LogEvents.DATA_SOURCE_QUERY_FAILED,
                        endpoint_path=endpoint_path,
                        status_code=403,
                        error=error_detail,
                        latency_ms=latency_ms,
                    )
                    return RetrievalResult(
                        endpoint_path=endpoint_path,
                        documents=[],
                        status="error",
                        error_message=f"Access denied: {error_detail}",
                        latency_ms=latency_ms,
                    )

                if response.status_code != 200:
                    error_detail = self._extract_error_detail(response)
                    logger.warning(
                        LogEvents.DATA_SOURCE_QUERY_FAILED,
                        endpoint_path=endpoint_path,
                        status_code=response.status_code,
                        error=error_detail,
                        latency_ms=latency_ms,
                    )
                    return RetrievalResult(
                        endpoint_path=endpoint_path,
                        documents=[],
                        status="error",
                        error_message=f"HTTP {response.status_code}: {error_detail}",
                        latency_ms=latency_ms,
                    )

                data = response.json()
                documents = self._parse_syftai_response(data)

                logger.info(
                    LogEvents.DATA_SOURCE_QUERY_COMPLETED,
                    endpoint_path=endpoint_path,
                    documents_count=len(documents),
                    latency_ms=latency_ms,
                )

                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=documents,
                    status="success",
                    latency_ms=latency_ms,
                )

            except httpx.TimeoutException:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                logger.warning(
                    LogEvents.CHAT_RETRIEVAL_TIMEOUT,
                    endpoint_path=endpoint_path,
                    latency_ms=latency_ms,
                )
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="timeout",
                    error_message="Request timed out",
                    latency_ms=latency_ms,
                )

            except httpx.RequestError as e:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                logger.warning(
                    LogEvents.DATA_SOURCE_QUERY_FAILED,
                    endpoint_path=endpoint_path,
                    error=str(e),
                    latency_ms=latency_ms,
                )
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="error",
                    error_message=str(e),
                    latency_ms=latency_ms,
                )

            except Exception as e:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                logger.exception(
                    LogEvents.DATA_SOURCE_QUERY_FAILED,
                    endpoint_path=endpoint_path,
                    error=str(e),
                    latency_ms=latency_ms,
                )
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="error",
                    error_message=f"Unexpected error: {e}",
                    latency_ms=latency_ms,
                )

    def _extract_error_detail(self, response: httpx.Response) -> str:
        """Extract error detail from response."""
        try:
            data = response.json()
            return data.get("detail", response.text[:200])
        except Exception:
            return response.text[:200]

    def _parse_syftai_response(self, data: dict[str, Any]) -> list[Document]:
        """Parse documents from SyftAI-Space QueryEndpointResponse.

        SyftAI-Space returns:
        {
            "summary": {...} | null,
            "references": {
                "documents": [
                    {
                        "document_id": str,
                        "content": str,
                        "metadata": dict,
                        "similarity_score": float
                    }
                ],
                "provider_info": {...},
                "cost": float
            } | null
        }

        We extract from references.documents and map similarity_score -> score.
        """
        documents = []

        # Extract references from SyftAI-Space response
        references = data.get("references")
        if not references:
            logger.debug("No references in SyftAI-Space response")
            return documents

        raw_docs = references.get("documents", [])

        for doc in raw_docs:
            if isinstance(doc, dict):
                documents.append(
                    Document(
                        content=doc.get("content", ""),
                        # Map SyftAI-Space's similarity_score to score
                        score=float(doc.get("similarity_score", 0.0)),
                        metadata=doc.get("metadata", {}),
                    )
                )

        return documents
