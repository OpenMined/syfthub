"""
Tests for file mode executors.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from syfthub_api.file_mode.executors import (
    EndpointExecutor,
    ExecutionResult,
    ExecutorFactory,
    InProcessExecutor,
    SubprocessExecutor,
    create_executor,
    get_executor_factory,
)


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_from_success(self) -> None:
        """Test creating successful result."""
        result = ExecutionResult.from_success(
            result="test result",
            execution_time_ms=10.5,
            custom_key="custom_value",
        )
        assert result.success is True
        assert result.result == "test result"
        assert result.error is None
        assert result.error_type is None
        assert result.execution_time_ms == 10.5
        assert result.metadata.get("custom_key") == "custom_value"

    def test_from_error(self) -> None:
        """Test creating error result."""
        error = ValueError("Test error message")
        result = ExecutionResult.from_error(
            error=error,
            execution_time_ms=5.0,
            executor_type="in_process",
        )
        assert result.success is False
        assert result.result is None
        assert result.error == "Test error message"
        assert result.error_type == "ValueError"
        assert result.execution_time_ms == 5.0
        assert result.metadata.get("executor_type") == "in_process"


class TestInProcessExecutor:
    """Tests for InProcessExecutor."""

    @pytest.fixture
    def mock_handler(self) -> AsyncMock:
        """Create a mock async handler."""
        handler = AsyncMock(return_value="test result")
        return handler

    @pytest.fixture
    def executor(self, tmp_path: Path, mock_handler: AsyncMock) -> InProcessExecutor:
        """Create an InProcessExecutor for testing."""
        return InProcessExecutor(
            endpoint_path=tmp_path,
            endpoint_slug="test-endpoint",
            handler_fn=mock_handler,
            env_vars={"TEST_VAR": "test_value"},
        )

    @pytest.mark.asyncio
    async def test_start_stop(self, executor: InProcessExecutor) -> None:
        """Test executor start and stop lifecycle."""
        assert not executor.is_started

        await executor.start()
        assert executor.is_started

        # Start again should be idempotent
        await executor.start()
        assert executor.is_started

        await executor.stop()
        assert not executor.is_started

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        executor: InProcessExecutor,
        mock_handler: AsyncMock,
    ) -> None:
        """Test successful execution."""
        await executor.start()

        result = await executor.execute(
            messages=[{"role": "user", "content": "test"}],
            context=None,
        )

        assert result.success is True
        assert result.result == "test result"
        assert result.execution_time_ms > 0
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_without_start(
        self,
        executor: InProcessExecutor,
    ) -> None:
        """Test execution fails without start."""
        result = await executor.execute(
            messages=[],
            context=None,
        )

        assert result.success is False
        assert "not started" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_handler_error(
        self,
        executor: InProcessExecutor,
        mock_handler: AsyncMock,
    ) -> None:
        """Test execution when handler raises error."""
        mock_handler.side_effect = ValueError("Handler error")

        await executor.start()
        result = await executor.execute(
            messages=[],
            context=None,
        )

        assert result.success is False
        assert result.error == "Handler error"
        assert result.error_type == "ValueError"

    def test_supports_hot_reload(self, executor: InProcessExecutor) -> None:
        """Test that in-process executor supports hot reload."""
        assert executor.supports_hot_reload() is True

    @pytest.mark.asyncio
    async def test_reload_handler(
        self,
        executor: InProcessExecutor,
    ) -> None:
        """Test handler reload."""
        new_handler = AsyncMock(return_value="new result")

        await executor.start()
        await executor.reload_handler(new_handler)

        result = await executor.execute([], None)
        assert result.result == "new result"

    def test_repr(self, executor: InProcessExecutor) -> None:
        """Test string representation."""
        repr_str = repr(executor)
        assert "InProcessExecutor" in repr_str
        assert "test-endpoint" in repr_str


class TestExecutorFactory:
    """Tests for ExecutorFactory."""

    @pytest.fixture
    def factory(self) -> ExecutorFactory:
        """Create a factory for testing."""
        return ExecutorFactory()

    def test_create_in_process(self, factory: ExecutorFactory, tmp_path: Path) -> None:
        """Test creating in-process executor."""
        executor = factory.create(
            mode="in_process",
            endpoint_path=tmp_path,
            endpoint_slug="test",
            handler_fn=lambda: None,
        )
        assert isinstance(executor, InProcessExecutor)

    def test_create_subprocess(self, factory: ExecutorFactory, tmp_path: Path) -> None:
        """Test creating subprocess executor."""
        executor = factory.create(
            mode="subprocess",
            endpoint_path=tmp_path,
            endpoint_slug="test",
            handler_fn=lambda: None,
            workers=3,
            timeout=60,
        )
        assert isinstance(executor, SubprocessExecutor)
        assert executor.workers == 3
        assert executor.timeout == 60

    def test_create_container_not_implemented(
        self,
        factory: ExecutorFactory,
        tmp_path: Path,
    ) -> None:
        """Test that container mode raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            factory.create(
                mode="container",
                endpoint_path=tmp_path,
                endpoint_slug="test",
                handler_fn=lambda: None,
            )

    def test_create_invalid_mode(
        self,
        factory: ExecutorFactory,
        tmp_path: Path,
    ) -> None:
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError):
            factory.create(
                mode="invalid",  # type: ignore
                endpoint_path=tmp_path,
                endpoint_slug="test",
                handler_fn=lambda: None,
            )

    def test_create_from_endpoint(
        self,
        factory: ExecutorFactory,
        tmp_path: Path,
    ) -> None:
        """Test creating executor from endpoint data."""
        endpoint_data = {
            "_source_path": str(tmp_path),
            "slug": "my-endpoint",
            "fn": lambda: None,
            "_env": {"KEY": "value"},
            "_runtime": {
                "mode": "in_process",
                "workers": 2,
                "timeout": 30,
            },
        }

        executor = factory.create_from_endpoint(endpoint_data)
        assert isinstance(executor, InProcessExecutor)
        assert executor.endpoint_slug == "my-endpoint"
        assert executor.env_vars == {"KEY": "value"}

    def test_create_from_endpoint_missing_path(
        self,
        factory: ExecutorFactory,
    ) -> None:
        """Test error when endpoint data missing source path."""
        with pytest.raises(ValueError, match="_source_path"):
            factory.create_from_endpoint({})

    def test_create_from_endpoint_missing_fn(
        self,
        factory: ExecutorFactory,
        tmp_path: Path,
    ) -> None:
        """Test error when endpoint data missing handler function."""
        with pytest.raises(ValueError, match="fn"):
            factory.create_from_endpoint({"_source_path": str(tmp_path)})


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_executor_factory_singleton(self) -> None:
        """Test that get_executor_factory returns singleton."""
        factory1 = get_executor_factory()
        factory2 = get_executor_factory()
        assert factory1 is factory2

    def test_create_executor(self, tmp_path: Path) -> None:
        """Test create_executor convenience function."""
        executor = create_executor(
            mode="in_process",
            endpoint_path=tmp_path,
            endpoint_slug="test",
            handler_fn=lambda: None,
        )
        assert isinstance(executor, InProcessExecutor)


