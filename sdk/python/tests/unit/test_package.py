import tomllib
from pathlib import Path

import syfthub

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_version_matches_pyproject() -> None:
    # The release workflow checks the tag against pyproject.toml and runs this test, so a
    # bump that misses _version.py fails before anything is published.
    declared = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert syfthub.__version__ == declared


def test_public_surface() -> None:
    assert {"SearchPlan", "Results", "Source", "Wallet", "SyftHubError"} <= set(syfthub.__all__)
