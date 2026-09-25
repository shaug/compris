from __future__ import annotations

import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from chain import create_chain  # noqa: E402
from cli import cmd_validate_chain, main  # noqa: E402
from common import DEFAULT_PLAN_PATH, CommandError  # noqa: E402
from gh_stack import ProfileProbeResult, reviewed_preview_profile  # noqa: E402
from legacy_helpers import (  # noqa: E402
    SCRIPTS_DIR,
    chdir,
    commit,
    init_remote,
    init_repo,
    run,
    write_plan,
)
from metadata import parse_commit_message  # noqa: E402
from rehydrate import adopt_legacy_chain as rehydrate_from_live  # noqa: E402
from validate import validate_live_chain as validate_live  # noqa: E402


class ScriptIntegrationTests(unittest.TestCase):
    def test_create_chain_adopts_exact_native_order_and_restores_checkout(self) -> None:
        repo_dir, plan = init_repo()
        fake_bin = Path(tempfile.mkdtemp(prefix="pcs-fake-gh-"))
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            run(["git", "checkout", "main"], cwd=repo_dir)
            run(["git", "push", "-u", "origin", "main"], cwd=repo_dir)
            run(["git", "checkout", plan["source_branch"]], cwd=repo_dir)
            run(
                ["git", "push", "-u", "origin", plan["source_branch"]],
                cwd=repo_dir,
            )
            plan["test_argv"] = ["python3", "-c", "print('materialized')"]
            write_plan(repo_dir / DEFAULT_PLAN_PATH, plan)
            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                """#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


git_dir = Path(git("rev-parse", "--absolute-git-dir"))
args = sys.argv[1:]
if args[:2] == ["stack", "init"]:
    base_index = args.index("--base")
    base = args[base_index + 1]
    branches = args[base_index + 2 :]
    if git("branch", "--show-current") != branches[-1]:
        raise SystemExit("native init did not run from the top layer")
    (git_dir / "gh-stack").write_text(
        json.dumps({"base": base, "branches": branches}) + "\\n"
    )
    subprocess.check_call(["git", "config", "rerere.enabled", "true"])
elif args == ["stack", "view", "--json"]:
    state = json.loads((git_dir / "gh-stack").read_text())
    predecessor = git("rev-parse", state["base"])
    layers = []
    current = git("branch", "--show-current")
    for branch in state["branches"]:
        head = git("rev-parse", branch)
        layers.append(
            {
                "name": branch,
                "head": head,
                "base": predecessor,
                "isCurrent": branch == current,
                "isMerged": False,
                "isQueued": False,
                "needsRebase": False,
                "pr": None,
            }
        )
        predecessor = head
    print(
        json.dumps(
            {
                "trunk": state["base"],
                "currentBranch": current,
                "branches": layers,
            }
        )
    )
else:
    raise SystemExit(f"unexpected fake gh argv: {args!r}")
"""
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
            profile = reviewed_preview_profile(
                "14fc42ed9b6c376a53b2f999f138d3bd26dac546"
            )
            probe = ProfileProbeResult(
                status="supported",
                observed_version=profile.version,
                observed_surfaces=(),
                profile=profile,
                blocker=None,
            )

            original_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            with (
                chdir(repo_dir),
                mock.patch.dict(os.environ, {"PATH": f"{fake_bin}:{original_path}"}),
                mock.patch("chain.probe_profile", return_value=probe, create=True),
                redirect_stdout(stdout),
            ):
                try:
                    result = main(
                        [
                            "create-chain",
                            "--plan",
                            str(DEFAULT_PLAN_PATH),
                            "--remote",
                            "origin",
                            "--ack-local-stack-state",
                        ]
                    )
                except SystemExit as exc:
                    result = int(exc.code)

            self.assertEqual(0, result, stdout.getvalue())
            self.assertEqual(
                plan["source_branch"],
                run(["git", "branch", "--show-current"], cwd=repo_dir).stdout.strip(),
            )
            native_state = json.loads(
                (
                    Path(
                        run(
                            ["git", "rev-parse", "--absolute-git-dir"], cwd=repo_dir
                        ).stdout.strip()
                    )
                    / "gh-stack"
                ).read_text()
            )
            self.assertEqual(
                ["feature/test-1", "feature/test-2"], native_state["branches"]
            )
            self.assertIn("TRUTH PHASE  materialized", stdout.getvalue())
            self.assertIn("CHAIN READY  false", stdout.getvalue())
            self.assertIn("NEXT VALIDATE  python3 ", stdout.getvalue())
            self.assertIn(
                "validate-chain --plan .carve-changesets/plan.json --remote origin "
                "--test-argv",
                stdout.getvalue(),
            )
            self.assertIn("NEXT REVIEW  layer=feature/test-1", stdout.getvalue())
            self.assertIn("NEXT REVIEW  layer=feature/test-2", stdout.getvalue())
            self.assertIn("NEXT EQUIVALENCE  python3 ", stdout.getvalue())
        finally:
            shutil.rmtree(repo_dir)
            shutil.rmtree(fake_bin)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_create_chain_interruption_preserves_layers_and_exact_resume(self) -> None:
        repo_dir, plan = init_repo()
        fake_bin = Path(tempfile.mkdtemp(prefix="pcs-failing-gh-"))
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            run(["git", "checkout", "main"], cwd=repo_dir)
            run(["git", "push", "-u", "origin", "main"], cwd=repo_dir)
            run(["git", "checkout", plan["source_branch"]], cwd=repo_dir)
            run(
                ["git", "push", "-u", "origin", plan["source_branch"]],
                cwd=repo_dir,
            )
            write_plan(repo_dir / DEFAULT_PLAN_PATH, plan)
            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                """#!/usr/bin/env python3
import sys

if sys.argv[1:3] == ["stack", "init"]:
    raise SystemExit("simulated native init interruption")
raise SystemExit(f"unexpected fake gh argv: {sys.argv[1:]!r}")
"""
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
            profile = reviewed_preview_profile(
                "14fc42ed9b6c376a53b2f999f138d3bd26dac546"
            )
            probe = ProfileProbeResult(
                status="supported",
                observed_version=profile.version,
                observed_surfaces=(),
                profile=profile,
                blocker=None,
            )

            original_path = os.environ.get("PATH", "")
            stdout = io.StringIO()
            with (
                chdir(repo_dir),
                mock.patch.dict(os.environ, {"PATH": f"{fake_bin}:{original_path}"}),
                mock.patch("chain.probe_profile", return_value=probe, create=True),
                redirect_stdout(stdout),
            ):
                result = main(
                    [
                        "create-chain",
                        "--plan",
                        str(DEFAULT_PLAN_PATH),
                        "--remote",
                        "origin",
                        "--ack-local-stack-state",
                    ]
                )

            output = stdout.getvalue()
            self.assertEqual(1, result, output)
            self.assertEqual(1, output.count("Resume exactly:"), output)
            self.assertIn(
                "create-chain --plan .carve-changesets/plan.json --remote origin "
                "--ack-local-stack-state",
                output,
            )
            self.assertEqual(
                plan["source_branch"],
                run(["git", "branch", "--show-current"], cwd=repo_dir).stdout.strip(),
            )
            for branch in ("feature/test-1", "feature/test-2"):
                self.assertEqual(
                    0,
                    run(
                        ["git", "rev-parse", "--verify", branch],
                        cwd=repo_dir,
                        check=False,
                    ).returncode,
                )
            git_dir = Path(
                run(
                    ["git", "rev-parse", "--absolute-git-dir"], cwd=repo_dir
                ).stdout.strip()
            )
            self.assertFalse((git_dir / "gh-stack").exists())
        finally:
            shutil.rmtree(repo_dir)
            shutil.rmtree(fake_bin)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_semantic_materialization_stamps_the_selected_remote(self) -> None:
        repo_dir, plan = init_repo()
        try:
            with chdir(repo_dir):
                create_chain(plan, remote="upstream")

            message = run(
                ["git", "show", "-s", "--format=%B", "feature/test-1"],
                cwd=repo_dir,
            ).stdout
            metadata = parse_commit_message(message)
            self.assertEqual("upstream", metadata.active_source.remote)
        finally:
            shutil.rmtree(repo_dir)

    def test_single_cli_exercises_ported_surface(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            plan_path = repo_dir / DEFAULT_PLAN_PATH
            remote_dir = init_remote(repo_dir)
            run(["git", "checkout", "main"], cwd=repo_dir)
            run(["git", "push", "-u", "origin", "main"], cwd=repo_dir)
            run(["git", "checkout", plan["source_branch"]], cwd=repo_dir)
            run(["git", "push", "-u", "origin", plan["source_branch"]], cwd=repo_dir)

            run(
                [
                    cli,
                    "init-plan",
                    "--base",
                    plan["base_branch"],
                    "--source",
                    plan["source_branch"],
                    "--title",
                    plan["feature_title"],
                    "--changesets",
                    "2",
                    "--force",
                ],
                cwd=repo_dir,
            )
            write_plan(plan_path, plan)
            run(
                [
                    cli,
                    "preflight",
                    "--base",
                    plan["base_branch"],
                    "--source",
                    plan["source_branch"],
                    "--skip-tests",
                ],
                cwd=repo_dir,
            )
            run([cli, "validate"], cwd=repo_dir)
            run([cli, "squash-ref"], cwd=repo_dir)
            with chdir(repo_dir):
                create_chain(plan)
            run(
                [
                    cli,
                    "status",
                    "--source",
                    plan["source_branch"],
                    "--base",
                    plan["base_branch"],
                    "--local-only",
                ],
                cwd=repo_dir,
            )
            run([cli, "squash-check"], cwd=repo_dir)
            run(
                [
                    cli,
                    "validate-chain",
                    "--test-argv",
                    '["python3", "-c", "print(\\"ok\\")"]',
                    "--local-only",
                ],
                cwd=repo_dir,
            )
            run([cli, "compare"], cwd=repo_dir)
            run([cli, "push-chain", "--remote", "origin"], cwd=repo_dir)
            run(
                [
                    "git",
                    "remote",
                    "set-url",
                    "origin",
                    "git@github.com:example/carve-eval.git",
                ],
                cwd=repo_dir,
            )
            run([cli, "pr-create"], cwd=repo_dir)
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_help_lists_mutation_class_for_every_operation(self) -> None:
        result = run([str(SCRIPTS_DIR / "cli.py"), "--help"], cwd=SCRIPTS_DIR)
        for mutation_class in ("read-only", "local-mutating", "remote-mutating"):
            self.assertIn(f"[{mutation_class}]", result.stdout)
        self.assertIn("remote mutation is dry-run", result.stdout)
        self.assertIn("by default", result.stdout)

    def test_legacy_test_command_surfaces_fail_before_branch_mutation(self) -> None:
        repo_dir, plan = init_repo()
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            marker = repo_dir / "legacy-test-command-ran"
            legacy_command = f"touch {marker}"
            branches_before = run(
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads/"],
                cwd=repo_dir,
            ).stdout
            cases = [
                (
                    "preflight",
                    [
                        "preflight",
                        "--base",
                        plan["base_branch"],
                        "--source",
                        plan["source_branch"],
                        "--test-cmd",
                        legacy_command,
                    ],
                ),
                (
                    "init-plan",
                    [
                        "init-plan",
                        "--base",
                        plan["base_branch"],
                        "--source",
                        plan["source_branch"],
                        "--title",
                        "Legacy",
                        "--test-cmd",
                        legacy_command,
                    ],
                ),
                (
                    "validate-chain",
                    ["validate-chain", "--test-cmd", legacy_command],
                ),
                (
                    "run",
                    [
                        "run",
                        "--base",
                        plan["base_branch"],
                        "--source",
                        plan["source_branch"],
                        "--title",
                        "Legacy",
                        "--test-cmd",
                        legacy_command,
                    ],
                ),
            ]
            for name, arguments in cases:
                with self.subTest(command=name):
                    result = run([cli, *arguments], cwd=repo_dir, check=False)
                    self.assertEqual(1, result.returncode)
                    self.assertIn("--test-cmd is no longer supported", result.stdout)
                    self.assertIn("--test-argv", result.stdout)
            branches_after = run(
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads/"],
                cwd=repo_dir,
            ).stdout
            self.assertEqual(branches_before, branches_after)
            self.assertFalse(marker.exists())
        finally:
            shutil.rmtree(repo_dir)

    def test_legacy_database_command_surfaces_fail_before_branch_mutation(self) -> None:
        repo_dir, _plan = init_repo()
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            marker = repo_dir / "legacy-database-command-ran"
            legacy_command = f"touch {marker}"
            branches_before = run(
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads/"],
                cwd=repo_dir,
            ).stdout
            cases = [
                (
                    "--source-cmd",
                    [
                        "db-compare",
                        "--source-cmd",
                        legacy_command,
                        "--chain-argv",
                        '["true"]',
                    ],
                    "--source-argv",
                ),
                (
                    "--chain-cmd",
                    [
                        "db-compare",
                        "--source-argv",
                        '["true"]',
                        "--chain-cmd",
                        legacy_command,
                    ],
                    "--chain-argv",
                ),
            ]
            for legacy_flag, arguments, replacement_flag in cases:
                with self.subTest(flag=legacy_flag):
                    result = run([cli, *arguments], cwd=repo_dir, check=False)
                    self.assertEqual(1, result.returncode)
                    self.assertIn(
                        f"{legacy_flag} is no longer supported", result.stdout
                    )
                    self.assertIn(replacement_flag, result.stdout)
            branches_after = run(
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads/"],
                cwd=repo_dir,
            ).stdout
            self.assertEqual(branches_before, branches_after)
            self.assertFalse(marker.exists())
        finally:
            shutil.rmtree(repo_dir)

    def test_db_compare_cli_defaults_to_ephemeral_and_accepts_explicit_legacy_retention(
        self,
    ) -> None:
        repo_dir, plan = init_repo()
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            plan_path = repo_dir / DEFAULT_PLAN_PATH
            write_plan(plan_path, plan)
            with chdir(repo_dir):
                create_chain(plan)

            default_result = run(
                [
                    cli,
                    "db-compare",
                    "--source-argv",
                    '["cat", "a.txt"]',
                    "--chain-argv",
                    '["cat", "a.txt"]',
                ],
                cwd=repo_dir,
            )
            historical_default = repo_dir / ".carve-changesets" / "db-compare"
            self.assertIn(
                "Raw comparison outputs are ephemeral.", default_result.stdout
            )
            self.assertFalse(historical_default.exists())

            retained = repo_dir / ".carve-changesets" / "legacy-retained"
            retained_result = run(
                [
                    cli,
                    "db-compare",
                    "--source-argv",
                    '["cat", "a.txt"]',
                    "--chain-argv",
                    '["cat", "a.txt"]',
                    "--out-dir",
                    str(retained),
                ],
                cwd=repo_dir,
            )
            for name in ("source.txt", "chain.txt"):
                output = retained / name
                self.assertTrue(output.is_file())
                self.assertEqual(0o600, stat.S_IMODE(output.stat().st_mode))
                self.assertIn(str(output.resolve()), retained_result.stdout)
        finally:
            shutil.rmtree(repo_dir)

    def test_malformed_test_argv_fails_before_branch_mutation(self) -> None:
        repo_dir, plan = init_repo()
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            branches_before = run(
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads/"],
                cwd=repo_dir,
            ).stdout
            result = run(
                [
                    cli,
                    "preflight",
                    "--base",
                    plan["base_branch"],
                    "--source",
                    plan["source_branch"],
                    "--test-argv",
                    "not-json",
                ],
                cwd=repo_dir,
                check=False,
            )
            branches_after = run(
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads/"],
                cwd=repo_dir,
            ).stdout
            self.assertEqual(1, result.returncode)
            self.assertIn("--test-argv must be valid JSON", result.stdout)
            self.assertEqual(branches_before, branches_after)
        finally:
            shutil.rmtree(repo_dir)

    def test_status_rehydrates_without_a_plan(self) -> None:
        repo_dir, plan = init_repo()
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            plan_path = repo_dir / DEFAULT_PLAN_PATH
            write_plan(plan_path, plan)
            with chdir(repo_dir):
                create_chain(plan)
            shutil.rmtree(plan_path.parent)

            result = run(
                [
                    cli,
                    "status",
                    "--source",
                    plan["source_branch"],
                    "--base",
                    plan["base_branch"],
                    "--local-only",
                ],
                cwd=repo_dir,
            )

            self.assertIn("feature/test-1", result.stdout)
            self.assertIn("feature/test-2", result.stdout)
        finally:
            shutil.rmtree(repo_dir)

    def test_strict_validate_rejects_a_rewritten_middle_branch(self) -> None:
        repo_dir, plan = init_repo()
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            plan_path = repo_dir / DEFAULT_PLAN_PATH
            write_plan(plan_path, plan)
            with chdir(repo_dir):
                create_chain(plan)
            message = run(
                ["git", "show", "-s", "--format=%B", "feature/test-2"],
                cwd=repo_dir,
            ).stdout
            run(["git", "checkout", "-b", "replacement", "main"], cwd=repo_dir)
            run(
                ["git", "checkout", "feature/test", "--", "a.txt", "b.txt", "c.txt"],
                cwd=repo_dir,
            )
            run(["git", "add", "a.txt", "b.txt", "c.txt"], cwd=repo_dir)
            commit(repo_dir, message)
            replacement = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
            run(
                ["git", "update-ref", "refs/heads/feature/test-2", replacement],
                cwd=repo_dir,
            )

            result = run(
                [cli, "validate", "--strict", "--local-only"],
                cwd=repo_dir,
                check=False,
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("predecessor_ancestry_broken", result.stdout)
        finally:
            shutil.rmtree(repo_dir)

    def test_strict_validate_rejects_moved_native_source_ref(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            plan_path = repo_dir / DEFAULT_PLAN_PATH
            remote_dir = init_remote(repo_dir)
            run(["git", "push", "origin", "main", "feature/test"], cwd=repo_dir)
            write_plan(plan_path, plan)
            with chdir(repo_dir):
                create_chain(plan)
            run(["git", "checkout", "-b", "alternate-source", "main"], cwd=repo_dir)
            run(
                ["git", "checkout", "feature/test", "--", "a.txt", "b.txt", "c.txt"],
                cwd=repo_dir,
            )
            run(["git", "add", "a.txt", "b.txt", "c.txt"], cwd=repo_dir)
            commit(repo_dir, "alternate source history")
            alternate = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
            run(
                ["git", "push", "--force", "origin", f"{alternate}:feature/test"],
                cwd=repo_dir,
            )

            result = run(
                [cli, "validate", "--strict", "--local-only"],
                cwd=repo_dir,
                check=False,
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("source_lineage_ref_moved", result.stdout)
            self.assertNotIn("source_history_mismatch", result.stdout)
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)

    def test_validate_chain_rejects_an_externally_moved_native_source_ref(
        self,
    ) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            remote_dir = init_remote(repo_dir)
            run(["git", "push", "origin", "main", "feature/test"], cwd=repo_dir)
            write_plan(repo_dir / DEFAULT_PLAN_PATH, plan)
            with chdir(repo_dir):
                create_chain(plan)
            cached_source = run(
                ["git", "rev-parse", "refs/remotes/origin/feature/test"],
                cwd=repo_dir,
            ).stdout.strip()
            run(
                ["git", "checkout", "-b", "external-source", "feature/test"],
                cwd=repo_dir,
            )
            (repo_dir / "external.txt").write_text("external source move\n")
            run(["git", "add", "external.txt"], cwd=repo_dir)
            commit(repo_dir, "external source move")
            moved_source = run(
                ["git", "rev-parse", "HEAD"], cwd=repo_dir
            ).stdout.strip()
            run(
                ["git", "push", "origin", "external-source:external-source"],
                cwd=repo_dir,
            )
            run(
                [
                    "git",
                    "--git-dir",
                    str(remote_dir),
                    "update-ref",
                    "refs/heads/feature/test",
                    moved_source,
                ],
                cwd=repo_dir,
            )
            self.assertEqual(
                cached_source,
                run(
                    ["git", "rev-parse", "refs/remotes/origin/feature/test"],
                    cwd=repo_dir,
                ).stdout.strip(),
            )
            run(["git", "checkout", "feature/test-2"], cwd=repo_dir)

            output = io.StringIO()
            with (
                chdir(repo_dir),
                mock.patch("cli.pull_requests_for_source", return_value=[]),
                mock.patch(
                    "cli.adopt_legacy_chain",
                    side_effect=lambda **kwargs: rehydrate_from_live(
                        cwd=repo_dir, **kwargs
                    ),
                ),
                mock.patch(
                    "cli.validate_live_chain",
                    side_effect=lambda chain, **kwargs: validate_live(
                        chain, cwd=repo_dir, **kwargs
                    ),
                ),
                redirect_stdout(output),
                self.assertRaisesRegex(CommandError, "Live chain validation failed"),
            ):
                cmd_validate_chain(
                    SimpleNamespace(
                        plan=str(repo_dir / DEFAULT_PLAN_PATH),
                        legacy_test_cmd=None,
                        test_argv='["python3", "-c", "print(\\"ok\\")"]',
                        local_only=False,
                        remote="origin",
                    )
                )

            self.assertIn("source_lineage_ref_moved", output.getvalue())
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)


if __name__ == "__main__":
    unittest.main()
