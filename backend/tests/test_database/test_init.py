"""Tests for database initialization utilities."""

from __future__ import annotations

from unittest.mock import Mock, patch

from syfthub.database.init import (
    initialize_database,
    main,
    reset_database,
)


class TestDatabaseInit:
    """Test database initialization functions."""

    @patch("syfthub.database.init.db_manager")
    @patch("logging.getLogger")
    def test_initialize_database(self, mock_get_logger, mock_db_manager):
        """Test database initialization."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        initialize_database()

        mock_db_manager.create_all_tables.assert_called_once()
        mock_logger.info.assert_any_call("Initializing database...")
        mock_logger.info.assert_any_call("Database initialized successfully.")

    @patch("syfthub.database.init.db_manager")
    @patch("logging.getLogger")
    def test_reset_database(self, mock_get_logger, mock_db_manager):
        """Test database reset."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        reset_database()

        mock_db_manager.reset_database.assert_called_once()
        mock_logger.info.assert_any_call("Resetting database...")
        mock_logger.info.assert_any_call("Database reset successfully.")


class TestMainFunction:
    """Test main CLI function."""

    @patch("syfthub.database.init.initialize_database")
    def test_main_init_command(self, mock_initialize):
        """Test main function with init command."""
        import asyncio

        with patch("sys.argv", ["script", "init"]):
            asyncio.run(main())

        mock_initialize.assert_called_once()

    @patch("syfthub.database.init.reset_database")
    def test_main_reset_command(self, mock_reset):
        """Test main function with reset command."""
        import asyncio

        with patch("sys.argv", ["script", "reset"]):
            asyncio.run(main())

        mock_reset.assert_called_once()

    @patch("syfthub.database.init.initialize_database")
    @patch("logging.getLogger")
    def test_main_unknown_command(self, mock_get_logger, mock_initialize):
        """Test main function with unknown command."""
        import asyncio

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        with patch("sys.argv", ["script", "unknown"]):
            asyncio.run(main())

        mock_initialize.assert_not_called()
        mock_logger.error.assert_any_call("Unknown command: unknown")
        mock_logger.info.assert_any_call("Available commands: init, reset")

    @patch("syfthub.database.init.initialize_database")
    def test_main_no_command(self, mock_initialize):
        """Test main function with no command (defaults to init)."""
        import asyncio

        with patch("sys.argv", ["script"]):
            asyncio.run(main())

        mock_initialize.assert_called_once()
