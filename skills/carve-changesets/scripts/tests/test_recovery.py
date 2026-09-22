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
    parse_pr_metadata,
    stamp_commit_message,
)
from recovery import recover_suffix_from_live
from rehydrate import ChangesetRecord, PullRequestRecord, rehydrate_chain
from validate import validate_live_chain


class SuffixRecoveryTests(unittest.TestCase):
    def test_durable_predecessor_normalizes_selected_non_origin_remote(self) -> None:
        root = SourceIdentity("upstream", "feature/report", "a" * 40)
        previous_metadata = ChangesetMetadata(
            "part-1",
            1,
            root.branch,
            root.sha,
            source_lineage=(root,),
            marker_version=1,
        )
        previous = ChangesetRecord(
            previous_metadata,
            "feature/report-1",
            "b" * 40,
            "main",
        )
        record = ChangesetRecord(
            ChangesetMetadata(
                "part-2",
                2,
                root.branch,
                root.sha,
                source_lineage=(root,),
                marker_version=1,
            ),
            "feature/report-2",
            "c" * 40,
            "feature/report-1",
        )
        historical = "d" * 40
        message = stamp_commit_message("feat: changeset 1", previous_metadata)

        def git_result(*args, **_kwargs):
            stdout = historical if args[0] == "rev-list" else message
            return mock.Mock(stdout=stdout)

        with (
            mock.patch.object(recovery_mod, "_is_ancestor", return_value=False),
            mock.patch.object(recovery_mod, "git", side_effect=git_result),
        ):
            predecessor = recovery_mod._durable_predecessor(record, previous)

        self.assertEqual(historical, predecessor)

    def test_native_suffix_verification_uses_exact_head_not_pr_body(self) -> None:
        head = "a" * 40
        lineage = (SourceIdentity("origin", "feature/report", head),)
        record = ChangesetRecord(
            metadata=ChangesetMetadata(slug="part-1", source_lineage=lineage),
            branch="feature/report-1",
            head=head,
            base="main",
            pr_number=91,
            pr_state="OPEN",
            topology_position=1,
        )
        pull_request = PullRequestRecord(
            number=91,
            head_branch=record.branch,
            head_sha=head,
            base_branch="main",
            state="OPEN",
            body="Human-readable context only.\n",
        )

        with (
            mock.patch.object(
                recovery_mod, "pull_request_by_number", return_value=pull_request
            ),
            mock.patch.object(recovery_mod, "remote_branch_head", return_value=head),
        ):
            verified = recovery_mod._verify_open_suffix_pr(
                record,
                expected_head=head,
                expected_base="main",
                target_lineage=lineage,
                remote="origin",
            )

        self.assertEqual(pull_request, verified)

    def test_source_identity_rejects_a_different_selected_remote(self) -> None:
        identity = SourceIdentity("upstream", "feature/report", "a" * 40)

        with self.assertRaisesRegex(CommandError, "records remote 'upstream'"):
            recovery_mod._resolve_identity(identity, remote="origin")

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

    def _live_pr(self, number: int, **_kwargs) -> PullRequestRecord:
        pr = self.prs[number]
        return PullRequestRecord(
            **{
                **pr.__dict__,
                "head_sha": self._remote_head(pr.head_branch),
            }
        )

    def _all_live_prs(self, *_args, **_kwargs) -> list[PullRequestRecord]:
        return [self._live_pr(number) for number in sorted(self.prs)]

    def _edit(self, number: int, *, body=None, **_kwargs) -> None:
        pr = self.prs[number]
        self.prs[number] = PullRequestRecord(
            **{**pr.__dict__, "body": body if body is not None else pr.body}
        )

    def _run_recovery(self, *, edit_side_effect=None) -> str:
        output = io.StringIO()
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
                successor_branch="feature/report-corrected",
                successor_sha=self.successor_sha,
                remote="origin",
                dry_run=False,
                authority_acknowledged=True,
            )
        return output.getvalue()

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
        self.assertEqual(self.fixed_head, metadata.recovery_from_head)
        self.assertEqual(metadata, parse_pr_metadata(self.prs[102].body))
        self.assertIn("EVIDENCE-INVALIDATED", output)

        clone = self.temp_dir / "fresh"
        helpers.run(self.temp_dir, "git", "clone", str(self.bare), str(clone))
        chain = rehydrate_chain(
            source_branch="feature/report",
            base_branch="main",
            pull_requests=self._all_live_prs(),
            cwd=clone,
        )
        validation = validate_live_chain(chain, cwd=clone)
        self.assertTrue(validation.valid, validation.errors)
        self.assertEqual(self.successor_sha, chain.source_sha)

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

        with self.assertRaisesRegex(CommandError, "unavailable on origin"):
            self._run_recovery()

        self.assertEqual(suffix_before, self._remote_head("feature/report-2"))
        self.assertEqual(body_before, self.prs[102].body)

    def test_recovery_rejects_unowned_suffix_pr(self) -> None:
        self.prs[102] = PullRequestRecord(
            **{**self.prs[102].__dict__, "is_cross_repository": True}
        )

        with self.assertRaisesRegex(CommandError, "fork"):
            self._run_recovery()

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

    def test_interrupted_metadata_update_resumes_from_live_state(self) -> None:
        failed = False

        def fail_once(number: int, *, body=None, **kwargs) -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise CommandError("injected PR metadata interruption")
            self._edit(number, body=body, **kwargs)

        with self.assertRaisesRegex(CommandError, "injected"):
            self._run_recovery(edit_side_effect=fail_once)
        pushed_head = self._remote_head("feature/report-2")
        self.assertNotEqual(self.fixed_head, pushed_head)
        self.assertEqual(
            2,
            len(
                parse_commit_message(
                    helpers.run(
                        self.repo, "git", "show", "-s", "--format=%B", pushed_head
                    )
                ).source_lineage
            ),
        )
        self.assertEqual(1, len(parse_pr_metadata(self.prs[102].body).source_lineage))

        output = self._run_recovery(edit_side_effect=fail_once)

        self.assertEqual(pushed_head, self._remote_head("feature/report-2"))
        self.assertEqual(
            parse_commit_message(
                helpers.run(self.repo, "git", "show", "-s", "--format=%B", pushed_head)
            ),
            parse_pr_metadata(self.prs[102].body),
        )
        self.assertIn("Suffix recovery completed", output)


if __name__ == "__main__":
    unittest.main()
