from __future__ import annotations

import importlib.util
import json
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


class SlugifyTests(unittest.TestCase):
    def test_slugifies_branch_with_slash(self) -> None:
        self.assertEqual(
            LEDGER.slugify("feature/cloud-host-migration"),
            "feature-cloud-host-migration",
        )

    def test_rejects_empty_slug(self) -> None:
        with self.assertRaises(ValueError):
            LEDGER.slugify("///")


class WorkspaceTests(TempRootTestCase):
    def test_ensure_workspace_creates_self_excluding_gitignore(self) -> None:
        directory = LEDGER.ensure_workspace(self.root, "feature/x")
        self.assertTrue(directory.is_dir())
        gitignore = directory / ".gitignore"
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "*\n")

    def test_ensure_workspace_lives_under_carve_changesets_dirname(self) -> None:
        directory = LEDGER.workspace_dir(self.root, "feature/x")
        self.assertEqual(directory.parent.name, ".carve-changesets")

    def test_distinct_source_branches_get_distinct_workspaces(self) -> None:
        first = LEDGER.workspace_dir(self.root, "feature/x")
        second = LEDGER.workspace_dir(self.root, "feature/y")
        self.assertNotEqual(first, second)


class WriteTests(TempRootTestCase):
    def test_record_session_start_writes_one_line(self) -> None:
        record = LEDGER.record_session_start(self.root, "feature/x", session_id="s1")
        lines = (
            LEDGER.ledger_path(self.root, "feature/x")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), record)

    def test_record_entry_appends_per_changeset(self) -> None:
        LEDGER.record_session_start(self.root, "feature/x", session_id="s1")
        LEDGER.record_entry(
            self.root,
            "feature/x",
            changeset_slug="rename-config-types",
            action="review_fix_loop",
            terminal_result="converged",
            head_sha="head-1",
        )
        lines = (
            LEDGER.ledger_path(self.root, "feature/x")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(len(lines), 2)
        entry = json.loads(lines[1])
        self.assertEqual(entry["changeset_slug"], "rename-config-types")
        self.assertEqual(entry["terminal_result"], "converged")


class ReadTests(TempRootTestCase):
    def test_read_empty_ledger(self) -> None:
        result = LEDGER.read_ledger(self.root, "feature/x")
        self.assertEqual(result.sessions, [])
        self.assertEqual(result.entries, [])

    def test_read_skips_malformed_line(self) -> None:
        LEDGER.record_entry(
            self.root, "feature/x", changeset_slug="a", action="review_fix_loop"
        )
        path = LEDGER.ledger_path(self.root, "feature/x")
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{not json\n")
        result = LEDGER.read_ledger(self.root, "feature/x")
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.skipped_lines, [2])


class RecoveryTests(TempRootTestCase):
    def test_already_recorded_complete_true_for_converged(self) -> None:
        LEDGER.record_entry(
            self.root,
            "feature/x",
            changeset_slug="rename-config-types",
            action="review_fix_loop",
            terminal_result="converged",
        )
        result = LEDGER.read_ledger(self.root, "feature/x")
        entry = LEDGER.already_recorded_complete(result.entries, "rename-config-types")
        self.assertIsNotNone(entry)

    def test_already_recorded_complete_false_for_blocked(self) -> None:
        LEDGER.record_entry(
            self.root,
            "feature/x",
            changeset_slug="rename-config-types",
            action="review_fix_loop",
            terminal_result="blocked",
        )
        result = LEDGER.read_ledger(self.root, "feature/x")
        self.assertIsNone(
            LEDGER.already_recorded_complete(result.entries, "rename-config-types")
        )

    def test_already_recorded_complete_scoped_per_changeset(self) -> None:
        LEDGER.record_entry(
            self.root,
            "feature/x",
            changeset_slug="a",
            action="review_fix_loop",
            terminal_result="converged",
        )
        result = LEDGER.read_ledger(self.root, "feature/x")
        self.assertIsNone(LEDGER.already_recorded_complete(result.entries, "b"))

    def test_latest_entry_prefers_most_recent(self) -> None:
        LEDGER.record_entry(
            self.root,
            "feature/x",
            changeset_slug="a",
            action="review_fix_loop",
            terminal_result="blocked",
        )
        LEDGER.record_entry(
            self.root,
            "feature/x",
            changeset_slug="a",
            action="review_fix_loop",
            terminal_result="converged",
            head_sha="head-2",
        )
        result = LEDGER.read_ledger(self.root, "feature/x")
        entry = LEDGER.already_recorded_complete(result.entries, "a")
        self.assertEqual(entry["head_sha"], "head-2")


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


if __name__ == "__main__":
    unittest.main()
