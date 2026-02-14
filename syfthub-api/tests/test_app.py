"""
Tests for SyftAPI core functionality.

This module tests the main SyftAPI class including endpoint registration,
validation, lifecycle hooks, and middleware support.
"""

from __future__ import annotations

import pytest

from syfthub_api import (
    ConfigurationError,
    Document,
    EndpointRegistrationError,
    EndpointType,
    Message,
    SyftAPI,
)


class TestSyftAPIInitialization:
    """Tests for SyftAPI initialization."""

    def test_init_with_explicit_values(self) -> None:
        """Test initialization with explicit constructor arguments."""
        app = SyftAPI(
            syfthub_url="http://example.com",
            api_key="syft_pat_test_token",
            space_url="http://space.example.com",
        )
        assert app._syfthub_url == "http://example.com"
        assert app._api_key == "syft_pat_test_token"
        assert app._space_url == "http://space.example.com"

    def test_init_with_env_vars(self, app: SyftAPI) -> None:
        """Test initialization with environment variables (via fixture)."""
        assert app._syfthub_url == "http://test.example.com"
        assert app._api_key == "syft_pat_test_token"
        assert app._space_url == "http://localhost:8001"

    def test_init_missing_syfthub_url_raises(self) -> None:
        """Test that missing syfthub_url raises ConfigurationError."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigurationError, match="syfthub_url"):
                SyftAPI(
                    api_key="syft_pat_test_token",
                    space_url="http://space.example.com",
                )

    def test_init_missing_api_key_raises(self) -> None:
        """Test that missing api_key raises ConfigurationError."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigurationError, match="api_key"):
                SyftAPI(
                    syfthub_url="http://example.com",
                    space_url="http://space.example.com",
                )


class TestEndpointRegistration:
    """Tests for endpoint registration functionality."""

    def test_register_datasource(self, app: SyftAPI) -> None:
        """Test registering a data source endpoint."""

        @app.datasource(
            slug="test-datasource",
            name="Test Data Source",
            description="A test data source",
        )
        async def search(query: str) -> list[Document]:
            return []

        assert len(app.endpoints) == 1
        endpoint = app.endpoints[0]
        assert endpoint["slug"] == "test-datasource"
        assert endpoint["name"] == "Test Data Source"
        assert endpoint["type"] == EndpointType.DATA_SOURCE
        # The stored fn is the original function (before wrapper)
        assert endpoint["fn"].__name__ == "search"
        assert callable(endpoint["fn"])

    def test_register_model(self, app: SyftAPI) -> None:
        """Test registering a model endpoint."""

        @app.model(
            slug="test-model",
            name="Test Model",
            description="A test model",
        )
        async def generate(messages: list[Message]) -> str:
            return "Test response"

        assert len(app.endpoints) == 1
        endpoint = app.endpoints[0]
        assert endpoint["slug"] == "test-model"
        assert endpoint["name"] == "Test Model"
        assert endpoint["type"] == EndpointType.MODEL

    def test_register_multiple_endpoints(self, app: SyftAPI) -> None:
        """Test registering multiple endpoints."""

        @app.datasource(slug="ds1", name="DS1", description="First data source")
        async def ds1(query: str) -> list[Document]:
            return []

        @app.model(slug="model1", name="Model1", description="First model")
        async def model1(messages: list[Message]) -> str:
            return ""

        @app.datasource(slug="ds2", name="DS2", description="Second data source")
        async def ds2(query: str) -> list[Document]:
            return []

        assert len(app.endpoints) == 3
        assert app.endpoints[0]["slug"] == "ds1"
        assert app.endpoints[1]["slug"] == "model1"
        assert app.endpoints[2]["slug"] == "ds2"


