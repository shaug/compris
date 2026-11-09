"""The public executors use one vote rule without losing their own contracts."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
from sampling_helpers import FIXTURES, ROOT, voting_executors  # noqa: E402


class ExecutorPolicyTests(unittest.TestCase):
    def run_executor(self, executor, answers, repetitions=None):
        with (
            mock.patch.object(executor, "run_claude", side_effect=answers),
            mock.patch.object(
                sys,
                "argv",
                ["executor", "--repetitions", str(repetitions or len(answers))],
            ),
            mock.patch.object(
                sys,
                "stdin",
                io.StringIO(
                    json.dumps(
                        {
                            "target_skill": "implement-ticket",
                            "skill_prompt": "skill",
                            "request": "request",
                            "artifacts": {},
                            "prompt": "prompt",
                            "catalog": [
                                {"skill": "alpha", "description": "A"},
                                {"skill": "zeta", "description": "Z"},
                            ],
                        }
                    )
                ),
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(executor.main(), 0)
        return json.loads(output.getvalue())

    def test_each_voting_executor_breaks_ties_lexically_in_both_draw_orders(self):
        for name, executor in voting_executors():
            values = {
                "ticket": ["ready_pr", "ready_pr", "merged", "merged"],
                "planner": [
                    "ticket_ready",
                    "ticket_ready",
                    "draft_ready",
                    "draft_ready",
                ],
                "router": ["zeta", "zeta", "alpha", "alpha"],
            }[name]
            for sequence in (values, list(reversed(values))):
                answers = (
                    sequence
                    if name == "router"
                    else [
                        {
                            "terminal_state": value,
                            "target_skill": "implement-ticket",
                            "actions": [],
                        }
                        for value in sequence
                    ]
                )
                with self.subTest(executor=name, sequence=sequence):
                    result = self.run_executor(executor, answers)
                    field = "selected_skill" if name == "router" else "terminal_state"
                    self.assertEqual(result[field], min(values))
                    self.assertEqual(result["repetitions"], 4)
                    self.assertEqual(result["agreement"], 0.5)

    def test_actions_require_more_than_half_the_drawn_samples(self):
        for name, executor in voting_executors():
            if name == "router":
                continue
            action = executor.ACTION_VOCABULARY[0]
            answers = [
                {
                    "terminal_state": executor.TERMINAL_STATES[0],
                    "target_skill": "implement-ticket",
                    "actions": [action] if index < 2 else [],
                }
                for index in range(4)
            ]
            with self.subTest(executor=name):
                self.assertNotIn(
                    action, self.run_executor(executor, answers)["actions"]
                )
                answers[2]["actions"] = [action]
                result = self.run_executor(executor, answers)
                self.assertIn(action, result["actions"])
                if name == "planner":
                    self.assertNotIn("target_skill", result)

    def test_successful_samples_report_no_runtime_refusals(self):
        for name, executor in voting_executors():
            answer = (
                "alpha"
                if name == "router"
                else {"terminal_state": "blocked", "actions": []}
            )
            with self.subTest(executor=name):
                self.assertEqual(
                    self.run_executor(executor, [answer]).get("failed_samples"), 0
                )

    def test_each_executor_counts_refusals_across_a_burst_redraw(self):
        for name, executor in voting_executors():
            answer = (
                "alpha"
                if name == "router"
                else {"terminal_state": "blocked", "actions": []}
            )
            refused = executor.core.SampleUnavailable("runtime unavailable")
            answers = [refused] * 5 + [answer, refused, answer, refused, answer]
            with (
                self.subTest(executor=name),
                mock.patch.object(executor.core.time, "sleep") as sleep,
            ):
                result = self.run_executor(executor, answers, repetitions=5)
                self.assertEqual(result["repetitions"], 3)
                self.assertEqual(result["failed_samples"], 7)
                sleep.assert_called_once_with(
                    executor.core.SCENARIO_RETRY_PAUSE_SECONDS
                )

    def test_each_executor_votes_over_partial_success_without_redrawing(self):
        for name, executor in voting_executors():
            answer = (
                "alpha"
                if name == "router"
                else {"terminal_state": "blocked", "actions": []}
            )
            answers = [
                answer,
                executor.core.SampleUnavailable("runtime unavailable"),
                answer,
            ]
            with (
                self.subTest(executor=name),
                mock.patch.object(executor.core.time, "sleep") as sleep,
            ):
                result = self.run_executor(executor, answers)
                self.assertEqual(result["repetitions"], 2)
                self.assertEqual(result["failed_samples"], 1)
                sleep.assert_not_called()

    def test_router_unknown_answer_still_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "stub-claude"
            runtime.write_text(
                f"#!{sys.executable}\nimport json\nprint(json.dumps({{'result': 'unknown'}}))\n"
            )
            runtime.chmod(0o700)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "triggering/executors/description_executor.py"),
                    "--claude-bin",
                    str(runtime),
                    "--repetitions",
                    "1",
                ],
                input=json.dumps(
                    {
                        "prompt": "request",
                        "catalog": [{"skill": "alpha", "description": "A"}],
                    }
                ),
                text=True,
                capture_output=True,
                cwd=directory,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognised router answer", result.stderr)

    def test_skill_executors_are_self_contained_when_installed_elsewhere(self):
        import shutil

        for skill in ("implement-ticket", "plan-implementation"):
            with self.subTest(skill=skill), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory)
                source = ROOT / "skills" / skill / "scripts" / "evals"
                for name in ("claude_executor.py", "sampling_core.py"):
                    shutil.copy2(source / name, destination / name)
                runtime = destination / "stub-claude"
                envelope = json.dumps(
                    {"result": json.dumps({"terminal_state": "blocked", "actions": []})}
                )
                runtime.write_text(f"#!{sys.executable}\nprint({envelope!r})\n")
                runtime.chmod(0o700)
                result = subprocess.run(
                    [
                        sys.executable,
                        str(destination / "claude_executor.py"),
                        "--claude-bin",
                        str(runtime),
                        "--repetitions",
                        "1",
                    ],
                    input=json.dumps(
                        {
                            "target_skill": skill,
                            "skill_prompt": "skill",
                            "request": "request",
                            "artifacts": {},
                        }
                    ),
                    text=True,
                    capture_output=True,
                    cwd=directory,
                    check=True,
                )
                self.assertEqual(json.loads(result.stdout)["terminal_state"], "blocked")

    def test_review_executor_keeps_the_pre_migration_golden_output(self):
        request = (FIXTURES / "review-request.json").read_text()
        envelope = (FIXTURES / "review-envelope.json").read_text()
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "stub-claude"
            runtime.write_text(
                f"#!{sys.executable}\nimport sys\nsys.stdin.read()\nprint({envelope!r})\n"
            )
            runtime.chmod(0o700)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "review-suite/scripts/evals/claude_executor.py"),
                    "--claude-bin",
                    str(runtime),
                ],
                input=request,
                text=True,
                capture_output=True,
                cwd=directory,
                check=True,
            )
        self.assertEqual(result.stdout, (FIXTURES / "review-response.json").read_text())


if __name__ == "__main__":
    unittest.main()
