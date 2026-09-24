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
    parse_commit_message,
    stamp_commit_message,
)
from propagate import (
    merge_propagate_from_live,
    propagate_from_live,
    push_chain,
    push_changeset_branch,
)
from rehydrate import PullRequestRecord


class PushChainTests(unittest.TestCase):
    def test_push_chain_rejects_unproven_successor_lineage_before_any_push(
        self,
    ) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                source_sha = run(
                    ["git", "rev-parse", "feature/test"], cwd=repo_dir
                ).stdout.strip()
                run(
                    ["git", "branch", "feature/test-corrected", source_sha],
                    cwd=repo_dir,
                )
                for branch in ("feature/test", "feature/test-corrected"):
                    run(["git", "push", "origin", branch], cwd=repo_dir)
                lineage = (
                    SourceIdentity("origin", "feature/test", source_sha),
                    SourceIdentity("origin", "feature/test-corrected", source_sha),
                )
                for index in (1, 2):
                    branch = f"feature/test-{index}"
                    run(["git", "checkout", branch], cwd=repo_dir)
                    message = stamp_commit_message(
                        f"feat: changeset {index}",
                        ChangesetMetadata(
                            slug=f"part-{index}",
                            source_lineage=lineage,
                            recovery_from_head="f" * 40,
                        ),
                    )
                    helpers.run(
                        repo_dir,
                        "git",
                        "commit",
                        "--amend",
                        "-F",
                        "-",
                        input_text=message,
                    )

                with mock.patch("propagate.push_changeset_branch") as push:
                    with self.assertRaisesRegex(CommandError, "recover-suffix"):
                        push_chain(plan, remote="origin", dry_run=False)

            push.assert_not_called()
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_push_chain_rejects_missing_recorded_source_before_any_push(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                with mock.patch("propagate.push_changeset_branch") as push:
                    with self.assertRaisesRegex(CommandError, "is unavailable"):
                        push_chain(plan, remote="origin", dry_run=False)
            push.assert_not_called()
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_push_chain_rejects_moved_recorded_source_before_any_push(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                run(["git", "push", "origin", "feature/test"], cwd=repo_dir)
                (repo_dir / "after-carve.txt").write_text("advanced source\n")
                run(["git", "add", "after-carve.txt"], cwd=repo_dir)
                helpers.commit(repo_dir, "advance source")
                run(["git", "push", "origin", "feature/test"], cwd=repo_dir)
                with mock.patch("propagate.push_changeset_branch") as push:
                    with self.assertRaisesRegex(CommandError, "moved from"):
                        push_chain(plan, remote="origin", dry_run=False)
            push.assert_not_called()
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

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

    def test_native_human_only_prs_propagate_through_public_workflow(self) -> None:
        self._merge(101)
        human_bodies: dict[int, str] = {}
        lineage = (SourceIdentity("origin", "feature/report", self.source_sha),)

        def restamp_native(index: int) -> str:
            branch = f"feature/report-{index}"
            helpers.run(self.repo, "git", "checkout", branch)
            metadata = ChangesetMetadata(slug=f"part-{index}", source_lineage=lineage)
            helpers.run(
                self.repo,
                "git",
                "commit",
                "--amend",
                "-F",
                "-",
                input_text=stamp_commit_message(f"feat: changeset {index}", metadata),
            )
            head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
            helpers.run(
                self.repo,
                "git",
                "push",
                "--force-with-lease",
                "origin",
                branch,
            )
            human_bodies[100 + index] = f"Human context for layer {index}.\n"
            self.prs[100 + index] = PullRequestRecord(
                **{
                    **self.prs[100 + index].__dict__,
                    "head_sha": head,
                    "body": human_bodies[100 + index],
                }
            )
            return head

        old_second = self.prs[102].head_sha
        native_second = restamp_native(2)
        helpers.run(self.repo, "git", "checkout", "feature/report-3")
        helpers.run(
            self.repo,
            "git",
            "rebase",
            "--onto",
            native_second,
            old_second,
            "feature/report-3",
        )
        restamp_native(3)

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

        for number in (102, 103):
            self.assertEqual(human_bodies[number], self.prs[number].body)
            head = self._live_pr(number).head_sha
            metadata = parse_commit_message(
                helpers.run(self.repo, "git", "show", "-s", "--format=%B", head)
            )
            self.assertEqual(3, metadata.version)

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

    def test_non_origin_partial_propagation_resumes_public_workflow(self) -> None:
        self._merge(101)
        helpers.run(self.repo, "git", "remote", "add", "upstream", str(self.bare))
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
                    remote="upstream",
                    dry_run=False,
                    authority_acknowledged=True,
                )

        self.assertNotEqual(old_second, self._live_pr(102).head_sha)
        self.assertEqual(old_third, self._live_pr(103).head_sha)
        clone = self._fresh_clone("partial-frontier")
        helpers.run(clone, "git", "remote", "add", "upstream", str(self.bare))
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
                remote="upstream",
                dry_run=False,
                authority_acknowledged=True,
            )

        self.assertEqual(
            ["feature/report-3"], [call.args[0] for call in push.call_args_list]
        )
        self.assertEqual("main", self.prs[102].base_branch)
        self.assertEqual("Report API (3 of 3)", self.prs[103].title)
        third = self._live_pr(103).head_sha
        metadata = parse_commit_message(
            helpers.run(clone, "git", "show", "-s", "--format=%B", third),
            remote="upstream",
        )
        self.assertEqual("upstream", metadata.root_source.remote)

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
                run(["git", "push", "origin", "feature/test"], cwd=repo_dir)
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
