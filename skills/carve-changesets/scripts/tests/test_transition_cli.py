from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
for path in (TESTS_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import cli as cli_mod  # noqa: E402
import helpers  # noqa: E402
from cli import main  # noqa: E402
from common import CommandError  # noqa: E402
from native_stack import (  # noqa: E402
    NativeLayer,
    NativePullRequest,
    NativeStackSnapshot,
)
from transitions import (  # noqa: E402
    StackOperation,
    TransitionResult,
    TransitionState,
)


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
        self.main_head = helpers.run(self.repo, "git", "rev-parse", "main")
        self.native_snapshot = NativeStackSnapshot(
            trunk_branch="main",
            trunk_head=self.main_head,
            current_branch="feature/report-2",
            layers=(
                NativeLayer(
                    branch="feature/report-1",
                    head=self.head_one,
                    base=self.main_head,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=None,
                ),
                NativeLayer(
                    branch="feature/report-2",
                    head=self.head_two,
                    base=self.head_one,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=None,
                ),
            ),
        )
        self.native_reader = mock.patch.object(
            cli_mod,
            "_native_snapshot_for_transition",
            return_value=self.native_snapshot,
            create=True,
        )
        self.native_reader_mock = self.native_reader.start()
        self.addCleanup(self.native_reader.stop)
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
            status = main(
                (
                    "push-chain",
                    "--plan",
                    str(self.plan),
                    "--allow-stack-state-refresh",
                )
            )

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
            self.assertEqual(
                0,
                main(
                    (
                        "push-chain",
                        "--plan",
                        str(self.plan),
                        "--allow-stack-state-refresh",
                    )
                ),
            )
        return output.getvalue()

    def test_legacy_no_dry_run_cannot_bypass_manifest_execution(self) -> None:
        output = StringIO()

        with chdir(self.repo), redirect_stdout(output):
            status = main(
                (
                    "push-chain",
                    "--plan",
                    str(self.plan),
                    "--no-dry-run",
                    "--allow-stack-state-refresh",
                )
            )

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
        self.assertIn("fenced_push", output.getvalue())
        self.assertIn("no state was refreshed", output.getvalue())
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
            manifest = cli_mod._publish_manifest(
                plan,
                remote="origin",
                indices=(2,),
                allow_stack_state_refresh=True,
            )

        self.assertEqual(("feature/report-2",), manifest.identities)
        create = next(
            effect for effect in manifest.effects if effect.kind.value == "create_pr"
        )
        self.assertEqual("feature/report-1", create.after[3])

    def test_execute_refuses_unsupported_profile_before_manifest_refresh(self) -> None:
        args = cli_mod.build_parser().parse_args(
            (
                "propagate",
                "--source",
                "feature/report",
                "--index",
                "1",
                "--execute",
                "--ack-repair",
            )
        )
        output = StringIO()

        with (
            mock.patch.object(
                cli_mod,
                "_repair_manifest",
                side_effect=AssertionError("must not refresh"),
            ),
            redirect_stdout(output),
        ):
            status = cli_mod.main(
                (
                    "propagate",
                    "--source",
                    "feature/report",
                    "--index",
                    "1",
                    "--execute",
                    "--ack-repair",
                )
            )

        self.assertTrue(args.execute)
        self.assertEqual(1, status)
        self.assertIn("no state was refreshed", output.getvalue())

    def test_preview_requires_explicit_native_snapshot_refresh_authority(self) -> None:
        self.native_reader_mock.reset_mock()
        output = StringIO()

        with chdir(self.repo), redirect_stdout(output):
            status = main(("push-chain", "--plan", str(self.plan)))

        self.assertEqual(1, status)
        self.assertIn("--allow-stack-state-refresh", output.getvalue())
        self.native_reader_mock.assert_not_called()

    def test_preview_rejects_native_order_different_from_selected_chain(self) -> None:
        self.native_reader_mock.return_value = NativeStackSnapshot(
            trunk_branch="main",
            trunk_head=self.main_head,
            current_branch="feature/report-1",
            layers=tuple(reversed(self.native_snapshot.layers)),
        )
        output = StringIO()

        with chdir(self.repo), redirect_stdout(output):
            status = main(
                (
                    "push-chain",
                    "--plan",
                    str(self.plan),
                    "--allow-stack-state-refresh",
                )
            )

        self.assertEqual(1, status)
        self.assertIn("native stack order", output.getvalue())

    def test_finish_transition_refuses_partial_executor_failure(self) -> None:
        result = TransitionResult(
            state=TransitionState.PARTIAL,
            operation=StackOperation.REPAIR,
            identities=("feature/report-2",),
            evidence=("executor failed after one effect",),
            blocker="executor failed after one effect",
            next_action="approve a fresh manifest",
            fresh_manifest_required=True,
        )

        with redirect_stdout(StringIO()):
            with self.assertRaisesRegex(CommandError, "executor failed"):
                cli_mod._finish_transition(result)

    def test_finish_transition_refuses_divergent_readback(self) -> None:
        result = TransitionResult(
            state=TransitionState.DIVERGED,
            operation=StackOperation.MERGE,
            identities=("feature/report-1",),
            evidence=("unexpected head",),
            next_action="approve a fresh manifest",
            fresh_manifest_required=True,
        )

        with redirect_stdout(StringIO()):
            with self.assertRaisesRegex(CommandError, "fresh manifest"):
                cli_mod._finish_transition(result)

    def _published_chain(self, *, recovered: bool = False):
        root = SimpleNamespace(remote="origin", branch="feature/report", sha="a" * 40)
        active = (
            SimpleNamespace(
                remote="origin", branch="feature/report-corrected", sha="d" * 40
            )
            if recovered
            else root
        )
        first = SimpleNamespace(
            position=1,
            branch="feature/report-1",
            head=self.head_one,
            pr_number=41,
            metadata=SimpleNamespace(active_source=root),
        )
        second = SimpleNamespace(
            position=2,
            branch="feature/report-2",
            head=self.head_two,
            pr_number=42,
            metadata=SimpleNamespace(active_source=active),
        )
        chain = SimpleNamespace(base_branch="main", changesets=(first, second))
        prs = {
            41: SimpleNamespace(
                number=41,
                head_branch=first.branch,
                head_sha=first.head,
                base_branch="main",
                state="MERGED",
                draft=False,
                queued=False,
                auto_merge=False,
                title="Layer one",
                body="Layer one body",
            ),
            42: SimpleNamespace(
                number=42,
                head_branch=second.branch,
                head_sha=second.head,
                base_branch=first.branch,
                state="OPEN",
                draft=False,
                queued=False,
                auto_merge=False,
                title="Layer two",
                body="Layer two body",
            ),
        }
        return chain, prs

    def _published_snapshot(self, *, needs_rebase: bool) -> NativeStackSnapshot:
        return NativeStackSnapshot(
            trunk_branch="main",
            trunk_head=self.main_head,
            current_branch="feature/report-2",
            layers=(
                NativeLayer(
                    branch="feature/report-1",
                    head=self.head_one,
                    base=self.main_head,
                    merged=True,
                    queued=False,
                    needs_rebase=False,
                    pull_request=NativePullRequest(
                        41, "https://example/pr/41", "MERGED"
                    ),
                ),
                NativeLayer(
                    branch="feature/report-2",
                    head=self.head_two,
                    base=self.main_head,
                    merged=False,
                    queued=False,
                    needs_rebase=needs_rebase,
                    pull_request=NativePullRequest(42, "https://example/pr/42", "OPEN"),
                ),
            ),
        )

    def test_repair_preview_blocks_unknown_rewritten_head(self) -> None:
        chain, prs = self._published_chain()
        self.native_reader_mock.return_value = self._published_snapshot(
            needs_rebase=True
        )
        output = StringIO()
        with (
            mock.patch.object(cli_mod, "_rehydrate_live", return_value=(chain, prs)),
            chdir(self.repo),
            redirect_stdout(output),
        ):
            status = main(
                (
                    "propagate",
                    "--source",
                    "feature/report",
                    "--index",
                    "1",
                    "--allow-stack-state-refresh",
                )
            )

        self.assertEqual(1, status)
        self.assertIn("exact rewritten heads", output.getvalue())

    def test_already_propagated_repair_preview_records_exact_no_op_head(self) -> None:
        chain, prs = self._published_chain()
        self.native_reader_mock.return_value = self._published_snapshot(
            needs_rebase=False
        )
        output = StringIO()
        with (
            mock.patch.object(cli_mod, "_rehydrate_live", return_value=(chain, prs)),
            mock.patch.object(
                cli_mod,
                "remote_branch_head",
                side_effect=lambda _remote, branch: {
                    "main": self.main_head,
                    "feature/report-2": self.head_two,
                }.get(branch),
            ),
            mock.patch.object(
                cli_mod, "github_repo_for_remote", return_value="acme/widgets"
            ),
            chdir(self.repo),
            redirect_stdout(output),
        ):
            status = main(
                (
                    "propagate",
                    "--source",
                    "feature/report",
                    "--index",
                    "1",
                    "--allow-stack-state-refresh",
                )
            )

        self.assertEqual(0, status)
        manifest = json.loads(output.getvalue())
        ref = manifest["expected_refs"][0]
        self.assertEqual(self.head_two, ref["old_sha"])
        self.assertEqual(self.head_two, ref["proposed_sha"])

    def test_direct_merge_preview_blocks_unknown_automatic_suffix_heads(self) -> None:
        chain, prs = self._published_chain()
        chain.changesets[0].pr_state = "OPEN"
        self.native_reader_mock.return_value = self.native_snapshot
        output = StringIO()
        with (
            mock.patch.object(cli_mod, "_rehydrate_live", return_value=(chain, prs)),
            chdir(self.repo),
            redirect_stdout(output),
        ):
            status = main(
                (
                    "merge-propagate",
                    "--source",
                    "feature/report",
                    "--index",
                    "1",
                    "--allow-stack-state-refresh",
                )
            )

        self.assertEqual(1, status)
        self.assertIn("automatic suffix heads", output.getvalue())

    def test_merge_preview_rejects_non_bottom_native_target(self) -> None:
        chain, prs = self._published_chain()
        self.native_reader_mock.return_value = self.native_snapshot
        output = StringIO()
        with (
            mock.patch.object(cli_mod, "_rehydrate_live", return_value=(chain, prs)),
            chdir(self.repo),
            redirect_stdout(output),
        ):
            status = main(
                (
                    "merge-propagate",
                    "--source",
                    "feature/report",
                    "--index",
                    "2",
                    "--allow-stack-state-refresh",
                )
            )

        self.assertEqual(1, status)
        self.assertIn("not the bottom open native layer", output.getvalue())

    def test_recovery_preview_blocks_unmaterialized_successor_heads(self) -> None:
        chain, prs = self._published_chain(recovered=False)
        output = StringIO()
        with (
            mock.patch.object(cli_mod, "_rehydrate_live", return_value=(chain, prs)),
            chdir(self.repo),
            redirect_stdout(output),
        ):
            status = main(
                (
                    "recover-suffix",
                    "--source",
                    "feature/report",
                    "--base",
                    "main",
                    "--from-index",
                    "2",
                    "--successor-source",
                    "feature/report-corrected",
                    "--successor-sha",
                    "d" * 40,
                    "--allow-stack-state-refresh",
                )
            )

        self.assertEqual(1, status)
        self.assertIn("exact restamped successor heads", output.getvalue())


if __name__ == "__main__":
    unittest.main()
