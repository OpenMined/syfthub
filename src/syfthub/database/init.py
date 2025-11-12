"""Database initialization and migration utilities."""

from __future__ import annotations

import asyncio
from typing import Any

from syfthub.database.connection import db_manager
from syfthub.database.repositories import (
    DatasiteRepository,
    UserRepository,
)


def initialize_database() -> None:
    """Initialize database by creating all tables."""
    print("Initializing database...")
    db_manager.create_all_tables()
    print("Database initialized successfully.")


def reset_database() -> None:
    """Reset database by dropping and recreating all tables."""
    print("Resetting database...")
    db_manager.reset_database()
    print("Database reset successfully.")


def migrate_mock_data_to_database(
    mock_users: dict[int, Any] | None = None,
    mock_datasites: dict[int, Any] | None = None,
) -> None:
    """Migrate data from mock dictionaries to database.

    Args:
        mock_users: Mock users database dict
        mock_items: Mock items database dict
        mock_datasites: Mock datasites database dict
    """
    session = db_manager.get_session()

    try:
        user_repo = UserRepository(session)
        datasite_repo = DatasiteRepository(session)

        # Migrate users first (they're referenced by items and datasites)
        if mock_users:
            print(f"Migrating {len(mock_users)} users...")
            for user in mock_users.values():
                # Convert User schema to dict for repository
                user_data = {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "age": user.age,
                    "role": user.role.value,
                    "password_hash": user.password_hash,
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                }
                user_repo.create(user_data)
            print("Users migrated successfully.")

        # Migrate datasites
        if mock_datasites:
            print(f"Migrating {len(mock_datasites)} datasites...")
            for datasite in mock_datasites.values():
                datasite_data = {
                    "id": datasite.id,
                    "user_id": datasite.user_id,
                    "name": datasite.name,
                    "slug": datasite.slug,
                    "description": datasite.description,
                    "visibility": datasite.visibility.value,
                    "is_active": datasite.is_active,
                    "created_at": datasite.created_at,
                    "updated_at": datasite.updated_at,
                }
                datasite_repo.create(datasite_data)
            print("Datasites migrated successfully.")

    finally:
        session.close()


async def main() -> None:
    """Main function for CLI usage."""
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "init":
            initialize_database()
        elif command == "reset":
            reset_database()
        else:
            print(f"Unknown command: {command}")
            print("Available commands: init, reset")
    else:
        initialize_database()


if __name__ == "__main__":
    asyncio.run(main())
