from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "ledger.py"
MODULE_SPEC = importlib.util.spec_from_file_location("babysit_pr_ledger", MODULE_PATH)
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
    def test_unit_key_lowercases_repo(self) -> None:
        self.assertEqual(
            LEDGER.unit_key_for("Example/Project", 482), "example/project#482"
        )

    def test_slugify_produces_safe_directory_name(self) -> None:
        self.assertEqual(
            LEDGER.slugify(LEDGER.unit_key_for("Example/Project", 482)),
            "example-project-482",
        )


class WorkspaceTests(TempRootTestCase):
    def test_ensure_workspace_creates_self_excluding_gitignore(self) -> None:
        directory = LEDGER.ensure_workspace(self.root, "example/project", 482)
        self.assertTrue(directory.is_dir())
        self.assertEqual((directory / ".gitignore").read_text(encoding="utf-8"), "*\n")

    def test_distinct_prs_get_distinct_workspaces(self) -> None:
        first = LEDGER.workspace_dir(self.root, "example/project", 482)
        second = LEDGER.workspace_dir(self.root, "example/project", 483)
        self.assertNotEqual(first, second)

    def test_distinct_repos_same_pr_number_get_distinct_workspaces(self) -> None:
        first = LEDGER.workspace_dir(self.root, "example/project", 482)
        second = LEDGER.workspace_dir(self.root, "other/project", 482)
        self.assertNotEqual(first, second)


