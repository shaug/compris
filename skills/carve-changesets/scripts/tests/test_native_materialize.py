from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from chain import materialize_native_stack  # noqa: E402
from common import CommandError  # noqa: E402
from gh_stack import (  # noqa: E402
    GhStackError,
    GhStackProfileBlocker,
    ProfileProbeResult,
    reviewed_preview_profile,
)
from legacy_helpers import chdir, init_remote, init_repo, run  # noqa: E402


class RecordingNativeClient:
    def __init__(
        self,
        repo: Path,
        *,
        observed_order: tuple[str, ...] | None = None,
        fail_init: bool = False,
        wrong_head: bool = False,
        move_top_on_init: bool = False,
        move_source_on_init: bool = False,
    ) -> None:
        self.repo = repo
        self.observed_order = observed_order
        self.fail_init = fail_init
        self.wrong_head = wrong_head
        self.move_top_on_init = move_top_on_init
        self.move_source_on_init = move_source_on_init
        self.init_calls: list[tuple[str, tuple[str, ...]]] = []

    def init(self, *, base: str, branches: list[str]) -> None:
        expected = tuple(branches)
        for branch in expected:
            run(["git", "rev-parse", "--verify", branch], cwd=self.repo)
        self.init_calls.append((base, expected))
        if self.fail_init:
            raise GhStackError("simulated native init interruption")
        if self.move_top_on_init:
            run(
                ["git", "commit", "--allow-empty", "-m", "native moved layer"],
                cwd=self.repo,
            )
        if self.move_source_on_init:
            run(["git", "branch", "-f", "feature/test", base], cwd=self.repo)

    def view_json(self, *, allow_state_refresh: bool) -> dict[str, object]:
        if not allow_state_refresh:
            raise AssertionError("materialization did not authorize native readback")
        base, initialized = self.init_calls[-1]
        order = self.observed_order or initialized
        predecessor = run(["git", "rev-parse", base], cwd=self.repo).stdout.strip()
        layers: list[dict[str, object]] = []
        for index, branch in enumerate(order):
            head = run(["git", "rev-parse", branch], cwd=self.repo).stdout.strip()
            if self.wrong_head and index == 0:
                head = "f" * 40
            layers.append(
                {
                    "name": branch,
                    "head": head,
                    "base": predecessor,
                    "isCurrent": index == len(order) - 1,
                    "isMerged": False,
                    "isQueued": False,
                    "needsRebase": False,
                    "pr": None,
                }
            )
            predecessor = head
        return {
            "trunk": base,
            "currentBranch": order[-1],
            "branches": layers,
        }


class NativeMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo, self.plan = init_repo()
        self.remote = init_remote(self.repo)
        run(["git", "checkout", "main"], cwd=self.repo)
        run(["git", "push", "-u", "origin", "main"], cwd=self.repo)
        run(["git", "checkout", self.plan["source_branch"]], cwd=self.repo)
        run(
            ["git", "push", "-u", "origin", self.plan["source_branch"]],
            cwd=self.repo,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.repo)
        shutil.rmtree(self.remote.parent)

    @staticmethod
    def _supported_probe() -> ProfileProbeResult:
        profile = reviewed_preview_profile("14fc42ed9b6c376a53b2f999f138d3bd26dac546")
        return ProfileProbeResult(
            status="supported",
            observed_version=profile.version,
            observed_surfaces=(),
            profile=profile,
            blocker=None,
        )

    def test_materialization_reports_source_and_exact_layer_heads(self) -> None:
        client = RecordingNativeClient(self.repo)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            result = materialize_native_stack(
                self.plan,
                remote="origin",
                allow_local_stack_state=True,
                client=client,
            )

        expected_branches = ("feature/test-1", "feature/test-2")
        self.assertEqual(("main", expected_branches), client.init_calls[0])
        self.assertEqual("origin", result.active_source.remote)
        self.assertEqual(self.plan["source_branch"], result.active_source.branch)
        self.assertEqual(
            run(
                ["git", "rev-parse", self.plan["source_branch"]], cwd=self.repo
            ).stdout.strip(),
            result.active_source.sha,
        )
        self.assertEqual(
            tuple(
                (
                    branch,
                    run(["git", "rev-parse", branch], cwd=self.repo).stdout.strip(),
                )
                for branch in expected_branches
            ),
            result.layer_heads,
        )
        self.assertFalse(result.chain_ready)
        self.assertEqual("materialized", result.truth_phase.value)

    def test_materialization_requires_authority_before_capability_or_branches(
        self,
    ) -> None:
        client = RecordingNativeClient(self.repo)
        with chdir(self.repo), mock.patch("chain.probe_profile") as probe:
            with self.assertRaisesRegex(CommandError, "rerere.*stack state.*branch"):
                materialize_native_stack(
                    self.plan,
                    remote="origin",
                    allow_local_stack_state=False,
                    client=client,
                )

        probe.assert_not_called()
        self.assertFalse(client.init_calls)
        for branch in ("feature/test-1", "feature/test-2"):
            self.assertNotEqual(
                0,
                run(
                    ["git", "rev-parse", "--verify", branch],
                    cwd=self.repo,
                    check=False,
                ).returncode,
            )

    def test_missing_compatible_capability_creates_no_semantic_branches(self) -> None:
        blocker = GhStackProfileBlocker(
            reason="unknown_version",
            observed_version="gh stack version 9.9.9",
            observed_surfaces=(),
            mismatched_surfaces=(),
        )
        unsupported = ProfileProbeResult(
            status="blocked",
            observed_version=blocker.observed_version,
            observed_surfaces=(),
            profile=None,
            blocker=blocker,
        )
        client = RecordingNativeClient(self.repo)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=unsupported),
        ):
            with self.assertRaisesRegex(CommandError, "no semantic branches"):
                materialize_native_stack(
                    self.plan,
                    remote="origin",
                    allow_local_stack_state=True,
                    client=client,
                )

        self.assertFalse(client.init_calls)
        for branch in ("feature/test-1", "feature/test-2"):
            self.assertNotEqual(
                0,
                run(
                    ["git", "rev-parse", "--verify", branch],
                    cwd=self.repo,
                    check=False,
                ).returncode,
            )

    def test_native_order_disagreement_names_expected_and_observed_topology(
        self,
    ) -> None:
        client = RecordingNativeClient(
            self.repo,
            observed_order=("feature/test-2", "feature/test-1"),
        )
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            with self.assertRaisesRegex(
                CommandError,
                r"Native order mismatch: expected \['feature/test-1', 'feature/test-2'\]; "
                r"observed \['feature/test-2', 'feature/test-1'\]",
            ):
                materialize_native_stack(
                    self.plan,
                    remote="origin",
                    allow_local_stack_state=True,
                    client=client,
                )

        self.assertEqual(
            self.plan["source_branch"],
            run(["git", "branch", "--show-current"], cwd=self.repo).stdout.strip(),
        )

    def test_native_head_disagreement_names_the_exact_layer(self) -> None:
        client = RecordingNativeClient(self.repo, wrong_head=True)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            with self.assertRaisesRegex(
                CommandError,
                "layer feature/test-1 local head mismatch",
            ):
                materialize_native_stack(
                    self.plan,
                    remote="origin",
                    allow_local_stack_state=True,
                    client=client,
                )

        self.assertEqual(
            self.plan["source_branch"],
            run(["git", "branch", "--show-current"], cwd=self.repo).stdout.strip(),
        )

    def test_native_init_cannot_move_a_semantic_layer(self) -> None:
        client = RecordingNativeClient(self.repo, move_top_on_init=True)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            with self.assertRaisesRegex(
                CommandError,
                "semantic layer feature/test-2 moved during native adoption",
            ):
                materialize_native_stack(
                    self.plan,
                    remote="origin",
                    allow_local_stack_state=True,
                    client=client,
                )

    def test_native_init_cannot_move_the_immutable_source(self) -> None:
        client = RecordingNativeClient(self.repo, move_source_on_init=True)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            with self.assertRaisesRegex(
                CommandError,
                "source branch feature/test moved during native adoption",
            ):
                materialize_native_stack(
                    self.plan,
                    remote="origin",
                    allow_local_stack_state=True,
                    client=client,
                )

    def test_native_init_interruption_preserves_layers_and_one_resume_action(
        self,
    ) -> None:
        client = RecordingNativeClient(self.repo, fail_init=True)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            try:
                materialize_native_stack(
                    self.plan,
                    remote="origin",
                    allow_local_stack_state=True,
                    client=client,
                )
            except Exception as exc:  # noqa: BLE001 - assert public error contract
                self.assertIsInstance(exc, CommandError)
                self.assertRegex(
                    str(exc),
                    "Resume exactly: python3 skills/carve-changesets/scripts/cli.py "
                    "create-chain --plan .carve-changesets/plan.json --remote origin "
                    "--ack-local-stack-state",
                )
            else:
                self.fail("interrupted native init returned success")

        self.assertEqual(
            self.plan["source_branch"],
            run(["git", "branch", "--show-current"], cwd=self.repo).stdout.strip(),
        )
        for branch in ("feature/test-1", "feature/test-2"):
            self.assertEqual(
                0,
                run(
                    ["git", "rev-parse", "--verify", branch],
                    cwd=self.repo,
                    check=False,
                ).returncode,
            )

        resumed = RecordingNativeClient(self.repo)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            result = materialize_native_stack(
                self.plan,
                remote="origin",
                allow_local_stack_state=True,
                client=resumed,
            )

        self.assertEqual(
            ("feature/test-1", "feature/test-2"),
            tuple(layer.branch for layer in result.snapshot.layers),
        )
        self.assertEqual(1, len(resumed.init_calls))

    def test_materialization_restores_exact_detached_checkout(self) -> None:
        original_sha = run(["git", "rev-parse", "HEAD"], cwd=self.repo).stdout.strip()
        run(["git", "checkout", "--detach", original_sha], cwd=self.repo)
        client = RecordingNativeClient(self.repo)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            materialize_native_stack(
                self.plan,
                remote="origin",
                allow_local_stack_state=True,
                client=client,
            )

        self.assertEqual(
            "",
            run(["git", "branch", "--show-current"], cwd=self.repo).stdout.strip(),
        )
        self.assertEqual(
            original_sha,
            run(["git", "rev-parse", "HEAD"], cwd=self.repo).stdout.strip(),
        )

    def test_interruption_restores_exact_detached_checkout(self) -> None:
        original_sha = run(["git", "rev-parse", "HEAD"], cwd=self.repo).stdout.strip()
        run(["git", "checkout", "--detach", original_sha], cwd=self.repo)
        client = RecordingNativeClient(self.repo, fail_init=True)
        with (
            chdir(self.repo),
            mock.patch("chain.probe_profile", return_value=self._supported_probe()),
        ):
            with self.assertRaises(CommandError):
                materialize_native_stack(
                    self.plan,
                    remote="origin",
                    allow_local_stack_state=True,
                    client=client,
                )

        self.assertEqual(
            "",
            run(["git", "branch", "--show-current"], cwd=self.repo).stdout.strip(),
        )
        self.assertEqual(
            original_sha,
            run(["git", "rev-parse", "HEAD"], cwd=self.repo).stdout.strip(),
        )


if __name__ == "__main__":
    unittest.main()
