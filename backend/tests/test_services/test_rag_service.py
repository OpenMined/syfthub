"""Tests for RAGService - Semantic search using OpenAI vector stores."""

from unittest.mock import MagicMock, patch

import pytest

from syfthub.core.openai_client import (
    FileObject,
    OpenAIClient,
    OpenAIClientError,
    SearchResult,
    VectorStore,
)
from syfthub.models.endpoint import EndpointModel
from syfthub.services.rag_service import RAGService, get_rag_service


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    client = MagicMock(spec=OpenAIClient)
    return client


@pytest.fixture
def rag_service(mock_openai_client):
    """Create RAGService with mocked client."""
    return RAGService(client=mock_openai_client)


@pytest.fixture
def sample_endpoint():
    """Create a sample endpoint model for testing."""
    endpoint = MagicMock(spec=EndpointModel)
    endpoint.id = 1
    endpoint.name = "Test Endpoint"
    endpoint.type = "model"
    endpoint.description = "A test endpoint for semantic search"
    endpoint.readme = "# Test Endpoint\n\nThis is documentation."
    endpoint.tags = ["test", "ml", "api"]
    endpoint.connect = [{"type": "http"}, {"type": "grpc"}]
    return endpoint


class TestRAGServiceInit:
    """Test RAGService initialization."""

    def test_init_with_client(self, mock_openai_client):
        """Test initialization with provided client."""
        service = RAGService(client=mock_openai_client)
        assert service._client is mock_openai_client
        assert service._vector_store_id is None

    def test_init_without_client(self):
        """Test initialization without client (lazy loading)."""
        service = RAGService()
        assert service._client is None
        assert service._vector_store_id is None


class TestRAGServiceClientProperty:
    """Test client property lazy initialization."""

    def test_client_returns_provided_client(self, mock_openai_client):
        """Test client property returns provided client."""
        service = RAGService(client=mock_openai_client)
        assert service.client is mock_openai_client

    @patch("syfthub.services.rag_service.get_openai_client")
    def test_client_lazy_loads_from_global(self, mock_get_client):
        """Test client lazy loads from global when not provided."""
        mock_client = MagicMock(spec=OpenAIClient)
        mock_get_client.return_value = mock_client

        service = RAGService()
        result = service.client

        mock_get_client.assert_called_once()
        assert result is mock_client


class TestRAGServiceIsAvailable:
    """Test is_available property."""

    def test_is_available_when_client_exists(self, rag_service, mock_openai_client):
        """Test is_available returns True when client exists."""
        assert rag_service.is_available is True

    def test_is_not_available_when_client_is_none(self):
        """Test is_available returns False when client is None."""
        with patch("syfthub.services.rag_service.get_openai_client", return_value=None):
            service = RAGService()
            assert service.is_available is False


