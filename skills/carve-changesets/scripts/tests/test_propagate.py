from __future__ import annotations

import shutil
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import helpers
import propagate as propagate_mod
from chain import create_chain
from cli import cmd_merge_propagate
from common import CommandError
from legacy_helpers import chdir, init_remote, init_repo, run
from metadata import (
    ChangesetMetadata,
    SourceIdentity,
    embed_pr_metadata,
    stamp_commit_message,
)
from propagate import (
    merge_propagate_from_live,
    propagate_from_live,
    push_chain,
    push_changeset_branch,
)
from rehydrate import ChangesetRecord, PullRequestRecord


class PushChainTests(unittest.TestCase):
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
            mock.patch.object(propagate_mod, "_is_ancestor", return_value=False),
            mock.patch.object(propagate_mod, "git", side_effect=git_result),
        ):
            predecessor = propagate_mod._durable_predecessor(record, previous)

        self.assertEqual(historical, predecessor)

    def test_native_downstream_verification_uses_exact_head_not_pr_body(self) -> None:
        head = "a" * 40
        metadata = ChangesetMetadata(
            slug="payments",
            source_lineage=(SourceIdentity("origin", "feature/source", head),),
        )
        record = ChangesetRecord(
            metadata=metadata,
            branch="feature/source-1",
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
                propagate_mod, "pull_request_by_number", return_value=pull_request
            ),
            mock.patch.object(propagate_mod, "remote_branch_head", return_value=head),
        ):
            verified = propagate_mod._verify_live_downstream(
                record,
                expected_remote_head=head,
                allowed_bases={"main"},
                remote="origin",
            )

        self.assertEqual(pull_request, verified)

    def test_propagation_push_rejects_remote_head_moved_since_rehydration(self) -> None:
        with (
            mock.patch("propagate.remote_branch_head", return_value="b" * 40),
            mock.patch("propagate.git") as git_call,
        ):
            with self.assertRaisesRegex(CommandError, "moved from verified head"):
                push_changeset_branch(
                    "feature/test-2",
                    remote="origin",
                    dry_run=False,
                    expected_remote_head="a" * 40,
                )

        git_call.assert_not_called()

    def test_issue_30_and_33_push_chain_never_pushes_base_or_source(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                pushed: list[str] = []
                with mock.patch(
                    "propagate.push_changeset_branch",
                    side_effect=lambda branch, **_kwargs: pushed.append(branch),
                ):
                    push_chain(plan, remote="origin", dry_run=True)

            self.assertEqual(["feature/test-1", "feature/test-2"], pushed)
            self.assertNotIn(plan["base_branch"], pushed)
            self.assertNotIn(plan["source_branch"], pushed)
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)


