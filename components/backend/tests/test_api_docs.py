"""The generated backend API reference: in step with the routes the app serves."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.routing import APIRoute

from syfthub.main import app

GENERATOR = Path(__file__).resolve().parents[1] / "scripts" / "gen_api_docs.py"


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_api_docs", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reference_page_matches_the_routes(generator: ModuleType) -> None:
    target: Path = generator.TARGET
    if not target.parent.is_dir():
        pytest.skip("docs/ is not part of this checkout")
    assert target.read_text() == generator.generate(), (
        "regenerate with `uv run python scripts/gen_api_docs.py`"
    )


def test_every_route_is_listed_once(generator: ModuleType) -> None:
    page: str = generator.generate()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            for method in route.methods:
                heading = f"### `{method} {route.path}`\n"
                assert page.count(heading) == 1, heading