class TestRAGServiceGetVectorStoreId:
    """Test _get_vector_store_id method."""

    def test_returns_cached_id(self, rag_service):
        """Test returns cached vector store ID if already set."""
        rag_service._vector_store_id = "cached-store-id"
        result = rag_service._get_vector_store_id()
        assert result == "cached-store-id"
        # Should not call client
        rag_service._client.get_or_create_vector_store.assert_not_called()

    def test_creates_vector_store_on_first_call(self, rag_service, mock_openai_client):
        """Test creates vector store on first call and caches ID."""
        mock_store = VectorStore(
            id="new-store-id",
            name="test-store",
            status="completed",
            file_counts={"total": 0},
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store

        result = rag_service._get_vector_store_id()

        assert result == "new-store-id"
        assert rag_service._vector_store_id == "new-store-id"

    def test_returns_none_when_not_available(self):
        """Test returns None when RAG is not available."""
        with patch("syfthub.services.rag_service.get_openai_client", return_value=None):
            service = RAGService()
            result = service._get_vector_store_id()
            assert result is None

    def test_returns_none_on_client_error(self, rag_service, mock_openai_client):
        """Test returns None on OpenAI client error."""
        mock_openai_client.get_or_create_vector_store.side_effect = OpenAIClientError(
            "Failed to create store", status_code=500
        )

        result = rag_service._get_vector_store_id()

        assert result is None
        assert rag_service._vector_store_id is None


class TestRAGServiceGenerateMarkdown:
    """Test _generate_markdown method."""

    def test_generates_markdown_with_tags(self, rag_service, sample_endpoint):
        """Test generates markdown with tags."""
        result = rag_service._generate_markdown(sample_endpoint)

        assert "# Test Endpoint" in result
        assert "**Type**: model" in result
        assert "**Tags**: test, ml, api" in result
        assert "A test endpoint for semantic search" in result

    def test_generates_markdown_without_tags(self, rag_service, sample_endpoint):
        """Test generates markdown when no tags."""
        sample_endpoint.tags = []
        result = rag_service._generate_markdown(sample_endpoint)

        assert "**Tags**: None" in result

    def test_generates_markdown_with_connection_types(
        self, rag_service, sample_endpoint
    ):
        """Test generates markdown with connection types."""
        result = rag_service._generate_markdown(sample_endpoint)

        assert "http, grpc" in result

    def test_generates_markdown_without_connections(self, rag_service, sample_endpoint):
        """Test generates markdown when no connections."""
        sample_endpoint.connect = []
        result = rag_service._generate_markdown(sample_endpoint)

        assert "## Connection Methods" in result
        assert "None" in result

    def test_handles_connection_without_type(self, rag_service, sample_endpoint):
        """Test handles connections without type field."""
        sample_endpoint.connect = [{"url": "http://example.com"}]  # No 'type' key
        result = rag_service._generate_markdown(sample_endpoint)

        # Should handle gracefully with None for connection methods
        assert "## Connection Methods" in result


class TestRAGServiceIngestEndpoint:
    """Test ingest_endpoint method."""

    def test_ingest_success(self, rag_service, mock_openai_client, sample_endpoint):
        """Test successful endpoint ingestion."""
        # Setup mocks
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_file = FileObject(
            id="file-id-123",
            filename="endpoint_1.md",
            purpose="assistants",
            status="processed",
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.upload_file.return_value = mock_file

        result = rag_service.ingest_endpoint(sample_endpoint)

        assert result == "file-id-123"
        mock_openai_client.upload_file.assert_called_once()
        mock_openai_client.attach_file_to_store.assert_called_once_with(
            vector_store_id="store-id",
            file_id="file-id-123",
            attributes={"endpoint_id": "1"},
        )

    def test_ingest_when_not_available(self, sample_endpoint):
        """Test returns None when RAG not available."""
        with patch("syfthub.services.rag_service.get_openai_client", return_value=None):
            service = RAGService()
            result = service.ingest_endpoint(sample_endpoint)
            assert result is None

    def test_ingest_when_no_vector_store(
        self, rag_service, mock_openai_client, sample_endpoint
    ):
        """Test returns None when vector store unavailable."""
        mock_openai_client.get_or_create_vector_store.side_effect = OpenAIClientError(
            "Failed", 500
        )

        result = rag_service.ingest_endpoint(sample_endpoint)

        assert result is None

    def test_ingest_handles_client_error(
        self, rag_service, mock_openai_client, sample_endpoint
    ):
        """Test handles OpenAI client error during ingestion."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.upload_file.side_effect = OpenAIClientError(
            "Upload failed", 400
        )

        result = rag_service.ingest_endpoint(sample_endpoint)

        assert result is None

    def test_ingest_handles_unexpected_error(
        self, rag_service, mock_openai_client, sample_endpoint
    ):
        """Test handles unexpected exceptions during ingestion."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.upload_file.side_effect = RuntimeError("Unexpected error")

        result = rag_service.ingest_endpoint(sample_endpoint)

        assert result is None


class TestRAGServiceRemoveEndpoint:
    """Test remove_endpoint method."""

    def test_remove_success(self, rag_service, mock_openai_client):
        """Test successful endpoint removal."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store

        result = rag_service.remove_endpoint("file-id-123")

        assert result is True
        mock_openai_client.delete_file_from_store.assert_called_once_with(
            "store-id", "file-id-123"
        )
        mock_openai_client.delete_file.assert_called_once_with("file-id-123")

    def test_remove_when_not_available(self):
        """Test returns True when RAG not available (nothing to remove)."""
        with patch("syfthub.services.rag_service.get_openai_client", return_value=None):
            service = RAGService()
            result = service.remove_endpoint("file-id-123")
            assert result is True

    def test_remove_when_no_file_id(self, rag_service):
        """Test returns True when no file_id provided."""
        result = rag_service.remove_endpoint("")
        assert result is True
        result = rag_service.remove_endpoint(None)
        assert result is True

    def test_remove_when_no_vector_store(self, rag_service, mock_openai_client):
        """Test returns False when vector store unavailable."""
        mock_openai_client.get_or_create_vector_store.side_effect = OpenAIClientError(
            "Failed", 500
        )

        result = rag_service.remove_endpoint("file-id-123")

        assert result is False

    def test_remove_handles_client_error(self, rag_service, mock_openai_client):
        """Test handles OpenAI client error during removal."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.delete_file_from_store.side_effect = OpenAIClientError(
            "Delete failed", 404
        )

        result = rag_service.remove_endpoint("file-id-123")

        assert result is False

    def test_remove_handles_unexpected_error(self, rag_service, mock_openai_client):
        """Test handles unexpected exceptions during removal."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.delete_file_from_store.side_effect = RuntimeError(
            "Unexpected error"
        )

        result = rag_service.remove_endpoint("file-id-123")

        assert result is False


class TestRAGServiceUpdateEndpoint:
    """Test update_endpoint method."""

    def test_update_success_with_old_file(
        self, rag_service, mock_openai_client, sample_endpoint
    ):
        """Test successful update with old file removal."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_file = FileObject(
            id="new-file-id",
            filename="endpoint_1.md",
            purpose="assistants",
            status="processed",
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.upload_file.return_value = mock_file

        result = rag_service.update_endpoint(sample_endpoint, "old-file-id")

        assert result == "new-file-id"
        mock_openai_client.delete_file_from_store.assert_called_once()
        mock_openai_client.upload_file.assert_called_once()

    def test_update_success_without_old_file(
        self, rag_service, mock_openai_client, sample_endpoint
    ):
        """Test successful update without old file."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_file = FileObject(
            id="new-file-id",
            filename="endpoint_1.md",
            purpose="assistants",
            status="processed",
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.upload_file.return_value = mock_file

        result = rag_service.update_endpoint(sample_endpoint, None)

        assert result == "new-file-id"
        mock_openai_client.delete_file_from_store.assert_not_called()

    def test_update_when_not_available(self, sample_endpoint):
        """Test returns None when RAG not available."""
        with patch("syfthub.services.rag_service.get_openai_client", return_value=None):
            service = RAGService()
            result = service.update_endpoint(sample_endpoint, "old-file-id")
            assert result is None


class TestRAGServiceSearch:
    """Test search method."""

    def test_search_success_with_results(self, rag_service, mock_openai_client):
        """Test successful search with results."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_results = [
            SearchResult(
                file_id="file-1",
                score=0.95,
                content="Endpoint 1 content",
                attributes={"endpoint_id": "101"},
            ),
            SearchResult(
                file_id="file-2",
                score=0.85,
                content="Endpoint 2 content",
                attributes={"endpoint_id": "102"},
            ),
        ]
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.search.return_value = mock_results

        result = rag_service.search("test query", max_results=5)

        assert len(result) == 2
        assert result[0] == (101, 0.95)
        assert result[1] == (102, 0.85)

    def test_search_when_not_available(self):
        """Test returns empty list when RAG not available."""
        with patch("syfthub.services.rag_service.get_openai_client", return_value=None):
            service = RAGService()
            result = service.search("test query")
            assert result == []

    def test_search_with_empty_query(self, rag_service):
        """Test returns empty list for empty query."""
        assert rag_service.search("") == []
        assert rag_service.search("   ") == []
        assert rag_service.search(None) == []

    def test_search_when_no_vector_store(self, rag_service, mock_openai_client):
        """Test returns empty list when vector store unavailable."""
        mock_openai_client.get_or_create_vector_store.side_effect = OpenAIClientError(
            "Failed", 500
        )

        result = rag_service.search("test query")

        assert result == []

    def test_search_deduplicates_results(self, rag_service, mock_openai_client):
        """Test search deduplicates results by endpoint ID."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        # Simulate duplicate endpoint IDs
        mock_results = [
            SearchResult(
                file_id="file-1",
                score=0.95,
                content="Content 1",
                attributes={"endpoint_id": "101"},
            ),
            SearchResult(
                file_id="file-2",
                score=0.90,
                content="Content 2",
                attributes={"endpoint_id": "101"},  # Duplicate
            ),
            SearchResult(
                file_id="file-3",
                score=0.85,
                content="Content 3",
                attributes={"endpoint_id": "102"},
            ),
        ]
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.search.return_value = mock_results

        result = rag_service.search("test query")

        # Should have only 2 unique endpoints
        assert len(result) == 2
        assert result[0] == (101, 0.95)  # First occurrence kept
        assert result[1] == (102, 0.85)

    def test_search_handles_invalid_endpoint_id(self, rag_service, mock_openai_client):
        """Test handles invalid endpoint_id gracefully."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_results = [
            SearchResult(
                file_id="file-1",
                score=0.95,
                content="Content 1",
                attributes={"endpoint_id": "not-a-number"},
            ),
            SearchResult(
                file_id="file-2",
                score=0.85,
                content="Content 2",
                attributes={"endpoint_id": "102"},
            ),
        ]
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.search.return_value = mock_results

        result = rag_service.search("test query")

        # Should skip invalid and return only valid
        assert len(result) == 1
        assert result[0] == (102, 0.85)

    def test_search_handles_missing_endpoint_id(self, rag_service, mock_openai_client):
        """Test handles missing endpoint_id in attributes."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_results = [
            SearchResult(
                file_id="file-1",
                score=0.95,
                content="Content 1",
                attributes={},  # No endpoint_id
            ),
            SearchResult(
                file_id="file-2",
                score=0.85,
                content="Content 2",
                attributes={"endpoint_id": "102"},
            ),
        ]
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.search.return_value = mock_results

        result = rag_service.search("test query")

        # Should skip missing and return only valid
        assert len(result) == 1
        assert result[0] == (102, 0.85)

    def test_search_normalizes_scores(self, rag_service, mock_openai_client):
        """Test scores are normalized to 0-1 range."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_results = [
            SearchResult(
                file_id="file-1",
                score=1.5,  # Above 1.0
                content="Content 1",
                attributes={"endpoint_id": "101"},
            ),
            SearchResult(
                file_id="file-2",
                score=-0.5,  # Below 0.0
                content="Content 2",
                attributes={"endpoint_id": "102"},
            ),
        ]
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.search.return_value = mock_results

        result = rag_service.search("test query")

        assert result[0] == (101, 1.0)  # Clamped to 1.0
        assert result[1] == (102, 0.0)  # Clamped to 0.0

    def test_search_handles_client_error(self, rag_service, mock_openai_client):
        """Test handles OpenAI client error during search."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.search.side_effect = OpenAIClientError("Search failed", 500)

        result = rag_service.search("test query")

        assert result == []

    def test_search_handles_unexpected_error(self, rag_service, mock_openai_client):
        """Test handles unexpected exceptions during search."""
        mock_store = VectorStore(
            id="store-id", name="test", status="completed", file_counts={}
        )
        mock_openai_client.get_or_create_vector_store.return_value = mock_store
        mock_openai_client.search.side_effect = RuntimeError("Unexpected error")

        result = rag_service.search("test query")

        assert result == []


class TestGetRAGService:
    """Test get_rag_service function."""

    def test_returns_singleton_instance(self):
        """Test returns the same instance on multiple calls."""
        # Reset the global instance for clean test
        import syfthub.services.rag_service as rag_module

        rag_module._rag_service_instance = None

        with patch("syfthub.services.rag_service.get_openai_client", return_value=None):
            service1 = get_rag_service()
            service2 = get_rag_service()

            assert service1 is service2
