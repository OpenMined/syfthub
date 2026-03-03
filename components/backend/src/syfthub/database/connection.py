"""Database connection and session management."""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from syfthub.core.config import settings
from syfthub.models import Base

logger = logging.getLogger(__name__)


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


def _run_alembic_migrations() -> bool:
    """Run Alembic migrations programmatically.

    Handles three cases:
    1. Fresh database: runs all migrations from scratch.
    2. Existing database (created via create_all, no alembic_version table):
       stamps the initial migration as applied, then runs remaining migrations.
    3. Previously migrated database: runs only pending migrations.

    Returns True if migrations were applied, False if Alembic files are unavailable.
    """
    alembic_ini = Path("alembic.ini")
    alembic_dir = Path("alembic")
    if not alembic_ini.exists() or not alembic_dir.exists():
        return False

    try:
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import inspect

        alembic_cfg = Config(str(alembic_ini))
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        has_app_tables = "users" in table_names
        has_alembic_version = "alembic_version" in table_names

        if has_app_tables and not has_alembic_version:
            # Existing DB created via create_all() — stamp up to the last
            # migration that create_all() already covers (api_tokens table
            # exists from the model definitions). This prevents Alembic from
            # trying to recreate existing tables/columns.
            logger.info(
                "Existing database without alembic_version detected. "
                "Stamping baseline migration (002_api_tokens)."
            )
            command.stamp(alembic_cfg, "002_api_tokens")

        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully.")
        return True
    except Exception:
        logger.exception("Alembic migration failed, falling back to create_all()")
        return False


def create_tables() -> None:
    """Create all database tables, applying Alembic migrations if available."""
    if not _run_alembic_migrations():
        Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """Drop all database tables including Alembic version tracking."""
    Base.metadata.drop_all(bind=engine)
    # Drop alembic_version so migrations re-run on next create_tables() call
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


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
