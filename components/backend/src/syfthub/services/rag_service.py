"""Search service for endpoint indexing and discovery using Meilisearch.

This module provides functionality to index endpoints in Meilisearch
and perform full-text search to find relevant endpoints based on
natural language queries.
"""

import logging
from typing import Any, Optional

import meilisearch
from meilisearch.errors import MeilisearchApiError, MeilisearchCommunicationError

from syfthub.core.config import settings
from syfthub.models.endpoint import EndpointModel

logger = logging.getLogger(__name__)


class RAGService:
    """Service for managing endpoint indexing and search via Meilisearch.

    This service handles:
    - Converting endpoints to searchable documents
    - Indexing and managing documents in Meilisearch
    - Performing full-text search and returning endpoint IDs
    """

    def __init__(self, client: Optional[meilisearch.Client] = None):
        """Initialize the search service.

        Args:
            client: Optional Meilisearch client. If not provided, will be
                   created lazily when RAG is available.
        """
        self._client = client
        self._index_configured: bool = False

    @property
    def client(self) -> Optional[meilisearch.Client]:
        """Get the Meilisearch client, creating it lazily if needed."""
        if self._client is None and settings.rag_available:
            assert settings.meili_url is not None
            self._client = meilisearch.Client(
                settings.meili_url,
                settings.meili_master_key,
            )
        return self._client

    @property
    def is_available(self) -> bool:
        """Check if search service is available."""
        return self.client is not None

    def _ensure_index(self) -> bool:
        """Ensure the Meilisearch index exists and is configured.

        Creates the index if it doesn't exist and configures searchable
        and filterable attributes. Only runs once per service instance.

        Returns:
            True if index is ready, False on error.
        """
        if self._index_configured:
            return True

        if not self.is_available:
            return False

        assert self.client is not None
        try:
            # create_index is idempotent - returns existing index if present
            self.client.create_index(settings.meili_index_name, {"primaryKey": "id"})

            index = self.client.index(settings.meili_index_name)
            index.update_settings(
                {
                    "searchableAttributes": [
                        "name",
                        "description",
                        "readme",
                        "tags",
                    ],
                    "filterableAttributes": ["type", "endpoint_id"],
                    "rankingRules": [
                        "words",
                        "typo",
                        "proximity",
                        "attribute",
                        "sort",
                        "exactness",
                    ],
                }
            )

            self._index_configured = True
            logger.info(f"Meilisearch index '{settings.meili_index_name}' ready")
            return True

        except MeilisearchApiError as e:
            logger.error(f"Failed to configure Meilisearch index: {e}")
            return False
        except MeilisearchCommunicationError as e:
            logger.error(f"Cannot connect to Meilisearch: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error configuring Meilisearch index: {e}")
            return False

    def _build_document(self, endpoint: EndpointModel) -> dict[str, Any]:
        """Build a Meilisearch document from an endpoint model.

        Args:
            endpoint: The endpoint to build a document for.

        Returns:
            Dictionary suitable for Meilisearch indexing.
        """
        tags_str = " ".join(endpoint.tags) if endpoint.tags else ""

        connect_types: list[str] = []
        if endpoint.connect:
            for conn in endpoint.connect:
                if isinstance(conn, dict) and conn.get("type"):
                    connect_types.append(conn["type"])
        connect_str = ", ".join(connect_types) if connect_types else ""

        return {
            "id": str(endpoint.id),
            "endpoint_id": endpoint.id,
            "name": endpoint.name or "",
            "description": endpoint.description or "",
            "readme": endpoint.readme or "",
            "tags": tags_str,
            "type": str(endpoint.type) if endpoint.type else "",
            "connect_types": connect_str,
        }

    def ingest_endpoint(self, endpoint: EndpointModel) -> Optional[str]:
        """Index an endpoint in Meilisearch.

        Args:
            endpoint: The endpoint to index.

        Returns:
            str(endpoint.id) if successful, None otherwise.
        """
        if not self.is_available:
            logger.debug("Search service not available, skipping ingestion")
            return None

        if not self._ensure_index():
            logger.warning("Could not configure search index, skipping ingestion")
            return None

        assert self.client is not None
        try:
            document = self._build_document(endpoint)
            self.client.index(settings.meili_index_name).add_documents([document])

            logger.info(f"Successfully indexed endpoint {endpoint.id}")
            return str(endpoint.id)

        except MeilisearchApiError as e:
            logger.error(
                f"Failed to index endpoint {endpoint.id}: {e}",
                extra={"endpoint_id": endpoint.id},
            )
            return None
        except MeilisearchCommunicationError as e:
            logger.error(
                f"Cannot connect to Meilisearch while indexing endpoint {endpoint.id}: {e}"
            )
            return None
        except Exception as e:
            logger.exception(f"Unexpected error indexing endpoint {endpoint.id}: {e}")
            return None

    def remove_endpoint(self, file_id: str) -> bool:
        """Remove an endpoint from the Meilisearch index.

        Args:
            file_id: The document ID to remove (str(endpoint.id)).

        Returns:
            True if successful or not applicable, False on error.
        """
        if not self.is_available:
            logger.debug("Search service not available, skipping removal")
            return True  # Consider it a success if search is disabled

        if not file_id:
            logger.debug("No file_id provided, nothing to remove")
            return True

        assert self.client is not None
        try:
            self.client.index(settings.meili_index_name).delete_document(file_id)
            logger.info(f"Successfully removed document {file_id} from search index")
            return True

        except MeilisearchApiError as e:
            logger.error(
                f"Failed to remove document {file_id}: {e}",
                extra={"file_id": file_id},
            )
            return False
        except MeilisearchCommunicationError as e:
            logger.error(
                f"Cannot connect to Meilisearch while removing document {file_id}: {e}"
            )
            return False
        except Exception as e:
            logger.exception(f"Unexpected error removing document {file_id}: {e}")
            return False

    def update_endpoint(
        self, endpoint: EndpointModel, _old_file_id: Optional[str]
    ) -> Optional[str]:
        """Update an endpoint in the Meilisearch index.

        Since Meilisearch add_documents is an upsert, we simply re-index.
        _old_file_id is ignored because document IDs are stable (str(endpoint.id)).

        Args:
            endpoint: The updated endpoint.
            _old_file_id: The previous document ID (ignored, kept for interface compat).

        Returns:
            str(endpoint.id) if successful, None otherwise.
        """
        if not self.is_available:
            logger.debug("Search service not available, skipping update")
            return None

        return self.ingest_endpoint(endpoint)

    def search(self, query: str, max_results: int = 10) -> list[tuple[int, float]]:
        """Search for endpoints matching the query.

        Performs a full-text search on Meilisearch and returns endpoint IDs
        with relevance scores, ordered by relevance.

        Args:
            query: The search query.
            max_results: Maximum number of results to return.

        Returns:
            List of (endpoint_id, relevance_score) tuples ordered by relevance.
            Scores are normalized to 0-1 range. Empty list if search fails
            or search is unavailable.
        """
        if not self.is_available:
            logger.debug("Search service not available, returning empty results")
            return []

        if not query or not query.strip():
            logger.debug("Empty query, returning empty results")
            return []

        if not self._ensure_index():
            logger.warning("Search index not ready, returning empty results")
            return []

        assert self.client is not None
        try:
            request_limit = min(max_results * 2, settings.rag_max_results)

            logger.debug(
                f"Searching Meilisearch for: {query[:100]} (limit={request_limit})"
            )

            result = self.client.index(settings.meili_index_name).search(
                query,
                {
                    "limit": request_limit,
                    "showRankingScore": True,
                },
            )

            endpoint_results: list[tuple[int, float]] = []
            seen_ids: set[int] = set()

            for hit in result.get("hits", []):
                endpoint_id_raw = hit.get("endpoint_id")
                if endpoint_id_raw is not None:
                    try:
                        endpoint_id = int(endpoint_id_raw)
                        if endpoint_id not in seen_ids:
                            seen_ids.add(endpoint_id)
                            score = min(
                                1.0, max(0.0, float(hit.get("_rankingScore", 0.0)))
                            )
                            endpoint_results.append((endpoint_id, score))
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Invalid endpoint_id in search result: {endpoint_id_raw}"
                        )

            logger.info(
                f"Search returned {len(endpoint_results)} results "
                f"for query: {query[:50]}"
            )
            return endpoint_results

        except MeilisearchApiError as e:
            logger.error(
                f"Meilisearch search failed: {e}",
                extra={"query": query[:100]},
            )
            return []
        except MeilisearchCommunicationError as e:
            logger.error(f"Cannot connect to Meilisearch during search: {e}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error during search: {e}")
            return []


# Module-level instance for convenience
_rag_service_instance: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get the search service instance.

    Returns:
        RAGService instance.
    """
    global _rag_service_instance

    if _rag_service_instance is None:
        _rag_service_instance = RAGService()

    return _rag_service_instance
