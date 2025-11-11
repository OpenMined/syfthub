"""Test fixtures for database tests."""

import os
import tempfile
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from syfthub.database.models import Base


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


@pytest.fixture
def sample_user_data() -> dict:
    """Sample user data for testing."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "age": 25,
        "role": "user",
        "password_hash": "hashed_password_123",
        "is_active": True,
    }


@pytest.fixture
def sample_item_data() -> dict:
    """Sample item data for testing."""
    return {
        "user_id": 1,
        "name": "Test Item",
        "description": "A test item",
        "price": 19.99,
        "is_available": True,
        "category": "test",
    }


@pytest.fixture
def sample_datasite_data() -> dict:
    """Sample datasite data for testing."""
    return {
        "user_id": 1,
        "name": "Test Datasite",
        "slug": "test-datasite",
        "description": "A test datasite",
        "visibility": "public",
        "is_active": True,
    }
