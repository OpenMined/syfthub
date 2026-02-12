"""RAG (Retrieval-Augmented Generation) service for endpoint search.

This module provides functionality to index endpoints in OpenAI's vector store
and perform semantic search to find relevant endpoints based on natural language
queries.
"""

import logging
from typing import Optional

from syfthub.core.config import settings
from syfthub.core.openai_client import (
    OpenAIClient,
    OpenAIClientError,
    get_openai_client,
)
from syfthub.models.endpoint import EndpointModel

logger = logging.getLogger(__name__)


class RAGService:
    """Service for managing endpoint indexing and semantic search.

    This service handles:
    - Converting endpoints to markdown for indexing
    - Uploading and managing files in OpenAI's vector store
    - Performing semantic search and returning endpoint IDs
    """

    def __init__(self, client: Optional[OpenAIClient] = None):
        """Initialize the RAG service.

        Args:
            client: Optional OpenAI client. If not provided, will use the
                   global client if RAG is available.
        """
        self._client = client
        self._vector_store_id: Optional[str] = None

    @property
    def client(self) -> Optional[OpenAIClient]:
        """Get the OpenAI client."""
        if self._client is None:
            self._client = get_openai_client()
        return self._client

    @property
    def is_available(self) -> bool:
        """Check if RAG service is available."""
        return self.client is not None

    def _get_vector_store_id(self) -> Optional[str]:
        """Get or create the vector store ID.

        Returns:
            Vector store ID if available, None otherwise.
        """
        if self._vector_store_id is not None:
            return self._vector_store_id

        if not self.is_available:
            return None

        assert self.client is not None  # Guaranteed by is_available check
        try:
            store = self.client.get_or_create_vector_store(
                settings.openai_vector_store_name
            )
            self._vector_store_id = store.id
            logger.info(f"Using vector store: {store.id} ({store.name})")
            return self._vector_store_id
        except OpenAIClientError as e:
            logger.error(f"Failed to get/create vector store: {e.message}")
            return None

    def _generate_markdown(self, endpoint: EndpointModel) -> str:
        """Generate markdown content for an endpoint.

        This creates a structured markdown document containing the endpoint's
        semantic information that will be indexed for search.

        Args:
            endpoint: The endpoint to generate markdown for.

        Returns:
            Markdown string representation of the endpoint.
        """
        # Format tags
        tags_str = ", ".join(endpoint.tags) if endpoint.tags else "None"

        # Format connection methods
        connect_types: list[str] = []
        if endpoint.connect:
            for conn in endpoint.connect:
                if isinstance(conn, dict) and conn.get("type"):
                    connect_types.append(conn["type"])
        connect_str = ", ".join(connect_types) if connect_types else "None"

        # Build markdown content
        markdown = f"""# {endpoint.name}

**Type**: {endpoint.type}
**Tags**: {tags_str}

## Description

{endpoint.description}

## Documentation

{endpoint.readme}

## Connection Methods

{connect_str}
"""
        return markdown.strip()

    def ingest_endpoint(self, endpoint: EndpointModel) -> Optional[str]:
        """Ingest an endpoint into the vector store.

        This uploads the endpoint's content as a markdown file and attaches
        it to the vector store with metadata for later retrieval.

        Args:
            endpoint: The endpoint to ingest.

        Returns:
            The file ID if successful, None otherwise.
        """
        if not self.is_available:
            logger.debug("RAG service not available, skipping ingestion")
            return None

        vector_store_id = self._get_vector_store_id()
        if not vector_store_id:
            logger.warning("Could not get vector store ID, skipping ingestion")
            return None

        assert self.client is not None  # Guaranteed by is_available check
        try:
            # Generate markdown content
            markdown_content = self._generate_markdown(endpoint)
            filename = f"endpoint_{endpoint.id}.md"

            # Upload file
            logger.debug(f"Uploading file for endpoint {endpoint.id}")
            file_obj = self.client.upload_file(
                content=markdown_content.encode("utf-8"),
                filename=filename,
            )

            # Attach to vector store with metadata
            logger.debug(
                f"Attaching file {file_obj.id} to vector store {vector_store_id}"
            )
            attributes = {
                "endpoint_id": str(endpoint.id),
            }
            self.client.attach_file_to_store(
                vector_store_id=vector_store_id,
                file_id=file_obj.id,
                attributes=attributes,
            )

            logger.info(
                f"Successfully ingested endpoint {endpoint.id} (file_id: {file_obj.id})"
            )
            return file_obj.id

        except OpenAIClientError as e:
            logger.error(
                f"Failed to ingest endpoint {endpoint.id}: {e.message}",
                extra={"endpoint_id": endpoint.id, "status_code": e.status_code},
            )
            return None
        except Exception as e:
            logger.exception(f"Unexpected error ingesting endpoint {endpoint.id}: {e}")
            return None

    def remove_endpoint(self, file_id: str) -> bool:
        """Remove an endpoint from the vector store.

        This removes the file from the vector store and deletes the underlying
        file from OpenAI's storage.

        Args:
            file_id: The file ID to remove.

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_available:
            logger.debug("RAG service not available, skipping removal")
            return True  # Consider it a success if RAG is disabled

        if not file_id:
            logger.debug("No file_id provided, nothing to remove")
            return True

        vector_store_id = self._get_vector_store_id()
        if not vector_store_id:
            logger.warning("Could not get vector store ID, skipping removal")
            return False

        assert self.client is not None  # Guaranteed by is_available check
        try:
            # Remove from vector store
            logger.debug(f"Removing file {file_id} from vector store")
            self.client.delete_file_from_store(vector_store_id, file_id)

            # Delete the file itself
            logger.debug(f"Deleting file {file_id}")
            self.client.delete_file(file_id)

            logger.info(f"Successfully removed file {file_id} from RAG")
            return True

        except OpenAIClientError as e:
            logger.error(
                f"Failed to remove file {file_id}: {e.message}",
                extra={"file_id": file_id, "status_code": e.status_code},
            )
            return False
        except Exception as e:
            logger.exception(f"Unexpected error removing file {file_id}: {e}")
            return False

    def update_endpoint(
        self, endpoint: EndpointModel, old_file_id: Optional[str]
    ) -> Optional[str]:
        """Update an endpoint in the vector store.

        This removes the old file (if any) and uploads a new one with the
        updated content.

        Args:
            endpoint: The updated endpoint.
            old_file_id: The previous file ID to remove (if any).

        Returns:
            The new file ID if successful, None otherwise.
        """
        if not self.is_available:
            logger.debug("RAG service not available, skipping update")
            return None

        # Remove old file first
        if old_file_id:
            self.remove_endpoint(old_file_id)

        # Ingest updated endpoint
        return self.ingest_endpoint(endpoint)

    def search(self, query: str, max_results: int = 10) -> list[tuple[int, float]]:
        """Search for endpoints matching the query.

        This performs a semantic search on the vector store and returns
        the IDs and relevance scores of matching endpoints, ordered by relevance.

        Args:
            query: The search query.
            max_results: Maximum number of results to return.

        Returns:
            List of (endpoint_id, relevance_score) tuples ordered by relevance.
            Scores are normalized to 0-1 range. Empty list if search fails
            or RAG is unavailable.
        """
        if not self.is_available:
            logger.debug("RAG service not available, returning empty results")
            return []

        if not query or not query.strip():
            logger.debug("Empty query, returning empty results")
            return []

        vector_store_id = self._get_vector_store_id()
        if not vector_store_id:
            logger.warning("Could not get vector store ID, returning empty results")
            return []

        assert self.client is not None  # Guaranteed by is_available check
        try:
            # Request more results than needed to account for filtering
            # (deleted endpoints, visibility changes, etc.)
            request_limit = min(max_results * 2, settings.rag_max_results)

            logger.debug(
                f"Searching vector store for: {query[:100]}... "
                f"(max_results={request_limit})"
            )

            results = self.client.search(
                vector_store_id=vector_store_id,
                query=query,
                max_results=request_limit,
            )

            # Extract endpoint IDs and scores from results
            endpoint_results: list[tuple[int, float]] = []
            seen_ids: set[int] = set()

            for result in results:
                endpoint_id_str = result.attributes.get("endpoint_id")
                if endpoint_id_str:
                    try:
                        endpoint_id = int(endpoint_id_str)
                        if endpoint_id not in seen_ids:  # Deduplicate
                            seen_ids.add(endpoint_id)
                            # Normalize score to 0-1 range (OpenAI returns scores ~0-1)
                            score = min(1.0, max(0.0, result.score))
                            endpoint_results.append((endpoint_id, score))
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Invalid endpoint_id in search result: {endpoint_id_str}"
                        )

            logger.info(
                f"Search returned {len(endpoint_results)} endpoint results "
                f"for query: {query[:50]}..."
            )
            return endpoint_results

        except OpenAIClientError as e:
            logger.error(
                f"Search failed: {e.message}",
                extra={"query": query[:100], "status_code": e.status_code},
            )
            return []
        except Exception as e:
            logger.exception(f"Unexpected error during search: {e}")
            return []


# Module-level instance for convenience
_rag_service_instance: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get the RAG service instance.

    Returns:
        RAGService instance.
    """
    global _rag_service_instance

    if _rag_service_instance is None:
        _rag_service_instance = RAGService()

    return _rag_service_instance