class WriteTests(TempRootTestCase):
    def test_record_session_start_writes_one_line(self) -> None:
        record = LEDGER.record_session_start(
            self.root, "example/project", 482, session_id="s1"
        )
        lines = (
            LEDGER.ledger_path(self.root, "example/project", 482)
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), record)

    def test_record_entry_for_feedback_disposition(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="review-comment-9001",
            action="feedback_disposition",
            terminal_result="fixed",
            head_sha="head-1",
            evidence={"disposition": "fixed"},
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0]["item_id"], "review-comment-9001")

    def test_record_entry_for_retry_keyed_by_head_sha(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="head-1",
            action="retry",
            terminal_result="rerun",
            head_sha="head-1",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertEqual(result.entries[0]["action"], "retry")
        self.assertEqual(result.entries[0]["head_sha"], "head-1")


class ReadTests(TempRootTestCase):
    def test_read_empty_ledger(self) -> None:
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertEqual(result.sessions, [])
        self.assertEqual(result.entries, [])

    def test_read_skips_malformed_line(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="a",
            action="feedback_disposition",
        )
        path = LEDGER.ledger_path(self.root, "example/project", 482)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{broken\n")
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.skipped_lines, [2])


class RecoveryTests(TempRootTestCase):
    def test_already_dispositioned_true_for_fixed(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="review-comment-9001",
            action="feedback_disposition",
            terminal_result="fixed",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertIsNotNone(
            LEDGER.already_dispositioned(result.entries, "review-comment-9001")
        )

    def test_already_dispositioned_false_for_deferred(self) -> None:
        # A deferred finding is preserved, not resolved: recovery must never
        # treat it as done and must still surface it as outstanding.
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="review-comment-9001",
            action="feedback_disposition",
            terminal_result="deferred",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertIsNone(
            LEDGER.already_dispositioned(result.entries, "review-comment-9001")
        )

    def test_already_dispositioned_ignores_non_disposition_actions(self) -> None:
        # A retry entry happens to share an item_id space in principle; only
        # feedback_disposition entries may satisfy the disposition guard.
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="review-comment-9001",
            action="retry",
            terminal_result="fixed",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertIsNone(
            LEDGER.already_dispositioned(result.entries, "review-comment-9001")
        )

    def test_already_dispositioned_none_when_never_recorded(self) -> None:
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertIsNone(LEDGER.already_dispositioned(result.entries, "unknown"))


class RetryCountTests(TempRootTestCase):
    def test_recorded_retry_counts_groups_by_head_sha(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="head-1",
            action="retry",
            head_sha="head-1",
        )
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="head-1",
            action="retry",
            head_sha="head-1",
        )
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="head-2",
            action="retry",
            head_sha="head-2",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        counts = LEDGER.recorded_retry_counts(result.entries)
        self.assertEqual(counts, {"head-1": 2, "head-2": 1})

    def test_recorded_retry_counts_ignores_other_actions(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="a",
            action="feedback_disposition",
            head_sha="head-1",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        self.assertEqual(LEDGER.recorded_retry_counts(result.entries), {})


class ReconcileTests(TempRootTestCase):
    def test_reconcile_reports_no_mismatch_when_watcher_matches_or_exceeds(
        self,
    ) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="head-1",
            action="retry",
            head_sha="head-1",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        report = LEDGER.reconcile_with_watcher_state(
            result.entries, {"retries_by_sha": {"head-1": 1}}
        )
        self.assertEqual(report["retry_mismatches"], {})

    def test_reconcile_flags_retry_the_watcher_never_recorded(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="head-1",
            action="retry",
            head_sha="head-1",
        )
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="head-1",
            action="retry",
            head_sha="head-1",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        report = LEDGER.reconcile_with_watcher_state(
            result.entries, {"retries_by_sha": {"head-1": 1}}
        )
        self.assertEqual(
            report["retry_mismatches"],
            {"head-1": {"ledger_recorded": 2, "watcher_recorded": 1}},
        )

    def test_reconcile_handles_missing_watcher_state(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="head-1",
            action="retry",
            head_sha="head-1",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        report = LEDGER.reconcile_with_watcher_state(result.entries, None)
        self.assertEqual(
            report["retry_mismatches"],
            {"head-1": {"ledger_recorded": 1, "watcher_recorded": 0}},
        )

    def test_reconcile_reports_dispositioned_feedback_ids(self) -> None:
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="a",
            action="feedback_disposition",
            terminal_result="fixed",
        )
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="b",
            action="feedback_disposition",
            terminal_result="deferred",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        report = LEDGER.reconcile_with_watcher_state(result.entries, {})
        self.assertEqual(report["dispositioned_feedback_ids"], ["a"])

    def test_load_watcher_state_uses_gh_pr_watch_default_path(self) -> None:
        fake_watcher = mock.Mock()
        fake_watcher.default_state_file_for.return_value = Path(
            "/tmp/does-not-exist.json"
        )
        fake_watcher.load_state.return_value = (
            {"retries_by_sha": {"head-1": 3}},
            False,
        )
        with mock.patch.object(
            LEDGER, "_load_watcher_module", return_value=fake_watcher
        ):
            state = LEDGER.load_watcher_state("example/project", 482)
        fake_watcher.default_state_file_for.assert_called_once_with(
            {"repo": "example/project", "number": 482}
        )
        self.assertEqual(state, {"retries_by_sha": {"head-1": 3}})


class CliTests(TempRootTestCase):
    def test_cli_round_trip(self) -> None:
        root = str(self.root)
        self.assertEqual(
            LEDGER.main(
                [
                    "--root",
                    root,
                    "session-start",
                    "--repo",
                    "example/project",
                    "--pr",
                    "482",
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
                    "--repo",
                    "example/project",
                    "--pr",
                    "482",
                    "--item",
                    "review-comment-9001",
                    "--action",
                    "feedback_disposition",
                    "--terminal-result",
                    "fixed",
                    "--head-sha",
                    "head-1",
                ]
            ),
            0,
        )
        self.assertEqual(
            LEDGER.main(
                [
                    "--root",
                    root,
                    "find",
                    "--repo",
                    "example/project",
                    "--pr",
                    "482",
                    "--item",
                    "review-comment-9001",
                ]
            ),
            0,
        )
        self.assertEqual(
            LEDGER.main(
                [
                    "--root",
                    root,
                    "find",
                    "--repo",
                    "example/project",
                    "--pr",
                    "482",
                    "--item",
                    "unknown",
                ]
            ),
            1,
        )

    def test_cli_reconcile_uses_live_watcher_module(self) -> None:
        root = str(self.root)
        LEDGER.main(
            [
                "--root",
                root,
                "record",
                "--repo",
                "example/project",
                "--pr",
                "482",
                "--item",
                "head-1",
                "--action",
                "retry",
                "--head-sha",
                "head-1",
            ]
        )
        fake_watcher = mock.Mock()
        fake_watcher.default_state_file_for.return_value = Path(
            "/tmp/does-not-exist.json"
        )
        fake_watcher.load_state.return_value = ({"retries_by_sha": {}}, False)
        with mock.patch.object(
            LEDGER, "_load_watcher_module", return_value=fake_watcher
        ):
            exit_code = LEDGER.main(
                [
                    "--root",
                    root,
                    "reconcile",
                    "--repo",
                    "example/project",
                    "--pr",
                    "482",
                ]
            )
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
