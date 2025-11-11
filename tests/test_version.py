"""Tests for package version and metadata."""

import syfthub


def test_version() -> None:
    """Test that the package version is accessible."""
    assert syfthub.__version__ == "0.1.0"


def test_author() -> None:
    """Test that the author metadata is correct."""
    assert syfthub.__author__ == "Ionesio Junior"


def test_email() -> None:
    """Test that the email metadata is correct."""
    assert syfthub.__email__ == "ionesiojr@gmail.com"