class TestSlugValidation:
    """Tests for endpoint slug validation."""

    def test_valid_slug_lowercase(self, app: SyftAPI) -> None:
        """Test that lowercase slugs are valid."""

        @app.datasource(slug="my-endpoint", name="Test", description="Test")
        async def fn(query: str) -> list[Document]:
            return []

        assert app.endpoints[0]["slug"] == "my-endpoint"

    def test_valid_slug_with_numbers(self, app: SyftAPI) -> None:
        """Test that slugs with numbers are valid."""

        @app.datasource(slug="endpoint-v2", name="Test", description="Test")
        async def fn(query: str) -> list[Document]:
            return []

        assert app.endpoints[0]["slug"] == "endpoint-v2"

    def test_valid_slug_with_underscores(self, app: SyftAPI) -> None:
        """Test that slugs with underscores are valid."""

        @app.datasource(slug="my_endpoint", name="Test", description="Test")
        async def fn(query: str) -> list[Document]:
            return []

        assert app.endpoints[0]["slug"] == "my_endpoint"

    def test_valid_single_char_slug(self, app: SyftAPI) -> None:
        """Test that single character slugs are valid."""

        @app.datasource(slug="a", name="Test", description="Test")
        async def fn(query: str) -> list[Document]:
            return []

        assert app.endpoints[0]["slug"] == "a"

    def test_invalid_slug_uppercase_raises(self, app: SyftAPI) -> None:
        """Test that uppercase slugs raise EndpointRegistrationError."""
        with pytest.raises(EndpointRegistrationError, match="Invalid slug"):

            @app.datasource(slug="MyEndpoint", name="Test", description="Test")
            async def fn(query: str) -> list[Document]:
                return []

    def test_invalid_slug_spaces_raises(self, app: SyftAPI) -> None:
        """Test that slugs with spaces raise EndpointRegistrationError."""
        with pytest.raises(EndpointRegistrationError, match="Invalid slug"):

            @app.datasource(slug="my endpoint", name="Test", description="Test")
            async def fn(query: str) -> list[Document]:
                return []

    def test_invalid_slug_special_chars_raises(self, app: SyftAPI) -> None:
        """Test that slugs with special characters raise error."""
        with pytest.raises(EndpointRegistrationError, match="Invalid slug"):

            @app.datasource(slug="my@endpoint!", name="Test", description="Test")
            async def fn(query: str) -> list[Document]:
                return []

    def test_empty_slug_raises(self, app: SyftAPI) -> None:
        """Test that empty slugs raise EndpointRegistrationError."""
        with pytest.raises(EndpointRegistrationError, match="cannot be empty"):

            @app.datasource(slug="", name="Test", description="Test")
            async def fn(query: str) -> list[Document]:
                return []

    def test_duplicate_slug_raises(self, app: SyftAPI) -> None:
        """Test that duplicate slugs raise EndpointRegistrationError."""

        @app.datasource(slug="duplicate", name="First", description="First endpoint")
        async def first(query: str) -> list[Document]:
            return []

        with pytest.raises(EndpointRegistrationError, match="Duplicate endpoint slug"):

            @app.datasource(slug="duplicate", name="Second", description="Second endpoint")
            async def second(query: str) -> list[Document]:
                return []


class TestNameAndDescriptionValidation:
    """Tests for endpoint name and description validation."""

    def test_empty_name_raises(self, app: SyftAPI) -> None:
        """Test that empty name raises EndpointRegistrationError."""
        with pytest.raises(EndpointRegistrationError, match="name cannot be empty"):

            @app.datasource(slug="test", name="", description="Test description")
            async def fn(query: str) -> list[Document]:
                return []

    def test_whitespace_name_raises(self, app: SyftAPI) -> None:
        """Test that whitespace-only name raises error."""
        with pytest.raises(EndpointRegistrationError, match="name cannot be empty"):

            @app.datasource(slug="test", name="   ", description="Test description")
            async def fn(query: str) -> list[Document]:
                return []

    def test_empty_description_raises(self, app: SyftAPI) -> None:
        """Test that empty description raises EndpointRegistrationError."""
        with pytest.raises(EndpointRegistrationError, match="description cannot be empty"):

            @app.datasource(slug="test", name="Test Name", description="")
            async def fn(query: str) -> list[Document]:
                return []

    def test_long_name_raises(self, app: SyftAPI) -> None:
        """Test that overly long name raises error."""
        long_name = "x" * 101
        with pytest.raises(EndpointRegistrationError, match="exceeds 100 characters"):

            @app.datasource(slug="test", name=long_name, description="Test")
            async def fn(query: str) -> list[Document]:
                return []

    def test_long_description_raises(self, app: SyftAPI) -> None:
        """Test that overly long description raises error."""
        long_desc = "x" * 501
        with pytest.raises(EndpointRegistrationError, match="exceeds 500 characters"):

            @app.datasource(slug="test", name="Test", description=long_desc)
            async def fn(query: str) -> list[Document]:
                return []


