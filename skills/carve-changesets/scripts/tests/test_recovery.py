from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
import propagate as propagate_mod
import recovery as recovery_mod
from common import CommandError
from legacy_helpers import chdir
from metadata import (
    ChangesetMetadata,
    SourceIdentity,
    embed_pr_metadata,
    parse_commit_message,
    stamp_commit_message,
)
from recovery import recover_suffix_from_live
from rehydrate import PullRequestRecord, RehydrationError, adopt_legacy_chain
from validate import validate_live_chain


class SuffixRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo, self.bare, _ = helpers.init_repo(self.temp_dir)
        helpers.run(
            self.temp_dir,
            "git",
            "--git-dir",
            str(self.bare),
            "symbolic-ref",
            "HEAD",
            "refs/heads/main",
        )
        helpers.run(self.repo, "git", "checkout", "feature/report")
        (self.repo / "second.txt").write_text("second source part\n")
        helpers.run(self.repo, "git", "add", "second.txt")
        self.source_sha = helpers.commit(self.repo, "complete original source")
        helpers.run(self.repo, "git", "push", "-u", "origin", "feature/report")

        root = SourceIdentity("feature/report", self.source_sha)
        helpers.run(self.repo, "git", "checkout", "-b", "feature/report-1", "main")
        source_text = helpers.run(self.repo, "git", "show", "feature/report:source.txt")
        (self.repo / "source.txt").write_text(source_text + "\n")
        helpers.run(self.repo, "git", "add", "source.txt")
        first_metadata = ChangesetMetadata("part-1", 1, root.branch, root.sha)
        self.first_head = helpers.commit(
            self.repo, stamp_commit_message("feat: changeset 1", first_metadata)
        )
        helpers.run(self.repo, "git", "push", "-u", "origin", "feature/report-1")

        helpers.run(
            self.repo,
            "git",
            "checkout",
            "-b",
            "feature/report-2",
            "feature/report-1",
        )
        second_text = helpers.run(self.repo, "git", "show", "feature/report:second.txt")
        (self.repo / "second.txt").write_text(second_text + "\n")
        helpers.run(self.repo, "git", "add", "second.txt")
        second_metadata = ChangesetMetadata("part-2", 2, root.branch, root.sha)
        second_head = helpers.commit(
            self.repo, stamp_commit_message("feat: changeset 2", second_metadata)
        )
        helpers.run(self.repo, "git", "push", "-u", "origin", "feature/report-2")

        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(
            self.repo,
            "git",
            "merge",
            "--no-ff",
            "--no-edit",
            "feature/report-1",
        )
        merge_sha = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(self.repo, "git", "push", "origin", "main")

        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "rebase",
            "--onto",
            "main",
            self.first_head,
            "feature/report-2",
        )
        propagated_head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        self.assertNotEqual(second_head, propagated_head)
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-2",
        )

        (self.repo / "accepted-fix.txt").write_text("accepted review fix\n")
        helpers.run(self.repo, "git", "add", "accepted-fix.txt")
        self.fixed_head = helpers.commit(
            self.repo,
            stamp_commit_message("fix: accept review feedback", second_metadata),
        )
        helpers.run(self.repo, "git", "push", "origin", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "branch",
            "feature/report-corrected",
            self.fixed_head,
        )
        helpers.run(
            self.repo,
            "git",
            "push",
            "-u",
            "origin",
            "feature/report-corrected",
        )
        self.successor_sha = self.fixed_head

        self.prs = {
            101: PullRequestRecord(
                number=101,
                head_branch="feature/report-1",
                head_sha=self.first_head,
                base_branch="main",
                state="MERGED",
                body=embed_pr_metadata("Position 1\n", first_metadata),
                title="Report (1 of 2)",
                merge_sha=merge_sha,
            ),
            102: PullRequestRecord(
                number=102,
                head_branch="feature/report-2",
                head_sha=self.fixed_head,
                base_branch="main",
                state="OPEN",
                body=embed_pr_metadata("Position 2\n", second_metadata),
                title="Report (2 of 2)",
            ),
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _remote_head(self, branch: str) -> str:
        output = helpers.run(
            self.repo,
            "git",
            "ls-remote",
            "origin",
            f"refs/heads/{branch}",
        )
        return output.split()[0]

    def _move_remote_ref_without_refresh(self, branch: str, head: str) -> None:
        helpers.run(
            self.temp_dir,
            "git",
            "--git-dir",
            str(self.bare),
            "update-ref",
            f"refs/heads/{branch}",
            head,
        )

    def _live_pr(self, number: int, **_kwargs) -> PullRequestRecord:
        pr = self.prs[number]
        head = self._remote_head(pr.head_branch)
        if head != pr.head_sha:
            pr = PullRequestRecord(
                **{
                    **pr.__dict__,
                    "head_sha": head,
                    "head_rewrite_edges": pr.head_rewrite_edges
                    + ((pr.head_sha, head),),
                }
            )
            self.prs[number] = pr
        return pr

    def _all_live_prs(self, *_args, **_kwargs) -> list[PullRequestRecord]:
        return [self._live_pr(number) for number in sorted(self.prs)]

    def _edit(self, number: int, *, body=None, **_kwargs) -> None:
        pr = self.prs[number]
        self.prs[number] = PullRequestRecord(
            **{**pr.__dict__, "body": body if body is not None else pr.body}
        )

    def _run_recovery(
        self,
        *,
        edit_side_effect=None,
        pull_requests_side_effect=None,
        successor_branch: str = "feature/report-corrected",
        successor_sha: str | None = None,
        dry_run: bool = False,
    ) -> str:
        output = io.StringIO()
        with (
            chdir(self.repo),
            mock.patch.object(
                recovery_mod,
                "pull_requests_for_source",
                side_effect=pull_requests_side_effect or self._all_live_prs,
            ),
            mock.patch.object(
                recovery_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(
                recovery_mod,
                "edit_pull_request",
                side_effect=edit_side_effect or self._edit,
            ),
            mock.patch.object(recovery_mod, "_verify_merged_on_base"),
            contextlib.redirect_stdout(output),
        ):
            recover_suffix_from_live(
                source="feature/report",
                base="main",
                from_index=2,
                successor_branch=successor_branch,
                successor_sha=successor_sha or self.successor_sha,
                remote="origin",
                dry_run=dry_run,
                authority_acknowledged=True,
            )
        return output.getvalue()

    def _prepare_completed_legacy_recovery(
        self, *, prove_boundary: bool, merge_tail: bool = False
    ) -> tuple[str, str, str]:
        root = SourceIdentity("origin", "feature/report", self.source_sha)
        prior = SourceIdentity("origin", "feature/report-reviewed", self.fixed_head)
        helpers.run(
            self.repo,
            "git",
            "branch",
            prior.branch,
            prior.sha,
        )
        helpers.run(
            self.repo,
            "git",
            "push",
            "-u",
            "origin",
            prior.branch,
        )
        prior_metadata = ChangesetMetadata(
            slug="part-2",
            index=2,
            source_branch=prior.branch,
            source_sha=prior.sha,
            source_lineage=(root, prior),
            recovery_from_head=self.fixed_head,
        )
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message(
                "fix: accept review feedback",
                prior_metadata,
            ),
        )
        boundary_head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-2",
        )

        if merge_tail:
            helpers.run(
                self.repo,
                "git",
                "checkout",
                "-b",
                "feature/report-side",
                boundary_head,
            )
            (self.repo / "legacy-side.txt").write_text("side history\n")
            helpers.run(self.repo, "git", "add", "legacy-side.txt")
            helpers.commit(
                self.repo,
                stamp_commit_message("fix: side history", prior_metadata),
            )
            helpers.run(self.repo, "git", "checkout", "feature/report-2")
        (self.repo / "legacy-follow-up.txt").write_text("later accepted fix\n")
        helpers.run(self.repo, "git", "add", "legacy-follow-up.txt")
        current_head = helpers.commit(
            self.repo,
            stamp_commit_message("fix: preserve later review fix", prior_metadata),
        )
        if merge_tail:
            helpers.run(
                self.repo,
                "git",
                "merge",
                "--no-ff",
                "--no-commit",
                "feature/report-side",
            )
            current_head = helpers.commit(
                self.repo,
                stamp_commit_message("fix: merge later history", prior_metadata),
            )
        helpers.run(self.repo, "git", "push", "origin", "feature/report-2")

        requested_branch = "feature/report-final"
        helpers.run(self.repo, "git", "branch", requested_branch, current_head)
        helpers.run(
            self.repo,
            "git",
            "push",
            "-u",
            "origin",
            requested_branch,
        )
        rewrite_edges = ((self.fixed_head, boundary_head),) if prove_boundary else ()
        self.prs[102] = PullRequestRecord(
            **{
                **self.prs[102].__dict__,
                "head_sha": current_head,
                "body": embed_pr_metadata("Position 2\n", prior_metadata),
                "head_rewrite_edges": rewrite_edges,
            }
        )
        return boundary_head, current_head, requested_branch

    def _prepare_evidence_preserving_join(
        self,
        *,
        arbitrary_second_parent: bool = False,
        join_base_branch: str = "main",
    ) -> tuple[str, str, str]:
        _, current_head, _ = self._prepare_completed_legacy_recovery(
            prove_boundary=True
        )
        prior_metadata = parse_commit_message(
            helpers.run(
                self.repo,
                "git",
                "show",
                "-s",
                "--format=%B",
                current_head,
            )
        )
        join_base_head = helpers.run(
            self.repo,
            "git",
            "rev-parse",
            join_base_branch,
        )
        helpers.run(
            self.repo,
            "git",
            "checkout",
            "-b",
            "feature/report-evidence-source",
            "main",
        )
        (self.repo / "evidence-source.txt").write_text("reviewed successor\n")
        helpers.run(self.repo, "git", "add", "evidence-source.txt")
        successor_sha = helpers.commit(self.repo, "fix: reviewed successor source")
        successor_branch = "feature/report-evidence-source"
        helpers.run(
            self.repo,
            "git",
            "push",
            "-u",
            "origin",
            successor_branch,
        )

        second_parent = successor_sha
        if arbitrary_second_parent:
            helpers.run(
                self.repo,
                "git",
                "checkout",
                "-b",
                "feature/report-arbitrary-parent",
                "main",
            )
            (self.repo / "arbitrary.txt").write_text("unreviewed merge parent\n")
            helpers.run(self.repo, "git", "add", "arbitrary.txt")
            second_parent = helpers.commit(self.repo, "fix: arbitrary merge parent")

        successor_tree = helpers.run(
            self.repo,
            "git",
            "rev-parse",
            f"{successor_sha}^{{tree}}",
        )
        joined_head = helpers.run(
            self.repo,
            "git",
            "commit-tree",
            successor_tree,
            "-p",
            join_base_head,
            "-p",
            second_parent,
            input_text=stamp_commit_message(
                "fix: preserve reviewed successor evidence",
                prior_metadata,
            ),
        )
        helpers.run(
            self.repo,
            "git",
            "push",
            "origin",
            f"{joined_head}:refs/heads/feature/report-2",
            f"--force-with-lease=refs/heads/feature/report-2:{current_head}",
        )
        helpers.run(
            self.repo,
            "git",
            "branch",
            "-f",
            "feature/report-2",
            joined_head,
        )
        self.prs[102] = PullRequestRecord(
            **{
                **self.prs[102].__dict__,
                "head_sha": joined_head,
                "base_branch": join_base_branch,
                "body": embed_pr_metadata("Position 2\n", prior_metadata),
                "head_rewrite_edges": self.prs[102].head_rewrite_edges
                + ((current_head, joined_head),),
            }
        )
        return joined_head, successor_branch, successor_sha

    def _complete_evidence_preserving_join(
        self,
        joined_head: str,
        successor_branch: str,
        successor_sha: str,
    ) -> str:
        prior_metadata = parse_commit_message(
            helpers.run(
                self.repo,
                "git",
                "show",
                "-s",
                "--format=%B",
                joined_head,
            )
        )
        recovered_metadata = ChangesetMetadata(
            slug=prior_metadata.slug,
            source_lineage=(
                *prior_metadata.source_lineage,
                SourceIdentity("origin", successor_branch, successor_sha),
            ),
            recovery_from_head=joined_head,
        )
        successor_tree = helpers.run(
            self.repo,
            "git",
            "rev-parse",
            f"{successor_sha}^{{tree}}",
        )
        parents = helpers.run(
            self.repo,
            "git",
            "show",
            "-s",
            "--format=%P",
            joined_head,
        ).split()
        parent_args = [item for parent in parents for item in ("-p", parent)]
        recovered_head = helpers.run(
            self.repo,
            "git",
            "commit-tree",
            successor_tree,
            *parent_args,
            input_text=stamp_commit_message(
                helpers.run(
                    self.repo,
                    "git",
                    "show",
                    "-s",
                    "--format=%B",
                    joined_head,
                ),
                recovered_metadata,
            ),
        )
        helpers.run(
            self.repo,
            "git",
            "push",
            "origin",
            f"{recovered_head}:refs/heads/feature/report-2",
            f"--force-with-lease=refs/heads/feature/report-2:{joined_head}",
        )
        helpers.run(
            self.repo,
            "git",
            "branch",
            "-f",
            "feature/report-2",
            recovered_head,
        )
        self.prs[102] = PullRequestRecord(
            **{
                **self.prs[102].__dict__,
                "head_sha": recovered_head,
                "body": embed_pr_metadata("Position 2\n", recovered_metadata),
                "head_rewrite_edges": self.prs[102].head_rewrite_edges
                + ((joined_head, recovered_head),),
            }
        )
        return recovered_head

    def _prepare_completed_multilayer_legacy_recovery(
        self, *, merge_tail: bool = False
    ) -> tuple[str, str]:
        root = SourceIdentity("origin", "feature/report", self.source_sha)
        prior = SourceIdentity("origin", "feature/report-reviewed", self.fixed_head)
        helpers.run(self.repo, "git", "branch", prior.branch, prior.sha)
        helpers.run(self.repo, "git", "push", "-u", "origin", prior.branch)

        helpers.run(
            self.repo,
            "git",
            "checkout",
            "-b",
            "feature/report-3",
            self.fixed_head,
        )
        (self.repo / "third.txt").write_text("third source part\n")
        helpers.run(self.repo, "git", "add", "third.txt")
        original_third_metadata = ChangesetMetadata("part-3", 3, root.branch, root.sha)
        original_third = helpers.commit(
            self.repo,
            stamp_commit_message("feat: changeset 3", original_third_metadata),
        )
        helpers.run(self.repo, "git", "push", "-u", "origin", "feature/report-3")

        second_metadata = ChangesetMetadata(
            slug="part-2",
            index=2,
            source_branch=prior.branch,
            source_sha=prior.sha,
            source_lineage=(root, prior),
            recovery_from_head=self.fixed_head,
        )
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message(
                "fix: accept review feedback",
                second_metadata,
            ),
        )
        second_boundary = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-2",
        )
        (self.repo / "legacy-follow-up.txt").write_text("later accepted fix\n")
        helpers.run(self.repo, "git", "add", "legacy-follow-up.txt")
        current_second = helpers.commit(
            self.repo,
            stamp_commit_message("fix: preserve later review fix", second_metadata),
        )
        helpers.run(self.repo, "git", "push", "origin", "feature/report-2")

        helpers.run(self.repo, "git", "checkout", "feature/report-3")
        helpers.run(
            self.repo,
            "git",
            "rebase",
            "--onto",
            current_second,
            self.fixed_head,
            "feature/report-3",
        )
        third_metadata = ChangesetMetadata(
            slug="part-3",
            index=3,
            source_branch=prior.branch,
            source_sha=prior.sha,
            source_lineage=(root, prior),
            recovery_from_head=original_third,
        )
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message("feat: changeset 3", third_metadata),
        )
        third_boundary = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-3",
        )
        if merge_tail:
            helpers.run(
                self.repo,
                "git",
                "checkout",
                "-b",
                "feature/report-3-side",
                third_boundary,
            )
            (self.repo / "third-side.txt").write_text("side history\n")
            helpers.run(self.repo, "git", "add", "third-side.txt")
            helpers.commit(
                self.repo,
                stamp_commit_message("fix: side history", third_metadata),
            )
            helpers.run(self.repo, "git", "checkout", "feature/report-3")
        (self.repo / "third-follow-up.txt").write_text("later third-layer fix\n")
        helpers.run(self.repo, "git", "add", "third-follow-up.txt")
        current_third = helpers.commit(
            self.repo,
            stamp_commit_message("fix: preserve third-layer fix", third_metadata),
        )
        if merge_tail:
            helpers.run(
                self.repo,
                "git",
                "merge",
                "--no-ff",
                "--no-commit",
                "feature/report-3-side",
            )
            current_third = helpers.commit(
                self.repo,
                stamp_commit_message("fix: merge third-layer history", third_metadata),
            )
        helpers.run(self.repo, "git", "push", "origin", "feature/report-3")

        requested_branch = (
            "feature/report-merged-final" if merge_tail else "feature/report-final"
        )
        helpers.run(self.repo, "git", "branch", requested_branch, current_third)
        helpers.run(
            self.repo,
            "git",
            "push",
            "-u",
            "origin",
            requested_branch,
        )
        self.prs[101] = PullRequestRecord(
            **{**self.prs[101].__dict__, "title": "Report (1 of 3)"}
        )
        self.prs[102] = PullRequestRecord(
            **{
                **self.prs[102].__dict__,
                "head_sha": current_second,
                "body": embed_pr_metadata("Position 2\n", second_metadata),
                "title": "Report (2 of 3)",
                "head_rewrite_edges": ((self.fixed_head, second_boundary),),
            }
        )
        self.prs[103] = PullRequestRecord(
            number=103,
            head_branch="feature/report-3",
            head_sha=current_third,
            base_branch="feature/report-2",
            state="OPEN",
            body=embed_pr_metadata("Position 3\n", third_metadata),
            title="Report (3 of 3)",
            head_rewrite_edges=((original_third, third_boundary),),
        )
        return current_third, requested_branch

    def _interrupt_after_v3_branch_update(self) -> str:
        def fail_before_edit(*_args, **_kwargs) -> None:
            raise CommandError("injected before PR metadata cleanup")

        with self.assertRaisesRegex(CommandError, "injected"):
            self._run_recovery(edit_side_effect=fail_before_edit)
        return self._remote_head("feature/report-2")

    def _push_v3_with_legacy_body(self, *, recovery_from_head: str) -> str:
        metadata = ChangesetMetadata(
            slug="part-2",
            source_lineage=(
                SourceIdentity("origin", "feature/report", self.source_sha),
                SourceIdentity(
                    "origin", "feature/report-corrected", self.successor_sha
                ),
            ),
            recovery_from_head=recovery_from_head,
        )
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message(
                "fix: accept review feedback",
                metadata,
            ),
        )
        head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-2",
        )
        return head

    def _restamp_open_suffix_as_native(self, *, identity_remote: str) -> str:
        metadata = ChangesetMetadata(
            slug="part-2",
            source_lineage=(
                SourceIdentity(
                    identity_remote,
                    "feature/report",
                    self.source_sha,
                ),
            ),
        )
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message("fix: accept review feedback", metadata),
        )
        head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-2",
        )
        self.prs[102] = PullRequestRecord(
            **{
                **self.prs[102].__dict__,
                "head_sha": head,
                "body": "Human-readable recovery context only.\n",
            }
        )
        return head

    def test_recovers_two_position_chain_and_preserves_merged_prefix(self) -> None:
        output = self._run_recovery()

        recovered_head = self._remote_head("feature/report-2")
        self.assertEqual(self.first_head, self._remote_head("feature/report-1"))
        self.assertNotEqual(self.fixed_head, recovered_head)
        metadata = parse_commit_message(
            helpers.run(
                self.repo,
                "git",
                "show",
                "-s",
                "--format=%B",
                recovered_head,
            )
        )
        self.assertEqual(
            ("feature/report", "feature/report-corrected"),
            tuple(identity.branch for identity in metadata.source_lineage),
        )
        self.assertEqual(3, metadata.version)
        self.assertIsNone(metadata.legacy_position)
        self.assertEqual(self.fixed_head, metadata.recovery_from_head)
        self.assertEqual("Position 2\n", self.prs[102].body)
        self.assertNotIn("carve-changesets:metadata", self.prs[102].body)
        self.assertIn("EVIDENCE-INVALIDATED", output)

        clone = self.temp_dir / "fresh"
        helpers.run(self.temp_dir, "git", "clone", str(self.bare), str(clone))
        chain = adopt_legacy_chain(
            source_branch="feature/report",
            base_branch="main",
            pull_requests=self._all_live_prs(),
            cwd=clone,
        )
        validation = validate_live_chain(chain, cwd=clone)
        self.assertTrue(validation.valid, validation.errors)
        self.assertEqual(self.successor_sha, chain.source_sha)

    def test_native_human_only_pr_recovers_through_public_workflow(self) -> None:
        native_head = self._restamp_open_suffix_as_native(identity_remote="origin")

        output = self._run_recovery()

        recovered_head = self._remote_head("feature/report-2")
        self.assertNotEqual(native_head, recovered_head)
        self.assertEqual(
            "Human-readable recovery context only.\n",
            self.prs[102].body,
        )
        metadata = parse_commit_message(
            helpers.run(
                self.repo,
                "git",
                "show",
                "-s",
                "--format=%B",
                recovered_head,
            )
        )
        self.assertEqual(3, metadata.version)
        self.assertEqual(2, len(metadata.source_lineage))
        self.assertIn("Suffix recovery completed", output)

    def test_public_recovery_extends_authenticated_legacy_successor_lineage(
        self,
    ) -> None:
        prior_source_head = self.fixed_head
        _, current_head, requested_branch = self._prepare_completed_legacy_recovery(
            prove_boundary=True
        )

        output = self._run_recovery(
            successor_branch=requested_branch,
            successor_sha=current_head,
        )

        recovered_head = self._remote_head("feature/report-2")
        metadata = parse_commit_message(
            helpers.run(
                self.repo,
                "git",
                "show",
                "-s",
                "--format=%B",
                recovered_head,
            )
        )
        self.assertEqual(
            (
                "feature/report",
                "feature/report-reviewed",
                requested_branch,
            ),
            tuple(identity.branch for identity in metadata.source_lineage),
        )
        self.assertEqual(current_head, metadata.recovery_from_head)
        self.assertEqual(
            prior_source_head,
            self._remote_head("feature/report-reviewed"),
        )
        self.assertEqual(current_head, self._remote_head(requested_branch))
        self.assertEqual(self.first_head, self._remote_head("feature/report-1"))
        self.assertIn("Suffix recovery completed", output)

    def test_public_recovery_rejects_unproven_legacy_successor_lineage(self) -> None:
        _, current_head, requested_branch = self._prepare_completed_legacy_recovery(
            prove_boundary=False
        )
        original_body = self.prs[102].body

        with self.assertRaisesRegex(
            CommandError,
            "Live suffix recovery state is invalid.*cannot prove",
        ):
            self._run_recovery(
                successor_branch=requested_branch,
                successor_sha=current_head,
            )

        self.assertEqual(current_head, self._remote_head("feature/report-2"))
        self.assertEqual(original_body, self.prs[102].body)

    def test_public_recovery_rejects_merge_in_legacy_successor_tail(self) -> None:
        _, current_head, requested_branch = self._prepare_completed_legacy_recovery(
            prove_boundary=True,
            merge_tail=True,
        )
        original_body = self.prs[102].body

        with self.assertRaisesRegex(
            CommandError,
            "Live suffix recovery state is invalid.*cannot prove",
        ):
            self._run_recovery(
                successor_branch=requested_branch,
                successor_sha=current_head,
            )

        self.assertEqual(current_head, self._remote_head("feature/report-2"))
        self.assertEqual(original_body, self.prs[102].body)

    def test_public_recovery_authenticates_exact_evidence_preserving_join(
        self,
    ) -> None:
        joined_head, successor_branch, successor_sha = (
            self._prepare_evidence_preserving_join()
        )

        output = self._run_recovery(
            successor_branch=successor_branch,
            successor_sha=successor_sha,
        )

        recovered_head = self._remote_head("feature/report-2")
        self.assertNotEqual(joined_head, recovered_head)
        recovered_metadata = parse_commit_message(
            helpers.run(
                self.repo,
                "git",
                "show",
                "-s",
                "--format=%B",
                recovered_head,
            )
        )
        self.assertEqual(successor_sha, recovered_metadata.active_source.sha)
        self.assertEqual(
            helpers.run(self.repo, "git", "rev-parse", f"{successor_sha}^{{tree}}"),
            helpers.run(self.repo, "git", "rev-parse", f"{recovered_head}^{{tree}}"),
        )
        self.assertIn("Suffix recovery completed", output)

    def test_public_recovery_rejects_arbitrary_evidence_join_parent(self) -> None:
        joined_head, successor_branch, successor_sha = (
            self._prepare_evidence_preserving_join(arbitrary_second_parent=True)
        )
        original_body = self.prs[102].body

        with self.assertRaisesRegex(
            CommandError,
            "Live suffix recovery state is invalid.*cannot prove",
        ):
            self._run_recovery(
                successor_branch=successor_branch,
                successor_sha=successor_sha,
            )

        self.assertEqual(joined_head, self._remote_head("feature/report-2"))
        self.assertEqual(original_body, self.prs[102].body)

    def test_public_recovery_rejects_evidence_join_on_stale_live_base(self) -> None:
        joined_head, successor_branch, successor_sha = (
            self._prepare_evidence_preserving_join()
        )
        original_body = self.prs[102].body

        def move_base_after_fetch(*_args, **_kwargs):
            self._move_remote_ref_without_refresh("main", successor_sha)
            return self._all_live_prs()

        with self.assertRaisesRegex(
            CommandError,
            "Live suffix recovery state is invalid.*cannot prove",
        ):
            self._run_recovery(
                successor_branch=successor_branch,
                successor_sha=successor_sha,
                pull_requests_side_effect=move_base_after_fetch,
                dry_run=True,
            )

        self.assertEqual(joined_head, self._remote_head("feature/report-2"))
        self.assertEqual(original_body, self.prs[102].body)

    def test_public_recovery_rejects_evidence_join_on_stale_successor_ref(
        self,
    ) -> None:
        joined_head, successor_branch, successor_sha = (
            self._prepare_evidence_preserving_join()
        )
        original_body = self.prs[102].body
        main_head = helpers.run(self.repo, "git", "rev-parse", "main")

        def move_successor_after_fetch(*_args, **_kwargs):
            self._move_remote_ref_without_refresh(successor_branch, main_head)
            return self._all_live_prs()

        with self.assertRaisesRegex(
            CommandError,
            "Live suffix recovery state is invalid.*cannot prove",
        ):
            self._run_recovery(
                successor_branch=successor_branch,
                successor_sha=successor_sha,
                pull_requests_side_effect=move_successor_after_fetch,
                dry_run=True,
            )

        self.assertEqual(joined_head, self._remote_head("feature/report-2"))
        self.assertEqual(original_body, self.prs[102].body)

    def test_public_completed_lineage_rejects_stale_evidence_join_base(
        self,
    ) -> None:
        _, successor_branch, successor_sha = self._prepare_evidence_preserving_join()
        self._run_recovery(
            successor_branch=successor_branch,
            successor_sha=successor_sha,
        )
        self._move_remote_ref_without_refresh("main", successor_sha)

        with self.assertRaisesRegex(
            RehydrationError,
            "missing, conflicting, or discontinuous successor-source lineage",
        ):
            adopt_legacy_chain(
                source_branch="feature/report",
                base_branch="main",
                pull_requests=self._all_live_prs(),
                cwd=self.repo,
                remote="origin",
                prefer_remote=True,
            )

    def test_public_completed_lineage_rejects_stale_evidence_join_successor(
        self,
    ) -> None:
        _, successor_branch, successor_sha = self._prepare_evidence_preserving_join()
        self._run_recovery(
            successor_branch=successor_branch,
            successor_sha=successor_sha,
        )
        main_head = helpers.run(self.repo, "git", "rev-parse", "main")
        self._move_remote_ref_without_refresh(successor_branch, main_head)

        with self.assertRaisesRegex(
            RehydrationError,
            "missing, conflicting, or discontinuous successor-source lineage",
        ):
            adopt_legacy_chain(
                source_branch="feature/report",
                base_branch="main",
                pull_requests=self._all_live_prs(),
                cwd=self.repo,
                remote="origin",
                prefer_remote=True,
            )

    def test_public_completed_lineage_rejects_predecessor_based_evidence_join(
        self,
    ) -> None:
        joined_head, successor_branch, successor_sha = (
            self._prepare_evidence_preserving_join(
                join_base_branch="feature/report-1",
            )
        )
        self._complete_evidence_preserving_join(
            joined_head,
            successor_branch,
            successor_sha,
        )

        with self.assertRaisesRegex(
            RehydrationError,
            "missing, conflicting, or discontinuous successor-source lineage",
        ):
            adopt_legacy_chain(
                source_branch="feature/report",
                base_branch="main",
                pull_requests=self._all_live_prs(),
                cwd=self.repo,
                remote="origin",
                prefer_remote=True,
            )

    def test_public_completed_lineage_requires_explicit_evidence_join_base(
        self,
    ) -> None:
        helpers.run(self.repo, "git", "branch", "release-old", "main")
        helpers.run(self.repo, "git", "push", "-u", "origin", "release-old")
        helpers.run(self.repo, "git", "checkout", "main")
        (self.repo / "new-main.txt").write_text("new live main\n")
        helpers.run(self.repo, "git", "add", "new-main.txt")
        helpers.commit(self.repo, "advance live main")
        helpers.run(self.repo, "git", "push", "origin", "main")
        self.prs[101] = PullRequestRecord(
            **{
                **self.prs[101].__dict__,
                "base_branch": "release-old",
            }
        )
        joined_head, successor_branch, successor_sha = (
            self._prepare_evidence_preserving_join(
                join_base_branch="release-old",
            )
        )
        self._complete_evidence_preserving_join(
            joined_head,
            successor_branch,
            successor_sha,
        )

        with self.assertRaisesRegex(
            RehydrationError,
            "missing, conflicting, or discontinuous successor-source lineage",
        ):
            adopt_legacy_chain(
                source_branch="feature/report",
                pull_requests=self._all_live_prs(),
                cwd=self.repo,
                remote="origin",
                prefer_remote=True,
            )

    def test_public_repeated_recovery_resumes_after_metadata_interruption(
        self,
    ) -> None:
        _, current_head, requested_branch = self._prepare_completed_legacy_recovery(
            prove_boundary=True
        )
        original_body = self.prs[102].body

        def fail_before_metadata_update(*_args, **_kwargs) -> None:
            raise CommandError("injected before repeated-recovery metadata update")

        with self.assertRaisesRegex(CommandError, "injected before repeated"):
            self._run_recovery(
                edit_side_effect=fail_before_metadata_update,
                successor_branch=requested_branch,
                successor_sha=current_head,
            )

        interrupted_head = self._remote_head("feature/report-2")
        self.assertNotEqual(current_head, interrupted_head)
        self.assertEqual(original_body, self.prs[102].body)

        output = self._run_recovery(
            successor_branch=requested_branch,
            successor_sha=current_head,
        )

        self.assertEqual(interrupted_head, self._remote_head("feature/report-2"))
        self.assertIn("Suffix recovery completed", output)

    def test_public_repeated_recovery_rejects_missing_later_prior_boundary(
        self,
    ) -> None:
        current_head, requested_branch = (
            self._prepare_completed_multilayer_legacy_recovery()
        )

        def fail_on_later_metadata_update(number: int, **kwargs) -> None:
            if number == 103:
                raise CommandError("injected before later metadata update")
            self._edit(number, **kwargs)

        with self.assertRaisesRegex(CommandError, "injected before later"):
            self._run_recovery(
                edit_side_effect=fail_on_later_metadata_update,
                successor_branch=requested_branch,
                successor_sha=current_head,
            )

        interrupted_head = self._remote_head("feature/report-3")
        original_body = self.prs[103].body
        self.prs[103] = PullRequestRecord(
            **{**self.prs[103].__dict__, "head_rewrite_edges": ()}
        )

        with self.assertRaisesRegex(
            CommandError,
            "Live suffix recovery state is invalid.*cannot prove",
        ):
            self._run_recovery(
                successor_branch=requested_branch,
                successor_sha=current_head,
            )

        self.assertEqual(interrupted_head, self._remote_head("feature/report-3"))
        self.assertEqual(original_body, self.prs[103].body)

    def test_public_repeated_recovery_fetches_later_rewrite_objects(self) -> None:
        boundary_head, current_head, original_requested = (
            self._prepare_completed_legacy_recovery(prove_boundary=True)
        )
        helpers.run(
            self.repo,
            "git",
            "push",
            "origin",
            "--delete",
            original_requested,
        )
        boundary_tree = helpers.run(
            self.repo,
            "git",
            "rev-parse",
            f"{boundary_head}^{{tree}}",
        )
        boundary_parent = helpers.run(
            self.repo,
            "git",
            "show",
            "-s",
            "--format=%P",
            boundary_head,
        )
        boundary_message = helpers.run(
            self.repo,
            "git",
            "show",
            "-s",
            "--format=%B",
            boundary_head,
        )
        rewritten_head = helpers.run(
            self.repo,
            "git",
            "-c",
            "user.name=Recovery Rewrite",
            "-c",
            "user.email=rewrite@example.test",
            "commit-tree",
            boundary_tree,
            "-p",
            boundary_parent,
            input_text=boundary_message,
        )
        helpers.run(
            self.repo,
            "git",
            "push",
            "origin",
            f"{rewritten_head}:refs/heads/feature/report-2",
            f"--force-with-lease=refs/heads/feature/report-2:{current_head}",
        )

        helpers.run(
            self.repo,
            "git",
            "checkout",
            "-b",
            "feature/report-later-tail",
            rewritten_head,
        )
        (self.repo / "later-tail.txt").write_text("later accepted tail\n")
        helpers.run(self.repo, "git", "add", "later-tail.txt")
        metadata = parse_commit_message(boundary_message)
        final_head = helpers.commit(
            self.repo,
            stamp_commit_message("fix: preserve later tail", metadata),
        )
        helpers.run(
            self.repo,
            "git",
            "push",
            "origin",
            "HEAD:refs/heads/feature/report-2",
        )
        requested_branch = "feature/report-later-final"
        helpers.run(self.repo, "git", "branch", requested_branch, final_head)
        helpers.run(
            self.repo,
            "git",
            "push",
            "-u",
            "origin",
            requested_branch,
        )
        self.prs[102] = PullRequestRecord(
            **{
                **self.prs[102].__dict__,
                "head_sha": final_head,
                "head_rewrite_edges": (
                    (self.fixed_head, boundary_head),
                    (current_head, rewritten_head),
                ),
            }
        )

        fresh_clone = self.temp_dir / "fresh-later-rewrite"
        helpers.run(
            self.temp_dir,
            "git",
            "clone",
            "--no-local",
            str(self.bare),
            str(fresh_clone),
        )
        helpers.run(fresh_clone, "git", "config", "user.name", "Carve Tests")
        helpers.run(
            fresh_clone,
            "git",
            "config",
            "user.email",
            "carve@example.test",
        )
        output = io.StringIO()
        with (
            chdir(fresh_clone),
            mock.patch.object(
                recovery_mod,
                "pull_requests_for_source",
                side_effect=self._all_live_prs,
            ),
            mock.patch.object(
                recovery_mod,
                "pull_request_by_number",
                side_effect=self._live_pr,
            ),
            mock.patch.object(recovery_mod, "edit_pull_request"),
            mock.patch.object(recovery_mod, "_verify_merged_on_base"),
            contextlib.redirect_stdout(output),
        ):
            recover_suffix_from_live(
                source="feature/report",
                base="main",
                from_index=2,
                successor_branch=requested_branch,
                successor_sha=final_head,
                remote="origin",
                dry_run=True,
                authority_acknowledged=True,
            )

        self.assertIn("Dry-run suffix recovery passed", output.getvalue())

    def test_public_recovery_extends_multilayer_legacy_successor_lineage(
        self,
    ) -> None:
        current_head, requested_branch = (
            self._prepare_completed_multilayer_legacy_recovery()
        )

        output = self._run_recovery(
            successor_branch=requested_branch,
            successor_sha=current_head,
        )

        recovered_head = self._remote_head("feature/report-3")
        metadata = parse_commit_message(
            helpers.run(
                self.repo,
                "git",
                "show",
                "-s",
                "--format=%B",
                recovered_head,
            )
        )
        self.assertEqual(
            (
                "feature/report",
                "feature/report-reviewed",
                requested_branch,
            ),
            tuple(identity.branch for identity in metadata.source_lineage),
        )
        self.assertIn("Suffix recovery completed", output)

    def test_public_recovery_rejects_merge_in_multilayer_legacy_tail(self) -> None:
        current_head, requested_branch = (
            self._prepare_completed_multilayer_legacy_recovery(merge_tail=True)
        )
        original_body = self.prs[103].body

        with self.assertRaisesRegex(
            CommandError,
            "Live suffix recovery state is invalid.*cannot prove",
        ):
            self._run_recovery(
                successor_branch=requested_branch,
                successor_sha=current_head,
            )

        self.assertEqual(current_head, self._remote_head("feature/report-3"))
        self.assertEqual(original_body, self.prs[103].body)

    def test_public_recovery_rejects_divergent_pr_body_readback(self) -> None:
        def persist_divergent_body(number: int, **_kwargs) -> None:
            self._edit(number, body="Server-altered recovery context.\n")

        with self.assertRaisesRegex(CommandError, "could not be verified"):
            self._run_recovery(edit_side_effect=persist_divergent_body)

        self.assertEqual(
            "Server-altered recovery context.\n",
            self.prs[102].body,
        )

    def test_public_recovery_rejects_lineage_from_another_remote(self) -> None:
        self._restamp_open_suffix_as_native(identity_remote="upstream")

        with self.assertRaisesRegex(
            CommandError,
            "Live suffix recovery state is invalid.*root source",
        ):
            self._run_recovery()

    def test_recovery_rechecks_lineage_after_each_push(self) -> None:
        actual_push = recovery_mod.push_changeset_branch
        successor_deleted = False

        def push_then_delete_successor(*args, **kwargs) -> None:
            nonlocal successor_deleted
            actual_push(*args, **kwargs)
            if not successor_deleted:
                helpers.run(
                    self.repo,
                    "git",
                    "push",
                    "origin",
                    "--delete",
                    "feature/report-corrected",
                )
                successor_deleted = True

        with (
            chdir(self.repo),
            mock.patch.object(
                recovery_mod,
                "pull_requests_for_source",
                side_effect=self._all_live_prs,
            ),
            mock.patch.object(
                recovery_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(
                recovery_mod,
                "push_changeset_branch",
                side_effect=push_then_delete_successor,
            ),
            mock.patch.object(
                recovery_mod, "edit_pull_request", side_effect=self._edit
            ) as edit,
            mock.patch.object(recovery_mod, "_verify_merged_on_base"),
        ):
            with self.assertRaisesRegex(CommandError, "source.*unavailable"):
                recover_suffix_from_live(
                    source="feature/report",
                    base="main",
                    from_index=2,
                    successor_branch="feature/report-corrected",
                    successor_sha=self.successor_sha,
                    remote="origin",
                    dry_run=False,
                    authority_acknowledged=True,
                )

        edit.assert_not_called()

    def test_multi_layer_recovery_propagates_fix_and_survives_merge(self) -> None:
        case_dir = self.temp_dir / "non-origin"
        case_dir.mkdir()
        repo, bare, source_sha = helpers.init_repo(case_dir)
        helpers.run(repo, "git", "remote", "add", "upstream", str(bare))
        helpers.run(repo, "git", "fetch", "upstream")
        root = SourceIdentity("feature/report", source_sha)

        helpers.run(repo, "git", "checkout", "-b", "feature/report-1", "main")
        source_text = helpers.run(repo, "git", "show", "feature/report:source.txt")
        (repo / "source.txt").write_text(source_text + "\n")
        helpers.run(repo, "git", "add", "source.txt")
        first_metadata = ChangesetMetadata("part-1", 1, root.branch, root.sha)
        first_head = helpers.commit(
            repo,
            stamp_commit_message("feat: changeset 1", first_metadata),
        )
        helpers.run(repo, "git", "push", "-u", "upstream", "feature/report-1")
        helpers.run(repo, "git", "checkout", "main")
        helpers.run(
            repo,
            "git",
            "merge",
            "--no-ff",
            "--no-edit",
            "feature/report-1",
        )
        merge_sha = helpers.run(repo, "git", "rev-parse", "HEAD")
        helpers.run(repo, "git", "push", "upstream", "main")

        helpers.run(
            repo,
            "git",
            "checkout",
            "-b",
            "feature/report-2",
            "main",
        )
        (repo / "second.txt").write_text("second source part\n")
        helpers.run(repo, "git", "add", "second.txt")
        second_metadata = ChangesetMetadata("part-2", 2, root.branch, root.sha)
        second_head = helpers.commit(
            repo,
            stamp_commit_message("feat: changeset 2", second_metadata),
        )
        helpers.run(repo, "git", "push", "-u", "upstream", "feature/report-2")
        helpers.run(
            repo,
            "git",
            "checkout",
            "-b",
            "feature/report-3",
            "feature/report-2",
        )
        (repo / "third.txt").write_text("third source part\n")
        helpers.run(repo, "git", "add", "third.txt")
        third_metadata = ChangesetMetadata("part-3", 3, root.branch, root.sha)
        third_head = helpers.commit(
            repo,
            stamp_commit_message("feat: changeset 3", third_metadata),
        )
        (repo / "third-review.txt").write_text("accepted third-layer review fix\n")
        helpers.run(repo, "git", "add", "third-review.txt")
        third_head = helpers.commit(
            repo,
            stamp_commit_message("fix: changeset 3 review", third_metadata),
        )
        helpers.run(repo, "git", "push", "-u", "upstream", "feature/report-3")
        successor_sha = third_head
        original_successor_sha = successor_sha
        helpers.run(repo, "git", "branch", "feature/report-corrected", third_head)
        helpers.run(
            repo,
            "git",
            "push",
            "-u",
            "upstream",
            "feature/report-corrected",
        )

        helpers.run(repo, "git", "checkout", "main")
        helpers.run(repo, "git", "cherry-pick", second_head)
        (repo / "accepted-fix.txt").write_text("accepted second-layer fix\n")
        helpers.run(repo, "git", "add", "accepted-fix.txt")
        helpers.run(
            repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message(
                "feat: changeset 2 rewritten", second_metadata
            ),
        )
        rewritten_second = helpers.run(repo, "git", "rev-parse", "HEAD")
        helpers.run(
            repo,
            "git",
            "push",
            "upstream",
            "HEAD:refs/heads/feature/report-2",
            f"--force-with-lease=refs/heads/feature/report-2:{second_head}",
        )
        helpers.run(repo, "git", "branch", "-f", "feature/report-2", rewritten_second)
        helpers.run(repo, "git", "checkout", "-b", "feature/report-successor-build")
        helpers.run(
            repo,
            "git",
            "cherry-pick",
            f"{second_head}..{third_head}",
        )
        successor_sha = helpers.run(repo, "git", "rev-parse", "HEAD")
        helpers.run(
            repo,
            "git",
            "push",
            "upstream",
            "HEAD:refs/heads/feature/report-corrected",
            f"--force-with-lease=refs/heads/feature/report-corrected:{original_successor_sha}",
        )
        helpers.run(
            repo,
            "git",
            "branch",
            "-f",
            "feature/report-corrected",
            successor_sha,
        )
        helpers.run(repo, "git", "branch", "-f", "main", merge_sha)

        prs = {
            101: PullRequestRecord(
                number=101,
                head_branch="feature/report-1",
                head_sha=first_head,
                base_branch="main",
                state="MERGED",
                body=embed_pr_metadata("Position 1\n", first_metadata),
                title="Report API (1 of 3)",
                merge_sha=merge_sha,
            ),
            102: PullRequestRecord(
                number=102,
                head_branch="feature/report-2",
                head_sha=rewritten_second,
                base_branch="main",
                state="OPEN",
                body=embed_pr_metadata("Position 2\n", second_metadata),
                title="Report API (2 of 3)",
                head_rewrite_edges=((second_head, rewritten_second),),
            ),
            103: PullRequestRecord(
                number=103,
                head_branch="feature/report-3",
                head_sha=third_head,
                base_branch="feature/report-2",
                state="OPEN",
                body=embed_pr_metadata("Position 3\n", third_metadata),
                title="Report API (3 of 3)",
            ),
        }

        def remote_head(branch: str) -> str:
            output = helpers.run(
                repo,
                "git",
                "ls-remote",
                "upstream",
                f"refs/heads/{branch}",
            )
            return output.split()[0]

        def live_pr(number: int, **_kwargs) -> PullRequestRecord:
            pr = prs[number]
            head = remote_head(pr.head_branch)
            if head != pr.head_sha:
                pr = PullRequestRecord(
                    **{
                        **pr.__dict__,
                        "head_sha": head,
                        "head_rewrite_edges": pr.head_rewrite_edges
                        + ((pr.head_sha, head),),
                    }
                )
                prs[number] = pr
            return pr

        def all_live_prs(*_args, **_kwargs) -> list[PullRequestRecord]:
            return [live_pr(number) for number in sorted(prs)]

        def edit_pr(
            number: int, *, body=None, base=None, title=None, **_kwargs
        ) -> None:
            prs[number] = PullRequestRecord(
                **{
                    **prs[number].__dict__,
                    "body": body if body is not None else prs[number].body,
                    "base_branch": base or prs[number].base_branch,
                    "title": title or prs[number].title,
                }
            )

        actual_push = recovery_mod.push_changeset_branch

        def interrupt_on_third_push(branch: str, **kwargs) -> None:
            if branch == "feature/report-3":
                raise CommandError("injected after first suffix push")
            actual_push(branch, **kwargs)

        with (
            chdir(repo),
            mock.patch.object(
                recovery_mod,
                "pull_requests_for_source",
                side_effect=all_live_prs,
            ),
            mock.patch.object(
                recovery_mod,
                "pull_request_by_number",
                side_effect=live_pr,
            ),
            mock.patch.object(
                propagate_mod,
                "pull_request_by_number",
                side_effect=live_pr,
            ),
            mock.patch.object(
                recovery_mod,
                "edit_pull_request",
                side_effect=edit_pr,
            ),
            mock.patch.object(
                recovery_mod,
                "push_changeset_branch",
                side_effect=interrupt_on_third_push,
            ),
        ):
            with self.assertRaisesRegex(CommandError, "injected after first"):
                recover_suffix_from_live(
                    source="feature/report",
                    base="main",
                    from_index=2,
                    successor_branch="feature/report-corrected",
                    successor_sha=successor_sha,
                    remote="upstream",
                    dry_run=False,
                    authority_acknowledged=True,
                )

        partial_second = remote_head("feature/report-2")
        self.assertNotEqual(rewritten_second, partial_second)
        self.assertEqual(third_head, remote_head("feature/report-3"))
        self.assertEqual(
            3,
            parse_commit_message(
                helpers.run(repo, "git", "show", "-s", "--format=%B", partial_second),
                remote="upstream",
            ).version,
        )

        with (
            chdir(repo),
            mock.patch.object(
                recovery_mod,
                "pull_requests_for_source",
                side_effect=all_live_prs,
            ),
            mock.patch.object(
                recovery_mod,
                "pull_request_by_number",
                side_effect=live_pr,
            ),
            mock.patch.object(
                propagate_mod,
                "pull_request_by_number",
                side_effect=live_pr,
            ),
            mock.patch.object(
                recovery_mod,
                "edit_pull_request",
                side_effect=edit_pr,
            ),
        ):
            recover_suffix_from_live(
                source="feature/report",
                base="main",
                from_index=2,
                successor_branch="feature/report-corrected",
                successor_sha=successor_sha,
                remote="upstream",
                dry_run=False,
                authority_acknowledged=True,
            )

        recovered_first = remote_head("feature/report-1")
        recovered_second = remote_head("feature/report-2")
        recovered_third = remote_head("feature/report-3")
        self.assertEqual(first_head, recovered_first)
        self.assertNotEqual(rewritten_second, recovered_second)
        self.assertNotEqual(third_head, recovered_third)
        metadata = parse_commit_message(
            helpers.run(
                repo,
                "git",
                "show",
                "-s",
                "--format=%B",
                recovered_third,
            ),
            remote="upstream",
        )
        self.assertEqual(
            ("upstream", "upstream"),
            tuple(identity.remote for identity in metadata.source_lineage),
        )
        self.assertEqual(3, metadata.version)
        self.assertIsNone(metadata.legacy_position)
        self.assertEqual("Position 2\n", prs[102].body)
        self.assertEqual("Position 3\n", prs[103].body)
        self.assertNotIn("carve-changesets:metadata", prs[102].body)
        self.assertNotIn("carve-changesets:metadata", prs[103].body)

        recovered_third_tree = helpers.run(
            repo, "git", "rev-parse", f"{recovered_third}^{{tree}}"
        )
        recovered_third_message = helpers.run(
            repo, "git", "show", "-s", "--format=%B", recovered_third
        )
        second_parent_forgery = helpers.run(
            repo,
            "git",
            "commit-tree",
            recovered_third_tree,
            "-p",
            source_sha,
            "-p",
            recovered_second,
            input_text=recovered_third_message,
        )
        helpers.run(
            repo,
            "git",
            "push",
            "upstream",
            f"{second_parent_forgery}:refs/heads/feature/report-3",
            f"--force-with-lease=refs/heads/feature/report-3:{recovered_third}",
        )

        with self.assertRaisesRegex(RehydrationError, "cannot prove"):
            adopt_legacy_chain(
                source_branch="feature/report",
                base_branch="main",
                pull_requests=all_live_prs(),
                cwd=repo,
                remote="upstream",
                prefer_remote=True,
            )

        helpers.run(
            repo,
            "git",
            "push",
            "upstream",
            f"{recovered_third}:refs/heads/feature/report-3",
            f"--force-with-lease=refs/heads/feature/report-3:{second_parent_forgery}",
        )

        original = helpers.run(repo, "git", "branch", "--show-current")
        helpers.run(repo, "git", "checkout", "main")
        helpers.run(repo, "git", "merge", "--no-ff", "--no-edit", recovered_second)
        second_merge = helpers.run(repo, "git", "rev-parse", "HEAD")
        helpers.run(repo, "git", "push", "upstream", "main")
        helpers.run(repo, "git", "checkout", original)
        prs[102] = PullRequestRecord(
            **{
                **prs[102].__dict__,
                "state": "MERGED",
                "merge_sha": second_merge,
            }
        )

        with (
            chdir(repo),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=all_live_prs,
            ),
            mock.patch.object(
                propagate_mod,
                "pull_request_by_number",
                side_effect=live_pr,
            ),
            mock.patch.object(
                propagate_mod,
                "edit_pull_request",
                side_effect=edit_pr,
            ),
        ):
            propagate_mod.propagate_from_live(
                source="feature/report",
                base="main",
                pr_number=102,
                index=None,
                strategy="rebase",
                remote="upstream",
                dry_run=False,
                authority_acknowledged=True,
            )

        clone = self.temp_dir / "post-recovery-merge"
        helpers.run(self.temp_dir, "git", "clone", str(bare), str(clone))
        helpers.run(clone, "git", "remote", "add", "upstream", str(bare))
        helpers.run(clone, "git", "fetch", "upstream")
        chain = adopt_legacy_chain(
            source_branch="feature/report",
            base_branch="main",
            pull_requests=all_live_prs(),
            cwd=clone,
            remote="upstream",
            prefer_remote=True,
        )
        validation = validate_live_chain(chain, cwd=clone, remote="upstream")
        self.assertTrue(validation.valid, validation.errors)
        self.assertEqual("main", prs[103].base_branch)

        propagated_third = remote_head("feature/report-3")
        third_tree = helpers.run(
            repo, "git", "rev-parse", f"{propagated_third}^{{tree}}"
        )
        third_message = helpers.run(
            repo,
            "git",
            "show",
            "-s",
            "--format=%B",
            propagated_third,
        )
        forged_third = helpers.run(
            repo,
            "git",
            "commit-tree",
            third_tree,
            "-p",
            source_sha,
            input_text=third_message,
        )
        helpers.run(
            repo,
            "git",
            "push",
            "upstream",
            f"{forged_third}:refs/heads/feature/report-3",
            f"--force-with-lease=refs/heads/feature/report-3:{propagated_third}",
        )
        helpers.run(clone, "git", "fetch", "upstream", "--prune")

        with self.assertRaisesRegex(RehydrationError, "cannot prove"):
            adopt_legacy_chain(
                source_branch="feature/report",
                base_branch="main",
                pull_requests=all_live_prs(),
                cwd=clone,
                remote="upstream",
                prefer_remote=True,
            )

    def test_recovery_rejects_original_source_mutation(self) -> None:
        helpers.run(self.repo, "git", "checkout", "feature/report")
        (self.repo / "mutated.txt").write_text("forbidden source advance\n")
        helpers.run(self.repo, "git", "add", "mutated.txt")
        helpers.commit(self.repo, "mutate original source")
        helpers.run(self.repo, "git", "push", "origin", "feature/report")

        with self.assertRaisesRegex(CommandError, "moved from"):
            self._run_recovery()

    def test_recovery_rejects_a_local_only_successor_before_remote_mutation(
        self,
    ) -> None:
        suffix_before = self._remote_head("feature/report-2")
        body_before = self.prs[102].body
        helpers.run(
            self.repo,
            "git",
            "push",
            "origin",
            "--delete",
            "feature/report-corrected",
        )

        with self.assertRaisesRegex(CommandError, "unavailable"):
            self._run_recovery()

        self.assertEqual(suffix_before, self._remote_head("feature/report-2"))
        self.assertEqual(body_before, self.prs[102].body)

    def test_recovery_rejects_stale_cached_successor_ref_before_remote_mutation(
        self,
    ) -> None:
        suffix_before = self._remote_head("feature/report-2")
        body_before = self.prs[102].body
        helpers.run(
            self.repo,
            "git",
            "config",
            "--replace-all",
            "remote.origin.fetch",
            "+refs/heads/main:refs/remotes/origin/main",
        )
        helpers.run(
            self.temp_dir,
            "git",
            "--git-dir",
            str(self.bare),
            "update-ref",
            "-d",
            "refs/heads/feature/report-corrected",
        )

        with self.assertRaisesRegex(CommandError, "unavailable"):
            self._run_recovery()

        self.assertEqual(suffix_before, self._remote_head("feature/report-2"))
        self.assertEqual(body_before, self.prs[102].body)

    def test_recovery_rejects_unowned_suffix_pr(self) -> None:
        self.prs[102] = PullRequestRecord(
            **{**self.prs[102].__dict__, "is_cross_repository": True}
        )

        with self.assertRaisesRegex(CommandError, "fork"):
            self._run_recovery()

    def test_recovery_rejects_legacy_head_without_pr_metadata(self) -> None:
        self.prs[102] = PullRequestRecord(
            **{**self.prs[102].__dict__, "body": "Position 2\n"}
        )
        suffix_before = self._remote_head("feature/report-2")
        body_before = self.prs[102].body

        with self.assertRaisesRegex(CommandError, "lacks required legacy metadata"):
            self._run_recovery()

        self.assertEqual(suffix_before, self._remote_head("feature/report-2"))
        self.assertEqual(body_before, self.prs[102].body)

    def test_recovery_enforces_exact_remote_lease_after_reauthorization(self) -> None:
        actual = recovery_mod.remote_branch_head
        calls = 0

        def move_before_push(remote: str, branch: str) -> str | None:
            nonlocal calls
            calls += 1
            if branch == "feature/report-2" and calls >= 3:
                return "d" * 40
            return actual(remote, branch)

        with (
            chdir(self.repo),
            mock.patch.object(
                recovery_mod,
                "pull_requests_for_source",
                side_effect=self._all_live_prs,
            ),
            mock.patch.object(
                recovery_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(recovery_mod, "remote_branch_head", move_before_push),
            mock.patch.object(propagate_mod, "remote_branch_head", move_before_push),
            mock.patch.object(
                recovery_mod,
                "push_changeset_branch",
                wraps=recovery_mod.push_changeset_branch,
            ),
            mock.patch.object(
                recovery_mod, "edit_pull_request", side_effect=self._edit
            ),
            mock.patch.object(recovery_mod, "_verify_merged_on_base"),
        ):
            with self.assertRaisesRegex(CommandError, "moved from"):
                recover_suffix_from_live(
                    source="feature/report",
                    base="main",
                    from_index=2,
                    successor_branch="feature/report-corrected",
                    successor_sha=self.successor_sha,
                    remote="origin",
                    dry_run=False,
                    authority_acknowledged=True,
                )

    def test_interrupted_branch_update_resumes_from_live_state(self) -> None:
        interrupted_head = self._interrupt_after_v3_branch_update()
        self.assertNotEqual(self.fixed_head, interrupted_head)
        self.assertIn("carve-changesets:metadata", self.prs[102].body)

        output = self._run_recovery()

        self.assertEqual(interrupted_head, self._remote_head("feature/report-2"))
        self.assertEqual("Position 2\n", self.prs[102].body)
        self.assertNotIn("carve-changesets:metadata", self.prs[102].body)
        self.assertIn("Suffix recovery completed", output)

    def test_interrupted_resume_rejects_unproven_same_metadata_predecessor(
        self,
    ) -> None:
        older_same_metadata = helpers.run(
            self.repo, "git", "rev-parse", f"{self.fixed_head}^"
        )
        forged_head = self._push_v3_with_legacy_body(
            recovery_from_head=older_same_metadata
        )
        self.prs[102] = PullRequestRecord(
            **{**self.prs[102].__dict__, "body": "Position 2\n"}
        )
        body_before = self.prs[102].body

        with self.assertRaisesRegex(CommandError, "cannot prove|unsupported"):
            self._run_recovery()

        self.assertEqual(forged_head, self._remote_head("feature/report-2"))
        self.assertEqual(body_before, self.prs[102].body)

    def test_interrupted_resume_allows_retired_marker_text_in_human_prose(
        self,
    ) -> None:
        interrupted_head = self._push_v3_with_legacy_body(
            recovery_from_head=self.fixed_head
        )
        prose = "Position 2 removes carve-changesets:metadata blocks.\n"
        self.prs[102] = PullRequestRecord(**{**self.prs[102].__dict__, "body": prose})

        output = self._run_recovery()

        self.assertEqual(interrupted_head, self._remote_head("feature/report-2"))
        self.assertEqual(prose, self.prs[102].body)
        self.assertIn("Suffix recovery completed", output)

    def test_interrupted_resume_rejects_conflicting_legacy_pr_evidence(self) -> None:
        pushed_head = self._push_v3_with_legacy_body(recovery_from_head=self.fixed_head)
        conflicting = ChangesetMetadata(
            "foreign-part",
            2,
            "feature/report",
            self.source_sha,
        )
        self.prs[102] = PullRequestRecord(
            **{
                **self.prs[102].__dict__,
                "body": embed_pr_metadata("Tampered position 2\n", conflicting),
            }
        )
        body_before = self.prs[102].body

        with self.assertRaisesRegex(CommandError, "unsupported|cannot prove"):
            self._run_recovery()

        self.assertEqual(pushed_head, self._remote_head("feature/report-2"))
        self.assertEqual(body_before, self.prs[102].body)

    def test_interrupted_resume_requires_exact_predecessor_pr_evidence(self) -> None:
        pushed_head = self._push_v3_with_legacy_body(recovery_from_head=self.fixed_head)
        wrong_position = ChangesetMetadata(
            "part-2",
            3,
            "feature/report",
            self.source_sha,
        )
        self.prs[102] = PullRequestRecord(
            **{
                **self.prs[102].__dict__,
                "body": embed_pr_metadata("Tampered position 2\n", wrong_position),
            }
        )
        body_before = self.prs[102].body

        with self.assertRaisesRegex(CommandError, "cannot prove"):
            self._run_recovery()

        self.assertEqual(pushed_head, self._remote_head("feature/report-2"))
        self.assertEqual(body_before, self.prs[102].body)

    def test_interrupted_resume_rejects_malformed_legacy_pr_evidence(self) -> None:
        pushed_head = self._push_v3_with_legacy_body(recovery_from_head=self.fixed_head)
        malformed = (
            "Tampered position 2\n\n"
            "<!-- carve-changesets:metadata:v1\n"
            "{not-json}\n"
            "-->\n"
        )
        self.prs[102] = PullRequestRecord(
            **{**self.prs[102].__dict__, "body": malformed}
        )

        with self.assertRaisesRegex(CommandError, "unsupported|cannot prove"):
            self._run_recovery()

        self.assertEqual(pushed_head, self._remote_head("feature/report-2"))
        self.assertEqual(malformed, self.prs[102].body)


if __name__ == "__main__":
    unittest.main()
