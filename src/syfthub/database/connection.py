"""Database connection and session management."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from syfthub.core.config import settings
from syfthub.models import Base


# Create SQLAlchemy engine
def _get_connect_args() -> dict[str, Any]:
    """Get connection arguments based on database type."""
    if "sqlite" in settings.database_url:
        return {
            "check_same_thread": False,
            # Enable foreign key constraints in SQLite
            "isolation_level": None,
        }
    return {}


engine = create_engine(
    settings.database_url,
    echo=settings.debug,  # Log SQL queries in debug mode
    pool_pre_ping=True,  # Verify connections before use
    connect_args=_get_connect_args(),
)


# Enable foreign key constraints for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enable foreign key constraints in SQLite."""
    if "sqlite" in settings.database_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """Drop all database tables."""
    Base.metadata.drop_all(bind=engine)


def get_db_session() -> Generator[Session, None, None]:
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatabaseManager:
    """Database manager for handling database operations."""

    def __init__(self) -> None:
        """Initialize database manager."""
        self.engine = engine
        self.session_factory = SessionLocal

    def create_all_tables(self) -> None:
        """Create all tables in the database."""
        Base.metadata.create_all(bind=self.engine)

    def drop_all_tables(self) -> None:
        """Drop all tables from the database."""
        Base.metadata.drop_all(bind=self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.session_factory()

    def reset_database(self) -> None:
        """Reset the database by dropping and recreating all tables."""
        self.drop_all_tables()
        self.create_all_tables()


# Global database manager instance
db_manager = DatabaseManager()
