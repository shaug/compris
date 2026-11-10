"""Path loaders and fixed inputs for the sampling policy's regression tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def voting_executors():
    for name, path in (
        ("ticket", "skills/implement-ticket/scripts/evals/claude_executor.py"),
        ("planner", "skills/plan-implementation/scripts/evals/claude_executor.py"),
        ("router", "triggering/executors/description_executor.py"),
    ):
        yield name, load_module(f"sampling_{name}_executor", ROOT / path)
