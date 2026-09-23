from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from gh_stack import (  # noqa: E402
    GH_STACK_ENV,
    GhStackClient,
    GhStackError,
    StackCapability,
    probe_profile,
    reviewed_preview_profile,
)

FIXTURES = TESTS_DIR / "fixtures" / "gh-stack"
VIEW_OPEN_JSON = (FIXTURES / "view-open.json").read_text()
PROFILE = json.loads((FIXTURES / "profile-reviewed.json").read_text())


class GhStackClientTest(unittest.TestCase):
    def test_view_returns_machine_readable_state_with_noninteractive_argv(self) -> None:
        runner = mock.Mock(return_value=VIEW_OPEN_JSON)
        client = GhStackClient(runner=runner)

        payload = client.view_json(allow_state_refresh=True)

        self.assertEqual("main", payload["trunk"])
        self.assertEqual("feature-2", payload["currentBranch"])
        runner.assert_called_once_with(
            ["gh", "stack", "view", "--json"], env=GH_STACK_ENV
        )

    def test_view_without_local_state_authority_runs_no_command(self) -> None:
        runner = mock.Mock()
        client = GhStackClient(runner=runner)

        with self.assertRaisesRegex(GhStackError, "local-state authority"):
            client.view_json(allow_state_refresh=False)

        runner.assert_not_called()

    def test_view_reports_command_failure_with_stderr(self) -> None:
        failure = subprocess.CalledProcessError(
            7,
            ["gh", "stack", "view", "--json"],
            stderr="native state unavailable",
        )
        client = GhStackClient(runner=mock.Mock(side_effect=failure))

        with self.assertRaisesRegex(
            GhStackError,
            "gh stack view --json failed: exit 7: native state unavailable",
        ):
            client.view_json(allow_state_refresh=True)

    def test_default_runner_executes_in_the_bound_repository(self) -> None:
        repo = Path("/tmp/native-stack-target")
        completed = subprocess.CompletedProcess(
            args=["gh", "stack", "view", "--json"],
            returncode=0,
            stdout=VIEW_OPEN_JSON,
            stderr="",
        )
        with mock.patch("gh_stack.subprocess.run", return_value=completed) as run:
            client = GhStackClient(cwd=repo)

            client.view_json(allow_state_refresh=True)

        self.assertEqual(repo, run.call_args.kwargs["cwd"])

    def test_only_reviewed_local_mutations_have_adapter_methods(self) -> None:
        runner = mock.Mock(return_value="")
        client = GhStackClient(runner=runner)

        client.init(base="main", branches=("feature-1", "feature-2"))
        client.rebase_no_trunk_upstack("feature-1")

        self.assertEqual(
            [
                mock.call(
                    [
                        "gh",
                        "stack",
                        "init",
                        "--base",
                        "main",
                        "feature-1",
                        "feature-2",
                    ],
                    env=GH_STACK_ENV,
                ),
                mock.call(
                    [
                        "gh",
                        "stack",
                        "rebase",
                        "--no-trunk",
                        "--upstack",
                        "feature-1",
                    ],
                    env=GH_STACK_ENV,
                ),
            ],
            runner.call_args_list,
        )
        for unsupported in ("push", "submit", "sync", "merge"):
            self.assertFalse(hasattr(client, unsupported), unsupported)

    def test_generic_capture_is_not_public(self) -> None:
        runner = mock.Mock()
        client = GhStackClient(runner=runner)

        self.assertFalse(hasattr(client, "capture"))

        runner.assert_not_called()

    def test_reviewed_preview_profile_grants_only_local_capabilities(self) -> None:
        profile = reviewed_preview_profile(PROFILE["source_revision"])

        self.assertEqual(PROFILE["version"], profile.version)
        self.assertEqual(PROFILE["source_revision"], profile.source_revision)
        self.assertEqual(
            frozenset(
                {
                    StackCapability.LOCAL_INIT,
                    StackCapability.VIEW_JSON,
                    StackCapability.LOCAL_REBASE_NO_TRUNK,
                }
            ),
            profile.capabilities,
        )

    def test_probe_accepts_exact_reviewed_version_and_surfaces(self) -> None:
        runner, reviewed_profile = self._profile_runner()

        result = probe_profile(runner=runner, reviewed_profile=reviewed_profile)

        self.assertEqual("supported", result.status)
        self.assertIsNotNone(result.profile)
        self.assertIsNone(result.blocker)
        self.assertEqual(PROFILE["version"], result.observed_version)
        self.assertEqual(
            tuple(sorted(PROFILE["commands"])),
            tuple(name for name, _ in result.observed_surfaces),
        )

    def test_probe_blocks_unknown_version_with_observed_surface(self) -> None:
        runner, reviewed_profile = self._profile_runner(
            version="gh stack version 9.9.9"
        )

        result = probe_profile(runner=runner, reviewed_profile=reviewed_profile)

        self.assertEqual("blocked", result.status)
        self.assertIsNone(result.profile)
        self.assertIsNotNone(result.blocker)
        self.assertEqual("unknown_version", result.blocker.reason)
        self.assertEqual("gh stack version 9.9.9", result.blocker.observed_version)
        self.assertEqual(7, len(result.blocker.observed_surfaces))

    def test_probe_blocks_surface_mismatch_and_names_command(self) -> None:
        runner, reviewed_profile = self._profile_runner(
            overrides={"submit": "changed help\n"}
        )

        result = probe_profile(runner=runner, reviewed_profile=reviewed_profile)

        self.assertEqual("blocked", result.status)
        self.assertIsNotNone(result.blocker)
        self.assertEqual("surface_mismatch", result.blocker.reason)
        self.assertEqual(("submit",), result.blocker.mismatched_surfaces)
        self.assertEqual(7, len(result.blocker.observed_surfaces))

    def test_probe_blocks_failed_help_command_with_observed_evidence(self) -> None:
        runner, reviewed_profile = self._profile_runner()
        successful_runner = runner.side_effect

        def fail_init_help(argv: list[str], *, env: dict[str, str]) -> str:
            if argv == ["gh", "stack", "init", "--help"]:
                raise subprocess.CalledProcessError(
                    2, argv, stderr="unknown command init"
                )
            return successful_runner(argv, env=env)

        runner.side_effect = fail_init_help

        result = probe_profile(runner=runner, reviewed_profile=reviewed_profile)

        self.assertEqual("blocked", result.status)
        self.assertIsNone(result.profile)
        self.assertIsNotNone(result.blocker)
        self.assertEqual("surface_probe_failed", result.blocker.reason)
        self.assertEqual(PROFILE["version"], result.blocker.observed_version)
        self.assertEqual(6, len(result.blocker.observed_surfaces))
        self.assertEqual(
            (("init", "exit 2: unknown command init"),),
            result.blocker.probe_errors,
        )

    @staticmethod
    def _profile_runner(
        *, version: str | None = None, overrides: dict[str, str] | None = None
    ) -> tuple[mock.Mock, dict[str, object]]:
        overrides = overrides or {}
        reviewed_profile = deepcopy(PROFILE)
        help_by_command: dict[str, str] = {}
        for command in PROFILE["commands"]:
            help_by_command[command] = f"reviewed {command} help\n"
            reviewed_profile["commands"][command]["help_sha256"] = hashlib.sha256(
                help_by_command[command].encode()
            ).hexdigest()

        def run(argv: list[str], *, env: dict[str, str]) -> str:
            if env != GH_STACK_ENV:
                raise AssertionError(f"unexpected environment: {env}")
            if argv == ["gh", "stack", "--version"]:
                return (version or PROFILE["version"]) + "\n"
            command = argv[2]
            if argv != ["gh", "stack", command, "--help"]:
                raise AssertionError(f"unexpected argv: {argv}")
            if command in overrides:
                return overrides[command]
            return help_by_command[command]

        return mock.Mock(side_effect=run), reviewed_profile


if __name__ == "__main__":
    unittest.main()
