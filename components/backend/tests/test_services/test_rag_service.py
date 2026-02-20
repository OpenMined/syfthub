"""Tests for RAGService - Endpoint search using Meilisearch."""

from unittest.mock import MagicMock, patch

import meilisearch
import pytest
from meilisearch.errors import MeilisearchApiError, MeilisearchCommunicationError

from syfthub.models.endpoint import EndpointModel
from syfthub.services.rag_service import RAGService, get_rag_service


@pytest.fixture
def mock_meili_client():
    """Create a mock Meilisearch client."""
    client = MagicMock(spec=meilisearch.Client)
    client.index.return_value = MagicMock()
    return client


@pytest.fixture
def rag_service(mock_meili_client):
    """Create RAGService with mocked Meilisearch client."""
    return RAGService(client=mock_meili_client)


@pytest.fixture
def sample_endpoint():
    """Create a sample endpoint model for testing."""
    endpoint = MagicMock(spec=EndpointModel)
    endpoint.id = 1
    endpoint.name = "Test Endpoint"
    endpoint.type = "model"
    endpoint.description = "A test endpoint for search"
    endpoint.readme = "# Test Endpoint\n\nThis is documentation."
    endpoint.tags = ["test", "ml", "api"]
    endpoint.connect = [{"type": "http"}, {"type": "grpc"}]
    return endpoint


class TestRAGServiceInit:
    """Test RAGService initialization."""

    def test_init_with_client(self, mock_meili_client):
        """Test initialization with provided client."""
        service = RAGService(client=mock_meili_client)
        assert service._client is mock_meili_client
        assert service._index_configured is False

    def test_init_without_client(self):
        """Test initialization without client (lazy loading)."""
        service = RAGService()
        assert service._client is None
        assert service._index_configured is False


class TestRAGServiceClientProperty:
    """Test client property lazy initialization."""

    def test_client_returns_provided_client(self, mock_meili_client):
        """Test client property returns provided client."""
        service = RAGService(client=mock_meili_client)
        assert service.client is mock_meili_client

    def test_client_lazy_creates_when_rag_available(self):
        """Test client is created lazily when settings.rag_available is True."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = True
            mock_settings.meili_url = "http://meilisearch:7700"
            mock_settings.meili_master_key = "test-key"

            with patch("syfthub.services.rag_service.meilisearch.Client") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client

                service = RAGService()
                result = service.client

                mock_cls.assert_called_once_with(
                    mock_settings.meili_url, mock_settings.meili_master_key
                )
                assert result is mock_client

    def test_client_returns_none_when_rag_not_available(self):
        """Test client returns None when settings.rag_available is False."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = False
            service = RAGService()
            assert service.client is None


class TestRAGServiceIsAvailable:
    """Test is_available property."""

    def test_is_available_when_client_exists(self, rag_service):
        """Test is_available returns True when client exists."""
        assert rag_service.is_available is True

    def test_is_not_available_when_client_is_none(self):
        """Test is_available returns False when client is None."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = False
            service = RAGService()
            assert service.is_available is False


class TestRAGServiceEnsureIndex:
    """Test _ensure_index method."""

    def test_ensure_index_creates_and_configures_on_first_call(
        self, rag_service, mock_meili_client
    ):
        """Test _ensure_index creates index and updates settings on first call."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            result = rag_service._ensure_index()

            assert result is True
            assert rag_service._index_configured is True
            mock_meili_client.create_index.assert_called_once_with(
                "syfthub-endpoints", {"primaryKey": "id"}
            )
            mock_meili_client.index.assert_called_with("syfthub-endpoints")
            mock_meili_client.index.return_value.update_settings.assert_called_once()

    def test_ensure_index_is_idempotent(self, rag_service, mock_meili_client):
        """Test _ensure_index only configures once."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            rag_service._ensure_index()
            rag_service._ensure_index()

            # create_index called only once
            mock_meili_client.create_index.assert_called_once()

    def test_ensure_index_returns_false_when_not_available(self):
        """Test _ensure_index returns False when service not available."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = False
            service = RAGService()
            result = service._ensure_index()
            assert result is False

    def test_ensure_index_handles_api_error(self, rag_service, mock_meili_client):
        """Test _ensure_index returns False on MeilisearchApiError."""
        mock_request = MagicMock()
        mock_request.text = '{"message": "Internal error", "code": "internal_error"}'
        mock_meili_client.create_index.side_effect = MeilisearchApiError(
            "Internal error", mock_request
        )
        result = rag_service._ensure_index()
        assert result is False
        assert rag_service._index_configured is False

    def test_ensure_index_handles_communication_error(
        self, rag_service, mock_meili_client
    ):
        """Test _ensure_index returns False on MeilisearchCommunicationError."""
        mock_meili_client.create_index.side_effect = MeilisearchCommunicationError(
            "Connection refused"
        )
        result = rag_service._ensure_index()
        assert result is False
        assert rag_service._index_configured is False


