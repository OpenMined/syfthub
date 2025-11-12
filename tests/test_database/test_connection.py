"""Tests for database connection and session management."""

from __future__ import annotations

from unittest.mock import Mock, patch

from sqlalchemy.orm import Session

from syfthub.database.connection import (
    DatabaseManager,
    _get_connect_args,
    create_tables,
    db_manager,
    drop_tables,
    get_db_session,
    set_sqlite_pragma,
)


class TestConnectArgs:
    """Test connection arguments function."""

    @patch("syfthub.database.connection.settings")
    def test_get_connect_args_sqlite(self, mock_settings):
        """Test connection args for SQLite database."""
        mock_settings.database_url = "sqlite:///test.db"

        args = _get_connect_args()

        expected_args = {
            "check_same_thread": False,
            "isolation_level": None,
        }
        assert args == expected_args

    @patch("syfthub.database.connection.settings")
    def test_get_connect_args_non_sqlite(self, mock_settings):
        """Test connection args for non-SQLite database."""
        mock_settings.database_url = "postgresql://user:pass@localhost/db"

        args = _get_connect_args()

        assert args == {}


class TestTableFunctions:
    """Test table management functions."""

    @patch("syfthub.database.connection.Base")
    @patch("syfthub.database.connection.engine")
    def test_create_tables(self, mock_engine, mock_base):
        """Test creating all tables."""
        create_tables()

        mock_base.metadata.create_all.assert_called_once_with(bind=mock_engine)

    @patch("syfthub.database.connection.Base")
    @patch("syfthub.database.connection.engine")
    def test_drop_tables(self, mock_engine, mock_base):
        """Test dropping all tables."""
        drop_tables()

        mock_base.metadata.drop_all.assert_called_once_with(bind=mock_engine)


class TestSessionDependency:
    """Test database session dependency."""

    @patch("syfthub.database.connection.SessionLocal")
    def test_get_db_session_normal_flow(self, mock_session_local):
        """Test normal flow of get_db_session dependency."""
        mock_db = Mock(spec=Session)
        mock_session_local.return_value = mock_db

        # Use the generator
        session_generator = get_db_session()

        # Get the session from generator
        session = next(session_generator)
        assert session == mock_db

        # Close the generator (simulates FastAPI dependency cleanup)
        import contextlib

        with contextlib.suppress(StopIteration):
            next(session_generator)

        # Verify session was closed
        mock_db.close.assert_called_once()

    @patch("syfthub.database.connection.SessionLocal")
    def test_get_db_session_exception_handling(self, mock_session_local):
        """Test that session is closed even if exception occurs."""
        mock_db = Mock(spec=Session)
        mock_session_local.return_value = mock_db

        session_generator = get_db_session()
        session = next(session_generator)
        assert session == mock_db

        # Simulate exception by calling close on generator
        session_generator.close()

        # Verify session was closed
        mock_db.close.assert_called_once()


class TestDatabaseManager:
    """Test DatabaseManager class."""

    @patch("syfthub.database.connection.engine")
    @patch("syfthub.database.connection.SessionLocal")
    def test_database_manager_init(self, mock_session_local, mock_engine):
        """Test DatabaseManager initialization."""
        manager = DatabaseManager()

        assert manager.engine == mock_engine
        assert manager.session_factory == mock_session_local

    @patch("syfthub.database.connection.Base")
    def test_create_all_tables(self, mock_base):
        """Test creating all tables through manager."""
        manager = DatabaseManager()
        manager.create_all_tables()

        mock_base.metadata.create_all.assert_called_once_with(bind=manager.engine)

    @patch("syfthub.database.connection.Base")
    def test_drop_all_tables(self, mock_base):
        """Test dropping all tables through manager."""
        manager = DatabaseManager()
        manager.drop_all_tables()

        mock_base.metadata.drop_all.assert_called_once_with(bind=manager.engine)

    def test_get_session(self):
        """Test getting session through manager."""
        manager = DatabaseManager()

        with patch.object(manager, "session_factory") as mock_session_factory:
            mock_session = Mock(spec=Session)
            mock_session_factory.return_value = mock_session

            session = manager.get_session()

            assert session == mock_session
            mock_session_factory.assert_called_once()

    @patch("syfthub.database.connection.Base")
    def test_reset_database(self, mock_base):
        """Test resetting database through manager."""
        manager = DatabaseManager()

        manager.reset_database()

        # Should call drop then create
        mock_base.metadata.drop_all.assert_called_with(bind=manager.engine)
        mock_base.metadata.create_all.assert_called_with(bind=manager.engine)


class TestSQLitePragma:
    """Test SQLite pragma event handler."""

    @patch("syfthub.database.connection.settings")
    def test_set_sqlite_pragma_sqlite_db(self, mock_settings):
        """Test pragma setting for SQLite database."""
        mock_settings.database_url = "sqlite:///test.db"

        # Mock database connection
        mock_cursor = Mock()
        mock_dbapi_connection = Mock()
        mock_dbapi_connection.cursor.return_value = mock_cursor

        # Call the pragma function
        set_sqlite_pragma(mock_dbapi_connection, None)

        # Verify pragma was set
        mock_dbapi_connection.cursor.assert_called_once()
        mock_cursor.execute.assert_called_once_with("PRAGMA foreign_keys=ON")
        mock_cursor.close.assert_called_once()

    @patch("syfthub.database.connection.settings")
    def test_set_sqlite_pragma_non_sqlite_db(self, mock_settings):
        """Test pragma setting for non-SQLite database (should not set pragma)."""
        mock_settings.database_url = "postgresql://user:pass@localhost/db"

        # Mock database connection
        mock_dbapi_connection = Mock()

        # Call the pragma function
        set_sqlite_pragma(mock_dbapi_connection, None)

        # Verify no cursor operations were performed
        mock_dbapi_connection.cursor.assert_not_called()


class TestGlobalManagerInstance:
    """Test global database manager instance."""

    def test_db_manager_is_database_manager_instance(self):
        """Test that db_manager is a DatabaseManager instance."""
        assert isinstance(db_manager, DatabaseManager)

    def test_db_manager_has_required_methods(self):
        """Test that db_manager has all required methods."""
        required_methods = [
            "create_all_tables",
            "drop_all_tables",
            "get_session",
            "reset_database",
        ]

        for method_name in required_methods:
            assert hasattr(db_manager, method_name)
            assert callable(getattr(db_manager, method_name))
