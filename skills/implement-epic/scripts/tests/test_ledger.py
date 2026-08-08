"""Skill-specific tests for implement-epic's ledger wrapper.

Generic ledger mechanics (workspace derivation/self-exclusion, append-only
I/O, malformed-line tolerance, the action-scoped dedup guard) are exercised
once against arbitrary parameters in `ledger/scripts/tests/test_core.py` —
see that file's own module docstring for why. This file covers only what is
genuinely specific to this skill: `unit_key_for`'s epic-key composition and
collision disambiguation, this skill's own completed-terminal-results
vocabulary (`ready_pr`/`ready_prs`/`merged`, excluding `blocked`), and the
CLI wiring that proves the wrapper actually delegates to the bundled core
under this skill's real flag names and field names.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "ledger.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "implement_epic_ledger", MODULE_PATH
)
LEDGER = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
# The dataclass below resolves its field types through
# `sys.modules[cls.__module__]`, so the module must be registered before
# `exec_module` runs it.
sys.modules[MODULE_SPEC.name] = LEDGER
MODULE_SPEC.loader.exec_module(LEDGER)


class TempRootTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


class UnitKeyTests(unittest.TestCase):
    def test_unit_key_digest_disambiguates_collision(self) -> None:
        # Without the digest, two epic keys differing only in where a `/`
        # falls could alias onto the same slug and silently share one
        # workspace.
        first = LEDGER.slugify(LEDGER.unit_key_for("github/119"))
        second = LEDGER.slugify(LEDGER.unit_key_for("github-119"))
        self.assertNotEqual(first, second)

    def test_unit_key_is_deterministic(self) -> None:
        self.assertEqual(
            LEDGER.unit_key_for("github-119"), LEDGER.unit_key_for("github-119")
        )

    def test_workspace_lives_under_the_skills_own_dirname(self) -> None:
        directory = LEDGER.workspace_dir(Path("/tmp/root"), "github-119")
        self.assertEqual(directory.parent.name, ".implement-epic")


class VocabularyTests(TempRootTestCase):
    def test_ready_pr_counts_as_complete(self) -> None:
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result="ready_pr",
        )
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertIsNotNone(LEDGER.already_recorded_complete(result.entries, "133"))

    def test_blocked_never_counts_as_complete(self) -> None:
        # A blocked child is not done; the dedup guard must never suppress a
        # re-dispatch of a child the ledger itself shows is unfinished.
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result="blocked",
        )
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertIsNone(LEDGER.already_recorded_complete(result.entries, "133"))


class CliTests(TempRootTestCase):
    def test_cli_session_start_and_record_round_trip_through_read(self) -> None:
        root = str(self.root)
        self.assertEqual(
            LEDGER.main(
                [
                    "--root",
                    root,
                    "session-start",
                    "--epic",
                    "github-119",
                    "--session-id",
                    "s1",
                ]
            ),
            0,
        )
        self.assertEqual(
            LEDGER.main(
                [
                    "--root",
                    root,
                    "record",
                    "--epic",
                    "github-119",
                    "--child",
                    "133",
                    "--action",
                    "child_dispatch",
                    "--terminal-result",
                    "ready_pr",
                    "--head-sha",
                    "abc123",
                    "--evidence-json",
                    '{"pr": 181}',
                ]
            ),
            0,
        )
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertEqual(len(result.sessions), 1)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0]["child_id"], "133")
        self.assertEqual(result.entries[0]["evidence"], {"pr": 181})

    def test_cli_find_exit_code_reflects_completion(self) -> None:
        root = str(self.root)
        self.assertEqual(
            LEDGER.main(
                ["--root", root, "find", "--epic", "github-119", "--child", "133"]
            ),
            1,
        )
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result="ready_pr",
        )
        self.assertEqual(
            LEDGER.main(
                ["--root", root, "find", "--epic", "github-119", "--child", "133"]
            ),
            0,
        )

    def test_cli_record_rejects_non_object_evidence(self) -> None:
        with self.assertRaises(ValueError):
            LEDGER._parse_evidence("[1, 2, 3]")


if __name__ == "__main__":
    unittest.main()
