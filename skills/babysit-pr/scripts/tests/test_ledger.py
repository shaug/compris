"""Skill-specific tests for babysit-pr's ledger wrapper.

Generic ledger mechanics (workspace derivation/self-exclusion, append-only
I/O, malformed-line tolerance, the action-scoped dedup guard) are exercised
once against arbitrary parameters in `ledger/scripts/tests/test_core.py` —
see that file's own module docstring for why. This file covers only what is
genuinely specific to this skill: `unit_key_for`'s repo+PR composition and
collision disambiguation, this skill's own `deferred`-excluded disposition
vocabulary and its actual `action_filter` predicate, the retry-count and
watcher-state-reconciliation helpers that have no core equivalent, and the
CLI wiring that proves the wrapper actually delegates to the bundled core
under this skill's real flag names.
"""

from __future__ import annotations

import hashlib
import importlib.util
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


def _expected_digest(repo_normalized: str) -> str:
    return hashlib.sha256(repo_normalized.encode("utf-8")).hexdigest()[:8]


class UnitKeyTests(unittest.TestCase):
    def test_unit_key_lowercases_repo(self) -> None:
        digest = _expected_digest("example/project")
        self.assertEqual(
            LEDGER.unit_key_for("Example/Project", 482),
            f"example/project#{digest}#482",
        )

    def test_slugify_produces_safe_directory_name(self) -> None:
        digest = _expected_digest("example/project")
        self.assertEqual(
            LEDGER.slugify(LEDGER.unit_key_for("Example/Project", 482)),
            f"example-project-{digest}-482",
        )

    def test_unit_key_digest_disambiguates_slash_boundary_collision(self) -> None:
        # Without the digest, `octocat/hello-world#482` and
        # `octocat-hello/world#482` would both slugify to
        # `octocat-hello-world-482`, silently merging two distinct repos'
        # workspaces onto one ledger file.
        first = LEDGER.slugify(LEDGER.unit_key_for("octocat/hello-world", 482))
        second = LEDGER.slugify(LEDGER.unit_key_for("octocat-hello/world", 482))
        self.assertNotEqual(first, second)

    def test_workspace_lives_under_the_skills_own_dirname(self) -> None:
        directory = LEDGER.workspace_dir(Path("/tmp/root"), "example/project", 482)
        self.assertEqual(directory.parent.name, ".babysit-pr")


class DispositionVocabularyTests(TempRootTestCase):
    def test_already_dispositioned_false_for_deferred(self) -> None:
        # A deferred finding is preserved, not resolved: recovery must never
        # treat it as done and must still surface it as outstanding. This is
        # this skill's own disposition vocabulary, not a generic core concept.
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
        # Proves the wrapper's actual action_filter predicate
        # (`action == "feedback_disposition"`) is wired correctly: a `retry`
        # entry happens to share an item_id space in principle, but only
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

    def test_reconcile_uses_latest_disposition_not_history_existence(self) -> None:
        # An item fixed, then later reopened (a regression) and deferred,
        # must report as still-open — an existential OR across the item's
        # full history would incorrectly report it as closed because a
        # *prior* entry was once "fixed".
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="c",
            action="feedback_disposition",
            terminal_result="fixed",
        )
        LEDGER.record_entry(
            self.root,
            "example/project",
            482,
            item_id="c",
            action="feedback_disposition",
            terminal_result="deferred",
        )
        result = LEDGER.read_ledger(self.root, "example/project", 482)
        report = LEDGER.reconcile_with_watcher_state(result.entries, {})
        self.assertNotIn("c", report["dispositioned_feedback_ids"])
        # Sanity: reconcile's set matches already_dispositioned's own verdict.
        self.assertIsNone(LEDGER.already_dispositioned(result.entries, "c"))

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
