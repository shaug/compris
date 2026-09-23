from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from metadata import ChangesetMetadata, stamp_commit_message
from rehydrate import adopt_legacy_chain
from validate import validate_live_chain


class LiveValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo, _, _ = helpers.init_repo(self.temp_dir)
        helpers.run(self.repo, "git", "checkout", "feature/report")
        (self.repo / "second.txt").write_text("second source part\n")
        (self.repo / "third.txt").write_text("third source part\n")
        helpers.run(self.repo, "git", "add", "second.txt", "third.txt")
        self.source_sha = helpers.commit(self.repo, "complete source result")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _stamp(self, index: int, *, detail: str | None = None) -> str:
        message = f"feat: changeset {index}"
        if detail is not None:
            message += f"\n\n{detail}"
        return stamp_commit_message(
            message,
            ChangesetMetadata(
                slug=f"part-{index}",
                index=index,
                source_branch="feature/report",
                source_sha=self.source_sha,
            ),
        )

    def _materialize_equivalent_chain(self) -> dict[int, str]:
        heads: dict[int, str] = {}
        previous = "main"
        files = ("source.txt", "second.txt", "third.txt")
        for index, path in enumerate(files, start=1):
            branch = f"feature/report-{index}"
            helpers.run(self.repo, "git", "checkout", "-b", branch, previous)
            content = helpers.run(self.repo, "git", "show", f"feature/report:{path}")
            (self.repo / path).write_text(content + "\n")
            helpers.run(self.repo, "git", "add", path)
            heads[index] = helpers.commit(self.repo, self._stamp(index))
            previous = branch
        return heads

    def _rehydrate(self):
        return adopt_legacy_chain(
            source_branch="feature/report", base_branch="main", cwd=self.repo
        )

    def test_issue_32_legitimate_propagation_has_no_stale_drift_warning(self) -> None:
        heads = self._materialize_equivalent_chain()
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        amended_message = self._stamp(2, detail="Refresh the propagated commit.")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=amended_message,
        )
        propagated_second = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        self.assertNotEqual(heads[2], propagated_second)
        helpers.run(self.repo, "git", "checkout", "feature/report-3")
        helpers.run(
            self.repo,
            "git",
            "rebase",
            "--onto",
            propagated_second,
            heads[2],
            "feature/report-3",
        )
        propagated_third = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        self.assertNotEqual(heads[3], propagated_third)

        result = validate_live_chain(self._rehydrate(), cwd=self.repo)

        self.assertTrue(result.valid)
        self.assertEqual("unchanged", result.source_status)
        self.assertEqual((), result.diagnostics)

    def test_issue_32_rewritten_mid_chain_branch_breaks_live_ancestry(self) -> None:
        self._materialize_equivalent_chain()
        chain = self._rehydrate()
        helpers.run(self.repo, "git", "checkout", "-b", "replacement", "main")
        for path in ("source.txt", "second.txt"):
            content = helpers.run(self.repo, "git", "show", f"feature/report:{path}")
            (self.repo / path).write_text(content + "\n")
        helpers.run(self.repo, "git", "add", "source.txt", "second.txt")
        replacement = helpers.commit(self.repo, self._stamp(2))
        helpers.run(
            self.repo,
            "git",
            "update-ref",
            "refs/heads/feature/report-2",
            replacement,
        )

        result = validate_live_chain(chain, cwd=self.repo)

        self.assertFalse(result.valid)
        self.assertIn("changeset_ref_moved", {item.code for item in result.errors})
        self.assertIn(
            "predecessor_ancestry_broken", {item.code for item in result.errors}
        )

    def test_non_equivalent_chain_tip_is_rejected(self) -> None:
        self._materialize_equivalent_chain()
        helpers.run(self.repo, "git", "checkout", "feature/report-3")
        (self.repo / "extra.txt").write_text("not in source\n")
        helpers.run(self.repo, "git", "add", "extra.txt")
        helpers.commit(self.repo, self._stamp(3, detail="Rewrite the chain tip."))

        result = validate_live_chain(self._rehydrate(), cwd=self.repo)

        self.assertFalse(result.valid)
        self.assertIn(
            "source_equivalence_mismatch", {item.code for item in result.errors}
        )

    def test_issue_32_source_advance_is_distinct_from_history_mismatch(self) -> None:
        self._materialize_equivalent_chain()
        helpers.run(self.repo, "git", "checkout", "feature/report")
        (self.repo / "later.txt").write_text("later source work\n")
        helpers.run(self.repo, "git", "add", "later.txt")
        helpers.commit(self.repo, "feat: advance source")

        advanced = validate_live_chain(self._rehydrate(), cwd=self.repo)

        self.assertTrue(advanced.valid)
        self.assertEqual("advanced", advanced.source_status)
        self.assertEqual(["source_advanced"], [item.code for item in advanced.warnings])

        helpers.run(self.repo, "git", "checkout", "-b", "alternate-source", "main")
        (self.repo / "other.txt").write_text("different source\n")
        helpers.run(self.repo, "git", "add", "other.txt")
        different_head = helpers.commit(self.repo, "feat: different source")
        helpers.run(
            self.repo,
            "git",
            "update-ref",
            "refs/heads/feature/report",
            different_head,
        )

        different = validate_live_chain(self._rehydrate(), cwd=self.repo)

        self.assertFalse(different.valid)
        self.assertEqual("different", different.source_status)
        self.assertIn(
            "source_history_mismatch", {item.code for item in different.errors}
        )

    def test_source_ancestry_command_failure_is_not_reported_as_divergence(
        self,
    ) -> None:
        self._materialize_equivalent_chain()
        helpers.run(self.repo, "git", "checkout", "feature/report")
        (self.repo / "later.txt").write_text("later source work\n")
        helpers.run(self.repo, "git", "add", "later.txt")
        helpers.commit(self.repo, "feat: advance source")

        with mock.patch("validate._is_ancestor", side_effect=[True, True, True, None]):
            result = validate_live_chain(self._rehydrate(), cwd=self.repo)

        self.assertFalse(result.valid)
        self.assertEqual("unavailable", result.source_status)
        self.assertIn(
            "source_ancestry_check_failed", {item.code for item in result.errors}
        )
        self.assertNotIn(
            "source_history_mismatch", {item.code for item in result.errors}
        )


if __name__ == "__main__":
    unittest.main()