class TestSubprocessExecutor:
    """Tests for SubprocessExecutor."""

    @pytest.fixture
    def executor(self, tmp_path: Path) -> SubprocessExecutor:
        """Create a SubprocessExecutor for testing."""
        # Create runner.py for the executor
        (tmp_path / "runner.py").write_text("""
async def handler(messages, ctx):
    return "subprocess result"
""")
        return SubprocessExecutor(
            endpoint_path=tmp_path,
            endpoint_slug="test-subprocess",
            handler_fn=lambda: None,  # Not used in subprocess mode
            env_vars={"TEST_VAR": "test_value"},
            workers=2,
            timeout=30,
        )

    def test_init(self, executor: SubprocessExecutor) -> None:
        """Test executor initialization."""
        assert executor.endpoint_slug == "test-subprocess"
        assert executor.workers == 2
        assert executor.timeout == 30
        assert not executor.is_started

    def test_supports_hot_reload(self, executor: SubprocessExecutor) -> None:
        """Test that subprocess executor supports hot reload."""
        assert executor.supports_hot_reload() is True

    @pytest.mark.asyncio
    async def test_reload_handler_restarts_pool(
        self,
        executor: SubprocessExecutor,
    ) -> None:
        """Test that reload_handler restarts the worker pool."""
        await executor.start()
        assert executor.is_started
        old_executor_instance = executor._executor

        await executor.reload_handler(lambda: None)

        # Executor should still be running with a new pool
        assert executor.is_started
        # The loky executor instance should be different after restart
        assert executor._executor is not old_executor_instance

        await executor.stop()

    def test_repr(self, executor: SubprocessExecutor) -> None:
        """Test string representation."""
        repr_str = repr(executor)
        assert "SubprocessExecutor" in repr_str
        assert "test-subprocess" in repr_str
        assert "workers=2" in repr_str
        assert "timeout=30" in repr_str

    @pytest.mark.asyncio
    async def test_start_stop(self, executor: SubprocessExecutor) -> None:
        """Test executor start and stop lifecycle."""
        assert not executor.is_started

        await executor.start()
        assert executor.is_started
        assert executor._executor is not None

        await executor.stop()
        assert not executor.is_started
        assert executor._executor is None

    @pytest.mark.asyncio
    async def test_execute_without_start(
        self,
        executor: SubprocessExecutor,
    ) -> None:
        """Test execution fails without start."""
        result = await executor.execute(
            messages=[],
            context=None,
        )

        assert result.success is False
        assert "not started" in result.error.lower()


class TestWorkerModule:
    """Tests for the worker module."""

    def test_worker_request_dataclass(self) -> None:
        """Test WorkerRequest dataclass structure."""
        from syfthub_api.file_mode.executors.worker import WorkerRequest

        request = WorkerRequest(
            runner_path="/tmp/runner.py",
            messages=[{"role": "user", "content": "test"}],
            context_data={"request_id": "123"},
            endpoint_slug="test-endpoint",
        )
        assert request.runner_path == "/tmp/runner.py"
        assert request.endpoint_slug == "test-endpoint"
        assert len(request.messages) == 1

    def test_worker_response_dataclass(self) -> None:
        """Test WorkerResponse dataclass structure."""
        from syfthub_api.file_mode.executors.worker import WorkerResponse

        # Success response
        success = WorkerResponse(success=True, result="test result")
        assert success.success is True
        assert success.result == "test result"
        assert success.error is None

        # Error response
        error = WorkerResponse(
            success=False,
            error="Something went wrong",
            error_type="ValueError",
        )
        assert error.success is False
        assert error.error == "Something went wrong"
        assert error.error_type == "ValueError"

    def test_handler_cache_exists(self) -> None:
        """Test handler cache is properly initialized."""
        from syfthub_api.file_mode.executors import worker

        assert hasattr(worker, "_handler_cache")
        assert isinstance(worker._handler_cache, dict)
