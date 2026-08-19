"""CI-run tests for review-fix-loop's cross-cutting evaluation corpus
(issue #101).

Unlike `test_local_commit.py`/`test_update_pr.py` (which own each
capability's own contract assertions), this module tests the *evaluation
harness itself*: that the full result-blind corpus passes against the real
engine, that it covers the scope this ticket's body requires, and — the
ticket's own required demonstration — that the grader actually rejects a
fabricated success claim and a fixture that cannot really converge. It never
duplicates a `test_local_commit.py`/`test_update_pr.py` assertion; it proves
the *corpus* is trustworthy, matching `carve-changesets/scripts/tests/
test_evals.py`'s own precedent for testing an eval harness under `just test`.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = SKILL_ROOT / "scripts" / "evals"
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EVALS_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load("review_fix_loop_eval_runner", "runner.py")
CORPUS = _load("review_fix_loop_eval_corpus", "corpus.py")
GRADER = _load("review_fix_loop_eval_grader", "grader.py")
HELPERS = _load("review_fix_loop_eval_helpers", "helpers.py")
LC = HELPERS.LC

EXPECTED_SCENARIO_IDS = {
    "lc-converged-clean-initial",
    "lc-converged-after-one-fix",
    "lc-budget-exhausted-persistent-finding",
    "lc-declined-finding-blocked",
    "lc-scope-expanding-finding-blocked",
    "lc-validation-unavailable-blocked",
    "lc-validation-failure-not-tractable",
    "lc-validation-failure-tractable-converges",
    "lc-reviewer-mutation-blocked",
    "lc-unattributed-ref-advance-converges",
    "lc-incomplete-review-blocked-verdict",
    "lc-invalid-stale-review-result-blocked",
    "lc-missing-capability-without-override",
    "lc-in-agent-override-bypasses-missing-capability",
    "lc-checkpoint-mismatch-resume-blocked",
    "lc-interrupted-attempt-recovered-without-losing-commit",
    "up-converged-published",
    "up-remote-advanced-stale-target-blocked",
    "up-sequential-publication-race-second-clone-loses",
    "up-missing-authority-target-mismatch-blocked",
    "up-mismatched-grant-blocked",
}

EXPECTED_CATEGORIES = {
    "convergence",
    "budget_exhaustion",
    "declined_findings",
    "validation_failure",
    "reviewer_mutation",
    "invalid_review",
    "review_mode",
    "recovery",
    "publication_race",
    "publication_target",
}


class CorpusShapeTests(unittest.TestCase):
    """The corpus itself covers this ticket's required scope."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases, cls.failures = RUNNER.run_all()

    def test_corpus_covers_every_required_scenario_id(self) -> None:
        self.assertEqual(EXPECTED_SCENARIO_IDS, set(self.cases))

    def test_corpus_covers_every_required_category(self) -> None:
        observed = {case["category"] for case in self.cases.values()}
        self.assertEqual(EXPECTED_CATEGORIES, observed)

    def test_corpus_exercises_both_publication_policies(self) -> None:
        policies = {case["policy"] for case in self.cases.values()}
        self.assertEqual({"local_commit", "update_pr"}, policies)

    def test_every_case_carries_more_than_the_terminal_contract_fields(self) -> None:
        """Every scenario's `checks` must include at least one
        independently-derived Git-evidence entry beyond the terminal
        contract's own self-reported `terminal_state`/`reason`/
        `schema_valid` — otherwise a scenario would just be re-parsing the
        implementation's own claim."""
        self_report_only = {"terminal_state", "reason", "schema_valid"}
        for case_id, case in self.cases.items():
            independent = set(case["checks"]) - self_report_only
            self.assertTrue(
                independent, f"{case_id} has no independent evidence checks"
            )

    def test_full_corpus_passes_against_the_real_engine(self) -> None:
        self.assertEqual([], self.failures, "\n".join(self.failures))

    def test_failure_messages_identify_fixture_evidence_and_reason(self) -> None:
        """A synthetic mismatch (not a real corpus failure) must still read
        as `<fixture id>: <check name>: expected ... observed ...` — this is
        what lets an operator act on a real failure without re-running
        anything, per this ticket's "identifies the exact fixture, observed
        evidence, and reason for failure" acceptance criterion."""
        case = {
            "id": "synthetic-example",
            "checks": {"marker_at_final_head": ("fixed", "broken")},
        }
        failures = GRADER.grade_case(case)
        self.assertEqual(
            [
                "synthetic-example: marker_at_final_head: expected 'fixed', "
                "observed 'broken'"
            ],
            failures,
        )