class TestFunctionValidation:
    """Tests for endpoint function validation."""

    def test_non_async_function_raises(self, app: SyftAPI) -> None:
        """Test that non-async functions raise EndpointRegistrationError."""
        with pytest.raises(EndpointRegistrationError, match="must be async"):

            @app.datasource(slug="test", name="Test", description="Test")
            def sync_fn(query: str) -> list[Document]:  # type: ignore
                return []


class TestLifecycleHooks:
    """Tests for lifecycle hook registration."""

    def test_register_startup_hook(self, app: SyftAPI) -> None:
        """Test registering a startup hook."""

        @app.on_startup
        async def startup_hook() -> None:
            pass

        assert len(app._on_startup) == 1
        assert app._on_startup[0] == startup_hook

    def test_register_shutdown_hook(self, app: SyftAPI) -> None:
        """Test registering a shutdown hook."""

        @app.on_shutdown
        async def shutdown_hook() -> None:
            pass

        assert len(app._on_shutdown) == 1
        assert app._on_shutdown[0] == shutdown_hook

    def test_register_multiple_hooks(self, app: SyftAPI) -> None:
        """Test registering multiple lifecycle hooks."""

        @app.on_startup
        async def startup1() -> None:
            pass

        @app.on_startup
        async def startup2() -> None:
            pass

        @app.on_shutdown
        async def shutdown1() -> None:
            pass

        assert len(app._on_startup) == 2
        assert len(app._on_shutdown) == 1

    def test_non_async_startup_hook_raises(self, app: SyftAPI) -> None:
        """Test that non-async startup hooks raise TypeError."""
        with pytest.raises(TypeError, match="must be an async function"):

            @app.on_startup
            def sync_hook() -> None:  # type: ignore
                pass

    def test_non_async_shutdown_hook_raises(self, app: SyftAPI) -> None:
        """Test that non-async shutdown hooks raise TypeError."""
        with pytest.raises(TypeError, match="must be an async function"):

            @app.on_shutdown
            def sync_hook() -> None:  # type: ignore
                pass


class TestMiddleware:
    """Tests for middleware registration."""

    def test_add_middleware_class(self, app: SyftAPI) -> None:
        """Test adding a middleware class."""
        from starlette.middleware.cors import CORSMiddleware

        app.add_middleware(CORSMiddleware, allow_origins=["*"])

        assert len(app._middleware) == 1
        assert app._middleware[0][0] == CORSMiddleware
        assert app._middleware[0][1] == {"allow_origins": ["*"]}

    def test_register_middleware_dispatch(self, app: SyftAPI) -> None:
        """Test registering a middleware dispatch function."""
        from fastapi import Request, Response

        @app.middleware
        async def my_middleware(
            request: Request,
            call_next: callable,  # type: ignore
        ) -> Response:
            return await call_next(request)

        assert len(app._middleware_dispatch) == 1

    def test_non_async_middleware_raises(self, app: SyftAPI) -> None:
        """Test that non-async middleware raises TypeError."""
        with pytest.raises(TypeError, match="must be async"):

            @app.middleware
            def sync_middleware(request, call_next):  # type: ignore
                pass


class TestGetApp:
    """Tests for the get_app method."""

    def test_get_app_returns_fastapi(self, app: SyftAPI) -> None:
        """Test that get_app returns a FastAPI instance."""
        from fastapi import FastAPI

        fastapi_app = app.get_app()
        assert isinstance(fastapi_app, FastAPI)

    def test_get_app_includes_router(self, app: SyftAPI) -> None:
        """Test that get_app includes the endpoint router."""

        @app.datasource(slug="test", name="Test", description="Test")
        async def fn(query: str) -> list[Document]:
            return []

        fastapi_app = app.get_app()
        routes = [r.path for r in fastapi_app.routes]
        assert "/api/v1/endpoints/test/query" in routes
