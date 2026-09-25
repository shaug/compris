from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(TESTS_DIR))

import cli as cli_mod  # noqa: E402
import helpers  # noqa: E402
from cli import main  # noqa: E402


class TransitionCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo, self.bare, _source = helpers.init_repo(self.root)
        helpers.run(self.repo, "git", "checkout", "main")
        helpers.run(self.repo, "git", "checkout", "-b", "feature/report-1")
        (self.repo / "one.txt").write_text("one\n")
        helpers.run(self.repo, "git", "add", "one.txt")
        self.head_one = helpers.commit(self.repo, "feat: add layer one")
        helpers.run(self.repo, "git", "checkout", "-b", "feature/report-2")
        (self.repo / "two.txt").write_text("two\n")
        helpers.run(self.repo, "git", "add", "two.txt")
        self.head_two = helpers.commit(self.repo, "feat: add layer two")
        self.plan = self.root / "plan.json"
        self.plan.write_text(
            json.dumps(
                {
                    "feature_title": "Feature report",
                    "base_branch": "main",
                    "source_branch": "feature/report",
                    "test_argv": [],
                    "changesets": [
                        {
                            "slug": "one",
                            "description": "Layer one",
                            "include_paths": ["one.txt"],
                        },
                        {
                            "slug": "two",
                            "description": "Layer two",
                            "include_paths": ["two.txt"],
                        },
                    ],
                }
            )
            + "\n"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_push_chain_previews_complete_manifest_without_remote_mutation(
        self,
    ) -> None:
        output = StringIO()

        with chdir(self.repo), redirect_stdout(output):
            status = main(("push-chain", "--plan", str(self.plan)))

        self.assertEqual(0, status)
        manifest = json.loads(output.getvalue())
        self.assertEqual("publish", manifest["operation"])
        self.assertEqual(["push"], manifest["enabled_phases"])
        self.assertEqual(
            ["refs/heads/feature/report-1", "refs/heads/feature/report-2"],
            [item["name"] for item in manifest["expected_refs"]],
        )
        self.assertEqual(
            [self.head_one, self.head_two],
            [item["proposed_sha"] for item in manifest["expected_refs"]],
        )
        self.assertEqual(
            ["push_ref", "push_ref"],
            [item["kind"] for item in manifest["effects"]],
        )
        self.assertEqual(
            "",
            helpers.run(
                self.repo,
                "git",
                "ls-remote",
                "--heads",
                "origin",
                "refs/heads/feature/report-*",
            ),
        )

    def _preview_manifest(self) -> str:
        output = StringIO()
        with chdir(self.repo), redirect_stdout(output):
            self.assertEqual(0, main(("push-chain", "--plan", str(self.plan))))
        return output.getvalue()

    def test_legacy_no_dry_run_cannot_bypass_manifest_execution(self) -> None:
        output = StringIO()

        with chdir(self.repo), redirect_stdout(output):
            status = main(("push-chain", "--plan", str(self.plan), "--no-dry-run"))

        self.assertEqual(0, status)
        self.assertEqual("publish", json.loads(output.getvalue())["operation"])
        self.assertEqual(
            "",
            helpers.run(
                self.repo,
                "git",
                "ls-remote",
                "--heads",
                "origin",
                "refs/heads/feature/report-*",
            ),
        )

    def test_reviewed_profile_blocks_approved_push_before_remote_mutation(self) -> None:
        approved = self.root / "approved.json"
        approved.write_text(self._preview_manifest())
        output = StringIO()

        with chdir(self.repo), redirect_stdout(output):
            status = main(
                (
                    "push-chain",
                    "--plan",
                    str(self.plan),
                    "--manifest",
                    str(approved),
                    "--execute",
                    "--ack-push",
                )
            )

        self.assertEqual(1, status)
        self.assertIn('"state": "blocked"', output.getvalue())
        self.assertIn("fenced_push", output.getvalue())
        self.assertEqual(
            "",
            helpers.run(
                self.repo,
                "git",
                "ls-remote",
                "--heads",
                "origin",
                "refs/heads/feature/report-*",
            ),
        )

    def test_execute_requires_operation_specific_authority_acknowledgment(self) -> None:
        approved = self.root / "approved.json"
        approved.write_text(self._preview_manifest())
        output = StringIO()

        with chdir(self.repo), redirect_stdout(output):
            status = main(
                (
                    "push-chain",
                    "--plan",
                    str(self.plan),
                    "--manifest",
                    str(approved),
                    "--execute",
                )
            )

        self.assertEqual(1, status)
        self.assertIn("requires --ack-push", output.getvalue())
        self.assertEqual(
            "",
            helpers.run(
                self.repo,
                "git",
                "ls-remote",
                "--heads",
                "origin",
                "refs/heads/feature/report-*",
            ),
        )

    def test_single_layer_submit_binds_its_actual_predecessor(self) -> None:
        plan = json.loads(self.plan.read_text())

        with (
            chdir(self.repo),
            mock.patch.object(cli_mod, "pull_requests_for_source", return_value=[]),
            mock.patch.object(cli_mod, "pr_body_for", return_value="Layer body\n"),
            mock.patch.object(
                cli_mod, "github_repo_for_remote", return_value="acme/widgets"
            ),
        ):
            manifest = cli_mod._publish_manifest(plan, remote="origin", indices=(2,))

        self.assertEqual(("feature/report-2",), manifest.identities)
        create = next(
            effect for effect in manifest.effects if effect.kind.value == "create_pr"
        )
        self.assertEqual("feature/report-1", create.after[3])


if __name__ == "__main__":
    unittest.main()
