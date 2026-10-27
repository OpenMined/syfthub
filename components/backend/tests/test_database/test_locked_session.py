"""Tests for ``DatabaseManager.locked_session``.

Session-level advisory locks belong to the connection. The old jobs took the
lock through a pooled session and relied on ``session.close()`` to release it,
which it never did: the connection went back to the pool still holding the
lock, and every later cycle on another connection skipped as "held by another
worker". These tests pin the contract that fixed it: one dedicated connection
for the cycle, and an explicit unlock on the way out.
"""

from unittest.mock import MagicMock

import pytest

from syfthub.database.connection import DatabaseManager


def _manager(dialect: str, acquired: bool = True):
    """A DatabaseManager over a fake engine whose connection reports ``acquired``."""
    manager = DatabaseManager.__new__(DatabaseManager)
    manager.engine = MagicMock()
    manager.engine.dialect.name = dialect
    conn = manager.engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar.return_value = acquired
    manager.session_factory = MagicMock()
    return manager, conn


def _sql(call) -> str:
    return str(call.args[0])


class TestLockedSession:
    def test_postgres_runs_the_cycle_on_one_connection_and_unlocks(self):
        manager, conn = _manager("postgresql", acquired=True)
        session = manager.session_factory.return_value

        with manager.locked_session(42) as yielded:
            assert yielded is session
            manager.session_factory.assert_called_once_with(bind=conn)
            statements = [_sql(c) for c in conn.execute.call_args_list]
            assert any("pg_try_advisory_lock" in s for s in statements)
            assert not any("pg_advisory_unlock" in s for s in statements)

        session.close.assert_called_once()
        statements = [_sql(c) for c in conn.execute.call_args_list]
        assert any("pg_advisory_unlock" in s for s in statements)
        assert conn.execute.call_args_list[-1].args[1] == {"lock_id": 42}

    def test_postgres_yields_none_when_another_holder_has_the_lock(self):
        manager, conn = _manager("postgresql", acquired=False)

        with manager.locked_session(42) as yielded:
            assert yielded is None

        manager.session_factory.assert_not_called()
        statements = [_sql(c) for c in conn.execute.call_args_list]
        assert not any("pg_advisory_unlock" in s for s in statements)

    def test_postgres_unlocks_even_when_the_cycle_raises(self):
        manager, conn = _manager("postgresql", acquired=True)
        session = manager.session_factory.return_value

        with pytest.raises(RuntimeError), manager.locked_session(42):
            raise RuntimeError("cycle blew up")

        session.close.assert_called_once()
        statements = [_sql(c) for c in conn.execute.call_args_list]
        assert any("pg_advisory_unlock" in s for s in statements)

    def test_unlock_failure_is_logged_not_raised(self):
        manager, conn = _manager("postgresql", acquired=True)
        lock_result = MagicMock()
        lock_result.scalar.return_value = True
        conn.execute.side_effect = [lock_result, Exception("connection lost")]

        with manager.locked_session(42) as yielded:
            assert yielded is not None

    def test_other_dialects_get_a_plain_session_and_no_lock(self):
        manager, conn = _manager("sqlite")
        session = manager.session_factory.return_value

        with manager.locked_session(42) as yielded:
            assert yielded is session

        manager.engine.connect.assert_not_called()
        conn.execute.assert_not_called()
        session.close.assert_called_once()
