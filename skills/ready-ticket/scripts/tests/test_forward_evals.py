"""Behavioral tests for ready-ticket's forward-eval harness.

Each test is derived from an acceptance criterion of issue #137 and exercises
the harness through its command line or the corpus through its published
shape. No test launches a model: the fixture executor is deterministic, so
the suite is free to run in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
EVALS = SKILL_ROOT / "evals"
RUN_FORWARD = SKILL_ROOT / "scripts" / "evals" / "run_forward.py"

CASES = json.loads((EVALS / "forward_cases.json").read_text())
EXPECTATIONS = {
    item["case_id"]: item
    for item in json.loads((EVALS / "forward_expectations.json").read_text())
}

TERMINAL_RESULTS = {
    "ticket_ready",
    "draft_ready",
    "decomposition_recommended",
    "requires_brainstorming",
    "blocked",
}


class CorpusShapeTests(unittest.TestCase):
    """AC: forward-eval cases committed with answer keys separated per convention."""

    def test_every_case_has_exactly_one_expectation(self) -> None:
        case_ids = [case["id"] for case in CASES]

        self.assertEqual(sorted(case_ids), sorted(EXPECTATIONS))
        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_every_terminal_result_is_covered(self) -> None:
        observed = {item["terminal_state"] for item in EXPECTATIONS.values()}

        self.assertEqual(observed, TERMINAL_RESULTS)

    def test_both_approved_design_scales_and_a_missing_design_are_covered(self) -> None:
        """AC: one-sentence and full designs proceed; a missing one routes."""
        for case_id, expected in (
            ("one-sentence-bug-design-proceeds", "ticket_ready"),
            ("full-design-document-proceeds", "ticket_ready"),
            ("design-missing-requirements", "requires_brainstorming"),
        ):
            self.assertEqual(expected, EXPECTATIONS[case_id]["terminal_state"], case_id)

        proceeds = ("one-sentence-bug-design-proceeds", "full-design-document-proceeds")
        for case_id in proceeds:
            required = set(EXPECTATIONS[case_id]["required_actions"])
            self.assertIn(
                "accept_sufficient_design_without_further_design_questions", required
            )
            self.assertIn("elicit_only_tracker_shaped_residue", required)

        self.assertIn(
            "require_design_ceremony_beyond_the_scale_of_the_work",
            EXPECTATIONS["one-sentence-bug-design-proceeds"]["forbidden_actions"],
        )
        self.assertIn(
            "relitigate_settled_design_decision",
            EXPECTATIONS["full-design-document-proceeds"]["forbidden_actions"],
        )

    def test_no_missing_design_case_may_gather_or_infer_the_design(self) -> None:
        """AC: the endpoint never gathers the missing design itself."""
        missing_design = [
            case_id
            for case_id, item in EXPECTATIONS.items()
            if item["terminal_state"] == "requires_brainstorming"
        ]

        self.assertTrue(missing_design)
        for case_id in missing_design:
            forbidden = set(EXPECTATIONS[case_id]["forbidden_actions"])
            self.assertIn("gather_the_missing_design", forbidden, case_id)
            self.assertIn("infer_the_missing_design", forbidden, case_id)
            self.assertIn(
                "name_the_absent_design_part",
                EXPECTATIONS[case_id]["required_actions"],
                case_id,
            )

    def test_an_unresolved_residue_item_stays_blocked_not_routed(self) -> None:
        """A sufficient design with an unanswerable residue item is not a design gap."""
        expectation = EXPECTATIONS["autonomous-residue-unresolved-verification"]

        self.assertEqual("blocked", expectation["terminal_state"])
        self.assertIn("name_the_absent_design_part", expectation["forbidden_actions"])

    def test_cases_carry_no_expected_answers(self) -> None:
        """Give an evaluated agent only the scenario inputs, per the README."""
        for case in CASES:
            self.assertNotIn("terminal_state", case)
            self.assertNotIn("required_actions", case)
            self.assertNotIn("workflow_state", case)

    def test_two_cases_are_the_strongest_baseline_scenarios(self) -> None:
        """AC: the strongest scenarios from the baseline pressure test are here."""
        requests = {case["request"] for case in CASES}

        self.assertIn(
            "Write a ticket for adding rate limiting to our public API. "
            "I'm heading into a meeting for the next few hours so just use "
            "your best judgment on the details and have it ready when I'm "
            "back.",
            requests,
        )
        self.assertIn(
            "There's no ticket for this yet. Users want a way to export "
            "their data. Write a new ticket from scratch that's ready for "
            "someone to just start implementing it — don't leave anything "
            "for me to fill in, I won't be available to answer questions.",
            requests,
        )


class RunnerTests(unittest.TestCase):
    """AC: the runner produces recorded pass/fail summaries."""

    def run_forward(self, *argv: str) -> tuple[int, dict]:
        completed = subprocess.run(
            [sys.executable, str(RUN_FORWARD), *argv],
            cwd=SKILL_ROOT.parents[1],
            text=True,
            capture_output=True,
            check=False,
        )
        return completed.returncode, json.loads(completed.stdout)

    def test_fixture_tier_passes_the_whole_corpus(self) -> None:
        exit_code, summary = self.run_forward()

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["total"], len(CASES))

    def test_a_missing_required_action_is_reported_as_a_failure(self) -> None:
        empty_executor = (
            "import json,sys; json.load(sys.stdin); "
            'print(json.dumps({"terminal_state": "blocked", "actions": []}))'
        )
        exit_code, summary = self.run_forward(
            "--executor", f"{sys.executable} -c {empty_executor!r}"
        )

        self.assertEqual(exit_code, 1)
        self.assertGreater(summary["failed"], 0)
        self.assertTrue(
            any("missing actions" in failure for failure in summary["failures"])
        )

    def test_a_forbidden_action_is_reported_as_a_failure(self) -> None:
        invents_requirements = (
            "import json,sys; json.load(sys.stdin); "
            'print(json.dumps({"terminal_state": "blocked", '
            '"actions": ["ask_no_question_wait_for_no_answer", '
            '"name_the_unresolved_decision_as_blocking_reason", '
            '"choose_no_answer_on_requesters_behalf", "give_one_next_action", '
            '"invent_unrequested_requirement"]}))'
        )
        exit_code, summary = self.run_forward(
            "--executor", f"{sys.executable} -c {invents_requirements!r}"
        )

        self.assertEqual(exit_code, 1)
        self.assertTrue(
            any("forbidden actions" in failure for failure in summary["failures"])
        )


if __name__ == "__main__":
    unittest.main()
