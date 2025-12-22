"""Client for interacting with SyftAI-Space data source endpoints.

TODO: Satellite Token Integration
---------------------------------
When SyftAI-Space implements satellite token support, this client should:

1. Accept an optional `authorization_token` parameter in the `query()` method
2. Include the token in an Authorization header: `Authorization: Bearer <token>`
3. This allows SyftAI-Space to validate user permissions via the satellite token

Example change for query() method:
    async def query(
        self,
        url: str,
        slug: str,
        ...
        authorization_token: str | None = None,  # Add this parameter
    ) -> RetrievalResult:
        ...
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if tenant_name:
            headers["X-Tenant-Name"] = tenant_name
        if authorization_token:
            headers["Authorization"] = f"Bearer {authorization_token}"
"""

import logging
import time
from typing import Any

import httpx

from aggregator.schemas.internal import RetrievalResult
from aggregator.schemas.responses import Document

logger = logging.getLogger(__name__)


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
        user_email: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        tenant_name: str | None = None,
    ) -> RetrievalResult:
        """
        Query a SyftAI-Space endpoint for relevant documents.

        Args:
            url: Base URL of the SyftAI-Space instance
            slug: Endpoint slug for the API path
            endpoint_path: Path identifier for logging/tracking
            query: The search query
            user_email: User email for visibility/policy checks (required by SyftAI-Space)
            top_k: Number of documents to retrieve (maps to 'limit')
            similarity_threshold: Minimum similarity score for documents
            tenant_name: Tenant name for X-Tenant-Name header (optional)

        Returns:
            RetrievalResult with documents and status
        """
        start_time = time.perf_counter()

        # Build SyftAI-Space endpoint URL
        query_url = f"{url.rstrip('/')}/api/v1/endpoints/{slug}/query"

        # Build SyftAI-Space compatible request body
        # SyftAI-Space accepts messages as a string for simple queries
        request_data = {
            "user_email": user_email,
            "messages": query,  # String is accepted by SyftAI-Space
            "limit": top_k,
            "similarity_threshold": similarity_threshold,
            "include_metadata": True,
        }

        # Build headers
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if tenant_name:
            headers["X-Tenant-Name"] = tenant_name

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
                        f"Data source access denied: {endpoint_path} - {error_detail}"
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
                        f"Data source query failed: {endpoint_path} "
                        f"status={response.status_code} - {error_detail}"
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
