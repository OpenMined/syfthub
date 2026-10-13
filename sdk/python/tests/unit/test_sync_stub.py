"""The generated sync faces: in step with the async package, and seen by a type checker."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

import syfthub
from syfthub import sync
from syfthub.testing import FakeHub

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "gen_sync_stub.py"


def load_generator() -> object:
    spec = importlib.util.spec_from_file_location("gen_sync_stub", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # pydantic resolves the script's annotations through here
    spec.loader.exec_module(module)
    return module


def test_generated_files_match_the_async_package() -> None:
    generated = load_generator().generate()  # type: ignore[attr-defined]
    stale = [rel for rel, text in generated.items() if (ROOT / rel).read_text() != text]
    assert not stale, f"regenerate with `uv run python scripts/gen_sync_stub.py`: {stale}"


def test_sync_names_are_the_real_classes_at_runtime() -> None:
    assert sync.Hub is syfthub.Hub and sync.SearchPlan is syfthub.SearchPlan
    assert sync.Wallet is syfthub.Wallet and sync.Preflight is syfthub.Preflight
    fake = FakeHub()
    fake.add_source("alice", "notes")
    with syfthub.Hub(fake.url, token="t", options=fake.options()) as hub:
        plan = hub.search("q", ["alice/notes"])
        assert isinstance(plan, sync.SearchPlan) and isinstance(plan.preflight(), sync.Preflight)


PROBE = """
import syfthub
from syfthub import TopUp, sync

hub = syfthub.Hub(token="t")
reveal_type(hub.sources.list())
plan = hub.search("q")
reveal_type(plan.preflight())
for action in plan.preflight().actions:
    if isinstance(action, TopUp):
        reveal_type(action.top_up())
reveal_type(plan.execute().documents)
reveal_type(hub.wallets.list()[0].refresh())
reveal_type(hub.load(syfthub.Results, {}))

def review(pre: sync.Preflight) -> sync.PlanRow:
    return pre.rows[0]

hub.nope
"""

EXPECTED = [
    "syfthub.models.sources.SourceList",
    "syfthub._sync.Preflight",
    "syfthub._sync.Invoice",
    "tuple[tuple[str, syfthub.models.results.Document], ...]",
    "syfthub._sync.Wallet",
    "syfthub._sync.Results",
]


@pytest.mark.skipif(importlib.util.find_spec("mypy") is None, reason="mypy is a dev extra")
def test_a_type_checker_sees_through_the_sync_hub(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(PROBE)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--no-incremental",
            "--cache-dir",
            str(tmp_path),
            str(probe),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    revealed = re.findall(r'Revealed type is "([^"]+)"', result.stdout)
    assert revealed == EXPECTED, result.stdout
    errors = [line for line in result.stdout.splitlines() if ": error:" in line]
    assert len(errors) == 1 and '"Hub" has no attribute "nope"' in errors[0], result.stdout
