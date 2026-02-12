"""Tests for file_mode provider."""

import pytest
from pathlib import Path
import tempfile

from syfthub_api.file_mode.provider import FileBasedEndpointProvider


class TestFileBasedEndpointProvider:
    """Tests for FileBasedEndpointProvider."""

    def _create_endpoint_folder(
        self,
        base_dir: Path,
        name: str,
        slug: str,
        endpoint_type: str = "model",
    ) -> Path:
        """Helper to create a test endpoint folder."""
        folder = base_dir / name
        folder.mkdir(parents=True, exist_ok=True)

        # Create README.md
        readme_content = f"""---
slug: {slug}
type: {endpoint_type}
name: {name}
description: Test endpoint {name}
enabled: true
---

# {name}
"""
        (folder / "README.md").write_text(readme_content)

        # Create runner.py
        if endpoint_type == "model":
            handler_code = """
from syfthub_api import Message
from policy_manager.context import RequestContext

async def handler(messages: list[Message], ctx: RequestContext) -> str:
    return "test response"
"""
        else:
            handler_code = """
from syfthub_api import Message, Document
from policy_manager.context import RequestContext

async def handler(messages: list[Message], ctx: RequestContext) -> list[Document]:
    return [Document(document_id="1", content="test", similarity_score=0.9)]
"""
        (folder / "runner.py").write_text(handler_code)

        return folder

    @pytest.mark.asyncio
    async def test_load_all_endpoints(self) -> None:
        """Test loading all endpoints from a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_endpoint_folder(base, "model1", "model-1", "model")
            self._create_endpoint_folder(base, "model2", "model-2", "model")
            self._create_endpoint_folder(base, "data1", "data-1", "data_source")

            provider = FileBasedEndpointProvider(path=base, watch_enabled=False)
            endpoints = await provider.load_all()

            assert len(endpoints) == 3
            slugs = {ep["slug"] for ep in endpoints}
            assert slugs == {"model-1", "model-2", "data-1"}

    @pytest.mark.asyncio
    async def test_load_skips_hidden_folders(self) -> None:
        """Test that hidden folders are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_endpoint_folder(base, "visible", "visible", "model")
            self._create_endpoint_folder(base, ".hidden", "hidden", "model")
            self._create_endpoint_folder(base, "_disabled", "disabled", "model")

            provider = FileBasedEndpointProvider(path=base, watch_enabled=False)
            endpoints = await provider.load_all()

            assert len(endpoints) == 1
            assert endpoints[0]["slug"] == "visible"

    @pytest.mark.asyncio
    async def test_load_skips_folders_without_readme(self) -> None:
        """Test that folders without README.md are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_endpoint_folder(base, "valid", "valid", "model")

            # Create folder without README
            no_readme = base / "no-readme"
            no_readme.mkdir()
            (no_readme / "runner.py").write_text("pass")

            provider = FileBasedEndpointProvider(path=base, watch_enabled=False)
            endpoints = await provider.load_all()

            assert len(endpoints) == 1
            assert endpoints[0]["slug"] == "valid"

    @pytest.mark.asyncio
    async def test_load_all_empty_directory(self) -> None:
        """Test loading from empty directory returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileBasedEndpointProvider(path=Path(tmpdir), watch_enabled=False)
            endpoints = await provider.load_all()
            assert endpoints == []

    @pytest.mark.asyncio
    async def test_load_all_nonexistent_directory(self) -> None:
        """Test loading from nonexistent directory returns empty list."""
        provider = FileBasedEndpointProvider(
            path=Path("/nonexistent/path"), watch_enabled=False
        )
        endpoints = await provider.load_all()
        assert endpoints == []

    @pytest.mark.asyncio
    async def test_get_endpoint_by_slug(self) -> None:
        """Test finding endpoint by slug."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_endpoint_folder(base, "test", "find-me", "model")

            provider = FileBasedEndpointProvider(path=base, watch_enabled=False)
            await provider.load_all()

            endpoint = provider.get_endpoint_by_slug("find-me")
            assert endpoint is not None
            assert endpoint["slug"] == "find-me"

    @pytest.mark.asyncio
    async def test_get_endpoint_by_slug_not_found(self) -> None:
        """Test that missing slug returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileBasedEndpointProvider(path=Path(tmpdir), watch_enabled=False)
            await provider.load_all()

            endpoint = provider.get_endpoint_by_slug("nonexistent")
            assert endpoint is None

    @pytest.mark.asyncio
    async def test_reload_endpoint(self) -> None:
        """Test reloading a single endpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            folder = self._create_endpoint_folder(base, "reload-test", "reload", "model")

            provider = FileBasedEndpointProvider(path=base, watch_enabled=False)
            await provider.load_all()

            # Reload the endpoint
            reloaded = await provider.reload_endpoint(folder)
            assert reloaded is not None
            assert reloaded["slug"] == "reload"

    @pytest.mark.asyncio
    async def test_reload_invalid_endpoint(self) -> None:
        """Test that reloading invalid endpoint returns None."""
        provider = FileBasedEndpointProvider(
            path=Path("/tmp"), watch_enabled=False
        )

        reloaded = await provider.reload_endpoint(Path("/nonexistent/endpoint"))
        assert reloaded is None

    @pytest.mark.asyncio
    async def test_endpoints_property(self) -> None:
        """Test endpoints property returns copy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_endpoint_folder(base, "test", "test", "model")

            provider = FileBasedEndpointProvider(path=base, watch_enabled=False)
            await provider.load_all()

            endpoints1 = provider.endpoints
            endpoints2 = provider.endpoints

            # Should be equal but different objects
            assert endpoints1 == endpoints2
            assert endpoints1 is not endpoints2

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        """Test cleanup clears endpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_endpoint_folder(base, "test", "test", "model")

            provider = FileBasedEndpointProvider(path=base, watch_enabled=False)
            await provider.load_all()
            assert len(provider.endpoints) == 1

            await provider.cleanup()
            assert len(provider.endpoints) == 0

    @pytest.mark.asyncio
    async def test_is_watching_property(self) -> None:
        """Test is_watching property."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FileBasedEndpointProvider(
                path=Path(tmpdir), watch_enabled=True
            )

            assert provider.is_watching is False

            await provider.start_watching()
            assert provider.is_watching is True

            await provider.stop_watching()
            assert provider.is_watching is False

    @pytest.mark.asyncio
    async def test_on_change_callback(self) -> None:
        """Test on_change callback is called during hot-reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            folder = self._create_endpoint_folder(base, "callback-test", "callback", "model")

            provider = FileBasedEndpointProvider(path=base, watch_enabled=False)
            await provider.load_all()

            # Track callback invocations
            callback_invocations: list[list] = []

            async def on_change(endpoints: list) -> None:
                callback_invocations.append(endpoints)

            provider.on_change = on_change

            # Trigger change handling
            await provider._handle_changes({folder})

            assert len(callback_invocations) == 1
            assert len(callback_invocations[0]) == 1
