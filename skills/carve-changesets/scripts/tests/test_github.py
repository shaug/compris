from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import github as github_mod  # noqa: E402
import publication as publication_mod  # noqa: E402
from chain import create_chain  # noqa: E402
from common import CommandError  # noqa: E402
from legacy_helpers import (  # noqa: E402
    chdir,
    commit,
    init_remote,
    init_repo,
    run,
)
from metadata import (  # noqa: E402
    ChangesetMetadata,
    SourceIdentity,
    stamp_commit_message,
)


class GithubTests(unittest.TestCase):
    def test_shared_pr_decoder_reports_operation_context(self) -> None:
        with self.assertRaisesRegex(
            CommandError, "changeset PR for feature/test-2.*valid PR number"
        ):
            github_mod._pull_request_record(
                {"number": "not-a-number"},
                context="changeset PR for feature/test-2",
            )

    def test_pr_merge_fences_the_exact_number_and_head(self) -> None:
        with (
            mock.patch.object(
                github_mod,
                "github_repo_for_remote",
                return_value="github.com/acme/widgets",
            ),
            mock.patch.object(github_mod, "ensure_gh_ready"),
            mock.patch.object(github_mod, "gh_capture") as capture,
        ):
            github_mod.merge_pull_request(
                94,
                expected_head="a" * 40,
                method="squash",
                remote="origin",
                dry_run=False,
            )

        self.assertEqual(
            (
                "pr",
                "merge",
                "94",
                "-R",
                "github.com/acme/widgets",
                "--squash",
                "--match-head-commit",
                "a" * 40,
            ),
            capture.call_args.args[0],
        )

    def test_issue_33_pr_edit_targets_explicit_number(self) -> None:
        with (
            mock.patch.object(
                github_mod,
                "github_repo_for_remote",
                return_value="github.com/acme/widgets",
            ),
            mock.patch.object(github_mod, "ensure_gh_ready"),
            mock.patch.object(github_mod, "gh_capture") as capture,
        ):
            github_mod.edit_pull_request(
                93,
                remote="origin",
                base="main",
                title="Feature (2 of 3)",
                dry_run=False,
            )

        self.assertEqual(
            (
                "pr",
                "edit",
                "93",
                "-R",
                "github.com/acme/widgets",
                "--base",
                "main",
                "--title",
                "Feature (2 of 3)",
            ),
            capture.call_args.args[0],
        )

    def test_recovery_pr_edit_uses_body_file_for_exact_number(self) -> None:
        with (
            mock.patch.object(
                github_mod,
                "github_repo_for_remote",
                return_value="github.com/acme/widgets",
            ),
            mock.patch.object(github_mod, "ensure_gh_ready"),
            mock.patch.object(github_mod, "gh_capture") as capture,
        ):
            github_mod.edit_pull_request(
                93,
                remote="origin",
                body="updated metadata body",
                dry_run=False,
            )

        args = capture.call_args.args[0]
        self.assertEqual(("pr", "edit", "93"), args[:3])
        self.assertIn("--body-file", args)
        self.assertNotIn("--body", args)

    def test_pr_create_dry_run_uses_body_file(self) -> None:
        repo_dir, plan = init_repo()
        try:
            with chdir(repo_dir):
                create_chain(plan)
                captured: list[tuple[str, ...]] = []
                with (
                    mock.patch.object(
                        github_mod,
                        "github_repo_for_remote",
                        return_value="github.com/acme/widgets",
                    ),
                    mock.patch.object(
                        github_mod, "_print_command", side_effect=captured.append
                    ),
                ):
                    github_mod.pr_create(plan, indices=[1, 2], dry_run=True)

            self.assertEqual(2, len(captured))
            for command in captured:
                self.assertEqual(("gh", "pr", "create"), command[:3])
                self.assertIn("github.com/acme/widgets", command)
                self.assertIn("--body-file", command)
                self.assertNotIn("--body", command)
        finally:
            shutil.rmtree(repo_dir)

    def test_pr_create_rejects_legacy_head_before_gh(self) -> None:
        repo_dir, plan = init_repo()
        try:
            with chdir(repo_dir):
                create_chain(plan)
                source_sha = run(
                    ["git", "rev-parse", "feature/test"], cwd=repo_dir
                ).stdout.strip()
                run(["git", "checkout", "feature/test-1"], cwd=repo_dir)
                message = stamp_commit_message(
                    "cs1",
                    ChangesetMetadata("a-only", 1, "feature/test", source_sha),
                )
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8"
                ) as message_file:
                    message_file.write(message)
                    message_file.flush()
                    run(
                        ["git", "commit", "--amend", "-F", message_file.name],
                        cwd=repo_dir,
                    )

                with (
                    mock.patch.object(
                        github_mod,
                        "github_repo_for_remote",
                        return_value="github.com/acme/widgets",
                    ),
                    mock.patch.object(github_mod, "ensure_gh_ready") as auth,
                    mock.patch.object(github_mod, "gh_capture") as create_call,
                ):
                    with self.assertRaisesRegex(CommandError, "native v3"):
                        github_mod.pr_create(
                            plan, indices=[1], dry_run=True, remote="origin"
                        )

            auth.assert_not_called()
            create_call.assert_not_called()
        finally:
            shutil.rmtree(repo_dir)

    def test_gh_capture_wraps_missing_executable(self) -> None:
        with mock.patch("github.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(CommandError, "not found"):
                github_mod.gh_capture(("auth", "status"))

    def test_gh_capture_allows_only_named_return_codes(self) -> None:
        error = subprocess.CalledProcessError(
            4, ["gh", "example"], output="allowed", stderr="detail"
        )
        with mock.patch("github.subprocess.run", side_effect=error):
            stdout, stderr = github_mod.gh_capture(
                ("example",), allowed_returncodes=(4,)
            )
        self.assertEqual("allowed", stdout)
        self.assertEqual("detail", stderr)

        with mock.patch("github.subprocess.run", side_effect=error):
            with self.assertRaisesRegex(CommandError, "GitHub CLI command failed"):
                github_mod.gh_capture(("example",))

    def test_pr_create_binds_and_verifies_exact_remote_candidate(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                run(["git", "push", "origin", "feature/test"], cwd=repo_dir)
                run(["git", "push", "origin", "feature/test-1"], cwd=repo_dir)
                head = run(
                    ["git", "rev-parse", "feature/test-1"], cwd=repo_dir
                ).stdout.strip()
                body = github_mod.pr_body_for(
                    plan, 1, len(plan["changesets"]), plan["changesets"][0]
                )
                title = github_mod.pr_title_for(
                    plan["feature_title"], 1, len(plan["changesets"])
                )
                created = {
                    "number": 91,
                    "url": "https://example.test/pr/91",
                    "headRefOid": head,
                    "baseRefName": "main",
                    "title": title,
                    "body": body,
                }
                with (
                    mock.patch.object(
                        github_mod,
                        "github_repo_for_remote",
                        return_value="github.com/acme/widgets",
                    ),
                    mock.patch.object(github_mod, "ensure_gh_ready"),
                    mock.patch.object(github_mod, "gh_capture") as create_call,
                    mock.patch.object(
                        github_mod, "gh_json", return_value=created
                    ) as view,
                ):
                    github_mod.pr_create(
                        plan, indices=[1], dry_run=False, remote="origin"
                    )

            create_call.assert_called_once()
            self.assertIn("--body-file", create_call.call_args.args[0])
            self.assertEqual(
                (
                    "pr",
                    "view",
                    "feature/test-1",
                    "-R",
                    "github.com/acme/widgets",
                    "--json",
                    "number,url,headRefOid,baseRefName,title,body",
                ),
                view.call_args.args[0],
            )

            created["body"] = "GitHub replaced the submitted body.\n"
            with (
                chdir(repo_dir),
                mock.patch.object(
                    github_mod,
                    "github_repo_for_remote",
                    return_value="github.com/acme/widgets",
                ),
                mock.patch.object(github_mod, "ensure_gh_ready"),
                mock.patch.object(github_mod, "gh_capture"),
                mock.patch.object(github_mod, "gh_json", return_value=created),
            ):
                with self.assertRaisesRegex(CommandError, "body"):
                    github_mod.pr_create(
                        plan, indices=[1], dry_run=False, remote="origin"
                    )

            created["body"] = body
            created["title"] = "GitHub replaced the submitted title"
            with (
                chdir(repo_dir),
                mock.patch.object(
                    github_mod,
                    "github_repo_for_remote",
                    return_value="github.com/acme/widgets",
                ),
                mock.patch.object(github_mod, "ensure_gh_ready"),
                mock.patch.object(github_mod, "gh_capture"),
                mock.patch.object(github_mod, "gh_json", return_value=created),
            ):
                with self.assertRaisesRegex(CommandError, "title"):
                    github_mod.pr_create(
                        plan, indices=[1], dry_run=False, remote="origin"
                    )
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_pr_create_rechecks_lineage_after_creation(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                run(["git", "push", "origin", "feature/test"], cwd=repo_dir)
                run(["git", "push", "origin", "feature/test-1"], cwd=repo_dir)
                head = run(
                    ["git", "rev-parse", "feature/test-1"], cwd=repo_dir
                ).stdout.strip()
                body = github_mod.pr_body_for(
                    plan, 1, len(plan["changesets"]), plan["changesets"][0]
                )
                title = github_mod.pr_title_for(
                    plan["feature_title"], 1, len(plan["changesets"])
                )
                created = {
                    "number": 96,
                    "url": "https://example.test/pr/96",
                    "headRefOid": head,
                    "baseRefName": "main",
                    "title": title,
                    "body": body,
                }

                def create_then_delete_source(_args) -> tuple[str, str]:
                    run(
                        ["git", "push", "origin", "--delete", "feature/test"],
                        cwd=repo_dir,
                    )
                    return "", ""

                with (
                    mock.patch.object(
                        github_mod,
                        "github_repo_for_remote",
                        return_value="github.com/acme/widgets",
                    ),
                    mock.patch.object(github_mod, "ensure_gh_ready"),
                    mock.patch.object(
                        github_mod,
                        "gh_capture",
                        side_effect=create_then_delete_source,
                    ),
                    mock.patch.object(github_mod, "gh_json", return_value=created),
                ):
                    with self.assertRaisesRegex(CommandError, "source.*unavailable"):
                        github_mod.pr_create(
                            plan, indices=[1], dry_run=False, remote="origin"
                        )
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_pr_create_rejects_a_different_stamped_remote_before_gh(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan, remote="upstream")
                run(["git", "push", "origin", "feature/test"], cwd=repo_dir)
                run(["git", "push", "origin", "feature/test-1"], cwd=repo_dir)
                with (
                    mock.patch.object(
                        github_mod,
                        "github_repo_for_remote",
                        return_value="github.com/acme/widgets",
                    ),
                    mock.patch.object(github_mod, "ensure_gh_ready") as auth,
                    mock.patch.object(github_mod, "gh_capture") as create_call,
                ):
                    with self.assertRaisesRegex(CommandError, "records remote"):
                        github_mod.pr_create(
                            plan, indices=[1], dry_run=False, remote="origin"
                        )

            auth.assert_not_called()
            create_call.assert_not_called()
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_pr_create_rejects_non_exact_remote_lineage_response_before_gh(
        self,
    ) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                for branch in ("feature/test", "feature/test-1", "feature/test-2"):
                    run(["git", "push", "origin", branch], cwd=repo_dir)
                source_sha = run(
                    ["git", "rev-parse", "feature/test"], cwd=repo_dir
                ).stdout.strip()
                actual_git = publication_mod.git

                def duplicate_remote_ref(*args, **kwargs):
                    if (
                        args[0] == "ls-remote"
                        and args[-1] == "refs/heads/feature/test-1"
                    ):
                        return subprocess.CompletedProcess(
                            args,
                            0,
                            (
                                f"{source_sha}\trefs/heads/feature/test-1\n"
                                f"{source_sha}\trefs/heads/feature/test-1\n"
                            ),
                            "",
                        )
                    return actual_git(*args, **kwargs)

                with (
                    mock.patch.object(
                        github_mod,
                        "github_repo_for_remote",
                        return_value="github.com/acme/widgets",
                    ),
                    mock.patch.object(
                        publication_mod, "git", side_effect=duplicate_remote_ref
                    ),
                    mock.patch.object(github_mod, "ensure_gh_ready") as auth,
                    mock.patch.object(github_mod, "gh_capture") as create_call,
                ):
                    with self.assertRaisesRegex(CommandError, "one exact branch ref"):
                        github_mod.pr_create(
                            plan, indices=[1], dry_run=False, remote="origin"
                        )

            auth.assert_not_called()
            create_call.assert_not_called()
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_pr_create_rejects_divergent_unselected_layer_before_gh(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                run(["git", "branch", "feature/alternate", "main"], cwd=repo_dir)
                for branch in (
                    "feature/test",
                    "feature/alternate",
                    "feature/test-1",
                    "feature/test-2",
                ):
                    run(["git", "push", "origin", branch], cwd=repo_dir)

                alternate_sha = run(
                    ["git", "rev-parse", "feature/alternate"], cwd=repo_dir
                ).stdout.strip()
                run(["git", "checkout", "feature/test-2"], cwd=repo_dir)
                divergent_message = stamp_commit_message(
                    "cs2",
                    ChangesetMetadata(
                        slug="rest",
                        source_lineage=(
                            SourceIdentity(
                                "origin", "feature/alternate", alternate_sha
                            ),
                        ),
                    ),
                )
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8"
                ) as message_file:
                    message_file.write(divergent_message)
                    message_file.flush()
                    run(
                        ["git", "commit", "--amend", "-F", message_file.name],
                        cwd=repo_dir,
                    )
                run(
                    ["git", "push", "--force", "origin", "feature/test-2"],
                    cwd=repo_dir,
                )

                selected_head = run(
                    ["git", "rev-parse", "feature/test-1"], cwd=repo_dir
                ).stdout.strip()
                created = {
                    "number": 91,
                    "url": "https://example.test/pr/91",
                    "headRefOid": selected_head,
                    "baseRefName": "main",
                    "body": github_mod.pr_body_for(
                        plan, 1, len(plan["changesets"]), plan["changesets"][0]
                    ),
                }
                with (
                    mock.patch.object(
                        github_mod,
                        "github_repo_for_remote",
                        return_value="github.com/acme/widgets",
                    ),
                    mock.patch.object(github_mod, "ensure_gh_ready") as auth,
                    mock.patch.object(github_mod, "gh_capture") as create_call,
                    mock.patch.object(github_mod, "gh_json", return_value=created),
                ):
                    with self.assertRaisesRegex(
                        CommandError, "consistent source lineage"
                    ):
                        github_mod.pr_create(
                            plan, indices=[1], dry_run=False, remote="origin"
                        )

            auth.assert_not_called()
            create_call.assert_not_called()
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_non_dry_run_pr_create_executes_against_a_gh_stub(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        stub_dir = Path(tempfile.mkdtemp(prefix="carve-gh-stub-"))
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                run(["git", "push", "origin", "feature/test"], cwd=repo_dir)
                run(["git", "push", "origin", "feature/test-1"], cwd=repo_dir)
                head = run(
                    ["git", "rev-parse", "feature/test-1"], cwd=repo_dir
                ).stdout.strip()
                body = github_mod.pr_body_for(
                    plan, 1, len(plan["changesets"]), plan["changesets"][0]
                )
                title = github_mod.pr_title_for(
                    plan["feature_title"], 1, len(plan["changesets"])
                )

            stub = stub_dir / "gh"
            log_path = stub_dir / "calls.jsonl"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['GH_STUB_LOG'], 'a', encoding='utf-8') as f:\n"
                "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "if sys.argv[1:3] == ['pr', 'view']:\n"
                "    print(os.environ['GH_STUB_VIEW'])\n"
            )
            stub.chmod(0o755)
            created = {
                "number": 95,
                "url": "https://github.com/acme/widgets/pull/95",
                "headRefOid": head,
                "baseRefName": "main",
                "title": title,
                "body": body,
            }
            environment = {
                "PATH": f"{stub_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                "GH_STUB_LOG": str(log_path),
                "GH_STUB_VIEW": json.dumps(created),
            }
            with (
                chdir(repo_dir),
                mock.patch.dict(os.environ, environment),
                mock.patch.object(
                    github_mod,
                    "github_repo_for_remote",
                    return_value="github.com/acme/widgets",
                ),
            ):
                github_mod.pr_create(plan, indices=[1], dry_run=False, remote="origin")

            calls = [json.loads(line) for line in log_path.read_text().splitlines()]
            self.assertEqual(["auth", "status"], calls[0][:2])
            create_call = next(call for call in calls if call[:2] == ["pr", "create"])
            self.assertIn("--body-file", create_call)
            self.assertNotIn("--body", create_call)
            self.assertTrue(any(call[:2] == ["pr", "view"] for call in calls))
        finally:
            shutil.rmtree(repo_dir)
            shutil.rmtree(stub_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_issue_33_pr_create_rejects_local_head_not_on_remote(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
                run(["git", "push", "origin", "feature/test-1"], cwd=repo_dir)
                run(["git", "checkout", "feature/test-1"], cwd=repo_dir)
                (repo_dir / "local-only.txt").write_text("not published\n")
                run(["git", "add", "local-only.txt"], cwd=repo_dir)
                old_message = run(
                    ["git", "show", "-s", "--format=%B", "HEAD"], cwd=repo_dir
                ).stdout
                commit(repo_dir, old_message)
                with (
                    mock.patch.object(
                        github_mod,
                        "github_repo_for_remote",
                        return_value="github.com/acme/widgets",
                    ),
                    mock.patch.object(github_mod, "ensure_gh_ready"),
                    mock.patch.object(github_mod, "gh_capture") as create_call,
                ):
                    with self.assertRaisesRegex(CommandError, "differs from origin"):
                        github_mod.pr_create(
                            plan, indices=[1], dry_run=False, remote="origin"
                        )
            create_call.assert_not_called()
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_non_default_remote_binds_all_gh_pr_calls_to_its_repository(
        self,
    ) -> None:
        repo_dir, plan = init_repo()
        try:
            with chdir(repo_dir):
                run(
                    ["git", "remote", "add", "origin", "git@github.com:wrong/repo.git"],
                    cwd=repo_dir,
                )
                run(
                    [
                        "git",
                        "remote",
                        "add",
                        "release",
                        "ssh://git@github.enterprise.test/acme/widgets.git",
                    ],
                    cwd=repo_dir,
                )
                create_chain(plan, remote="release")
                head = run(
                    ["git", "rev-parse", "feature/test-1"], cwd=repo_dir
                ).stdout.strip()
                body = github_mod.pr_body_for(
                    plan, 1, len(plan["changesets"]), plan["changesets"][0]
                )
                title = github_mod.pr_title_for(
                    plan["feature_title"], 1, len(plan["changesets"])
                )
                created = {
                    "number": 92,
                    "url": "https://github.enterprise.test/acme/widgets/pull/92",
                    "headRefOid": head,
                    "baseRefName": "main",
                    "title": title,
                    "body": body,
                }
                with (
                    mock.patch.dict("os.environ", {"GH_REPO": "wrong/other"}),
                    mock.patch.object(github_mod, "ensure_gh_ready") as auth,
                    mock.patch.object(
                        github_mod, "_local_remote_head", return_value=head
                    ),
                    mock.patch.object(
                        github_mod, "verify_lineage_for_publication"
                    ) as provenance,
                    mock.patch.object(github_mod, "gh_capture") as create_call,
                    mock.patch.object(
                        github_mod, "gh_json", return_value=created
                    ) as view_call,
                ):
                    github_mod.pr_create(
                        plan, indices=[1], dry_run=False, remote="release"
                    )

                repository = "github.enterprise.test/acme/widgets"
                self.assertEqual(
                    [
                        mock.call(
                            ("feature/test-1", "feature/test-2"), remote="release"
                        ),
                        mock.call(
                            ("feature/test-1", "feature/test-2"), remote="release"
                        ),
                    ],
                    provenance.call_args_list,
                )
                auth.assert_called_once_with(repository)
                self.assertIn(
                    ("-R", repository),
                    list(
                        zip(
                            create_call.call_args.args[0],
                            create_call.call_args.args[0][1:],
                        )
                    ),
                )
                self.assertIn(
                    ("-R", repository),
                    list(
                        zip(
                            view_call.call_args.args[0],
                            view_call.call_args.args[0][1:],
                        )
                    ),
                )

                with mock.patch.object(
                    github_mod, "gh_json", return_value=[]
                ) as list_call:
                    self.assertEqual(
                        [],
                        github_mod.pull_requests_for_source(
                            plan["source_branch"], remote="release"
                        ),
                    )
                self.assertIn(
                    ("-R", repository),
                    list(
                        zip(
                            list_call.call_args.args[0],
                            list_call.call_args.args[0][1:],
                        )
                    ),
                )
        finally:
            shutil.rmtree(repo_dir)


if __name__ == "__main__":
    unittest.main()
