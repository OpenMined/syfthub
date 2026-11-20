"""The generated API reference page: in step with the public surface."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "gen_api_reference.py"


def load_generator() -> object:
    spec = importlib.util.spec_from_file_location("gen_api_reference", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reference_page_matches_the_public_surface() -> None:
    generator = load_generator()
    target: Path = generator.TARGET  # type: ignore[attr-defined]
    assert target.read_text() == generator.generate(), (  # type: ignore[attr-defined]
        "regenerate with `uv run python scripts/gen_api_reference.py`"
    )


def test_every_public_name_is_listed_once() -> None:
    import syfthub

    page = load_generator().generate()  # type: ignore[attr-defined]
    for name in syfthub.__all__:
        if not name.startswith("__"):
            assert page.count(f"| `syfthub.{name}` |") == 1, name
