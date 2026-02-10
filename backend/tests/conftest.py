"""Shared pytest fixtures and configuration."""

import contextlib
import os
import tempfile
from collections.abc import Generator

# Disable accounting integration for tests - must be set before syfthub imports
# This environment variable is read by Settings() during initialization
os.environ["DEFAULT_ACCOUNTING_URL"] = ""

# Set worker-specific database URL for pytest-xdist parallel execution
# This MUST happen before any syfthub imports to ensure each worker uses its own database
_worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
if _worker_id:
    # Create a unique database file for each xdist worker (gw0, gw1, etc.)
    os.environ["DATABASE_URL"] = f"sqlite:///./test_syfthub_{_worker_id}.db"
else:
    # Single-process execution - use a dedicated test database
    os.environ["DATABASE_URL"] = "sqlite:///./test_syfthub.db"

import pytest  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from syfthub.models import Base  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    """Clean up worker-specific database files after test session."""
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
    db_file = f"./test_syfthub_{worker_id}.db" if worker_id else "./test_syfthub.db"

    if os.path.exists(db_file):
        with contextlib.suppress(OSError):
            os.unlink(db_file)


@pytest.fixture(autouse=True)
def disable_accounting_integration(monkeypatch):
    """Disable accounting service integration for all tests.

    This fixture ensures no external accounting service calls are made during tests.
    It sets the default_accounting_url to empty string, which causes the
    auth service to skip accounting integration entirely.

    The auth_service._handle_accounting_registration() checks:
        if not effective_url:
            return (None, None)  # Skip accounting

    Empty string evaluates to False, so accounting is skipped.
    """
    monkeypatch.setattr(
        "syfthub.core.config.settings.default_accounting_url",
        "",
    )
    yield


@pytest.fixture
def example_fixture() -> str:
    """Example fixture that can be used across tests."""
    return "test_value"


@pytest.fixture
def test_db_url() -> str:
    """Create a test database URL with a temporary SQLite file."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        return f"sqlite:///{tmp_file.name}"


@pytest.fixture
def test_engine(test_db_url: str):
    """Create a test database engine."""
    engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    # Enable foreign key constraints for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield engine
    # Cleanup
    if os.path.exists(test_db_url.replace("sqlite:///", "")):
        os.unlink(test_db_url.replace("sqlite:///", ""))


@pytest.fixture
def test_session(test_engine) -> Generator[Session, None, None]:
    """Create a test database session with tables."""
    # Create all tables
    Base.metadata.create_all(bind=test_engine)

    # Create session factory
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    # Create session
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=test_engine)
