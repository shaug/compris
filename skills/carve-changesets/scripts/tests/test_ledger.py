"""Skill-specific tests for carve-changesets' ledger wrapper.

Generic ledger mechanics (workspace derivation/self-exclusion, append-only
I/O, malformed-line tolerance, the action-scoped dedup guard — including the
"a later entry from a different phase must not mask an earlier completed
one" behavior this skill's `review_fix_loop`/`publish`/`merge` phases depend
on) are exercised once against arbitrary parameters in
`ledger/scripts/tests/test_core.py` — see that file's own module docstring
for why. This file covers only what is genuinely specific to this skill:
`unit_key_for`'s source-branch composition and collision disambiguation, and
the CLI wiring that proves the wrapper actually delegates to the bundled
core under this skill's real flag names, field names, and phase vocabulary
(`review_fix_loop`/`publish`/`merge`).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "ledger.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "carve_changesets_ledger", MODULE_PATH
)
LEDGER = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
sys.modules[MODULE_SPEC.name] = LEDGER
MODULE_SPEC.loader.exec_module(LEDGER)


class TempRootTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


class UnitKeyTests(unittest.TestCase):
    def test_unit_key_digest_disambiguates_slash_boundary_collision(self) -> None:
        # Without the digest, "feature/api-timeout" and "feature-api/timeout"
        # would both slugify to "feature-api-timeout", silently merging two
        # distinct branches' workspaces onto one ledger file.
        first = LEDGER.slugify(LEDGER.unit_key_for("feature/api-timeout"))
        second = LEDGER.slugify(LEDGER.unit_key_for("feature-api/timeout"))
        self.assertNotEqual(first, second)

    def test_unit_key_is_deterministic(self) -> None:
        self.assertEqual(
            LEDGER.unit_key_for("feature/x"), LEDGER.unit_key_for("feature/x")
        )

    def test_workspace_lives_under_the_skills_own_dirname(self) -> None:
        directory = LEDGER.workspace_dir(Path("/tmp/root"), "feature/x")
        self.assertEqual(directory.parent.name, ".carve-changesets")


class CliTests(TempRootTestCase):
    def test_cli_round_trip(self) -> None:
        root = str(self.root)
        self.assertEqual(
            LEDGER.main(["--root", root, "session-start", "--source", "feature/x"]), 0
        )
        self.assertEqual(
            LEDGER.main(
                [
                    "--root",
                    root,
                    "record",
                    "--source",
                    "feature/x",
                    "--changeset",
                    "a",
                    "--action",
                    "review_fix_loop",
                    "--terminal-result",
                    "converged",
                ]
            ),
            0,
        )
        self.assertEqual(
            LEDGER.main(
                ["--root", root, "find", "--source", "feature/x", "--changeset", "a"]
            ),
            0,
        )
        self.assertEqual(
            LEDGER.main(
                ["--root", root, "find", "--source", "feature/x", "--changeset", "b"]
            ),
            1,
        )

    def test_cli_find_supports_action_scope(self) -> None:
        # Proves the wrapper's `action` parameter reaches the shared core's
        # action-scoped dedup guard under this skill's own real phase
        # vocabulary: a `publish` entry must not satisfy a `review_fix_loop`
        # lookup for the same changeset.
        root = str(self.root)
        LEDGER.main(
            [
                "--root",
                root,
                "record",
                "--source",
                "feature/x",
                "--changeset",
                "a",
                "--action",
                "publish",
                "--terminal-result",
                "prs_open",
            ]
        )
        self.assertEqual(
            LEDGER.main(
                [
                    "--root",
                    root,
                    "find",
                    "--source",
                    "feature/x",
                    "--changeset",
                    "a",
                    "--action",
                    "review_fix_loop",
                ]
            ),
            1,
        )
        self.assertEqual(
            LEDGER.main(
                [
                    "--root",
                    root,
                    "find",
                    "--source",
                    "feature/x",
                    "--changeset",
                    "a",
                    "--action",
                    "publish",
                ]
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
