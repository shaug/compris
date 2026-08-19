"""Behavioral tests for ready-ticket's forward-eval harness.

Each test is derived from an acceptance criterion of issue #137 and exercises
the harness through its command line or the corpus through its published
shape. No test launches a model: the fixture executor is deterministic, so
the suite is free to run in CI.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[2]
EVALS = SKILL_ROOT / "evals"
RUN_FORWARD = SKILL_ROOT / "scripts" / "evals" / "run_forward.py"
CLAUDE_EXECUTOR = SKILL_ROOT / "scripts" / "evals" / "claude_executor.py"


def load_module(path: Path, name: str):
    """Import an eval script by file path.

    `scripts/evals/` is not a package, and both this skill and
    implement-ticket ship a `claude_executor.py`; importing by path keeps the
    two from colliding on a shared `sys.path` entry.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


claude_executor = load_module(CLAUDE_EXECUTOR, "ready_ticket_claude_executor")

CASES = json.loads((EVALS / "forward_cases.json").read_text())
EXPECTATIONS = {
    item["case_id"]: item
    for item in json.loads((EVALS / "forward_expectations.json").read_text())
}

TERMINAL_RESULTS = {
    "ticket_ready",
    "draft_ready",
    "decomposition_recommended",
    "graph_created",
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

    def test_a_case_grades_how_repository_state_is_cited(self) -> None:
        """AC: a case grades quoting, location-citing, and value-restating."""
        expectation = EXPECTATIONS["repository-citation-quotes-and-locates"]

        self.assertEqual("ticket_ready", expectation["terminal_state"])
        required = set(expectation["required_actions"])
        forbidden = set(expectation["forbidden_actions"])
        self.assertIn("quote_cited_repository_text", required)
        self.assertIn("cite_volatile_collection_by_location", required)
        self.assertIn("restate_architectural_fact_as_value", required)
        self.assertIn("cite_bare_file_line_without_quoted_text", forbidden)
        self.assertIn("restate_volatile_collection_membership_as_value", forbidden)
        self.assertFalse(required & forbidden)

    def test_the_citation_case_names_its_facts_without_classifying_them(self) -> None:
        """The scenario must state the facts and leave the rule to the prose.

        An earlier draft described the lens set as one that "gains a member
        whenever a lens is added" and the recorder's output as changing "only
        when someone decides to change it". Both phrasings are the answer
        rather than the scenario: a fresh model given them chose correctly at
        the pre-change tree, so the case graded the hint instead of the prose.
        """
        case = next(
            item
            for item in CASES
            if item["id"] == "repository-citation-quotes-and-locates"
        )
        repository = case["artifacts"]["repository"]

        self.assertIn("line 251 of", repository)
        self.assertIn("which review lenses", repository)
        self.assertIn("what the eval recorder emits", repository)
        for classification in (
            "gains a member",
            "only when someone decides",
            "volatile",
        ):
            self.assertNotIn(classification, repository)

    def test_each_breakdown_rule_the_ticket_names_has_its_own_case(self) -> None:
        """AC: one case per named breakdown risk, each carrying its own bait.

        The bait matters as much as the case: a corpus that only rewards good
        answers measures very little, so each scenario below states a fact that
        tempts the wrong cut — an epic on the board, a shared sprint, a team
        habit, a raw line count.
        """
        cases = {case["id"]: case for case in CASES}
        for case_id, terminal_state, bait in (
            (
                "fits-as-one-stays-one-ticket",
                "ticket_ready",
                "leadership likes seeing an epic with sub-issues",
            ),
            (
                "unrelated-concerns-become-separate-leaves",
                "decomposition_recommended",
                "migration reads both",
            ),
            (
                "mechanical-and-behavioral-change-separated",
                "decomposition_recommended",
                "would rather not open two things",
            ),
            (
                "validation-stays-with-the-behavior-it-proves",
                "decomposition_recommended",
                "after the features are in",
            ),
            (
                "generated-evidence-excluded-from-size",
                "ticket_ready",
                "4,500 lines of generated JSON",
            ),
        ):
            with self.subTest(case=case_id):
                self.assertEqual(
                    terminal_state, EXPECTATIONS[case_id]["terminal_state"]
                )
                self.assertIn(bait, json.dumps(cases[case_id]["artifacts"]))

    def test_a_case_that_fits_as_one_may_not_grow_a_parent(self) -> None:
        """AC: one reviewable initiative stays one ticket."""
        for case_id in (
            "fits-as-one-stays-one-ticket",
            "generated-evidence-excluded-from-size",
        ):
            expectation = EXPECTATIONS[case_id]
            with self.subTest(case=case_id):
                self.assertIn(
                    "keep_reviewable_initiative_as_one_ticket",
                    expectation["required_actions"],
                )
                self.assertIn(
                    "decompose_to_a_single_child", expectation["forbidden_actions"]
                )

    def test_every_decomposition_case_owes_the_graph_rather_than_a_rationale(
        self,
    ) -> None:
        """AC: the draft names its nodes, its edges, and every leaf's body.

        Each case also forbids an internal-signature criterion, which is where
        acceptance criterion 4 is actually observable: a leaf body only exists
        in a case that produces a graph, so the two `ticket_ready` cases that
        already carry this term cannot reach the obligation. Without it here,
        a run could draft every leaf against internal function signatures —
        the altitude failure the `writing-plans` borrow makes reachable — and
        all eighteen cases would still pass.
        """
        decomposing = [
            case_id
            for case_id, item in EXPECTATIONS.items()
            if item["terminal_state"] == "decomposition_recommended"
        ]

        self.assertTrue(decomposing)
        for case_id in decomposing:
            expectation = EXPECTATIONS[case_id]
            required = set(expectation["required_actions"])
            with self.subTest(case=case_id):
                self.assertIn("name_every_graph_node_and_edge", required)
                self.assertIn("draft_a_complete_body_for_every_leaf", required)
                self.assertIn(
                    "assert_criterion_on_internals", expectation["forbidden_actions"]
                )

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

    def test_every_fixture_answer_uses_the_closed_vocabulary(self) -> None:
        """A corpus term absent from the executor's list is ungradable."""
        fixture = load_module(
            SKILL_ROOT / "scripts" / "evals" / "fixture_executor.py",
            "ready_ticket_fixture_executor",
        )
        vocabulary = set(claude_executor.ACTION_VOCABULARY)

        self.assertEqual(set(fixture.ANSWERS), {case["request"] for case in CASES})
        for request, answer in fixture.ANSWERS.items():
            self.assertLessEqual(set(answer["actions"]), vocabulary, request)
        for case_id, expectation in EXPECTATIONS.items():
            self.assertLessEqual(
                set(expectation["required_actions"])
                | set(expectation["forbidden_actions"]),
                vocabulary,
                case_id,
            )


class RepetitionTests(unittest.TestCase):
    """AC: the real-model tier records how many repetitions agreed."""

    def combine(self, *samples: tuple[str, list[str]]) -> dict:
        return claude_executor.combine(
            [
                claude_executor.sample({"terminal_state": state, "actions": actions})
                for state, actions in samples
            ]
        )

    def test_the_majority_terminal_state_wins_and_its_agreement_is_recorded(
        self,
    ) -> None:
        combined = self.combine(
            ("ticket_ready", []),
            ("ticket_ready", []),
            ("blocked", []),
        )

        self.assertEqual("ticket_ready", combined["terminal_state"])
        self.assertEqual(3, combined["repetitions"])
        self.assertAlmostEqual(2 / 3, combined["agreement"])
        self.assertEqual(
            {"ticket_ready": 2, "blocked": 1}, combined["votes"]["terminal_state"]
        )

    def test_an_action_is_reported_only_on_a_strict_majority(self) -> None:
        combined = self.combine(
            ("ticket_ready", ["quote_cited_repository_text"]),
            ("ticket_ready", ["quote_cited_repository_text"]),
            ("ticket_ready", ["invent_unrequested_requirement"]),
        )

        self.assertEqual(["quote_cited_repository_text"], combined["actions"])
        self.assertEqual(
            {"quote_cited_repository_text": 2, "invent_unrequested_requirement": 1},
            combined["votes"]["actions"],
        )

    def test_a_sample_without_a_terminal_state_still_serializes(self) -> None:
        """One unusable sample grades as a mismatch; it does not end the run.

        The vote counts become JSON object keys, and
        `json.dump(..., sort_keys=True)` cannot order `None` against a string.
        Keying an absent state raw raised `TypeError` at output time, which
        `run_forward.py` surfaces as a non-zero executor exit — ending the
        whole corpus mid-run, discarding every case already sampled, and
        leaving `record_eval_run.py` to file the loss as `attempted`, the
        status reserved for an environment without model access.
        """
        combined = claude_executor.combine(
            [
                claude_executor.sample({"terminal_state": "ticket_ready"}),
                claude_executor.sample({"actions": []}),
            ]
        )

        json.dumps(combined, sort_keys=True)
        self.assertEqual(
            {"ticket_ready": 1, "none": 1}, combined["votes"]["terminal_state"]
        )

    def test_an_all_unusable_run_reports_no_terminal_state_rather_than_the_sentinel(
        self,
    ) -> None:
        """The sentinel is a vote key, never a graded answer."""
        combined = claude_executor.combine(
            [claude_executor.sample({"actions": []}) for _ in range(3)]
        )

        self.assertIsNone(combined["terminal_state"])
        self.assertEqual({"none": 3}, combined["votes"]["terminal_state"])

    def test_a_term_outside_the_vocabulary_is_discarded(self) -> None:
        combined = self.combine(("ticket_ready", ["not_a_real_action"]))

        self.assertEqual([], combined["actions"])
        self.assertEqual({}, combined["votes"]["actions"])

    @staticmethod
    def completed(result_text: str) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=json.dumps({"result": result_text}),
            stderr="",
        )

    def test_a_malformed_sample_is_retried_rather_than_sinking_the_run(self) -> None:
        """One flaky response must not end a run of many sequential samples."""
        malformed = '{"terminal_state": "ticket_ready"'
        valid = '{"terminal_state": "ticket_ready", "actions": []}'

        with mock.patch.object(
            claude_executor.subprocess,
            "run",
            side_effect=[self.completed(malformed), self.completed(valid)],
        ) as run_mock:
            observed = claude_executor.run_claude("prompt", "claude", None)

        self.assertEqual("ticket_ready", observed["terminal_state"])
        self.assertEqual(2, run_mock.call_count)

    def test_a_run_of_malformed_samples_raises_once_attempts_are_spent(self) -> None:
        malformed = '{"terminal_state": "ticket_ready"'
        attempts = claude_executor.RESULT_ATTEMPTS

        with mock.patch.object(
            claude_executor.subprocess,
            "run",
            side_effect=[self.completed(malformed)] * attempts,
        ) as run_mock:
            with self.assertRaises(RuntimeError):
                claude_executor.run_claude("prompt", "claude", None)

        self.assertEqual(attempts, run_mock.call_count)


if __name__ == "__main__":
    unittest.main()
