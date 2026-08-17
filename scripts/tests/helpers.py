"""Shared test fixture helpers for the repository-root `scripts/tests/` suite.

Follows the same `helpers.py`-per-test-directory convention already used by
`skills/carve-changesets/scripts/tests/helpers.py` and
`skills/review-fix-loop/scripts/tests/helpers.py`.
"""

from __future__ import annotations

import re
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


def compact(value: str) -> str:
    """Collapse runs of whitespace to a single space and strip the ends."""
    return re.sub(r"\s+", " ", value).strip()


JUSTFILE = REPOSITORY_ROOT / "justfile"

# One `@for skill in <names>; do … done` loop in `sync-contracts`, matched
# against the recipe's own shell syntax.
SYNC_BLOCK = re.compile(r"@for skill in (.+?); do(.*?)\n  done", re.S)


def sync_block_skills(copied: str) -> tuple[str, ...]:
    """The skills the `sync-contracts` block copying `copied` names, in order.

    Every bundled contract is drift-checked by a test whose failure message
    tells the reader to run `just sync-contracts`, so each of those tests has
    to confirm the recipe actually refreshes its own copy — otherwise the
    remedy it prescribes is a dead end. Scoping to the one block that copies
    `copied`, and returning it for an equality assertion, is what makes that
    confirmation real: every bundling skill is named in the recipe's other
    blocks too, so a whole-file substring check still passes after a skill is
    dropped from the block under test.

    Shared rather than written per caller because the thing being parsed is
    one justfile's shell syntax. Two independently maintained copies of this
    regex fail asymmetrically when that loop is reformatted — whichever copy
    is not updated goes quietly vacuous while the other still reddens.

    Raises when the block is absent or duplicated, since a caller asserting
    against an empty or ambiguous match would pass for the wrong reason.
    """
    blocks = [
        listed
        for listed, body in SYNC_BLOCK.findall(JUSTFILE.read_text())
        if f"cp {copied}" in body
    ]
    if len(blocks) != 1:
        raise AssertionError(
            f"expected exactly one sync block copying {copied}, found {len(blocks)}"
        )
    return tuple(blocks[0].split())