class TestRAGServiceBuildDocument:
    """Test _build_document method."""

    def test_builds_document_with_all_fields(self, rag_service, sample_endpoint):
        """Test _build_document produces correct dict structure."""
        doc = rag_service._build_document(sample_endpoint)

        assert doc["id"] == "1"
        assert doc["endpoint_id"] == 1
        assert doc["name"] == "Test Endpoint"
        assert doc["description"] == "A test endpoint for search"
        assert "test" in doc["tags"]
        assert doc["type"] == "model"
        assert "http" in doc["connect_types"]
        assert "grpc" in doc["connect_types"]

    def test_builds_document_with_empty_tags(self, rag_service, sample_endpoint):
        """Test _build_document handles empty tags."""
        sample_endpoint.tags = []
        doc = rag_service._build_document(sample_endpoint)
        assert doc["tags"] == ""

    def test_builds_document_with_empty_connections(self, rag_service, sample_endpoint):
        """Test _build_document handles empty connections."""
        sample_endpoint.connect = []
        doc = rag_service._build_document(sample_endpoint)
        assert doc["connect_types"] == ""

    def test_builds_document_skips_connections_without_type(
        self, rag_service, sample_endpoint
    ):
        """Test _build_document skips connections without type field."""
        sample_endpoint.connect = [{"url": "http://example.com"}]
        doc = rag_service._build_document(sample_endpoint)
        assert doc["connect_types"] == ""

    def test_builds_document_with_none_fields(self, rag_service, sample_endpoint):
        """Test _build_document handles None description and readme."""
        sample_endpoint.description = None
        sample_endpoint.readme = None
        doc = rag_service._build_document(sample_endpoint)
        assert doc["description"] == ""
        assert doc["readme"] == ""


