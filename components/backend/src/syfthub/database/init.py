"""Database initialization and migration utilities."""

from __future__ import annotations

import asyncio

from syfthub.database.connection import db_manager


def initialize_database() -> None:
    """Initialize database by creating all tables."""
    import logging

    logger = logging.getLogger(__name__)

    logger.info("Initializing database...")
    db_manager.create_all_tables()
    logger.info("Database initialized successfully.")


def reset_database() -> None:
    """Reset database by dropping and recreating all tables."""
    import logging

    logger = logging.getLogger(__name__)

    logger.info("Resetting database...")
    db_manager.reset_database()
    logger.info("Database reset successfully.")


async def main() -> None:
    """Main function for CLI usage."""
    import logging
    import sys

    logger = logging.getLogger(__name__)

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "init":
            initialize_database()
        elif command == "reset":
            reset_database()
        else:
            logger.error(f"Unknown command: {command}")
            logger.info("Available commands: init, reset")
    else:
        initialize_database()


if __name__ == "__main__":
    asyncio.run(main())
