"""Concurrency smoke test for the lock-guarded token blacklist.

Route handlers now run on threadpool threads, so ``token_blacklist`` is mutated
concurrently. These tests exercise the ``_blacklist_lock``-guarded functions
from many threads at once and assert no exceptions and consistent state.
"""

import threading
import time

import pytest

from syfthub.auth import security


@pytest.fixture(autouse=True)
def _clear_blacklist():
    """Isolate each test from shared module state."""
    with security._blacklist_lock:
        security.token_blacklist.clear()
    yield
    with security._blacklist_lock:
        security.token_blacklist.clear()


def test_concurrent_blacklist_and_check_no_errors() -> None:
    """Hammer blacklist/check/cleanup from many threads; expect no exceptions."""
    errors: list[Exception] = []
    n_threads = 24
    per_thread = 50

    def worker(worker_id: int) -> None:
        try:
            for i in range(per_thread):
                token = f"tok-{worker_id}-{i}"
                # Non-JWT tokens fall back to a far-future TTL, so entries stay
                # blacklisted for the assertion below.
                security.blacklist_token(token)
                assert security.is_token_blacklisted(token) is True
                # Interleave a cleanup to exercise the iterate-and-delete path.
                if i % 10 == 0:
                    security.cleanup_expired_tokens()
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent blacklist access raised: {errors[:3]}"
    # Every non-expired token inserted should still be present.
    assert len(security.token_blacklist) == n_threads * per_thread


def test_expired_entries_are_cleaned() -> None:
    """An entry whose expiry is in the past is dropped by cleanup and reads False."""
    token = "expired-token"
    with security._blacklist_lock:
        security.token_blacklist[token] = time.time() - 1.0

    # Lazy cleanup on read.
    assert security.is_token_blacklisted(token) is False
    with security._blacklist_lock:
        assert token not in security.token_blacklist
