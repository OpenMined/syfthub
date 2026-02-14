"""Tests for file_mode endpoint loader."""

import pytest
from pathlib import Path
import tempfile

from syfthub_api.file_mode.loader import EndpointLoader, EndpointLoadError
from syfthub_api.schemas import EndpointType


class TestEndpointLoader:
    """Tests for EndpointLoader."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.loader = EndpointLoader()

    def _create_endpoint_folder(
        self,
        tmpdir: Path,
        name: str,
        slug: str = "test-endpoint",
        endpoint_type: str = "model",
        handler_code: str | None = None,
    ) -> Path:
        """Helper to create a test endpoint folder."""
        folder = tmpdir / name
        folder.mkdir()

        # Create README.md
        readme_content = f"""---
slug: {slug}
type: {endpoint_type}
name: Test Endpoint
description: A test endpoint
enabled: true
---

# Test Endpoint Documentation
"""
        (folder / "README.md").write_text(readme_content)

        # Create runner.py
        if handler_code is None:
            handler_code = """
from syfthub_api import Message, Document
from policy_manager.context import RequestContext

async def handler(messages: list[Message], ctx: RequestContext) -> str:
    return "test response"
"""
        (folder / "runner.py").write_text(handler_code)

        return folder

    @pytest.mark.asyncio
    async def test_load_model_endpoint(self) -> None:
        """Test loading a model endpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = self._create_endpoint_folder(
                Path(tmpdir), "my-model", slug="my-model", endpoint_type="model"
            )

            endpoint = await self.loader.load(folder)

            assert endpoint["slug"] == "my-model"
            assert endpoint["type"] == EndpointType.MODEL
            assert endpoint["name"] == "Test Endpoint"
            assert endpoint["fn"] is not None
            assert callable(endpoint["fn"])
            assert endpoint.get("_file_mode") is True
            # Verify version and readme body are included
            assert endpoint["version"] == "1.0"  # Default version
            assert "# Test Endpoint Documentation" in endpoint["_readme_body"]

    @pytest.mark.asyncio
    async def test_load_datasource_endpoint(self) -> None:
        """Test loading a data source endpoint."""
        handler_code = """
from syfthub_api import Message, Document
from policy_manager.context import RequestContext

async def handler(messages: list[Message], ctx: RequestContext) -> list[Document]:
    return [Document(document_id="1", content="test", similarity_score=0.9)]
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = self._create_endpoint_folder(
                Path(tmpdir),
                "my-data",
                slug="my-data",
                endpoint_type="data_source",
                handler_code=handler_code,
            )

            endpoint = await self.loader.load(folder)

            assert endpoint["slug"] == "my-data"
            assert endpoint["type"] == EndpointType.DATA_SOURCE

    @pytest.mark.asyncio
    async def test_load_missing_readme(self) -> None:
        """Test that missing README.md raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "no-readme"
            folder.mkdir()
            (folder / "runner.py").write_text("async def handler(): pass")

            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(folder)
            assert "readme.md not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_missing_runner(self) -> None:
        """Test that missing runner.py raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "no-runner"
            folder.mkdir()
            (folder / "README.md").write_text("""---
slug: test
type: model
name: Test
description: Test
---
""")

            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(folder)
            assert "runner.py not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_invalid_handler_signature(self) -> None:
        """Test that handler without messages param raises error."""
        handler_code = """
async def handler(query: str):
    return "test"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = self._create_endpoint_folder(
                Path(tmpdir), "bad-handler", handler_code=handler_code
            )

            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(folder)
            assert "messages" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_handler_missing_ctx(self) -> None:
        """Test that handler without ctx param raises error."""
        handler_code = """
from syfthub_api import Message

async def handler(messages: list[Message]):
    return "test"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = self._create_endpoint_folder(
                Path(tmpdir), "no-ctx", handler_code=handler_code
            )

            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(folder)
            assert "ctx" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_non_async_handler(self) -> None:
        """Test that non-async handler raises error."""
        handler_code = """
from syfthub_api import Message
from policy_manager.context import RequestContext

def handler(messages: list[Message], ctx: RequestContext):
    return "test"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = self._create_endpoint_folder(
                Path(tmpdir), "sync-handler", handler_code=handler_code
            )

            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(folder)
            assert "async" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_syntax_error(self) -> None:
        """Test that syntax error in runner.py raises error."""
        handler_code = """
def handler(
    this is not valid python
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = self._create_endpoint_folder(
                Path(tmpdir), "syntax-error", handler_code=handler_code
            )

            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(folder)
            assert "syntax error" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_missing_handler_function(self) -> None:
        """Test that missing handler function raises error."""
        handler_code = """
async def some_other_function():
    pass
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = self._create_endpoint_folder(
                Path(tmpdir), "no-handler", handler_code=handler_code
            )

            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(folder)
            assert "handler" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_disabled_endpoint(self) -> None:
        """Test that disabled endpoint raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "disabled"
            folder.mkdir()
            (folder / "README.md").write_text("""---
slug: disabled
type: model
name: Disabled
description: A disabled endpoint
enabled: false
---
""")
            (folder / "runner.py").write_text("""
from syfthub_api import Message
from policy_manager.context import RequestContext

async def handler(messages: list[Message], ctx: RequestContext):
    return "test"
""")

            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(folder)
            assert "disabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_with_policies(self) -> None:
        """Test loading endpoint with policy folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = self._create_endpoint_folder(Path(tmpdir), "with-policies")

            # Add policy folder
            policy_dir = folder / "policy"
            policy_dir.mkdir()
            (policy_dir / "rate_limit.yaml").write_text("""
type: RateLimitPolicy
name: test_rate
config:
  max_requests: 100
  window_seconds: 60
""")

            endpoint = await self.loader.load(folder)

            assert len(endpoint["policies"]) == 1
            assert endpoint["policies"][0].name == "test_rate"

    @pytest.mark.asyncio
    async def test_load_not_a_directory(self) -> None:
        """Test that loading a file instead of directory raises error."""
        with tempfile.NamedTemporaryFile() as f:
            with pytest.raises(EndpointLoadError) as exc_info:
                await self.loader.load(Path(f.name))
            assert "not a directory" in str(exc_info.value).lower()

    def test_cleanup(self) -> None:
        """Test cleanup removes loaded modules."""
        self.loader.cleanup()
        # Should not raise even if nothing loaded
        assert len(self.loader._loaded_modules) == 0