class TestRAGServiceIngestEndpoint:
    """Test ingest_endpoint method."""

    def test_ingest_success(self, rag_service, mock_meili_client, sample_endpoint):
        """Test successful endpoint ingestion returns str(endpoint.id)."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_available = True

            result = rag_service.ingest_endpoint(sample_endpoint)

            assert result == "1"
            mock_meili_client.index.return_value.add_documents.assert_called_once()
            call_args = mock_meili_client.index.return_value.add_documents.call_args
            docs = call_args[0][0]
            assert len(docs) == 1
            assert docs[0]["id"] == "1"
            assert docs[0]["endpoint_id"] == 1

    def test_ingest_when_not_available(self, sample_endpoint):
        """Test returns None when search not available."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = False
            service = RAGService()
            result = service.ingest_endpoint(sample_endpoint)
            assert result is None

    def test_ingest_when_ensure_index_fails(
        self, rag_service, mock_meili_client, sample_endpoint
    ):
        """Test returns None when index setup fails."""
        mock_meili_client.create_index.side_effect = MeilisearchCommunicationError(
            "Connection refused"
        )
        result = rag_service.ingest_endpoint(sample_endpoint)
        assert result is None

    def test_ingest_handles_api_error(
        self, rag_service, mock_meili_client, sample_endpoint
    ):
        """Test handles MeilisearchApiError during ingestion."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            mock_request = MagicMock()
            mock_request.text = '{"message": "Bad request", "code": "bad_request"}'
            mock_meili_client.index.return_value.add_documents.side_effect = (
                MeilisearchApiError("Bad request", mock_request)
            )

            result = rag_service.ingest_endpoint(sample_endpoint)
            assert result is None

    def test_ingest_handles_communication_error(
        self, rag_service, mock_meili_client, sample_endpoint
    ):
        """Test handles MeilisearchCommunicationError during ingestion."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            mock_meili_client.index.return_value.add_documents.side_effect = (
                MeilisearchCommunicationError("Connection lost")
            )

            result = rag_service.ingest_endpoint(sample_endpoint)
            assert result is None

    def test_ingest_handles_unexpected_error(
        self, rag_service, mock_meili_client, sample_endpoint
    ):
        """Test handles unexpected exceptions during ingestion."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            mock_meili_client.index.return_value.add_documents.side_effect = (
                RuntimeError("Unexpected error")
            )

            result = rag_service.ingest_endpoint(sample_endpoint)
            assert result is None


class TestRAGServiceRemoveEndpoint:
    """Test remove_endpoint method."""

    def test_remove_success(self, rag_service, mock_meili_client):
        """Test successful endpoint removal."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            result = rag_service.remove_endpoint("1")

            assert result is True
            mock_meili_client.index.return_value.delete_document.assert_called_once_with(
                "1"
            )

    def test_remove_when_not_available(self):
        """Test returns True when search not available (nothing to remove)."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = False
            service = RAGService()
            result = service.remove_endpoint("1")
            assert result is True

    def test_remove_when_no_file_id(self, rag_service):
        """Test returns True when no file_id provided."""
        assert rag_service.remove_endpoint("") is True
        assert rag_service.remove_endpoint(None) is True

    def test_remove_handles_api_error(self, rag_service, mock_meili_client):
        """Test handles MeilisearchApiError during removal."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            mock_request = MagicMock()
            mock_request.text = '{"message": "Not found", "code": "document_not_found"}'
            mock_meili_client.index.return_value.delete_document.side_effect = (
                MeilisearchApiError("Not found", mock_request)
            )

            result = rag_service.remove_endpoint("1")
            assert result is False

    def test_remove_handles_communication_error(self, rag_service, mock_meili_client):
        """Test handles MeilisearchCommunicationError during removal."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            mock_meili_client.index.return_value.delete_document.side_effect = (
                MeilisearchCommunicationError("Connection refused")
            )

            result = rag_service.remove_endpoint("1")
            assert result is False

    def test_remove_handles_unexpected_error(self, rag_service, mock_meili_client):
        """Test handles unexpected exceptions during removal."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"

            mock_meili_client.index.return_value.delete_document.side_effect = (
                RuntimeError("Unexpected error")
            )

            result = rag_service.remove_endpoint("1")
            assert result is False