class SeededFaultDemonstrationTests(unittest.TestCase):
    """This ticket's Validation section requires demonstrating that a seeded
    faulty implementation or fixture is rejected, not merely asserted to be.
    Both tests below never call the real engine's success path; they prove
    the grader's independent Git checks — not the returned document's own
    claims — decide the outcome."""

    def test_grader_rejects_a_fabricated_convergence_claim(self) -> None:
        """A schema-shaped result that *claims* `converged` without any
        fix cycle ever having run must still be rejected, because the
        independent Git evidence (a real commit count and real file
        content) disagrees with that claim."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            repo = tmp_dir / "repo"
            HELPERS.init_repo(repo)
            base_sha, head_sha = HELPERS.start_candidate(
                repo, branch="lc/seeded-fault", marker="broken"
            )
            del base_sha
            # A faulty implementation that never actually ran a fix cycle,
            # yet reports success.
            fabricated_result = {
                "terminal_state": "converged",
                "head": {"initial": head_sha, "final": head_sha},
            }
            branch_head = GRADER.rev_parse(repo, "lc/seeded-fault")
            case = {
                "id": "seeded-fault-fabricated-convergence",
                "checks": {
                    "terminal_state": (
                        "converged",
                        fabricated_result["terminal_state"],
                    ),
                    # The same independent checks a genuine
                    # lc-converged-after-one-fix case uses.
                    "exactly_one_new_commit": (
                        1,
                        GRADER.rev_list_count(repo, head_sha, branch_head),
                    ),
                    "marker_at_final_head": (
                        "fixed",
                        GRADER.show_file(repo, branch_head, "marker.txt"),
                    ),
                },
            }
            failures = GRADER.grade_case(case)
        self.assertTrue(
            failures, "the grader must not be fooled by a self-reported success claim"
        )
        joined = "\n".join(failures)
        self.assertIn("exactly_one_new_commit", joined)
        self.assertIn("marker_at_final_head", joined)

    def test_grader_rejects_a_fixture_declared_to_converge_but_cannot(self) -> None:
        """A real engine run driven by a deliberately incomplete
        `apply_fix` fixture (it never writes the content the reviewer
        actually requires) cannot converge; declaring it "should converge"
        anyway (as a miswritten fixture might) must fail, proving this
        corpus does not rubber-stamp an arbitrary expectation either."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            repo = tmp_dir / "repo"
            HELPERS.init_repo(repo)
            base_sha, head_sha = HELPERS.start_candidate(
                repo, branch="lc/broken-fixture", marker="broken"
            )
            invocation = HELPERS.make_invocation(
                repo,
                policy="local_commit",
                branch="lc/broken-fixture",
                base_sha=base_sha,
                head_sha=head_sha,
                invocation_id="seeded-fault-broken-fixture",
                max_fix_cycles=1,
            )
            result = LC.run_local_commit(
                invocation,
                repo=repo,
                reviewer=HELPERS.make_marker_reviewer(repo),
                decide=HELPERS.accepting_decide,
                # Deliberately incomplete: this fixture can never satisfy
                # the reviewer, so the engine can never converge.
                apply_fix=HELPERS.make_never_fixing_apply_fix(),
            )
            # A miswritten fixture's expectation: "this converges."
            case = {
                "id": "seeded-fault-broken-fixture",
                "checks": {
                    "terminal_state": ("converged", result.get("terminal_state"))
                },
            }
            failures = GRADER.grade_case(case)
        self.assertTrue(failures)
        self.assertIn("terminal_state", failures[0])
        self.assertEqual("changes_remaining", result.get("terminal_state"))


if __name__ == "__main__":
    unittest.main()
