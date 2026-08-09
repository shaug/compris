"""Shared test fixture helpers for the repository-root `scripts/tests/` suite.

Follows the same `helpers.py`-per-test-directory convention already used by
`skills/carve-changesets/scripts/tests/helpers.py` and
`skills/review-fix-loop/scripts/tests/helpers.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# The directories that together make up a testable copy of the plugin
# packaging fixture: the two plugin manifests, the two marketplace catalogs,
# and the skill suite `validate_plugins.py` inspects.
PLUGIN_FIXTURE_DIRS = (".agents", ".claude-plugin", ".codex-plugin", "skills")


def copy_fixture(destination: Path) -> None:
    """Copy the plugin packaging fixture directories into `destination`."""
    for name in PLUGIN_FIXTURE_DIRS:
        shutil.copytree(REPOSITORY_ROOT / name, destination / name)
