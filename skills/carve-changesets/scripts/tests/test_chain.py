from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import helpers  # noqa: E402,F401
from chain import compare_chain, create_chain, validate_chain  # noqa: E402
from common import CommandError  # noqa: E402
from legacy_helpers import chdir, commit, init_repo  # noqa: E402
from metadata import parse_commit_message  # noqa: E402


class ChainTests(unittest.TestCase):
    def test_new_layers_share_the_selected_active_remote_source(self) -> None:
        repo_dir, plan = init_repo()
        try:
            from legacy_helpers import run

            source_sha = run(
                ["git", "rev-parse", plan["source_branch"]], cwd=repo_dir
            ).stdout.strip()
            with chdir(repo_dir):
                branches = create_chain(plan, remote="upstream")
                metadata = [
                    parse_commit_message(
                        run(
                            ["git", "show", "-s", "--format=%B", branch],
                            cwd=repo_dir,
                        ).stdout
                    )
                    for branch in branches
                ]

            expected = ("upstream", plan["source_branch"], source_sha)
            self.assertTrue(
                all(
                    (
                        item.active_source.remote,
                        item.active_source.branch,
                        item.active_source.sha,
                    )
                    == expected
                    for item in metadata
                )
            )
            self.assertTrue(
                all(
                    item.source_lineage == metadata[0].source_lineage
                    for item in metadata
                )
            )
        finally:
            shutil.rmtree(repo_dir)

    def test_validate_chain_rejects_unknown_command_representations_before_git(
        self,
    ) -> None:
        invalid_values = ["x", ("python3",), {"python3": "-V"}]
        with patch("chain.ensure_git_repo") as ensure_git_repo:
            for value in invalid_values:
                with self.subTest(value=value):
                    with self.assertRaises(CommandError):
                        validate_chain({}, test_argv=value)
            ensure_git_repo.assert_not_called()

    def test_create_chain_and_compare_equivalence(self) -> None:
        repo_dir, plan = init_repo()
        try:
            from legacy_helpers import run

            source_hash_before = run(
                ["git", "rev-parse", plan["source_branch"]], cwd=repo_dir
            ).stdout.strip()
            with chdir(repo_dir):
                create_chain(plan)
                diffstat, namestatus = compare_chain(plan)
            source_hash_after = run(
                ["git", "rev-parse", plan["source_branch"]], cwd=repo_dir
            ).stdout.strip()

            self.assertEqual(
                source_hash_before, source_hash_after, "Source branch hash changed"
            )
            self.assertEqual(diffstat.strip(), "")
            self.assertEqual(namestatus.strip(), "")
        finally:
            shutil.rmtree(repo_dir)

    def test_validate_chain_runs_tests(self) -> None:
        repo_dir, plan = init_repo()
        try:
            with chdir(repo_dir):
                create_chain(plan)
                validate_chain(plan, test_argv=["python3", "-c", "print('ok')"])
        finally:
            shutil.rmtree(repo_dir)

    def test_validate_chain_fails_on_bad_command(self) -> None:
        repo_dir, plan = init_repo()
        try:
            with chdir(repo_dir):
                create_chain(plan)
                with self.assertRaises(CommandError):
                    validate_chain(
                        plan, test_argv=["python3", "-c", "import sys; sys.exit(7)"]
                    )
        finally:
            shutil.rmtree(repo_dir)

    def test_validate_chain_requires_explicit_command(self) -> None:
        repo_dir, plan = init_repo()
        try:
            (repo_dir / "AGENTS.md").write_text(
                "```bash\npython3 -c \"print('test ok')\"\n```\n"
            )
            from legacy_helpers import run

            run(["git", "add", "AGENTS.md"], cwd=repo_dir)
            commit(repo_dir, "add agents")
            with chdir(repo_dir):
                create_chain(plan)
                with self.assertRaisesRegex(CommandError, "explicitly approved"):
                    validate_chain(plan, test_argv=[])
        finally:
            shutil.rmtree(repo_dir)

    def test_create_chain_is_append_only_for_existing_prefix(self) -> None:
        repo_dir, plan = init_repo()
        try:
            from legacy_helpers import run

            with chdir(repo_dir):
                create_chain(plan)
                cs1 = f"{plan['source_branch']}-1"
                cs2 = f"{plan['source_branch']}-2"
                cs1_before = run(["git", "rev-parse", cs1], cwd=repo_dir).stdout.strip()
                cs2_before = run(["git", "rev-parse", cs2], cwd=repo_dir).stdout.strip()

                plan["changesets"].append(
                    {
                        "slug": "noop-3",
                        "description": "Placeholder changeset to test append-only behavior.",
                        "include_paths": ["does-not-exist.txt"],
                        "exclude_paths": [],
                        "commit_message": "cs3",
                        "pr_notes": [],
                    }
                )

                create_chain(plan)
                cs1_after = run(["git", "rev-parse", cs1], cwd=repo_dir).stdout.strip()
                cs2_after = run(["git", "rev-parse", cs2], cwd=repo_dir).stdout.strip()
                cs3 = f"{plan['source_branch']}-3"
                cs3_rc = run(
                    ["git", "rev-parse", "--verify", cs3], cwd=repo_dir, check=False
                ).returncode

            self.assertEqual(cs1_before, cs1_after)
            self.assertEqual(cs2_before, cs2_after)
            self.assertEqual(cs3_rc, 0)
        finally:
            shutil.rmtree(repo_dir)

    def test_create_chain_rejects_a_reused_prefix_from_another_remote(self) -> None:
        repo_dir, plan = init_repo()
        try:
            from legacy_helpers import run

            with chdir(repo_dir):
                create_chain(plan)
                plan["changesets"].append(
                    {
                        "slug": "noop-3",
                        "description": "Append only after validating the prefix.",
                        "include_paths": ["does-not-exist.txt"],
                        "exclude_paths": [],
                        "commit_message": "cs3",
                        "pr_notes": [],
                    }
                )

                with self.assertRaisesRegex(CommandError, "source identity"):
                    create_chain(plan, remote="upstream")

                missing = run(
                    ["git", "rev-parse", "--verify", "feature/test-3"],
                    cwd=repo_dir,
                    check=False,
                )
                self.assertNotEqual(0, missing.returncode)
        finally:
            shutil.rmtree(repo_dir)

    def test_create_chain_rejects_a_reused_prefix_after_source_advances(self) -> None:
        repo_dir, plan = init_repo()
        try:
            from legacy_helpers import run

            with chdir(repo_dir):
                create_chain(plan)
                run(["git", "checkout", plan["source_branch"]], cwd=repo_dir)
                (repo_dir / "later.txt").write_text("later source work\n")
                run(["git", "add", "later.txt"], cwd=repo_dir)
                commit(repo_dir, "advance source")
                plan["changesets"].append(
                    {
                        "slug": "later",
                        "description": "Append only after validating the prefix.",
                        "include_paths": ["later.txt"],
                        "exclude_paths": [],
                        "commit_message": "cs3",
                        "pr_notes": [],
                    }
                )

                with self.assertRaisesRegex(CommandError, "source identity"):
                    create_chain(plan)

                missing = run(
                    ["git", "rev-parse", "--verify", "feature/test-3"],
                    cwd=repo_dir,
                    check=False,
                )
                self.assertNotEqual(0, missing.returncode)
        finally:
            shutil.rmtree(repo_dir)


if __name__ == "__main__":
    unittest.main()
