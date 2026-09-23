from __future__ import annotations

import shutil
import stat
import unittest

from common import DEFAULT_PLAN_PATH
from legacy_helpers import SCRIPTS_DIR, commit, init_remote, init_repo, run, write_plan
from metadata import parse_commit_message


class ScriptIntegrationTests(unittest.TestCase):
    def test_materialization_commands_stamp_the_selected_remote(self) -> None:
        for command in ("create-chain", "run"):
            with self.subTest(command=command):
                repo_dir, plan = init_repo()
                try:
                    cli = str(SCRIPTS_DIR / "cli.py")
                    write_plan(repo_dir / DEFAULT_PLAN_PATH, plan)
                    argv = [cli, command]
                    if command == "run":
                        argv.extend(
                            [
                                "--base",
                                plan["base_branch"],
                                "--source",
                                plan["source_branch"],
                                "--title",
                                plan["feature_title"],
                                "--skip-tests",
                                "--create-chain",
                            ]
                        )
                    argv.extend(["--remote", "upstream"])

                    run(argv, cwd=repo_dir)

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
            run([cli, "create-chain"], cwd=repo_dir)
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
            run([cli, "create-chain"], cwd=repo_dir)

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
            run([cli, "create-chain"], cwd=repo_dir)
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
            run([cli, "create-chain"], cwd=repo_dir)
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

    def test_strict_validate_rejects_different_source_history(self) -> None:
        repo_dir, plan = init_repo()
        remote_dir = None
        try:
            cli = str(SCRIPTS_DIR / "cli.py")
            plan_path = repo_dir / DEFAULT_PLAN_PATH
            remote_dir = init_remote(repo_dir)
            run(["git", "push", "origin", "main", "feature/test"], cwd=repo_dir)
            write_plan(plan_path, plan)
            run([cli, "create-chain"], cwd=repo_dir)
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
            self.assertIn("source_history_mismatch", result.stdout)
        finally:
            shutil.rmtree(repo_dir)
            if remote_dir is not None:
                shutil.rmtree(remote_dir.parent)


if __name__ == "__main__":
    unittest.main()
