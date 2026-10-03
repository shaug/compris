from __future__ import annotations

import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import helpers
import validate as validate_mod
from metadata import ChangesetMetadata, SourceIdentity, stamp_commit_message
from native_stack import NativeLayer, NativePullRequest, NativeStackSnapshot
from rehydrate import (
    Chain,
    ChangesetRecord,
    PullRequestRecord,
    adopt_legacy_chain,
    rehydrate_chain,
)
from validate import validate_live_chain


class LiveValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo, self.bare, _ = helpers.init_repo(self.temp_dir)
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

    def _materialize_native_single_layer(self) -> tuple[ChangesetMetadata, str]:
        helpers.run(self.repo, "git", "push", "origin", "feature/report")
        helpers.run(self.repo, "git", "checkout", "-b", "feature/report-1", "main")
        for path in ("source.txt", "second.txt", "third.txt"):
            content = helpers.run(self.repo, "git", "show", f"feature/report:{path}")
            (self.repo / path).write_text(content + "\n")
        helpers.run(self.repo, "git", "add", "source.txt", "second.txt", "third.txt")
        metadata = ChangesetMetadata(
            slug="report",
            source_lineage=(
                SourceIdentity("origin", "feature/report", self.source_sha),
            ),
        )
        head = helpers.commit(self.repo, stamp_commit_message("feat: report", metadata))
        helpers.run(self.repo, "git", "push", "-u", "origin", "feature/report-1")
        return metadata, head

    def _native_single_layer_chain(
        self,
        metadata: ChangesetMetadata,
        head: str,
        *,
        merge_sha: str | None = None,
        pr_state: str = "MERGED",
    ) -> Chain:
        return Chain(
            base_branch="main",
            source_branch="feature/report",
            source_sha=self.source_sha,
            root_source_sha=self.source_sha,
            source_lineage=metadata.source_lineage,
            changesets=(
                ChangesetRecord(
                    metadata=metadata,
                    branch="feature/report-1",
                    head=head,
                    base="main",
                    pr_number=101,
                    pr_state=pr_state,
                    topology_position=1,
                    pr_merge_sha=merge_sha,
                ),
            ),
            native_topology=True,
        )

    def _merge_single_layer_to_local_main(self) -> tuple[str, str]:
        prior_main = helpers.run(self.repo, "git", "rev-parse", "main")
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(
            self.repo,
            "git",
            "merge",
            "--no-ff",
            "--no-edit",
            "feature/report-1",
        )
        return prior_main, helpers.run(self.repo, "git", "rev-parse", "main")

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

    def test_fully_merged_chain_requires_the_result_on_current_trunk(self) -> None:
        metadata, head = self._materialize_native_single_layer()
        chain = self._native_single_layer_chain(metadata, head)

        result = validate_live_chain(chain, cwd=self.repo)

        self.assertFalse(result.valid)
        self.assertIn(
            "merged_prefix_missing_from_base", {item.code for item in result.errors}
        )
        self.assertIn(
            "source_equivalence_mismatch", {item.code for item in result.errors}
        )

    def test_live_validation_rejects_ahead_local_trunk(self) -> None:
        metadata, head = self._materialize_native_single_layer()
        _prior_main, merge_sha = self._merge_single_layer_to_local_main()
        chain = self._native_single_layer_chain(metadata, head, merge_sha=merge_sha)

        result = validate_live_chain(chain, cwd=self.repo)

        self.assertFalse(result.valid)
        self.assertIn(
            "merged_prefix_missing_from_base", {item.code for item in result.errors}
        )

    def test_live_validation_accepts_current_remote_over_stale_local_trunk(
        self,
    ) -> None:
        metadata, head = self._materialize_native_single_layer()
        prior_main, merge_sha = self._merge_single_layer_to_local_main()
        helpers.run(self.repo, "git", "push", "origin", "main")
        helpers.run(self.repo, "git", "checkout", "feature/report-1")
        helpers.run(self.repo, "git", "update-ref", "refs/heads/main", prior_main)
        chain = self._native_single_layer_chain(metadata, head, merge_sha=merge_sha)

        result = validate_live_chain(chain, cwd=self.repo)

        self.assertTrue(result.valid, result.diagnostics)

    def test_open_chain_rejects_stale_local_trunk_over_current_remote(self) -> None:
        metadata, head = self._materialize_native_single_layer()
        prior_main = helpers.run(self.repo, "git", "rev-parse", "main")
        helpers.run(self.repo, "git", "checkout", "main")
        (self.repo / "remote-only.txt").write_text("remote base\n")
        helpers.run(self.repo, "git", "add", "remote-only.txt")
        helpers.commit(self.repo, "advance remote base")
        helpers.run(self.repo, "git", "push", "origin", "main")
        helpers.run(self.repo, "git", "checkout", "feature/report-1")
        helpers.run(self.repo, "git", "update-ref", "refs/heads/main", prior_main)
        chain = self._native_single_layer_chain(metadata, head, pr_state="OPEN")

        result = validate_live_chain(chain, cwd=self.repo)

        self.assertFalse(result.valid)
        self.assertIn(
            "predecessor_ancestry_broken", {item.code for item in result.errors}
        )

    def test_open_chain_accepts_remote_trunk_over_ahead_local_trunk(self) -> None:
        metadata, head = self._materialize_native_single_layer()
        helpers.run(self.repo, "git", "checkout", "main")
        (self.repo / "local-only.txt").write_text("local base\n")
        helpers.run(self.repo, "git", "add", "local-only.txt")
        helpers.commit(self.repo, "advance local base")
        helpers.run(self.repo, "git", "checkout", "feature/report-1")
        chain = self._native_single_layer_chain(metadata, head, pr_state="OPEN")

        result = validate_live_chain(chain, cwd=self.repo)

        self.assertTrue(result.valid, result.diagnostics)

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

    def test_native_single_source_requires_the_stamped_remote_ref(self) -> None:
        helpers.run(self.repo, "git", "checkout", "-b", "feature/report-1", "main")
        for path in ("source.txt", "second.txt", "third.txt"):
            content = helpers.run(self.repo, "git", "show", f"feature/report:{path}")
            (self.repo / path).write_text(content + "\n")
        helpers.run(self.repo, "git", "add", "source.txt", "second.txt", "third.txt")
        metadata = ChangesetMetadata(
            slug="report",
            source_lineage=(
                SourceIdentity("upstream", "feature/report", self.source_sha),
            ),
        )
        head = helpers.commit(self.repo, stamp_commit_message("feat: report", metadata))
        chain = rehydrate_chain(
            source_branch="feature/report",
            remote="upstream",
            native_snapshot=NativeStackSnapshot(
                trunk_branch="main",
                trunk_head=helpers.run(self.repo, "git", "rev-parse", "main"),
                current_branch="feature/report-1",
                layers=(
                    NativeLayer(
                        branch="feature/report-1",
                        head=head,
                        base=helpers.run(self.repo, "git", "rev-parse", "main"),
                        merged=False,
                        queued=False,
                        needs_rebase=False,
                        pull_request=None,
                    ),
                ),
            ),
            cwd=self.repo,
            pull_requests=(),
        )

        result = validate_live_chain(chain, cwd=self.repo, remote="upstream")

        self.assertFalse(result.valid)
        self.assertIn(
            "source_lineage_ref_missing", {item.code for item in result.errors}
        )

    def test_native_single_source_rejects_a_moved_stamped_remote_ref(self) -> None:
        helpers.run(self.repo, "git", "remote", "add", "upstream", str(self.bare))
        helpers.run(self.repo, "git", "fetch", "upstream")
        helpers.run(self.repo, "git", "checkout", "feature/report")
        (self.repo / "later.txt").write_text("later source work\n")
        helpers.run(self.repo, "git", "add", "later.txt")
        helpers.commit(self.repo, "feat: move source")
        helpers.run(self.repo, "git", "push", "upstream", "feature/report")

        helpers.run(self.repo, "git", "checkout", "-b", "feature/report-1", "main")
        for path in ("source.txt", "second.txt", "third.txt"):
            content = helpers.run(self.repo, "git", "show", f"{self.source_sha}:{path}")
            (self.repo / path).write_text(content + "\n")
        helpers.run(self.repo, "git", "add", "source.txt", "second.txt", "third.txt")
        metadata = ChangesetMetadata(
            slug="report",
            source_lineage=(
                SourceIdentity("upstream", "feature/report", self.source_sha),
            ),
        )
        head = helpers.commit(self.repo, stamp_commit_message("feat: report", metadata))
        chain = rehydrate_chain(
            source_branch="feature/report",
            remote="upstream",
            native_snapshot=NativeStackSnapshot(
                trunk_branch="main",
                trunk_head=helpers.run(self.repo, "git", "rev-parse", "main"),
                current_branch="feature/report-1",
                layers=(
                    NativeLayer(
                        branch="feature/report-1",
                        head=head,
                        base=helpers.run(self.repo, "git", "rev-parse", "main"),
                        merged=False,
                        queued=False,
                        needs_rebase=False,
                        pull_request=None,
                    ),
                ),
            ),
            cwd=self.repo,
        )

        result = validate_live_chain(chain, cwd=self.repo, remote="upstream")

        self.assertFalse(result.valid)
        self.assertIn("source_lineage_ref_moved", {item.code for item in result.errors})
        self.assertNotIn("source_advanced", {item.code for item in result.warnings})
        self.assertEqual("different", result.source_status)


class LiveEquivalenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo, self.bare, self.source_sha = helpers.init_repo(self.temp_dir)
        self.trunk = helpers.run(self.repo, "git", "rev-parse", "main")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _assert_byte_replay(self, before: bytes | None, after: bytes) -> None:
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(self.repo, "git", "config", "core.autocrlf", "false")
        path = self.repo / "bytes.txt"
        if before is not None:
            path.write_bytes(before)
            helpers.run(self.repo, "git", "add", "bytes.txt")
            helpers.commit(self.repo, "feat: byte-preserving baseline")
        trunk = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(self.repo, "git", "push", "origin", "main")
        helpers.run(self.repo, "git", "checkout", "-b", "bytes-source")
        path.write_bytes(after)
        helpers.run(self.repo, "git", "add", "bytes.txt")
        head = helpers.commit(self.repo, "feat: byte-preserving source")
        helpers.run(self.repo, "git", "push", "origin", "bytes-source")
        snapshot = NativeStackSnapshot(
            "main",
            trunk,
            "bytes-source",
            (NativeLayer("bytes-source", head, trunk, False, False, False, None),),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "bytes-source", head),
            cwd=self.repo,
        )

        self.assertTrue(result.valid, result.code)
        self.assertEqual(result.source_tree, result.reconstructed_tree)
        self.assertEqual(after, path.read_bytes())

    def test_equivalence_preserves_crlf_addition(self) -> None:
        self._assert_byte_replay(None, b"first\r\nsecond\r\n")

    def test_equivalence_preserves_crlf_modification(self) -> None:
        self._assert_byte_replay(b"first\r\nold\r\n", b"first\r\nnew\r\n")

    def test_equivalence_preserves_non_utf8_text(self) -> None:
        self._assert_byte_replay(b"old\xff\n", b"new\xfe\n")

    def test_equivalence_preserves_modified_blob_with_zero_diff_context(self) -> None:
        helpers.run(self.repo, "git", "config", "diff.context", "0")
        self._assert_byte_replay(b"first\nold\nlast\n", b"first\nnew\nlast\n")

    def test_equivalence_preserves_blob_with_whitespace_fixing_configured(self) -> None:
        helpers.run(self.repo, "git", "config", "apply.whitespace", "fix")
        self._assert_byte_replay(b"first\nold\nlast\n", b"first\nnew \nlast\n")

    def test_equivalence_preserves_gitlinks_under_submodule_display_configuration(
        self,
    ) -> None:
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(
            self.repo,
            "git",
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{self.trunk},child",
        )
        trunk = helpers.commit(self.repo, "baseline gitlink")
        helpers.run(self.repo, "git", "push", "origin", "main")
        helpers.run(self.repo, "git", "checkout", "-b", "gitlink-source")
        helpers.run(
            self.repo,
            "git",
            "update-index",
            "--cacheinfo",
            f"160000,{self.source_sha},child",
        )
        head = helpers.commit(self.repo, "changed gitlink")
        helpers.run(self.repo, "git", "push", "origin", "gitlink-source")
        snapshot = NativeStackSnapshot(
            "main",
            trunk,
            "gitlink-source",
            (NativeLayer("gitlink-source", head, trunk, False, False, False, None),),
        )
        for setting, value in (
            ("diff.submodule", "log"),
            ("diff.ignoreSubmodules", "all"),
        ):
            with self.subTest(setting=setting):
                helpers.run(self.repo, "git", "config", setting, value)
                try:
                    result = validate_mod.validate_live_equivalence(
                        snapshot=snapshot,
                        active_source=SourceIdentity("origin", "gitlink-source", head),
                        cwd=self.repo,
                    )
                finally:
                    helpers.run(self.repo, "git", "config", "--unset", setting)
                self.assertTrue(result.valid, result.code)
                self.assertEqual(result.source_tree, result.reconstructed_tree)

    def _layer(self, branch: str, base: str, path: str) -> NativeLayer:
        helpers.run(self.repo, "git", "checkout", "-b", branch, base)
        content = helpers.run(self.repo, "git", "show", f"feature/report:{path}")
        (self.repo / path).write_text(content + "\n")
        helpers.run(self.repo, "git", "add", path)
        head = helpers.commit(self.repo, f"feat: {branch}")
        return NativeLayer(
            branch=branch,
            head=head,
            base=helpers.run(self.repo, "git", "rev-parse", base),
            merged=False,
            queued=False,
            needs_rebase=False,
            pull_request=None,
        )

    def test_unmerged_suffix_reconstructs_source_from_exact_remote_trunk(self) -> None:
        first = self._layer("layer-one", "main", "source.txt")
        snapshot = NativeStackSnapshot("main", self.trunk, "layer-one", (first,))
        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            cwd=self.repo,
        )

        self.assertTrue(result.valid)
        self.assertEqual("equivalent", result.code)
        self.assertEqual((1,), result.open_suffix)
        self.assertEqual(
            "",
            helpers.run(
                self.repo,
                "git",
                "for-each-ref",
                "refs/carve-changesets/equivalence",
            ),
        )

    def test_equivalence_ignores_human_facing_diff_configuration(self) -> None:
        first = self._layer("layer-one", "main", "source.txt")
        snapshot = NativeStackSnapshot("main", self.trunk, "layer-one", (first,))
        (self.repo / ".git" / "info" / "attributes").write_text(
            "source.txt diff=display\n"
        )
        index_before = (self.repo / ".git" / "index").read_bytes()
        content_before = (self.repo / "source.txt").read_bytes()
        for setting, value in (
            ("diff.external", "true"),
            ("color.ui", "always"),
            ("diff.noprefix", "true"),
            ("diff.display.textconv", "true"),
        ):
            with self.subTest(setting=setting):
                helpers.run(self.repo, "git", "config", setting, value)
                try:
                    result = validate_mod.validate_live_equivalence(
                        snapshot=snapshot,
                        active_source=SourceIdentity(
                            "origin", "feature/report", self.source_sha
                        ),
                        cwd=self.repo,
                    )
                finally:
                    helpers.run(self.repo, "git", "config", "--unset", setting)

                self.assertEqual(
                    index_before, (self.repo / ".git" / "index").read_bytes()
                )
                self.assertEqual(
                    content_before, (self.repo / "source.txt").read_bytes()
                )
                self.assertEqual(
                    "",
                    helpers.run(
                        self.repo,
                        "git",
                        "for-each-ref",
                        "refs/carve-changesets/equivalence",
                    ),
                )
                self.assertTrue(result.valid, result.code)
                self.assertEqual(result.source_tree, result.reconstructed_tree)

    def test_equivalence_rejects_whitespace_normalized_false_match(self) -> None:
        first = self._layer("layer-one", "main", "source.txt")
        path = self.repo / "source.txt"
        path.write_text(path.read_text().rstrip() + " \n")
        helpers.run(self.repo, "git", "add", "source.txt")
        head = helpers.commit(self.repo, "different layer whitespace")
        snapshot = NativeStackSnapshot(
            "main", self.trunk, "layer-one", (replace(first, head=head),)
        )
        helpers.run(self.repo, "git", "config", "apply.whitespace", "fix")

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            cwd=self.repo,
        )

        self.assertFalse(result.valid)
        self.assertEqual("source_equivalence_mismatch", result.code)

    def test_merged_prefix_and_rebased_open_suffix_reconstruct_source(self) -> None:
        (self.repo / "second.txt").write_text("second source part\n")
        helpers.run(self.repo, "git", "add", "second.txt")
        self.source_sha = helpers.commit(self.repo, "complete source")
        helpers.run(self.repo, "git", "push", "origin", "feature/report")
        first = self._layer("layer-one", "main", "source.txt")
        self._layer("layer-two", "layer-one", "second.txt")
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(self.repo, "git", "merge", "--no-ff", "--no-edit", "layer-one")
        helpers.run(self.repo, "git", "push", "origin", "main")
        trunk = helpers.run(self.repo, "git", "rev-parse", "main")
        helpers.run(self.repo, "git", "checkout", "layer-two")
        helpers.run(self.repo, "git", "rebase", "--onto", "main", first.head)
        rebased = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        snapshot = NativeStackSnapshot(
            "main",
            trunk,
            "layer-two",
            (
                NativeLayer(
                    "layer-one",
                    first.head,
                    self.trunk,
                    True,
                    False,
                    False,
                    NativePullRequest(101, "https://example.test/101", "MERGED"),
                ),
                NativeLayer(
                    "layer-two",
                    rebased,
                    trunk,
                    False,
                    False,
                    False,
                    NativePullRequest(102, "https://example.test/102", "OPEN"),
                ),
            ),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            merged_prs={
                101: PullRequestRecord(
                    101,
                    "layer-one",
                    first.head,
                    "main",
                    "MERGED",
                    "",
                    merge_sha=trunk,
                )
            },
            cwd=self.repo,
        )

        self.assertTrue(result.valid)
        self.assertEqual((101,), result.merged_prefix)
        self.assertEqual((102,), result.open_suffix)

    def test_squash_landed_prefix_and_rebased_open_suffix_reconstruct_source(
        self,
    ) -> None:
        (self.repo / "second.txt").write_text("second source part\n")
        helpers.run(self.repo, "git", "add", "second.txt")
        self.source_sha = helpers.commit(self.repo, "complete source")
        helpers.run(self.repo, "git", "push", "origin", "feature/report")
        first = self._layer("layer-one", "main", "source.txt")
        self._layer("layer-two", "layer-one", "second.txt")
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(self.repo, "git", "merge", "--squash", "layer-one")
        landing = helpers.commit(self.repo, "squash first layer")
        helpers.run(self.repo, "git", "push", "origin", "main")
        helpers.run(self.repo, "git", "checkout", "layer-two")
        helpers.run(self.repo, "git", "rebase", "--onto", "main", first.head)
        rebased = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        snapshot = NativeStackSnapshot(
            "main",
            landing,
            "layer-two",
            (
                NativeLayer(
                    "layer-one",
                    first.head,
                    self.trunk,
                    True,
                    False,
                    False,
                    NativePullRequest(101, "https://example.test/101", "MERGED"),
                ),
                NativeLayer(
                    "layer-two",
                    rebased,
                    landing,
                    False,
                    False,
                    False,
                    NativePullRequest(102, "https://example.test/102", "OPEN"),
                ),
            ),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            merged_prs={
                101: PullRequestRecord(
                    101,
                    "layer-one",
                    first.head,
                    "main",
                    "MERGED",
                    "",
                    merge_sha=landing,
                )
            },
            cwd=self.repo,
        )
        self.assertTrue(result.valid)
        self.assertEqual("equivalent", result.code)

    def test_merged_prefix_absent_from_remote_trunk_is_rejected(self) -> None:
        first = self._layer("layer-one", "main", "source.txt")
        snapshot = NativeStackSnapshot(
            "main",
            self.trunk,
            "layer-one",
            (
                NativeLayer(
                    "layer-one",
                    first.head,
                    self.trunk,
                    True,
                    False,
                    False,
                    NativePullRequest(101, "https://example.test/101", "MERGED"),
                ),
            ),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            merged_prs={
                101: PullRequestRecord(
                    101,
                    "layer-one",
                    first.head,
                    "main",
                    "MERGED",
                    "",
                    merge_sha=first.head,
                )
            },
            cwd=self.repo,
        )

        self.assertFalse(result.valid)
        self.assertEqual("merged_prefix_missing_from_trunk", result.code)

    def test_merged_prefix_survives_later_trunk_edit_to_same_file(self) -> None:
        first = self._layer("layer-one", "main", "source.txt")
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(self.repo, "git", "merge", "--no-ff", "--no-edit", "layer-one")
        landing = helpers.run(self.repo, "git", "rev-parse", "main")
        (self.repo / "source.txt").write_text("authorized trunk revision\n")
        helpers.run(self.repo, "git", "add", "source.txt")
        helpers.commit(self.repo, "revise merged content on trunk")
        helpers.run(self.repo, "git", "push", "origin", "main")
        trunk = helpers.run(self.repo, "git", "rev-parse", "main")
        helpers.run(self.repo, "git", "checkout", "-b", "successor", "main")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--allow-empty",
            "-m",
            "source lineage successor",
        )
        successor = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(self.repo, "git", "push", "origin", "successor")
        snapshot = NativeStackSnapshot(
            "main",
            trunk,
            "main",
            (
                NativeLayer(
                    "layer-one",
                    first.head,
                    self.trunk,
                    True,
                    False,
                    False,
                    NativePullRequest(101, "https://example.test/101", "MERGED"),
                ),
            ),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "successor", successor),
            merged_prs={
                101: PullRequestRecord(
                    101,
                    "layer-one",
                    first.head,
                    "main",
                    "MERGED",
                    "",
                    merge_sha=landing,
                )
            },
            cwd=self.repo,
        )
        self.assertTrue(result.valid)
        self.assertEqual("equivalent", result.code)

    def test_merged_prefix_requires_current_merged_pr_evidence(self) -> None:
        first = self._layer("layer-one", "main", "source.txt")
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(self.repo, "git", "merge", "--no-ff", "--no-edit", "layer-one")
        helpers.run(self.repo, "git", "push", "origin", "main")
        trunk = helpers.run(self.repo, "git", "rev-parse", "main")
        snapshot = NativeStackSnapshot(
            "main",
            trunk,
            "main",
            (
                NativeLayer(
                    "layer-one",
                    first.head,
                    self.trunk,
                    True,
                    False,
                    False,
                    NativePullRequest(101, "https://example.test/101", "OPEN"),
                ),
            ),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            merged_prs={
                101: PullRequestRecord(
                    101,
                    "layer-one",
                    first.head,
                    "main",
                    "OPEN",
                    "",
                    merge_sha=trunk,
                )
            },
            cwd=self.repo,
        )
        self.assertFalse(result.valid)
        self.assertEqual("merged_prefix_unavailable", result.code)

        merged_snapshot = replace(
            snapshot,
            layers=(
                replace(
                    snapshot.layers[0],
                    pull_request=NativePullRequest(
                        101, "https://example.test/101", "MERGED"
                    ),
                ),
            ),
        )
        missing_landing = validate_mod.validate_live_equivalence(
            snapshot=merged_snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            merged_prs={
                101: PullRequestRecord(
                    101,
                    "layer-one",
                    first.head,
                    "main",
                    "MERGED",
                    "",
                )
            },
            cwd=self.repo,
        )
        self.assertFalse(missing_landing.valid)
        self.assertEqual("merged_prefix_unavailable", missing_landing.code)

    def test_open_layer_base_must_match_native_predecessor(self) -> None:
        first = self._layer("layer-one", "main", "source.txt")
        snapshot = NativeStackSnapshot(
            "main",
            self.trunk,
            "layer-one",
            (
                NativeLayer(
                    "layer-one", first.head, self.source_sha, False, False, False, None
                ),
            ),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            cwd=self.repo,
        )

        self.assertFalse(result.valid)
        self.assertEqual("native_topology_changed", result.code)

    def test_extra_suffix_change_does_not_match_source(self) -> None:
        self._layer("layer-one", "main", "source.txt")
        (self.repo / "extra.txt").write_text("unapproved\n")
        helpers.run(self.repo, "git", "add", "extra.txt")
        changed = helpers.commit(self.repo, "unapproved suffix change")
        snapshot = NativeStackSnapshot(
            "main",
            self.trunk,
            "layer-one",
            (NativeLayer("layer-one", changed, self.trunk, False, False, False, None),),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            cwd=self.repo,
        )

        self.assertFalse(result.valid)
        self.assertEqual("source_equivalence_mismatch", result.code)
        self.assertEqual(
            "",
            helpers.run(
                self.repo, "git", "for-each-ref", "refs/carve-changesets/equivalence"
            ),
        )

    def test_empty_suffix_requires_current_trunk_to_equal_remote_source(self) -> None:
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(self.repo, "git", "merge", "--ff-only", "feature/report")
        helpers.run(self.repo, "git", "push", "origin", "main")
        trunk = helpers.run(self.repo, "git", "rev-parse", "main")
        snapshot = NativeStackSnapshot("main", trunk, "main", ())

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            cwd=self.repo,
        )

        self.assertTrue(result.valid)
        self.assertEqual((), result.open_suffix)
        self.assertEqual(result.source_tree, result.reconstructed_tree)

    def test_local_only_successor_cannot_prove_trunk_drift_recovery(self) -> None:
        helpers.run(self.repo, "git", "checkout", "main")
        (self.repo / "trunk-only.txt").write_text("new trunk\n")
        helpers.run(self.repo, "git", "add", "trunk-only.txt")
        helpers.commit(self.repo, "advance trunk")
        helpers.run(self.repo, "git", "push", "origin", "main")
        trunk = helpers.run(self.repo, "git", "rev-parse", "main")
        helpers.run(self.repo, "git", "checkout", "-b", "successor", "feature/report")
        (self.repo / "trunk-only.txt").write_text("new trunk\n")
        helpers.run(self.repo, "git", "add", "trunk-only.txt")
        successor = helpers.commit(self.repo, "successor source")

        result = validate_mod.validate_live_equivalence(
            snapshot=NativeStackSnapshot("main", trunk, "main", ()),
            active_source=SourceIdentity("origin", "successor", successor),
            cwd=self.repo,
        )

        self.assertFalse(result.valid)
        self.assertEqual("successor_source_not_remote", result.code)

    def test_predecessor_drift_blocks_unchanged_descendant_head(self) -> None:
        (self.repo / "second.txt").write_text("second source part\n")
        helpers.run(self.repo, "git", "add", "second.txt")
        self.source_sha = helpers.commit(self.repo, "complete source")
        helpers.run(self.repo, "git", "push", "origin", "feature/report")
        first = self._layer("layer-one", "main", "source.txt")
        second = self._layer("layer-two", "layer-one", "second.txt")
        helpers.run(self.repo, "git", "checkout", "layer-one")
        (self.repo / "predecessor-only.txt").write_text("new predecessor work\n")
        helpers.run(self.repo, "git", "add", "predecessor-only.txt")
        advanced = helpers.commit(self.repo, "advance predecessor")
        snapshot = NativeStackSnapshot(
            "main",
            self.trunk,
            "layer-two",
            (replace(first, head=advanced), replace(second, base=advanced)),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            cwd=self.repo,
        )

        self.assertFalse(result.valid)
        self.assertEqual("predecessor_ancestry_broken", result.code)

    def test_unavailable_open_head_ancestry_blocks_equivalence(self) -> None:
        tree = helpers.run(self.repo, "git", "rev-parse", f"{self.source_sha}^{{tree}}")
        head = helpers.run(
            self.repo,
            "git",
            "hash-object",
            "-t",
            "commit",
            "-w",
            "--stdin",
            input_text=(
                f"tree {tree}\nparent {'f' * 40}\n"
                "author Carve Tests <carve@example.test> 1000000000 +0000\n"
                "committer Carve Tests <carve@example.test> 1000000000 +0000\n"
                "\nLayer with unavailable parent\n"
            ),
        )
        snapshot = NativeStackSnapshot(
            "main",
            self.trunk,
            "layer-one",
            (NativeLayer("layer-one", head, self.trunk, False, False, False, None),),
        )

        result = validate_mod.validate_live_equivalence(
            snapshot=snapshot,
            active_source=SourceIdentity("origin", "feature/report", self.source_sha),
            cwd=self.repo,
        )

        self.assertFalse(result.valid)
        self.assertEqual("ancestry_check_failed", result.code)

    def test_remote_successor_restores_equivalence_after_trunk_drift(self) -> None:
        helpers.run(self.repo, "git", "checkout", "main")
        (self.repo / "trunk-only.txt").write_text("new trunk\n")
        helpers.run(self.repo, "git", "add", "trunk-only.txt")
        helpers.commit(self.repo, "advance trunk")
        helpers.run(self.repo, "git", "push", "origin", "main")
        trunk = helpers.run(self.repo, "git", "rev-parse", "main")
        helpers.run(self.repo, "git", "checkout", "-b", "successor", "feature/report")
        (self.repo / "trunk-only.txt").write_text("new trunk\n")
        helpers.run(self.repo, "git", "add", "trunk-only.txt")
        successor = helpers.commit(self.repo, "successor source")
        helpers.run(self.repo, "git", "push", "origin", "successor")
        first = self._layer("layer-one", "main", "source.txt")

        result = validate_mod.validate_live_equivalence(
            snapshot=NativeStackSnapshot("main", trunk, "layer-one", (first,)),
            active_source=SourceIdentity("origin", "successor", successor),
            cwd=self.repo,
        )

        self.assertTrue(result.valid)
        self.assertEqual("equivalent", result.code)


if __name__ == "__main__":
    unittest.main()
