from __future__ import annotations

import importlib.util
import json
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


class SlugifyTests(unittest.TestCase):
    def test_slugifies_mixed_case_and_punctuation(self) -> None:
        self.assertEqual(LEDGER.slugify("GitHub-119"), "github-119")

    def test_slugifies_tracker_prefixed_identity(self) -> None:
        self.assertEqual(LEDGER.slugify("Linear ENG-119"), "linear-eng-119")

    def test_rejects_empty_slug(self) -> None:
        with self.assertRaises(ValueError):
            LEDGER.slugify("   ")


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


class WorkspaceTests(TempRootTestCase):
    def test_ensure_workspace_creates_self_excluding_gitignore(self) -> None:
        directory = LEDGER.ensure_workspace(self.root, "github-119")
        self.assertTrue(directory.is_dir())
        gitignore = directory / ".gitignore"
        self.assertTrue(gitignore.exists())
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "*\n")

    def test_ensure_workspace_is_idempotent(self) -> None:
        LEDGER.ensure_workspace(self.root, "github-119")
        (LEDGER.workspace_dir(self.root, "github-119") / ".gitignore").write_text(
            "custom\n", encoding="utf-8"
        )
        LEDGER.ensure_workspace(self.root, "github-119")
        gitignore = LEDGER.workspace_dir(self.root, "github-119") / ".gitignore"
        # A pre-existing .gitignore is never clobbered by a second ensure call.
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "custom\n")

    def test_distinct_epics_get_distinct_workspaces(self) -> None:
        first = LEDGER.workspace_dir(self.root, "github-119")
        second = LEDGER.workspace_dir(self.root, "github-120")
        self.assertNotEqual(first, second)


class WriteTests(TempRootTestCase):
    def test_record_session_start_writes_one_line(self) -> None:
        record = LEDGER.record_session_start(self.root, "github-119", session_id="s1")
        path = LEDGER.ledger_path(self.root, "github-119")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), record)
        self.assertEqual(record["kind"], "session")
        self.assertEqual(record["session_id"], "s1")

    def test_record_entry_appends_without_truncating(self) -> None:
        LEDGER.record_session_start(self.root, "github-119", session_id="s1")
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result="ready_pr",
            head_sha="abc123",
            evidence={"pr": 181},
        )
        path = LEDGER.ledger_path(self.root, "github-119")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        second = json.loads(lines[1])
        self.assertEqual(second["kind"], "entry")
        self.assertEqual(second["child_id"], "133")
        self.assertEqual(second["terminal_result"], "ready_pr")
        self.assertEqual(second["evidence"], {"pr": 181})

    def test_record_entry_coerces_child_id_to_string(self) -> None:
        record = LEDGER.record_entry(
            self.root, "github-119", child_id=133, action="child_dispatch"
        )
        self.assertEqual(record["child_id"], "133")
        self.assertIsInstance(record["child_id"], str)


class ReadTests(TempRootTestCase):
    def test_read_empty_ledger_returns_empty_result(self) -> None:
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertEqual(result.sessions, [])
        self.assertEqual(result.entries, [])
        self.assertEqual(result.skipped_lines, [])

    def test_read_round_trips_sessions_and_entries(self) -> None:
        LEDGER.record_session_start(self.root, "github-119", session_id="s1")
        LEDGER.record_entry(
            self.root, "github-119", child_id="133", action="child_dispatch"
        )
        LEDGER.record_entry(
            self.root, "github-119", child_id="134", action="child_dispatch"
        )
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertEqual(len(result.sessions), 1)
        self.assertEqual(len(result.entries), 2)
        self.assertEqual(result.skipped_lines, [])

    def test_read_skips_malformed_trailing_line_without_losing_prior_lines(
        self,
    ) -> None:
        LEDGER.record_session_start(self.root, "github-119", session_id="s1")
        LEDGER.record_entry(
            self.root, "github-119", child_id="133", action="child_dispatch"
        )
        path = LEDGER.ledger_path(self.root, "github-119")
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"kind": "entry", "child_id": "134"' + "\n")  # truncated JSON
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertEqual(len(result.sessions), 1)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.skipped_lines, [3])

    def test_read_skips_unknown_kind(self) -> None:
        path = LEDGER.ledger_path(self.root, "github-119")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"kind": "mystery"}\n', encoding="utf-8")
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertEqual(result.entries, [])
        self.assertEqual(result.skipped_lines, [1])


class RecoveryTests(TempRootTestCase):
    def test_latest_entry_returns_most_recent_for_child(self) -> None:
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result=None,
        )
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result="ready_pr",
            head_sha="head-2",
        )
        result = LEDGER.read_ledger(self.root, "github-119")
        latest = LEDGER.latest_entry(result.entries, "133")
        self.assertEqual(latest["terminal_result"], "ready_pr")
        self.assertEqual(latest["head_sha"], "head-2")

    def test_latest_entry_returns_none_for_unknown_child(self) -> None:
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertIsNone(LEDGER.latest_entry(result.entries, "999"))

    def test_already_recorded_complete_true_for_merged(self) -> None:
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result="merged",
        )
        result = LEDGER.read_ledger(self.root, "github-119")
        entry = LEDGER.already_recorded_complete(result.entries, "133")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["terminal_result"], "merged")

    def test_already_recorded_complete_false_for_blocked(self) -> None:
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

    def test_already_recorded_complete_none_when_never_recorded(self) -> None:
        result = LEDGER.read_ledger(self.root, "github-119")
        self.assertIsNone(LEDGER.already_recorded_complete(result.entries, "133"))

    def test_already_recorded_complete_uses_latest_not_first(self) -> None:
        # A first blocked attempt followed by a later completed retry must
        # report the current (completed) state, not the stale blocked one.
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result="blocked",
        )
        LEDGER.record_entry(
            self.root,
            "github-119",
            child_id="133",
            action="child_dispatch",
            terminal_result="ready_pr",
            head_sha="head-3",
        )
        result = LEDGER.read_ledger(self.root, "github-119")
        entry = LEDGER.already_recorded_complete(result.entries, "133")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["head_sha"], "head-3")


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
