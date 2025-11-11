"""Tests for the main module."""

from syfthub.main import main


def test_main(capsys) -> None:
    """Test the main function output."""
    main()
    captured = capsys.readouterr()
    assert captured.out == "Hello from syfthub!\n"