class StatelessPropagationTests(unittest.TestCase):
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
        (self.repo / "third.txt").write_text("third source part\n")
        helpers.run(self.repo, "git", "add", "second.txt", "third.txt")
        self.source_sha = helpers.commit(self.repo, "complete source")
        helpers.run(self.repo, "git", "push", "--force", "origin", "feature/report")

        self.prs: dict[int, PullRequestRecord] = {}
        previous = "main"
        for index, filename in (
            (1, "source.txt"),
            (2, "second.txt"),
            (3, "third.txt"),
        ):
            branch = f"feature/report-{index}"
            helpers.run(self.repo, "git", "checkout", "-b", branch, previous)
            content = helpers.run(
                self.repo, "git", "show", f"feature/report:{filename}"
            )
            (self.repo / filename).write_text(content + "\n")
            helpers.run(self.repo, "git", "add", filename)
            metadata = ChangesetMetadata(
                slug=f"part-{index}",
                index=index,
                source_branch="feature/report",
                source_sha=self.source_sha,
            )
            head = helpers.commit(
                self.repo,
                stamp_commit_message(f"feat: changeset {index}", metadata),
            )
            helpers.run(self.repo, "git", "push", "-u", "origin", branch)
            self.prs[100 + index] = PullRequestRecord(
                number=100 + index,
                head_branch=branch,
                head_sha=head,
                base_branch=("main" if index == 1 else f"feature/report-{index - 1}"),
                state="OPEN",
                body=embed_pr_metadata("## Overall Feature\n\nReport API\n", metadata),
                title=f"Report API ({index} of 1)",
            )
            previous = branch

        state = self.repo / ".carve-changesets"
        state.mkdir()
        (state / "plan.json").write_text("{}\n")
        shutil.rmtree(state)
        helpers.run(self.repo, "git", "checkout", "feature/report")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _live_pr(self, number: int, **_kwargs) -> PullRequestRecord:
        pr = self.prs[number]
        remote_output = helpers.run(
            self.repo,
            "git",
            "ls-remote",
            "origin",
            f"refs/heads/{pr.head_branch}",
        )
        remote_head = remote_output.split()[0] if remote_output else pr.head_sha
        return PullRequestRecord(**{**pr.__dict__, "head_sha": remote_head})

    def _merge(self, number: int, **_kwargs) -> None:
        self.assertEqual(101, number)
        original = helpers.run(self.repo, "git", "branch", "--show-current")
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(
            self.repo, "git", "merge", "--no-ff", "--no-edit", "feature/report-1"
        )
        merge_sha = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(self.repo, "git", "push", "origin", "main")
        helpers.run(self.repo, "git", "checkout", original)
        self.prs[number] = PullRequestRecord(
            **{
                **self.prs[number].__dict__,
                "state": "MERGED",
                "merge_sha": merge_sha,
            }
        )

    def _edit(self, number: int, *, base=None, title=None, **_kwargs) -> None:
        pr = self.prs[number]
        self.prs[number] = PullRequestRecord(
            **{
                **pr.__dict__,
                "base_branch": base or pr.base_branch,
                "title": title or pr.title,
            }
        )

    def _all_live_prs(self) -> list[PullRequestRecord]:
        return [self._live_pr(number) for number in sorted(self.prs)]

    def _fresh_clone(self, name: str) -> Path:
        clone = self.temp_dir / name
        helpers.run(self.temp_dir, "git", "clone", str(self.bare), str(clone))
        helpers.run(clone, "git", "config", "user.name", "Carve Tests")
        helpers.run(clone, "git", "config", "user.email", "carve@example.test")
        return clone

    def _run_combined(self, strategy: str, *, through_cli: bool = False) -> None:
        real_push = propagate_mod.push_changeset_branch
        with (
            chdir(self.repo),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=lambda *_args, **_kwargs: [
                    self._live_pr(101),
                    self._live_pr(102),
                    self._live_pr(103),
                ],
            ),
            mock.patch.object(
                propagate_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(
                propagate_mod, "merge_pull_request", side_effect=self._merge
            ),
            mock.patch.object(
                propagate_mod, "edit_pull_request", side_effect=self._edit
            ) as edit,
            mock.patch.object(
                propagate_mod, "push_changeset_branch", wraps=real_push
            ) as push,
        ):
            if through_cli:
                cmd_merge_propagate(
                    Namespace(
                        source="feature/report",
                        base="main",
                        pr=101,
                        index=None,
                        strategy=strategy,
                        method="merge",
                        remote="origin",
                        dry_run=False,
                        ack_merge_and_propagate=True,
                    )
                )
            else:
                merge_propagate_from_live(
                    source="feature/report",
                    base="main",
                    pr_number=None,
                    index=1,
                    strategy=strategy,
                    method="merge",
                    remote="origin",
                    dry_run=False,
                    authority_acknowledged=True,
                )

        self.assertFalse((self.repo / ".carve-changesets").exists())
        main = helpers.run(self.repo, "git", "ls-remote", "origin", "refs/heads/main")
        branch_one = helpers.run(
            self.repo,
            "git",
            "ls-remote",
            "origin",
            "refs/heads/feature/report-1",
        )
        branch_two = helpers.run(
            self.repo,
            "git",
            "ls-remote",
            "origin",
            "refs/heads/feature/report-2",
        )
        branch_three = helpers.run(
            self.repo,
            "git",
            "ls-remote",
            "origin",
            "refs/heads/feature/report-3",
        )
        self.assertEqual(self.prs[101].merge_sha, main.split()[0])
        self.assertEqual(self.prs[101].head_sha, branch_one.split()[0])
        self.assertEqual(self._live_pr(102).head_sha, branch_two.split()[0])
        self.assertEqual(self._live_pr(103).head_sha, branch_three.split()[0])
        self.assertTrue(
            helpers.run(
                self.repo,
                "git",
                "merge-base",
                "--is-ancestor",
                main.split()[0],
                branch_two.split()[0],
            )
            == ""
        )
        self.assertEqual("main", self.prs[102].base_branch)
        self.assertEqual("feature/report-2", self.prs[103].base_branch)
        self.assertEqual("Report API (2 of 3)", self.prs[102].title)
        self.assertEqual("Report API (3 of 3)", self.prs[103].title)
        self.assertEqual([102, 103], [call.args[0] for call in edit.call_args_list])
        self.assertEqual(
            ["feature/report-2", "feature/report-3"],
            [call.args[0] for call in push.call_args_list],
        )

    def test_issue_33_combined_merge_then_propagate_rehydrates_and_rebases(
        self,
    ) -> None:
        self._run_combined("rebase", through_cli=True)

    def test_merge_propagate_supports_cherry_pick(self) -> None:
        self._run_combined("cherry-pick")

    def test_propagate_resumes_after_remote_merge_without_local_state(self) -> None:
        self._merge(101)
        with (
            chdir(self.repo),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=lambda *_args, **_kwargs: [
                    self._live_pr(101),
                    self._live_pr(102),
                    self._live_pr(103),
                ],
            ),
            mock.patch.object(
                propagate_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(
                propagate_mod, "edit_pull_request", side_effect=self._edit
            ),
        ):
            propagate_from_live(
                source="feature/report",
                base="main",
                pr_number=101,
                index=None,
                strategy="rebase",
                remote="origin",
                dry_run=False,
                authority_acknowledged=True,
            )

        self.assertEqual("main", self.prs[102].base_branch)
        self.assertEqual("Report API (2 of 3)", self.prs[102].title)
        self.assertEqual("Report API (3 of 3)", self.prs[103].title)

    def test_execution_requires_authority_acknowledgement(self) -> None:
        with chdir(self.repo):
            with self.assertRaisesRegex(CommandError, "ack-merge-and-propagate"):
                merge_propagate_from_live(
                    source="feature/report",
                    base="main",
                    pr_number=None,
                    index=1,
                    strategy="rebase",
                    method="merge",
                    remote="origin",
                    dry_run=False,
                    authority_acknowledged=False,
                )

    def test_fresh_clone_resumes_after_merged_head_branch_is_deleted(self) -> None:
        self._merge(101)
        helpers.run(
            self.repo,
            "git",
            "push",
            "origin",
            "--delete",
            "feature/report-1",
        )
        clone = self._fresh_clone("deleted-merged-head")

        with (
            chdir(clone),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=lambda *_args, **_kwargs: self._all_live_prs(),
            ),
            mock.patch.object(
                propagate_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(
                propagate_mod, "edit_pull_request", side_effect=self._edit
            ),
        ):
            propagate_from_live(
                source="feature/report",
                base="main",
                pr_number=101,
                index=None,
                strategy="rebase",
                remote="origin",
                dry_run=False,
                authority_acknowledged=True,
            )

        self.assertEqual("main", self.prs[102].base_branch)
        self.assertEqual("Report API (3 of 3)", self.prs[103].title)

    def test_partial_propagation_resumes_only_missing_remote_work(self) -> None:
        self._merge(101)
        old_second = self._live_pr(102).head_sha
        old_third = self._live_pr(103).head_sha

        def fail_first_edit(number: int, **_kwargs) -> None:
            if number == 102:
                raise CommandError("injected edit failure")
            self._edit(number, **_kwargs)

        with (
            chdir(self.repo),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=lambda *_args, **_kwargs: self._all_live_prs(),
            ),
            mock.patch.object(
                propagate_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(
                propagate_mod, "edit_pull_request", side_effect=fail_first_edit
            ),
        ):
            with self.assertRaisesRegex(CommandError, "injected edit failure"):
                propagate_from_live(
                    source="feature/report",
                    base="main",
                    pr_number=101,
                    index=None,
                    strategy="rebase",
                    remote="origin",
                    dry_run=False,
                    authority_acknowledged=True,
                )

        self.assertNotEqual(old_second, self._live_pr(102).head_sha)
        self.assertEqual(old_third, self._live_pr(103).head_sha)
        clone = self._fresh_clone("partial-frontier")
        real_push = propagate_mod.push_changeset_branch
        with (
            chdir(clone),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=lambda *_args, **_kwargs: self._all_live_prs(),
            ),
            mock.patch.object(
                propagate_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(
                propagate_mod, "edit_pull_request", side_effect=self._edit
            ),
            mock.patch.object(
                propagate_mod, "push_changeset_branch", wraps=real_push
            ) as push,
        ):
            propagate_from_live(
                source="feature/report",
                base="main",
                pr_number=101,
                index=None,
                strategy="rebase",
                remote="origin",
                dry_run=False,
                authority_acknowledged=True,
            )

        self.assertEqual(
            ["feature/report-3"], [call.args[0] for call in push.call_args_list]
        )
        self.assertEqual("main", self.prs[102].base_branch)
        self.assertEqual("Report API (3 of 3)", self.prs[103].title)

    def test_pr_state_change_after_planning_withholds_force_push(self) -> None:
        self._merge(101)
        old_second = self._live_pr(102).head_sha

        def close_second(number: int, **_kwargs) -> PullRequestRecord:
            live = self._live_pr(number)
            if number == 102:
                return PullRequestRecord(**{**live.__dict__, "state": "CLOSED"})
            return live

        with (
            chdir(self.repo),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=lambda *_args, **_kwargs: self._all_live_prs(),
            ),
            mock.patch.object(
                propagate_mod, "pull_request_by_number", side_effect=close_second
            ),
        ):
            with self.assertRaisesRegex(CommandError, "changed to CLOSED"):
                propagate_from_live(
                    source="feature/report",
                    base="main",
                    pr_number=101,
                    index=None,
                    strategy="rebase",
                    remote="origin",
                    dry_run=False,
                    authority_acknowledged=True,
                )

        self.assertEqual(old_second, self._live_pr(102).head_sha)

    def test_merge_target_still_based_on_merged_predecessor_is_withheld(
        self,
    ) -> None:
        self._merge(101)
        with (
            chdir(self.repo),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=lambda *_args, **_kwargs: self._all_live_prs(),
            ),
            mock.patch.object(
                propagate_mod, "pull_request_by_number", side_effect=self._live_pr
            ),
            mock.patch.object(propagate_mod, "merge_pull_request") as merge,
        ):
            with self.assertRaisesRegex(
                CommandError, "Resume propagation for the preceding merged changeset"
            ):
                merge_propagate_from_live(
                    source="feature/report",
                    base="main",
                    pr_number=None,
                    index=2,
                    strategy="rebase",
                    method="merge",
                    remote="origin",
                    dry_run=False,
                    authority_acknowledged=True,
                )

        merge.assert_not_called()
        self.assertEqual("OPEN", self.prs[102].state)
        self.assertEqual("feature/report-1", self.prs[102].base_branch)

    def test_concurrent_unrelated_retarget_withholds_push_and_edit(self) -> None:
        self._merge(101)
        local_second = helpers.run(
            self.repo, "git", "rev-parse", "refs/heads/feature/report-2"
        )

        def retarget_second(number: int, **_kwargs) -> PullRequestRecord:
            live = self._live_pr(number)
            if number == 102:
                return PullRequestRecord(
                    **{**live.__dict__, "base_branch": "release/unrelated"}
                )
            return live

        with (
            chdir(self.repo),
            mock.patch.object(
                propagate_mod,
                "pull_requests_for_source",
                side_effect=lambda *_args, **_kwargs: self._all_live_prs(),
            ),
            mock.patch.object(
                propagate_mod, "pull_request_by_number", side_effect=retarget_second
            ),
            mock.patch.object(propagate_mod, "push_changeset_branch") as push,
            mock.patch.object(propagate_mod, "edit_pull_request") as edit,
        ):
            with self.assertRaisesRegex(CommandError, "release/unrelated"):
                propagate_from_live(
                    source="feature/report",
                    base="main",
                    pr_number=101,
                    index=None,
                    strategy="rebase",
                    remote="origin",
                    dry_run=False,
                    authority_acknowledged=True,
                )

        push.assert_not_called()
        edit.assert_not_called()
        self.assertEqual(
            local_second,
            helpers.run(self.repo, "git", "rev-parse", "refs/heads/feature/report-2"),
        )

    def test_push_chain_uses_exact_refspecs_and_leases(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                push_chain(plan, remote="origin", dry_run=False)

            for branch in ("feature/test-1", "feature/test-2"):
                remote = run(
                    ["git", "ls-remote", "origin", f"refs/heads/{branch}"],
                    cwd=repo_dir,
                ).stdout.strip()
                self.assertTrue(remote)
            base = run(
                ["git", "ls-remote", "origin", "refs/heads/main"], cwd=repo_dir
            ).stdout.strip()
            self.assertEqual("", base)
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)


if __name__ == "__main__":
    unittest.main()
