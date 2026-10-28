"""Database connection and session management."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from syfthub.core.config import settings
from syfthub.models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Engine

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


def _get_pool_kwargs() -> dict[str, Any]:
    """Pool sizing for non-SQLite engines.

    Sync handlers run on the anyio threadpool, so the pool must have enough
    connections for the concurrent threads without exhausting Postgres's
    shared max_connections. SQLite (tests) uses its default pool untouched.
    """
    if "sqlite" in settings.database_url:
        return {}
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
    }


engine = create_engine(
    settings.database_url,
    echo=settings.debug,  # Log SQL queries in debug mode
    pool_pre_ping=True,  # Verify connections before use
    connect_args=_get_connect_args(),
    **_get_pool_kwargs(),
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


class JobLock:
    """A Postgres advisory lock one worker keeps across job cycles.

    Several uvicorn workers each run the same periodic job. Taking the lock
    per cycle only serialises them: with a 30 s interval and four workers,
    three or four cycles still run every 30 s, just not at the same instant.
    The job needs *one* run per interval across the deployment, so the lock
    is held for as long as the holder lives. The first worker to acquire it
    becomes the leader and keeps running cycles; the others try again each
    interval and take over if the leader's connection goes away, which is
    also what releases a session-level advisory lock.

    The leader pins one connection out of the pool for the life of the
    process. Followers open one only while trying.
    """

    def __init__(
        self, engine: Engine, session_factory: sessionmaker[Session], lock_id: int
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._lock_id = lock_id
        self._conn: Optional[Connection] = None
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self) -> bool:
        """True when this worker holds the lock, acquiring it if it is free.

        A held lock is re-checked with a round trip on the pinned connection,
        so a connection the server dropped is noticed here, not mid-cycle.
        Non-Postgres databases run one worker and always acquire.
        """
        if self._engine.dialect.name != "postgresql":
            return True

        if self._held and self._conn is not None:
            try:
                self._conn.execute(text("SELECT 1"))
                self._conn.commit()
                return True
            except Exception as e:
                logger.warning(
                    f"Advisory lock {self._lock_id} connection lost, re-acquiring: {e}"
                )
                self._drop_connection()

        try:
            conn = self._engine.connect()
        except Exception as e:
            logger.warning(f"Could not open a connection for lock {self._lock_id}: {e}")
            return False
        try:
            acquired = bool(
                conn.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": self._lock_id},
                ).scalar()
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to try advisory lock {self._lock_id}: {e}")
            conn.close()
            return False

        if not acquired:
            conn.close()
            return False
        self._conn = conn
        self._held = True
        return True

    def session(self) -> Session:
        """A session for one cycle, on the pinned connection when leading."""
        if self._conn is not None:
            return self._session_factory(bind=self._conn)
        return self._session_factory()

    def release(self) -> None:
        """Give the lock up and return the connection. Safe to call when not held."""
        if self._conn is not None and self._held:
            try:
                self._conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": self._lock_id},
                )
                self._conn.commit()
            except Exception as e:
                logger.warning(f"Failed to release advisory lock {self._lock_id}: {e}")
        self._drop_connection()

    def _drop_connection(self) -> None:
        self._held = False
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None


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

    def job_lock(self, lock_id: int) -> JobLock:
        """A leader lock for a periodic job; see ``JobLock``."""
        return JobLock(self.engine, self.session_factory, lock_id)

    @contextlib.contextmanager
    def locked_session(self, lock_id: int) -> Iterator[Optional[Session]]:
        """A session for one background job cycle, under a Postgres advisory lock.

        Yields ``None`` when another holder has the lock, so the caller skips
        the cycle. On databases other than Postgres there is one worker and no
        lock, so a plain session is yielded. Use this for jobs where an extra
        run is harmless (a cleanup); a job that must run once per interval
        across workers uses ``job_lock`` instead.

        Session-level advisory locks belong to the *connection*. Closing a
        Session only returns its connection to the pool, with a ROLLBACK, and
        a rollback does not release them. Taking the lock through a pooled
        session therefore parked it on whichever connection happened to run
        the ``pg_try_advisory_lock``, for the life of the process; every later
        cycle that drew a different connection from the pool found the lock
        "held by another worker" and skipped. The monitor then ran only when
        the pool happened to hand that one connection back, which is why
        cycles came every few minutes rather than every 30 seconds.

        So the cycle runs on one dedicated connection, the session's commits
        happen on that connection, and the lock is released explicitly before
        the connection goes back to the pool.
        """
        if self.engine.dialect.name != "postgresql":
            session = self.session_factory()
            try:
                yield session
            finally:
                session.close()
            return

        with self.engine.connect() as conn:
            acquired = conn.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
            ).scalar()
            conn.commit()
            if not acquired:
                yield None
                return

            session = self.session_factory(bind=conn)
            try:
                yield session
            finally:
                session.close()
                try:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": lock_id},
                    )
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to release advisory lock {lock_id}: {e}")

    def reset_database(self) -> None:
        """Reset the database by dropping and recreating all tables."""
        self.drop_all_tables()
        self.create_all_tables()


# Global database manager instance
db_manager = DatabaseManager()
