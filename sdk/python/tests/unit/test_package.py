"""Smoke test: the package imports and reports its version."""

import syfthub


def test_version() -> None:
    assert syfthub.__version__ == "2.0.0a1"
