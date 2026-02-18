"""Alembic environment configuration for SyftHub database migrations.

This module configures Alembic to work with the SyftHub SQLAlchemy models and
database settings. It supports both offline (SQL script generation) and online
(direct database connection) migration modes.
"""

import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add src directory to path for imports
src_path = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_path))

# ruff: noqa: E402
# Import all models to register them with Base.metadata
# This import must happen BEFORE accessing Base.metadata
from syfthub.core.config import settings
from syfthub.models import (
    Base,
    EndpointModel,
    EndpointStarModel,
    ErrorLogModel,
    OrganizationMemberModel,
    OrganizationModel,
    UserAggregatorModel,
    UserModel,
)

# Ensure models are registered (prevent "unused import" warnings)
_models = [
    EndpointModel,
    EndpointStarModel,
    ErrorLogModel,
    OrganizationMemberModel,
    OrganizationModel,
    UserAggregatorModel,
    UserModel,
]

# Alembic Config object - provides access to alembic.ini values
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
# This is the SQLAlchemy MetaData object containing all model definitions
target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from application settings.

    This ensures migrations use the same database configuration as the
    application, controlled by the DATABASE_URL environment variable.

    Returns:
        Database URL string
    """
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This generates SQL scripts without connecting to the database.
    Useful for reviewing migration SQL before applying, or for environments
    where direct database access isn't available during deployment.

    Configures the context with just a URL (no Engine needed).
    Calls to context.execute() emit the given SQL string.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Comparison options for autogenerate
        compare_type=True,  # Detect column type changes
        compare_server_default=True,  # Detect default value changes
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and connects to the database to apply migrations
    directly. This is the normal mode for development and production.
    """
    # Override sqlalchemy.url from alembic.ini with application settings
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Comparison options for autogenerate
            compare_type=True,  # Detect column type changes
            compare_server_default=True,  # Detect default value changes
            # Include object name in autogenerate comparisons
            include_object=include_object,
            # Render item for custom type handling (e.g., JSON vs JSONB)
            render_as_batch=is_sqlite(),  # Use batch mode for SQLite
        )

        with context.begin_transaction():
            context.run_migrations()


def is_sqlite() -> bool:
    """Check if the database is SQLite.

    SQLite has limited ALTER TABLE support, so we use batch mode
    for migrations when running against SQLite.

    Returns:
        True if using SQLite, False otherwise
    """
    return settings.database_url.startswith("sqlite")


def include_object(
    _object: Any,
    name: str | None,
    _type: str,
    _reflected: bool,
    _compare_to: Any,
) -> bool:
    """Filter objects for autogenerate comparison.

    This function controls which database objects are included in
    autogenerate comparisons. Used to exclude temporary tables and
    other objects that shouldn't be tracked in migrations.

    Args:
        _object: The database object being considered
        name: Name of the object
        _type: Type of object ('table', 'column', 'index', etc.)
        _reflected: Whether this object was reflected from the database
        _compare_to: The object from metadata being compared to

    Returns:
        True to include the object in comparisons, False to skip it
    """
    # Skip temporary tables created during migrations
    if name and name.startswith("_alembic_tmp"):
        return False

    # Skip internal SQLAlchemy/Alembic tables
    return not (name and name.startswith("alembic_"))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
