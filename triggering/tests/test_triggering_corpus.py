"""Behavioral tests for the triggering corpus and its runner.

Each test is derived from an acceptance criterion of issue #136 and exercises
the runner through its command line or the corpus through its published shape.
No test launches a model: the runs under test use the deterministic fixture
executor or a stub, so the suite is free to run in CI.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TRIGGERING = REPOSITORY_ROOT / "triggering"
SPEC = importlib.util.spec_from_file_location(
    "triggering_runner", TRIGGERING / "runner.py"
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

CORPUS = json.loads((TRIGGERING / "corpus.json").read_text(encoding="utf-8"))
EXPECTATIONS = json.loads(
    (TRIGGERING / "expectations.json").read_text(encoding="utf-8")
)
COMPOSITION = json.loads(
    (TRIGGERING / "composition-cases.json").read_text(encoding="utf-8")
)


class CorpusCoverageTests(unittest.TestCase):
    """AC: the corpus covers every skill, with positive, negative, and collisions."""

    def test_every_installed_skill_has_cases(self) -> None:
        skills_on_disk = {
            path.parent.name for path in (REPOSITORY_ROOT / "skills").glob("*/SKILL.md")
        }
        covered = {case["skill"] for case in CORPUS["cases"]}

        self.assertEqual(skills_on_disk, covered)

    def test_every_skill_has_a_positive_and_a_non_positive_case(self) -> None:
        for skill in CORPUS["skills"]:
            kinds = {case["kind"] for case in CORPUS["cases"] if case["skill"] == skill}
            self.assertIn("positive", kinds, f"{skill} has no positive prompt")
            self.assertTrue(
                kinds & {"negative", "collision"},
                f"{skill} has no negative or collision prompt",
            )

    def test_the_named_collision_prompts_are_present_in_both_directions(self) -> None:
        """Both named prompts, both filed from the skills they pull between.

        Asserting mere presence for one of them let it ship filed from a single
        side, which is the omission this now fails on.
        """
        both_directions = {
            "Review my change.": {"review-code-change", "review-code-simplicity"},
            "Before merging, give this a proper review.": {
                "review-code-change",
                "babysit-pr",
            },
        }
        for prompt, expected_sides in both_directions.items():
            filed_under = {
                case["skill"] for case in CORPUS["cases"] if case["prompt"] == prompt
            }
            self.assertEqual(
                filed_under,
                expected_sides,
                f"{prompt!r} must be filed from both sides it pulls between",
            )

    def test_implement_ticket_n_is_asserted_from_both_sides(self) -> None:
        cases = [
            case
            for case in CORPUS["cases"]
            if case["prompt"] == "Implement ticket 412."
        ]
        self.assertEqual(
            {case["skill"] for case in cases},
            {"implement-ticket", "plan-implementation"},
        )
        answers = {
            item["case_id"]: item["expected_skill"]
            for item in EXPECTATIONS["expectations"]
        }
        for case in cases:
            self.assertEqual(
                answers[case["id"]],
                "implement-ticket",
                "both sides must agree implement-ticket wins",
            )

    def test_planning_cutover_adds_a_positive_without_losing_review_negative(
        self,
    ) -> None:
        answers = {
            item["case_id"]: item["expected_skill"]
            for item in EXPECTATIONS["expectations"]
        }

        self.assertEqual(
            answers["plan-implementation-positive-planner"],
            "plan-implementation",
        )
        self.assertIsNone(answers["review-code-change-negative-plan"])


class ResultBlindnessTests(unittest.TestCase):
    """The evaluated router must never see the answer key."""

    def test_corpus_carries_no_expected_answers(self) -> None:
        for case in CORPUS["cases"]:
            self.assertNotIn("expected", case)
            self.assertNotIn("expected_skill", case)
            self.assertNotIn("note", case)

    def test_executor_payload_contains_only_the_prompt_and_catalog(self) -> None:
        case = CORPUS["cases"][0]
        payload = runner.build_payload(case, runner.skill_catalog())

        self.assertEqual(set(payload), {"prompt", "catalog"})
        self.assertEqual(payload["prompt"], case["prompt"])
        serialized = json.dumps(payload)
        self.assertNotIn(case["kind"], serialized)
        self.assertNotIn(case["id"], serialized)

    def test_catalog_is_read_from_the_live_skill_descriptions(self) -> None:
        catalog = {
            entry["skill"]: entry["description"] for entry in runner.skill_catalog()
        }

        self.assertIn("implement-ticket", catalog)
        self.assertIn("ready_pr", catalog["implement-ticket"])
        self.assertNotIn("allowed-tools", catalog["review-code-change"])


class RunnerTests(unittest.TestCase):
    """AC: the runner produces pass/fail summaries with tier provenance."""

    def run_runner(self, *argv: str) -> tuple[int, dict]:
        completed = subprocess.run(
            [sys.executable, str(TRIGGERING / "runner.py"), *argv],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        return completed.returncode, json.loads(completed.stdout)

    def test_deterministic_run_passes_the_whole_corpus(self) -> None:
        exit_code, summary = self.run_runner()

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["total"], len(CORPUS["cases"]))

    def test_summary_records_which_tier_produced_the_results(self) -> None:
        _, summary = self.run_runner()

        self.assertEqual(summary["tiers"], ["fixture"])

    def test_per_case_files_carry_the_tier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.run_runner("--output-dir", directory)
            written = sorted(Path(directory).glob("*.json"))
            self.assertEqual(len(written), len(CORPUS["cases"]))
            observed = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual(observed["tier"], "fixture")

    def test_skill_filter_runs_only_that_skills_cases(self) -> None:
        _, summary = self.run_runner("--skill", "babysit-pr")
        expected = sum(1 for case in CORPUS["cases"] if case["skill"] == "babysit-pr")

        self.assertEqual(summary["total"], expected)

    def test_a_wrong_answer_is_reported_as_a_failure(self) -> None:
        always_babysit = (
            "import json,sys; json.load(sys.stdin); "
            "print(json.dumps({'selected_skill':'babysit-pr','tier':'fixture'}))"
        )
        exit_code, summary = self.run_runner(
            "--executor", shlex.join([sys.executable, "-c", always_babysit])
        )

        self.assertEqual(exit_code, 1)
        self.assertGreater(summary["failed"], 0)
        self.assertTrue(
            any("selected_skill" in failure for failure in summary["failures"])
        )

    def test_a_result_without_a_tier_fails_rather_than_counting(self) -> None:
        """Provenance is required: an untiered answer is not usable evidence."""
        untiered = (
            "import json,sys; json.load(sys.stdin); "
            "print(json.dumps({'selected_skill':'babysit-pr'}))"
        )
        exit_code, summary = self.run_runner(
            "--skill",
            "babysit-pr",
            "--executor",
            shlex.join([sys.executable, "-c", untiered]),
        )

        self.assertEqual(exit_code, 1)
        self.assertTrue(any("tier" in failure for failure in summary["failures"]))


class CompositionCaseTests(unittest.TestCase):
    """AC: composition cases exist per seam, or the gap is recorded per case."""

    def test_every_case_names_a_seam_and_an_expected_behavior(self) -> None:
        self.assertTrue(COMPOSITION["cases"])
        for case in COMPOSITION["cases"]:
            self.assertTrue(case["seam"])
            self.assertTrue(case["expected_behavior"])
            self.assertTrue(case["why_it_matters"])

    def test_a_case_that_did_not_run_records_a_specific_gap(self) -> None:
        for case in COMPOSITION["cases"]:
            if case["status"] == "not_run":
                self.assertTrue(
                    case.get("gap"),
                    f"{case['id']} did not run and records no gap",
                )
                # #128 cites these, so a gap naming no cause is not citable.
                self.assertGreater(
                    len(case["gap"]), 80, f"{case['id']} gap is not specific"
                )

    def test_every_seam_named_in_shipped_prose_has_a_case(self) -> None:
        """A seam that has landed must be exercised or explicitly gapped.

        Derived from the prose rather than listed here, so a newly landed seam
        without a composition case fails instead of passing silently — which is
        how the test-driven-development and systematic-debugging seams were
        missed when they landed.
        """
        named_in_prose = set()
        for skill_md in (REPOSITORY_ROOT / "skills").glob("*/SKILL.md"):
            # Normalize whitespace across the whole file before matching. The
            # repository wraps prose at 80 columns, so an availability
            # condition routinely straddles a line break — matching per line
            # silently skipped three of the five landed seams, including both
            # seams this test exists to catch.
            prose = re.sub(r"\s+", " ", skill_md.read_text(encoding="utf-8"))
            for match in re.finditer(r"`(superpowers:[a-z-]+|load-bearing)`", prose):
                window = prose[match.end() : match.end() + 80]
                if "available in the session skill listing" in window:
                    named_in_prose.add(match.group(1).replace("superpowers:", ""))

        covered = " ".join(case["seam"] for case in COMPOSITION["cases"])
        missing = sorted(peer for peer in named_in_prose if peer not in covered)

        self.assertEqual(
            missing, [], f"landed seams with no composition case: {missing}"
        )

    def test_peer_install_state_is_recorded_for_every_required_peer(self) -> None:
        for case in COMPOSITION["cases"]:
            for peer in case["requires_peers"]:
                self.assertIn(peer, COMPOSITION["peers"])
                self.assertIn("installed", COMPOSITION["peers"][peer])


class KnownOverlapTests(unittest.TestCase):
    """Scope: vice-versa collisions are recorded with their observed behavior."""

    OVERLAPS = json.loads(
        (TRIGGERING / "known-overlaps.json").read_text(encoding="utf-8")
    )

    def test_every_overlap_records_what_was_actually_observed(self) -> None:
        for overlap in self.OVERLAPS["overlaps"]:
            observed = overlap["observed_at"]
            # An overlap asserted without a run behind it is an opinion; #128
            # cites these as evidence, so each needs its tier and its votes.
            self.assertIn(observed["tier"], ("headless", "description", "fixture"))
            self.assertTrue(observed["votes"])
            self.assertEqual(sum(observed["votes"].values()), observed["repetitions"])
            self.assertAlmostEqual(
                observed["agreement"],
                max(observed["votes"].values()) / observed["repetitions"],
            )

    def test_every_overlap_names_a_real_case_and_says_why_it_is_not_fixed(self) -> None:
        case_ids = {case["id"] for case in CORPUS["cases"]}
        for overlap in self.OVERLAPS["overlaps"]:
            self.assertIn(overlap["observed_at"]["case_id"], case_ids)
            self.assertTrue(overlap["why_not_fixed_here"])
            self.assertTrue(overlap["next_evidence"])


class AnswerKeyTests(unittest.TestCase):
    def test_every_case_has_exactly_one_expectation(self) -> None:
        case_ids = [case["id"] for case in CORPUS["cases"]]
        answer_ids = [item["case_id"] for item in EXPECTATIONS["expectations"]]

        self.assertEqual(sorted(case_ids), sorted(answer_ids))
        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_every_expectation_names_a_real_skill_or_nothing(self) -> None:
        known = {
            path.parent.name for path in (REPOSITORY_ROOT / "skills").glob("*/SKILL.md")
        }
        for item in EXPECTATIONS["expectations"]:
            expected = item["expected_skill"]
            if expected is not None:
                self.assertIn(expected, known, item["case_id"])
            self.assertTrue(item["rationale"], item["case_id"])


if __name__ == "__main__":
    unittest.main()
