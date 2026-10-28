"""Tests for ``DatabaseManager.locked_session``.

Session-level advisory locks belong to the connection. The old jobs took the
lock through a pooled session and relied on ``session.close()`` to release it,
which it never did: the connection went back to the pool still holding the
lock, and every later cycle on another connection skipped as "held by another
worker". These tests pin the contract that fixed it: one dedicated connection
for the cycle, and an explicit unlock on the way out.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from syfthub.database.connection import DatabaseManager, JobLock


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

        def blow_up() -> None:
            raise RuntimeError("cycle blew up")

        with pytest.raises(RuntimeError), manager.locked_session(42):
            blow_up()

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


def _job_lock(dialect: str, acquired: bool = True) -> SimpleNamespace:
    """A JobLock over a fake engine whose fresh connections report ``acquired``."""
    engine = MagicMock()
    engine.dialect.name = dialect
    conn = engine.connect.return_value
    conn.execute.return_value.scalar.return_value = acquired
    factory = MagicMock()
    return SimpleNamespace(
        lock=JobLock(engine, factory, 7), engine=engine, conn=conn, factory=factory
    )


class TestJobLock:
    """The leader lock: held across cycles, not taken and dropped per cycle.

    Taking the lock per cycle only serialised the workers; with four uvicorn
    workers three or four cycles still ran every interval. The first worker
    to acquire keeps the lock and the connection until stop() or the
    connection dies.
    """

    def test_leader_keeps_one_connection_across_cycles(self):
        fx = _job_lock("postgresql", acquired=True)

        assert fx.lock.acquire() is True
        assert fx.lock.acquire() is True

        fx.engine.connect.assert_called_once()
        statements = [_sql(c) for c in fx.conn.execute.call_args_list]
        assert sum("pg_try_advisory_lock" in s for s in statements) == 1
        assert statements[-1] == "SELECT 1", "a held lock is probed, not re-taken"
        fx.conn.close.assert_not_called()
        assert fx.lock.held

    def test_cycle_session_is_bound_to_the_pinned_connection(self):
        fx = _job_lock("postgresql", acquired=True)
        fx.lock.acquire()

        session = fx.lock.session()

        fx.factory.assert_called_once_with(bind=fx.conn)
        assert session is fx.factory.return_value

    def test_follower_tries_each_time_and_pins_nothing(self):
        fx = _job_lock("postgresql", acquired=False)

        assert fx.lock.acquire() is False
        assert fx.lock.acquire() is False

        assert fx.engine.connect.call_count == 2
        assert fx.conn.close.call_count == 2
        assert not fx.lock.held

    def test_release_unlocks_and_returns_the_connection(self):
        fx = _job_lock("postgresql", acquired=True)
        fx.lock.acquire()

        fx.lock.release()

        statements = [_sql(c) for c in fx.conn.execute.call_args_list]
        assert any("pg_advisory_unlock" in s for s in statements)
        assert fx.conn.execute.call_args_list[-1].args[1] == {"lock_id": 7}
        fx.conn.close.assert_called_once()
        assert not fx.lock.held

    def test_release_when_not_held_is_a_no_op(self):
        fx = _job_lock("postgresql", acquired=False)
        fx.lock.acquire()

        fx.lock.release()

        statements = [_sql(c) for c in fx.conn.execute.call_args_list]
        assert not any("pg_advisory_unlock" in s for s in statements)

    def test_dead_leader_connection_is_replaced(self):
        fx = _job_lock("postgresql", acquired=True)
        fx.lock.acquire()
        ok = MagicMock()
        ok.scalar.return_value = True
        fx.conn.execute.side_effect = [Exception("server closed the connection"), ok]

        assert fx.lock.acquire() is True

        assert fx.engine.connect.call_count == 2, "probe failed, so a new connection"
        assert fx.lock.held

    def test_other_dialects_always_acquire_without_a_connection(self):
        fx = _job_lock("sqlite")

        assert fx.lock.acquire() is True
        fx.engine.connect.assert_not_called()
        fx.factory.assert_not_called()
        fx.lock.session()
        fx.factory.assert_called_once_with()
