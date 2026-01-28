"""OpenAI API client for vector store operations.

This module provides a synchronous HTTP client for interacting with OpenAI's
vector store API endpoints. It handles file uploads, vector store management,
and semantic search operations.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional, cast

import httpx

from syfthub.core.config import settings

logger = logging.getLogger(__name__)


class OpenAIClientError(Exception):
    """Base exception for OpenAI client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class OpenAIRateLimitError(OpenAIClientError):
    """Raised when rate limit is exceeded."""

    pass


class OpenAINotFoundError(OpenAIClientError):
    """Raised when a resource is not found."""

    pass


@dataclass
class VectorStore:
    """Represents an OpenAI vector store."""

    id: str
    name: str
    status: str
    file_counts: dict[str, int]


@dataclass
class FileObject:
    """Represents an uploaded file."""

    id: str
    filename: str
    purpose: str
    status: str


@dataclass
class VectorStoreFile:
    """Represents a file attached to a vector store."""

    id: str
    vector_store_id: str
    status: str
    attributes: dict[str, Any]


@dataclass
class SearchResult:
    """Represents a search result from vector store."""

    file_id: str
    score: float
    content: str
    attributes: dict[str, Any]


class OpenAIClient:
    """Synchronous HTTP client for OpenAI vector store operations."""

    BASE_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key. If not provided, uses settings.openai_api_key.
        """
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ValueError("OpenAI API key is required")

        self._client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=settings.rag_request_timeout,
            headers=self._get_headers(),
        )

    def _get_headers(self) -> dict[str, str]:
        """Get common headers for API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "assistants=v2",
        }

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response and raise appropriate errors.

        Args:
            response: The HTTP response object.

        Returns:
            Parsed JSON response data.

        Raises:
            OpenAIRateLimitError: If rate limit is exceeded.
            OpenAINotFoundError: If resource is not found.
            OpenAIClientError: For other API errors.
        """
        if response.status_code == 429:
            raise OpenAIRateLimitError(
                "Rate limit exceeded", status_code=response.status_code
            )

        if response.status_code == 404:
            raise OpenAINotFoundError(
                "Resource not found", status_code=response.status_code
            )

        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_message = error_data.get("error", {}).get(
                    "message", "Unknown error"
                )
            except Exception:
                error_message = response.text or "Unknown error"

            raise OpenAIClientError(
                f"OpenAI API error: {error_message}",
                status_code=response.status_code,
            )

        return cast("dict[str, Any]", response.json())

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "OpenAIClient":
        """Enter context manager."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager."""
        self.close()

    # =========================================
    # Vector Store Operations
    # =========================================

    def create_vector_store(self, name: str) -> VectorStore:
        """Create a new vector store.

        Args:
            name: Name for the vector store.

        Returns:
            Created VectorStore object.
        """
        response = self._client.post(
            "/vector_stores",
            json={"name": name},
        )
        data = self._handle_response(response)

        return VectorStore(
            id=data["id"],
            name=data["name"],
            status=data["status"],
            file_counts=data.get("file_counts", {}),
        )

    def list_vector_stores(self, limit: int = 100) -> list[VectorStore]:
        """List all vector stores.

        Args:
            limit: Maximum number of stores to return.

        Returns:
            List of VectorStore objects.
        """
        response = self._client.get(
            "/vector_stores",
            params={"limit": limit},
        )
        data = self._handle_response(response)

        return [
            VectorStore(
                id=store["id"],
                name=store["name"],
                status=store["status"],
                file_counts=store.get("file_counts", {}),
            )
            for store in data.get("data", [])
        ]

    def get_vector_store(self, vector_store_id: str) -> VectorStore:
        """Get a specific vector store.

        Args:
            vector_store_id: ID of the vector store.

        Returns:
            VectorStore object.
        """
        response = self._client.get(f"/vector_stores/{vector_store_id}")
        data = self._handle_response(response)

        return VectorStore(
            id=data["id"],
            name=data["name"],
            status=data["status"],
            file_counts=data.get("file_counts", {}),
        )

    def get_or_create_vector_store(self, name: str) -> VectorStore:
        """Get existing vector store by name or create a new one.

        Args:
            name: Name of the vector store.

        Returns:
            VectorStore object (existing or newly created).
        """
        # First, try to find existing store by name
        stores = self.list_vector_stores()
        for store in stores:
            if store.name == name:
                logger.info(f"Found existing vector store: {store.id}")
                return store

        # Create new store if not found
        logger.info(f"Creating new vector store: {name}")
        return self.create_vector_store(name)

    # =========================================
    # File Operations
    # =========================================

    def upload_file(self, content: bytes, filename: str) -> FileObject:
        """Upload a file to OpenAI.

        Args:
            content: File content as bytes.
            filename: Name for the file.

        Returns:
            FileObject with the uploaded file details.
        """
        # For file upload, we need different headers (no Content-Type)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        response = self._client.post(
            "/files",
            headers=headers,
            files={"file": (filename, content, "text/markdown")},
            data={"purpose": "assistants"},
        )
        data = self._handle_response(response)

        return FileObject(
            id=data["id"],
            filename=data["filename"],
            purpose=data["purpose"],
            status=data.get("status", "uploaded"),
        )

    def delete_file(self, file_id: str) -> bool:
        """Delete a file from OpenAI.

        Args:
            file_id: ID of the file to delete.

        Returns:
            True if deleted successfully.
        """
        try:
            response = self._client.delete(f"/files/{file_id}")
            self._handle_response(response)
            return True
        except OpenAINotFoundError:
            # File already deleted, consider it a success
            logger.warning(f"File {file_id} not found, may already be deleted")
            return True
        except OpenAIClientError as e:
            logger.error(f"Failed to delete file {file_id}: {e.message}")
            return False

    # =========================================
    # Vector Store File Operations
    # =========================================

    def attach_file_to_store(
        self,
        vector_store_id: str,
        file_id: str,
        attributes: Optional[dict[str, Any]] = None,
    ) -> VectorStoreFile:
        """Attach a file to a vector store.

        Args:
            vector_store_id: ID of the vector store.
            file_id: ID of the file to attach.
            attributes: Optional metadata attributes for filtering.

        Returns:
            VectorStoreFile object.
        """
        payload: dict[str, Any] = {"file_id": file_id}
        if attributes:
            payload["attributes"] = attributes

        response = self._client.post(
            f"/vector_stores/{vector_store_id}/files",
            json=payload,
        )
        data = self._handle_response(response)

        return VectorStoreFile(
            id=data["id"],
            vector_store_id=vector_store_id,
            status=data.get("status", "in_progress"),
            attributes=attributes or {},
        )

    def get_vector_store_file(
        self, vector_store_id: str, file_id: str
    ) -> VectorStoreFile:
        """Get a file from a vector store.

        Args:
            vector_store_id: ID of the vector store.
            file_id: ID of the file.

        Returns:
            VectorStoreFile object.
        """
        response = self._client.get(f"/vector_stores/{vector_store_id}/files/{file_id}")
        data = self._handle_response(response)

        return VectorStoreFile(
            id=data["id"],
            vector_store_id=vector_store_id,
            status=data.get("status", "unknown"),
            attributes=data.get("attributes", {}),
        )

    def delete_file_from_store(self, vector_store_id: str, file_id: str) -> bool:
        """Remove a file from a vector store.

        This removes the file from the vector store but doesn't delete the
        underlying file. Call delete_file() separately to delete the file.

        Args:
            vector_store_id: ID of the vector store.
            file_id: ID of the file to remove.

        Returns:
            True if removed successfully.
        """
        try:
            response = self._client.delete(
                f"/vector_stores/{vector_store_id}/files/{file_id}"
            )
            self._handle_response(response)
            return True
        except OpenAINotFoundError:
            # File already removed, consider it a success
            logger.warning(
                f"File {file_id} not found in store {vector_store_id}, "
                "may already be removed"
            )
            return True
        except OpenAIClientError as e:
            logger.error(
                f"Failed to remove file {file_id} from store {vector_store_id}: "
                f"{e.message}"
            )
            return False

    def wait_for_file_processing(
        self,
        vector_store_id: str,
        file_id: str,
        max_attempts: int = 30,
        delay_seconds: float = 1.0,
    ) -> bool:
        """Wait for a file to be processed in the vector store.

        Args:
            vector_store_id: ID of the vector store.
            file_id: ID of the file.
            max_attempts: Maximum number of polling attempts.
            delay_seconds: Delay between attempts.

        Returns:
            True if file is processed, False if timeout or failed.
        """
        import time

        for _ in range(max_attempts):
            try:
                vs_file = self.get_vector_store_file(vector_store_id, file_id)
                if vs_file.status == "completed":
                    return True
                if vs_file.status in ("failed", "cancelled"):
                    logger.error(
                        f"File processing failed with status: {vs_file.status}"
                    )
                    return False
                time.sleep(delay_seconds)
            except OpenAIClientError as e:
                logger.warning(f"Error checking file status: {e.message}")
                time.sleep(delay_seconds)

        logger.warning(f"Timeout waiting for file {file_id} to be processed")
        return False

    # =========================================
    # Search Operations
    # =========================================

    def search(
        self,
        vector_store_id: str,
        query: str,
        max_results: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        """Search the vector store.

        Args:
            vector_store_id: ID of the vector store to search.
            query: Search query string.
            max_results: Maximum number of results to return.
            filters: Optional attribute filters.

        Returns:
            List of SearchResult objects ordered by relevance.
        """
        payload: dict[str, Any] = {
            "query": query,
            "max_num_results": max_results,
        }
        if filters:
            payload["filters"] = filters

        response = self._client.post(
            f"/vector_stores/{vector_store_id}/search",
            json=payload,
        )
        data = self._handle_response(response)

        results = []
        for item in data.get("data", []):
            # Extract content from the result
            content_parts = item.get("content", [])
            content = ""
            if content_parts and isinstance(content_parts, list):
                # Content is an array of objects with 'text' and 'type'
                content = " ".join(
                    part.get("text", "") for part in content_parts if part.get("text")
                )

            results.append(
                SearchResult(
                    file_id=item.get("file_id", ""),
                    score=item.get("score", 0.0),
                    content=content,
                    attributes=item.get("attributes", {}),
                )
            )

        return results


# Singleton instance for convenience
_client_instance: Optional[OpenAIClient] = None


def get_openai_client() -> Optional[OpenAIClient]:
    """Get the OpenAI client instance.

    Returns:
        OpenAIClient instance if RAG is available, None otherwise.
    """
    global _client_instance

    if not settings.rag_available:
        return None

    if _client_instance is None:
        try:
            _client_instance = OpenAIClient()
        except ValueError as e:
            logger.warning(f"Failed to create OpenAI client: {e}")
            return None

    return _client_instance