class TestRAGServiceUpdateEndpoint:
    """Test update_endpoint method."""

    def test_update_calls_ingest(self, rag_service, sample_endpoint):
        """Test update delegates to ingest_endpoint."""
        with patch.object(
            rag_service, "ingest_endpoint", return_value="1"
        ) as mock_ingest:
            result = rag_service.update_endpoint(sample_endpoint, "old-id")
            assert result == "1"
            mock_ingest.assert_called_once_with(sample_endpoint)

    def test_update_ignores_old_file_id(self, rag_service, sample_endpoint):
        """Test update ignores old_file_id (upsert semantics)."""
        with patch.object(
            rag_service, "ingest_endpoint", return_value="1"
        ) as mock_ingest:
            rag_service.update_endpoint(sample_endpoint, None)
            mock_ingest.assert_called_once_with(sample_endpoint)

    def test_update_when_not_available(self, sample_endpoint):
        """Test returns None when search not available."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = False
            service = RAGService()
            result = service.update_endpoint(sample_endpoint, "old-id")
            assert result is None


class TestRAGServiceSearch:
    """Test search method."""

    def test_search_success_with_results(self, rag_service, mock_meili_client):
        """Test successful search returns (endpoint_id, score) tuples."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.return_value = {
                "hits": [
                    {"endpoint_id": 101, "_rankingScore": 0.95},
                    {"endpoint_id": 102, "_rankingScore": 0.85},
                ]
            }

            result = rag_service.search("test query", max_results=5)

            assert len(result) == 2
            assert result[0] == (101, 0.95)
            assert result[1] == (102, 0.85)

    def test_search_passes_correct_options(self, rag_service, mock_meili_client):
        """Test search calls Meilisearch with showRankingScore=True."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.return_value = {"hits": []}

            rag_service.search("test query", max_results=5)

            call_args = mock_meili_client.index.return_value.search.call_args
            opts = call_args[0][1]
            assert opts["showRankingScore"] is True
            assert opts["limit"] == 10  # min(5*2, 50)

    def test_search_when_not_available(self):
        """Test returns empty list when search not available."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = False
            service = RAGService()
            result = service.search("test query")
            assert result == []

    def test_search_with_empty_query(self, rag_service):
        """Test returns empty list for empty or whitespace query."""
        assert rag_service.search("") == []
        assert rag_service.search("   ") == []
        assert rag_service.search(None) == []

    def test_search_deduplicates_results(self, rag_service, mock_meili_client):
        """Test search deduplicates results by endpoint_id."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.return_value = {
                "hits": [
                    {"endpoint_id": 101, "_rankingScore": 0.95},
                    {"endpoint_id": 101, "_rankingScore": 0.90},  # Duplicate
                    {"endpoint_id": 102, "_rankingScore": 0.85},
                ]
            }

            result = rag_service.search("test query")

            assert len(result) == 2
            assert result[0] == (101, 0.95)  # First occurrence kept
            assert result[1] == (102, 0.85)

    def test_search_handles_missing_endpoint_id(self, rag_service, mock_meili_client):
        """Test handles hits missing endpoint_id field."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.return_value = {
                "hits": [
                    {"_rankingScore": 0.95},  # No endpoint_id
                    {"endpoint_id": 102, "_rankingScore": 0.85},
                ]
            }

            result = rag_service.search("test query")

            assert len(result) == 1
            assert result[0] == (102, 0.85)

    def test_search_handles_invalid_endpoint_id(self, rag_service, mock_meili_client):
        """Test handles non-integer endpoint_id gracefully."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.return_value = {
                "hits": [
                    {"endpoint_id": "not-a-number", "_rankingScore": 0.95},
                    {"endpoint_id": 102, "_rankingScore": 0.85},
                ]
            }

            result = rag_service.search("test query")

            assert len(result) == 1
            assert result[0] == (102, 0.85)

    def test_search_normalizes_scores(self, rag_service, mock_meili_client):
        """Test scores are clamped to 0-1 range."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.return_value = {
                "hits": [
                    {"endpoint_id": 101, "_rankingScore": 1.5},  # Above 1.0
                    {"endpoint_id": 102, "_rankingScore": -0.5},  # Below 0.0
                ]
            }

            result = rag_service.search("test query")

            assert result[0] == (101, 1.0)  # Clamped to 1.0
            assert result[1] == (102, 0.0)  # Clamped to 0.0

    def test_search_handles_api_error(self, rag_service, mock_meili_client):
        """Test handles MeilisearchApiError during search."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_request = MagicMock()
            mock_request.text = '{"message": "Search failed", "code": "internal_error"}'
            mock_meili_client.index.return_value.search.side_effect = (
                MeilisearchApiError("Search failed", mock_request)
            )

            result = rag_service.search("test query")
            assert result == []

    def test_search_handles_communication_error(self, rag_service, mock_meili_client):
        """Test handles MeilisearchCommunicationError during search."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.side_effect = (
                MeilisearchCommunicationError("Connection refused")
            )

            result = rag_service.search("test query")
            assert result == []

    def test_search_handles_unexpected_error(self, rag_service, mock_meili_client):
        """Test handles unexpected exceptions during search."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = rag_service.search("test query")
            assert result == []

    def test_search_returns_empty_on_empty_hits(self, rag_service, mock_meili_client):
        """Test returns empty list when Meilisearch returns no hits."""
        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.meili_index_name = "syfthub-endpoints"
            mock_settings.rag_max_results = 50

            mock_meili_client.index.return_value.search.return_value = {"hits": []}

            result = rag_service.search("test query")
            assert result == []


class TestGetRAGService:
    """Test get_rag_service function."""

    def test_returns_singleton_instance(self):
        """Test returns the same instance on multiple calls."""
        import syfthub.services.rag_service as rag_module

        rag_module._rag_service_instance = None

        with patch("syfthub.services.rag_service.settings") as mock_settings:
            mock_settings.rag_available = False
            service1 = get_rag_service()
            service2 = get_rag_service()

            assert service1 is service2

        # Clean up singleton for other tests
        rag_module._rag_service_instance = None
