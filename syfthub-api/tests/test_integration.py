"""
Integration tests for endpoint execution.

This module tests the actual HTTP request/response cycle for registered endpoints
using FastAPI's TestClient.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from syfthub_api import (
    DataSourceQueryResponse,
    Document,
    Message,
    ModelQueryResponse,
    SyftAPI,
)


class TestDataSourceEndpointExecution:
    """Tests for data source endpoint HTTP execution."""

    def test_datasource_query_returns_documents(self, app: SyftAPI) -> None:
        """Test that a datasource endpoint returns documents correctly."""

        @app.datasource(
            slug="test-search",
            name="Test Search",
            description="A test search endpoint",
        )
        async def search(query: str) -> list[Document]:
            return [
                Document(
                    document_id="doc-1",
                    content=f"Result for: {query}",
                    metadata={"query": query},
                    similarity_score=0.95,
                ),
                Document(
                    document_id="doc-2",
                    content="Another result",
                    metadata={},
                    similarity_score=0.85,
                ),
            ]

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/test-search/query",
            json={"messages": "test query"},
        )

        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert "references" in data
        assert "documents" in data["references"]
        assert len(data["references"]["documents"]) == 2

        # Validate first document
        doc1 = data["references"]["documents"][0]
        assert doc1["document_id"] == "doc-1"
        assert doc1["content"] == "Result for: test query"
        assert doc1["metadata"]["query"] == "test query"
        assert doc1["similarity_score"] == 0.95

    def test_datasource_empty_results(self, app: SyftAPI) -> None:
        """Test that an empty result set is handled correctly."""

        @app.datasource(
            slug="empty-search",
            name="Empty Search",
            description="Returns no results",
        )
        async def empty_search(query: str) -> list[Document]:
            return []

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/empty-search/query",
            json={"messages": "no results query"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["references"]["documents"] == []

    def test_datasource_with_custom_request_params(self, app: SyftAPI) -> None:
        """Test datasource with custom request parameters."""

        @app.datasource(
            slug="custom-search",
            name="Custom Search",
            description="Search with custom params",
        )
        async def custom_search(query: str) -> list[Document]:
            return [
                Document(
                    document_id="custom-doc",
                    content=query,
                    similarity_score=1.0,
                )
            ]

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/custom-search/query",
            json={
                "messages": "custom query",
                "limit": 10,
                "similarity_threshold": 0.8,
                "include_metadata": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["references"]["documents"]) == 1

    def test_datasource_response_model_validation(self, app: SyftAPI) -> None:
        """Test that response matches DataSourceQueryResponse schema."""

        @app.datasource(
            slug="schema-test",
            name="Schema Test",
            description="Test schema validation",
        )
        async def schema_test(query: str) -> list[Document]:
            return [
                Document(
                    document_id="schema-doc",
                    content="Schema test content",
                    metadata={"key": "value"},
                    similarity_score=0.9,
                )
            ]

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/schema-test/query",
            json={"messages": "schema query"},
        )

        assert response.status_code == 200
        # Validate against Pydantic model
        parsed = DataSourceQueryResponse.model_validate(response.json())
        assert len(parsed.references.documents) == 1
        assert parsed.references.documents[0].document_id == "schema-doc"


class TestModelEndpointExecution:
    """Tests for model endpoint HTTP execution."""

    def test_model_query_returns_response(self, app: SyftAPI) -> None:
        """Test that a model endpoint returns a proper response."""

        @app.model(
            slug="test-model",
            name="Test Model",
            description="A test model endpoint",
        )
        async def generate(messages: list[Message]) -> str:
            last_message = messages[-1].content if messages else "empty"
            return f"Response to: {last_message}"

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/test-model/query",
            json={
                "messages": [
                    {"role": "user", "content": "Hello, model!"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert "summary" in data
        assert "message" in data["summary"]
        assert data["summary"]["message"]["content"] == "Response to: Hello, model!"
        assert data["summary"]["message"]["role"] == "assistant"
        assert data["summary"]["model"] == "test-model"
        assert data["summary"]["finish_reason"] == "stop"

    def test_model_with_conversation_history(self, app: SyftAPI) -> None:
        """Test model with multi-turn conversation."""

        @app.model(
            slug="conversation-model",
            name="Conversation Model",
            description="Handles conversations",
        )
        async def converse(messages: list[Message]) -> str:
            return f"Received {len(messages)} messages"

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/conversation-model/query",
            json={
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Hi!"},
                    {"role": "assistant", "content": "Hello!"},
                    {"role": "user", "content": "How are you?"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["message"]["content"] == "Received 4 messages"

    def test_model_response_has_unique_id(self, app: SyftAPI) -> None:
        """Test that each model response has a unique ID."""

        @app.model(
            slug="id-model",
            name="ID Model",
            description="Tests unique IDs",
        )
        async def generate(messages: list[Message]) -> str:
            return "Response"

        client = TestClient(app.get_app())

        # Make two requests
        response1 = client.post(
            "/api/v1/endpoints/id-model/query",
            json={"messages": [{"role": "user", "content": "First"}]},
        )
        response2 = client.post(
            "/api/v1/endpoints/id-model/query",
            json={"messages": [{"role": "user", "content": "Second"}]},
        )

        id1 = response1.json()["summary"]["id"]
        id2 = response2.json()["summary"]["id"]

        # IDs should be unique and follow OpenAI format
        assert id1 != id2
        assert id1.startswith("chatcmpl-")
        assert id2.startswith("chatcmpl-")

    def test_model_response_schema_validation(self, app: SyftAPI) -> None:
        """Test that response matches ModelQueryResponse schema."""

        @app.model(
            slug="schema-model",
            name="Schema Model",
            description="Tests schema",
        )
        async def generate(messages: list[Message]) -> str:
            return "Schema validated response"

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/schema-model/query",
            json={"messages": [{"role": "user", "content": "Test"}]},
        )

        assert response.status_code == 200
        # Validate against Pydantic model
        parsed = ModelQueryResponse.model_validate(response.json())
        assert parsed.summary.message.content == "Schema validated response"
        assert parsed.summary.finish_reason == "stop"


class TestMultipleEndpoints:
    """Tests for applications with multiple endpoints."""

    def test_multiple_datasources(self, app: SyftAPI) -> None:
        """Test multiple datasource endpoints work independently."""

        @app.datasource(slug="ds-one", name="DS One", description="First datasource")
        async def ds_one(query: str) -> list[Document]:
            return [Document(document_id="one", content="One", similarity_score=1.0)]

        @app.datasource(slug="ds-two", name="DS Two", description="Second datasource")
        async def ds_two(query: str) -> list[Document]:
            return [Document(document_id="two", content="Two", similarity_score=1.0)]

        client = TestClient(app.get_app())

        resp1 = client.post("/api/v1/endpoints/ds-one/query", json={"messages": "query"})
        resp2 = client.post("/api/v1/endpoints/ds-two/query", json={"messages": "query"})

        assert resp1.json()["references"]["documents"][0]["content"] == "One"
        assert resp2.json()["references"]["documents"][0]["content"] == "Two"

    def test_mixed_endpoint_types(self, app: SyftAPI) -> None:
        """Test datasource and model endpoints work together."""

        @app.datasource(slug="search", name="Search", description="Search endpoint")
        async def search(query: str) -> list[Document]:
            return [Document(document_id="s1", content="Search", similarity_score=1.0)]

        @app.model(slug="generate", name="Generate", description="Model endpoint")
        async def generate(messages: list[Message]) -> str:
            return "Generated"

        client = TestClient(app.get_app())

        search_resp = client.post("/api/v1/endpoints/search/query", json={"messages": "q"})
        model_resp = client.post(
            "/api/v1/endpoints/generate/query",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

        assert search_resp.status_code == 200
        assert model_resp.status_code == 200
        assert search_resp.json()["references"]["documents"][0]["content"] == "Search"
        assert model_resp.json()["summary"]["message"]["content"] == "Generated"


class TestErrorHandling:
    """Tests for error handling in endpoint execution."""

    def test_invalid_endpoint_returns_404(self, app: SyftAPI) -> None:
        """Test that non-existent endpoints return 404."""
        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/nonexistent/query",
            json={"messages": "test"},
        )
        assert response.status_code == 404

    def test_invalid_request_body_returns_422(self, app: SyftAPI) -> None:
        """Test that invalid request bodies return 422."""

        @app.datasource(slug="valid", name="Valid", description="Valid endpoint")
        async def valid(query: str) -> list[Document]:
            return []

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/valid/query",
            json={},  # Missing required 'messages' field
        )
        assert response.status_code == 422

    def test_invalid_message_role_returns_422(self, app: SyftAPI) -> None:
        """Test that invalid message roles return 422."""

        @app.model(slug="role-test", name="Role Test", description="Tests roles")
        async def role_test(messages: list[Message]) -> str:
            return "Response"

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/role-test/query",
            json={"messages": [{"role": "invalid_role", "content": "test"}]},
        )
        assert response.status_code == 422


class TestLifecycleHooksIntegration:
    """Tests for lifecycle hooks with endpoint execution."""

    def test_startup_hook_runs_before_requests(self, app: SyftAPI) -> None:
        """Test that startup hooks run before handling requests."""
        startup_called = {"value": False}

        @app.on_startup
        async def startup() -> None:
            startup_called["value"] = True

        @app.datasource(slug="hook-test", name="Hook Test", description="Tests hooks")
        async def hook_test(query: str) -> list[Document]:
            return [
                Document(
                    document_id="hook",
                    content=f"Startup was called: {startup_called['value']}",
                    similarity_score=1.0,
                )
            ]

        # Using TestClient triggers the lifespan context
        with TestClient(app.get_app()) as client:
            response = client.post(
                "/api/v1/endpoints/hook-test/query",
                json={"messages": "test"},
            )

        assert response.status_code == 200
        # Startup hook should have been called
        assert startup_called["value"] is True


class TestMiddlewareIntegration:
    """Tests for middleware with endpoint execution."""

    def test_custom_middleware_processes_requests(self, app: SyftAPI) -> None:
        """Test that custom middleware processes requests."""
        from fastapi import Request, Response

        middleware_called = {"value": False}

        @app.middleware
        async def track_middleware(
            request: Request,
            call_next: callable,  # type: ignore
        ) -> Response:
            middleware_called["value"] = True
            response = await call_next(request)
            response.headers["X-Middleware-Processed"] = "true"
            return response

        @app.datasource(slug="mw-test", name="MW Test", description="Tests middleware")
        async def mw_test(query: str) -> list[Document]:
            return []

        client = TestClient(app.get_app())
        response = client.post(
            "/api/v1/endpoints/mw-test/query",
            json={"messages": "test"},
        )

        assert response.status_code == 200
        assert middleware_called["value"] is True
        assert response.headers.get("X-Middleware-Processed") == "true"
