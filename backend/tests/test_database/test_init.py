"""Tests for database initialization utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock, call, patch

import pytest

from syfthub.database.init import (
    initialize_database,
    main,
    migrate_mock_data_to_database,
    reset_database,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.datasite import Datasite, DatasiteVisibility
from syfthub.schemas.user import User


class TestDatabaseInit:
    """Test database initialization functions."""

    @patch("syfthub.database.init.db_manager")
    @patch("builtins.print")
    def test_initialize_database(self, mock_print, mock_db_manager):
        """Test database initialization."""
        initialize_database()

        mock_db_manager.create_all_tables.assert_called_once()
        expected_calls = [
            call("Initializing database..."),
            call("Database initialized successfully."),
        ]
        mock_print.assert_has_calls(expected_calls)

    @patch("syfthub.database.init.db_manager")
    @patch("builtins.print")
    def test_reset_database(self, mock_print, mock_db_manager):
        """Test database reset."""
        reset_database()

        mock_db_manager.reset_database.assert_called_once()
        expected_calls = [
            call("Resetting database..."),
            call("Database reset successfully."),
        ]
        mock_print.assert_has_calls(expected_calls)

    @patch("syfthub.database.init.db_manager")
    @patch("builtins.print")
    def test_migrate_mock_data_to_database_empty(self, _mock_print, mock_db_manager):
        """Test migration with no data."""
        mock_session = Mock()
        mock_db_manager.get_session.return_value = mock_session

        migrate_mock_data_to_database()

        mock_db_manager.get_session.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("syfthub.database.init.db_manager")
    @patch("syfthub.database.init.UserRepository")
    @patch("syfthub.database.init.DatasiteRepository")
    @patch("builtins.print")
    def test_migrate_mock_data_to_database_with_users(
        self,
        mock_print,
        mock_datasite_repo_class,
        mock_user_repo_class,
        mock_db_manager,
    ):
        """Test migration with user data."""
        # Setup mocks
        mock_session = Mock()
        mock_db_manager.get_session.return_value = mock_session
        mock_user_repo = Mock()
        mock_user_repo_class.return_value = mock_user_repo
        mock_datasite_repo = Mock()
        mock_datasite_repo_class.return_value = mock_datasite_repo

        # Create test user
        from tests.test_utils import get_test_user_data

        user_data = get_test_user_data(
            {
                "id": 1,
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "age": 30,
                "role": UserRole.USER,
                "password_hash": "hashed_password",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        test_user = User(**user_data)

        mock_users = {1: test_user}

        migrate_mock_data_to_database(mock_users=mock_users)

        # Verify repositories were created
        mock_user_repo_class.assert_called_once_with(mock_session)
        mock_datasite_repo_class.assert_called_once_with(mock_session)

        # Verify user migration
        expected_user_data = {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "full_name": "Test User",
            "age": 30,
            "role": "user",
            "password_hash": "hashed_password",
            "is_active": True,
            "created_at": test_user.created_at,
            "updated_at": test_user.updated_at,
        }
        mock_user_repo.create.assert_called_once_with(expected_user_data)

        # Verify print statements
        print_calls = mock_print.call_args_list
        assert any("Migrating 1 users..." in str(call) for call in print_calls)
        assert any("Users migrated successfully." in str(call) for call in print_calls)

        # Verify session cleanup
        mock_session.close.assert_called_once()

    @patch("syfthub.database.init.db_manager")
    @patch("syfthub.database.init.UserRepository")
    @patch("syfthub.database.init.DatasiteRepository")
    @patch("builtins.print")
    def test_migrate_mock_data_to_database_with_datasites(
        self,
        mock_print,
        mock_datasite_repo_class,
        mock_user_repo_class,
        mock_db_manager,
    ):
        """Test migration with datasite data."""
        # Setup mocks
        mock_session = Mock()
        mock_db_manager.get_session.return_value = mock_session
        mock_user_repo = Mock()
        mock_user_repo_class.return_value = mock_user_repo
        mock_datasite_repo = Mock()
        mock_datasite_repo_class.return_value = mock_datasite_repo

        # Create test datasite
        test_datasite = Datasite(
            id=1,
            user_id=1,
            name="Test Datasite",
            slug="test-datasite",
            description="A test datasite",
            visibility=DatasiteVisibility.PUBLIC,
            is_active=True,
            contributors=[],
            version="1.0.0",
            readme="# Test Datasite",
            stars_count=0,
            policies=[],
            connect=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_datasites = {1: test_datasite}

        migrate_mock_data_to_database(mock_datasites=mock_datasites)

        # Verify datasite migration
        expected_datasite_data = {
            "id": 1,
            "user_id": 1,
            "name": "Test Datasite",
            "slug": "test-datasite",
            "description": "A test datasite",
            "visibility": "public",
            "is_active": True,
            "created_at": test_datasite.created_at,
            "updated_at": test_datasite.updated_at,
        }
        mock_datasite_repo.create.assert_called_once_with(expected_datasite_data)

        # Verify print statements
        print_calls = mock_print.call_args_list
        assert any("Migrating 1 datasites..." in str(call) for call in print_calls)
        assert any(
            "Datasites migrated successfully." in str(call) for call in print_calls
        )

    @patch("syfthub.database.init.db_manager")
    @patch("syfthub.database.init.UserRepository")
    @patch("syfthub.database.init.DatasiteRepository")
    def test_migrate_mock_data_session_cleanup_on_exception(
        self, _mock_datasite_repo_class, mock_user_repo_class, mock_db_manager
    ):
        """Test that session is cleaned up even if an exception occurs."""
        mock_session = Mock()
        mock_db_manager.get_session.return_value = mock_session
        mock_user_repo = Mock()
        mock_user_repo.create.side_effect = Exception("Test exception")
        mock_user_repo_class.return_value = mock_user_repo

        # Create test user
        from tests.test_utils import get_test_user_data

        user_data = get_test_user_data(
            {
                "id": 1,
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "age": 30,
                "role": UserRole.USER,
                "password_hash": "hashed_password",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        test_user = User(**user_data)

        mock_users = {1: test_user}

        with pytest.raises(Exception, match="Test exception"):
            migrate_mock_data_to_database(mock_users=mock_users)

        # Verify session cleanup happened despite exception
        mock_session.close.assert_called_once()


class TestMainFunction:
    """Test main CLI function."""

    @patch("syfthub.database.init.initialize_database")
    @patch("builtins.print")
    def test_main_init_command(self, _mock_print, mock_initialize):
        """Test main function with init command."""
        import asyncio

        with patch("sys.argv", ["script", "init"]):
            asyncio.run(main())

        mock_initialize.assert_called_once()

    @patch("syfthub.database.init.reset_database")
    @patch("builtins.print")
    def test_main_reset_command(self, _mock_print, mock_reset):
        """Test main function with reset command."""
        import asyncio

        with patch("sys.argv", ["script", "reset"]):
            asyncio.run(main())

        mock_reset.assert_called_once()

    @patch("syfthub.database.init.initialize_database")
    @patch("builtins.print")
    def test_main_unknown_command(self, mock_print, mock_initialize):
        """Test main function with unknown command."""
        import asyncio

        with patch("sys.argv", ["script", "unknown"]):
            asyncio.run(main())

        mock_initialize.assert_not_called()
        expected_calls = [
            call("Unknown command: unknown"),
            call("Available commands: init, reset"),
        ]
        mock_print.assert_has_calls(expected_calls)

    @patch("syfthub.database.init.initialize_database")
    @patch("builtins.print")
    def test_main_no_command(self, _mock_print, mock_initialize):
        """Test main function with no command (defaults to init)."""
        import asyncio

        with patch("sys.argv", ["script"]):
            asyncio.run(main())

        mock_initialize.assert_called_once()
