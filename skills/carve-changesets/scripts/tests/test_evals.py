from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from evals.grader import grade_repo  # noqa: E402
from evals.helpers import cleanup_repo, init_eval_repo  # noqa: E402
from legacy_helpers import chdir, commit, run  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = SKILL_ROOT / "scripts" / "evals" / "runner.py"
EXECUTOR_PATH = SKILL_ROOT / "scripts" / "evals" / "fixture_executor.py"

RUNNER_SPEC = importlib.util.spec_from_file_location(
    "carve_changesets_eval_runner", RUNNER_PATH
)
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
assert RUNNER_SPEC and RUNNER_SPEC.loader
RUNNER_SPEC.loader.exec_module(RUNNER)

EXECUTOR_SPEC = importlib.util.spec_from_file_location(
    "carve_changesets_fixture_executor", EXECUTOR_PATH
)
EXECUTOR = importlib.util.module_from_spec(EXECUTOR_SPEC)
assert EXECUTOR_SPEC and EXECUTOR_SPEC.loader
EXECUTOR_SPEC.loader.exec_module(EXECUTOR)


class EvalGraderTests(unittest.TestCase):
    def test_objective_grader_passes_the_integration_fixture(self) -> None:
        repo_dir, _plan, source_hash = init_eval_repo()
        try:
            with chdir(repo_dir):
                result = grade_repo(
                    plan_path=repo_dir / ".carve-changesets/plan.json",
                    expected_source_hash=source_hash,
                    test_argv=["python3", "-c", "print('ok')"],
                    auto_create_chain=True,
                )
            self.assertTrue(result.ok, f"grader should pass: {result.failures}")
            self.assertIn("equivalence", result.checks)
            self.assertIn("source_hash_unchanged", result.checks)
        finally:
            cleanup_repo(repo_dir)

    def test_objective_grader_detects_source_branch_mutation(self) -> None:
        repo_dir, _plan, source_hash = init_eval_repo()
        try:
            with chdir(repo_dir):
                (repo_dir / "a.txt").write_text("mutated-source\n")
                run(["git", "add", "a.txt"], cwd=repo_dir)
                commit(repo_dir, "mutate source")
                result = grade_repo(
                    plan_path=repo_dir / ".carve-changesets/plan.json",
                    expected_source_hash=source_hash,
                    test_argv=["python3", "-c", "print('ok')"],
                    auto_create_chain=True,
                )
            self.assertFalse(result.ok)
            self.assertTrue(
                any("source_hash_unchanged" in item for item in result.failures)
            )
        finally:
            cleanup_repo(repo_dir)


class ForwardEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(RUNNER.DEFAULT_CASES.read_text())
        cls.expectations_text = RUNNER.DEFAULT_EXPECTATIONS.read_text()

    def test_cases_match_peer_shape_and_cover_required_judgment(self) -> None:
        peer_shape = {
            "id",
            "request",
            "tracker_state",
            "authority",
            "runtime_profile",
            "capabilities",
            "candidate_state",
            "incoming_handoff",
            "publication_state",
        }
        expected_ids = {
            "decompose-independent-subsystems",
            "separate-mechanical-rename",
            "oversized-guardrail-negotiation",
            "mechanical-guardrail-exception",
            "refuse-validated-reorder",
            "validated-plan-conflict",
            "publish-with-merge-withheld",
            "refuse-dirty-source",
            "refuse-source-behind-base",
            "recover-successor-suffix",
            "reject-conflicting-successor-lineage",
            "reject-original-source-mutation",
            "blocked-after-publication",
        }
        self.assertEqual(expected_ids, {case["id"] for case in self.cases})
        for case in self.cases:
            self.assertIn("request", case)
            self.assertIn("candidate_state", case)
            self.assertLessEqual(set(case), peer_shape, case["id"])

    def test_publication_terminal_cases_require_lifecycle_observations(self) -> None:
        expectations = {
            item["case_id"]: item for item in json.loads(self.expectations_text)
        }
        for case_id in (
            "publish-with-merge-withheld",
            "recover-successor-suffix",
            "blocked-after-publication",
        ):
            with self.subTest(case_id=case_id):
                actions = expectations[case_id]["required_actions"]
                self.assertIn("return_exact_head_lifecycle_observations", actions)
                self.assertIn("mark_lifecycle_observations_non_gating", actions)

    def test_executor_payload_is_result_blind(self) -> None:
        for case in self.cases:
            payload = RUNNER.build_payload(case)
            serialized = json.dumps(payload, sort_keys=True)
            self.assertNotIn(case["id"], serialized)
            self.assertNotIn("case_id", serialized)
            self.assertNotIn("required_actions", serialized)
            self.assertNotIn("forbidden_actions", serialized)
            self.assertNotIn("terminal_state", serialized)
            self.assertNotIn(self.expectations_text, serialized)

    def test_forward_cases_execute_in_fresh_processes(self) -> None:
        observations, failures = RUNNER.evaluate_forward(
            RUNNER.DEFAULT_CASES,
            RUNNER.DEFAULT_EXPECTATIONS,
            [sys.executable, str(EXECUTOR_PATH)],
        )
        self.assertEqual([], failures)
        self.assertEqual(len(self.cases), len(observations))
        self.assertEqual(
            len(self.cases),
            len({result["executor_pid"] for result in observations.values()}),
        )

    def test_reference_executor_uses_the_supplied_contract(self) -> None:
        payload = RUNNER.build_payload(self.cases[0])
        payload["contract_documents"]["SPEC.md"] = ""
        observed = RUNNER.run_executor([sys.executable, str(EXECUTOR_PATH)], payload)
        self.assertEqual("blocked", observed["terminal_state"])
        self.assertEqual([], observed["actions"])

    def test_vocabulary_spam_cannot_pass_any_case(self) -> None:
        expectations = json.loads(self.expectations_text)
        action_vocabulary = sorted(
            {
                action
                for expected in expectations
                for field in ("required_actions", "forbidden_actions")
                for action in expected.get(field, [])
            }
        )
        for expected in expectations:
            observed = {
                "target_skill": "carve-changesets",
                "terminal_state": expected["terminal_state"],
                "actions": action_vocabulary,
            }
            failures = RUNNER.grade_forward(expected["case_id"], observed, expected)
            self.assertTrue(
                any("forbidden actions" in failure for failure in failures),
                expected["case_id"],
            )

    def test_integration_self_test_covers_baseline_and_successor_recovery(self) -> None:
        cases = json.loads(RUNNER.DEFAULT_INTEGRATION_CASES.read_text())
        self.assertEqual(
            {"chain-basic", "chain-compare", "successor-recovery-metadata"},
            {case["id"] for case in cases},
        )
        results = RUNNER.evaluate_integration(
            RUNNER.DEFAULT_INTEGRATION_CASES,
            test_argv=["python3", "-c", "print('ok')"],
        )
        self.assertTrue(all(result["ok"] for result in results.values()), results)
        for result in results.values():
            self.assertIn("equivalence", result["checks"])
            self.assertIn("validate_chain", result["checks"])
            self.assertIn("successor_recovery_metadata", result["checks"])

    def test_runner_has_no_agent_cli_specific_dependency(self) -> None:
        runner_source = RUNNER_PATH.read_text()
        parser_help = RUNNER.build_parser().format_help()
        self.assertIn("--executor", parser_help)
        self.assertIn("--integration-self-test", parser_help)
        self.assertNotIn("--skip-" + "codex", parser_help)
        self.assertNotIn("run_" + "codex", runner_source)
        self.assertNotIn("codex" + "_available", runner_source)

    def test_runner_writes_results_only_when_requested(self) -> None:
        output_dir = Path(tempfile.mkdtemp(prefix="carve-eval-output-"))
        try:
            rc = RUNNER.main(["--output-dir", str(output_dir)])
            self.assertEqual(0, rc)
            self.assertEqual(len(self.cases), len(list(output_dir.glob("*.json"))))
        finally:
            shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
