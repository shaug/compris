"""End-to-end tests for the standalone `local_commit` workflow (issue #99).

Every test drives `local_commit.run_local_commit` against a real temporary Git
repository (matching `test_local_execution.py`'s "no mocked Git state"
convention) with small, deterministic fakes for the two genuinely host-boundary
actions the design assigns to the executing agent: running one
`review-code-change` pass and writing a fix's content. The fake reviewer
inspects the real repository content at the exact head it is asked to review
(`marker.txt`) rather than counting calls, so the same fake works across every
scenario and the review verdict is always a real function of real repository
state.

Covers the ticket's required end-to-end fixtures: immediate convergence, one
or more fix cycles, budget exhaustion, validation failure (both the
"unavailable" and "no tractable correction" shapes), operator input
(rejected/deferred disposition and scope expansion), and recovery from an
interrupted attempt.

The module loader, a bare local repository, the always-passing validation
commands, the marker-file-driven fake reviewer, and the accepting
decider/fixer are shared with `test_update_pr.py` via this sibling
directory's own `helpers.py`, matching `carve-changesets/scripts/tests/
helpers.py`'s established precedent for one skill's own shared test fixture
module.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

import helpers

LC = helpers.load_module("review_fix_loop_local_commit", "local_commit.py")
LE = helpers.load_module(
    "review_fix_loop_local_execution_for_tests", "local_execution.py"
)
VALIDATE = helpers.load_module("review_fix_loop_validate_for_tests", "validate.py")

# Fixtures shared with test_update_pr.py; see helpers.py.
init_repo = helpers.init_repo
ALWAYS_PASS_VALIDATION = helpers.ALWAYS_PASS_VALIDATION
CLEAN_TEMPLATE = helpers.CLEAN_TEMPLATE
FINDING_ID = helpers.FINDING_ID
_finding = helpers.finding
make_marker_reviewer = helpers.make_marker_reviewer
fixing_apply_fix = helpers.fixing_apply_fix
accepting_decide = helpers.accepting_decide


# ---------------------------------------------------------------------------
# Repository fixtures
# ---------------------------------------------------------------------------


def start_candidate(
    repo: Path,
    *,
    branch: str = "fix/99-example",
    marker: str = "broken",
    validation_flag: str = "pass",
) -> tuple[str, str]:
    """Create `branch` off `main` with one commit adding the two control
    files this test suite's fakes read. Returns `(base_sha, head_sha)`."""
    base_sha = LE.current_head(repo)
    LE.git("checkout", "-q", "-b", branch, cwd=repo)
    (repo / "marker.txt").write_text(marker + "\n")
    (repo / "validation_flag.txt").write_text(validation_flag + "\n")
    LE.git("add", "-A", cwd=repo)
    LE.git("commit", "-q", "-m", "start candidate", cwd=repo)
    head_sha = LE.current_head(repo)
    return base_sha, head_sha


FLAG_GATED_VALIDATION = [
    {
        "name": "focused unit test",
        "command": (
            'python3 -c "import pathlib,sys; '
            "sys.exit(0 if pathlib.Path('validation_flag.txt').read_text().strip()"
            "=='pass' else 1)\""
        ),
        "scope": "focused",
    },
    {"name": "full repository gate", "command": "true", "scope": "full"},
]

# `marker.txt` also drives the fake reviewer (below); this command only fails
# for the literal sentinel `trigger-fail`, so it never fires for the ordinary
# 'broken'/'fixed' content the reviewer itself reacts to.
NOT_TRIGGER_FAIL_VALIDATION = [
    {
        "name": "focused unit test",
        "command": (
            'python3 -c "import pathlib,sys; '
            "sys.exit(1 if pathlib.Path('marker.txt').read_text().strip()"
            "=='trigger-fail' else 0)\""
        ),
        "scope": "focused",
    },
    {"name": "full repository gate", "command": "true", "scope": "full"},
]


def make_invocation(
    repo: Path,
    *,
    branch: str,
    base_sha: str,
    head_sha: str,
    invocation_id: str = "local-commit-test",
    max_fix_cycles: int = 3,
    validation: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    common_dir = LE.git_common_dir(repo)
    diff = LE.git("diff", base_sha, head_sha, cwd=repo).stdout
    worktree = LE.worktree_status(repo)
    return {
        "schema_version": "1.0",
        "invocation_id": invocation_id,
        "repository": {
            "identity": "shaug/compris",
            "git_common_directory": str(common_dir),
        },
        "candidate": {
            "branch": branch,
            "head_sha": head_sha,
            "comparison_base": {"ref": "main", "sha": base_sha},
            "diff": {"format": "unified_diff", "complete": True, "content": diff},
            "worktree": worktree,
            "all_changes_committed": True,
            "source_unavailable_reason": "standalone invocation has no recorded pushable source",
        },
        "change_contract": {
            "goal": "Fix the example.",
            "acceptance_criteria": ["marker.txt reads 'fixed'"],
            "non_goals": ["Unrelated refactors"],
            "preserved_behaviors": ["Existing README content"],
            "allowed_remediation_scope": "marker.txt only",
            "sources": {
                "repository_instructions": [],
                "named_documents": [],
                "nearby_patterns": [],
            },
        },
        "review_execution": {"mode": "fresh_subagent"},
        "fix_cycle_budget": {"max_fix_cycles": max_fix_cycles},
        "validation": validation or ALWAYS_PASS_VALIDATION,
        "publication": {"policy": "local_commit"},
    }


def ineffective_apply_fix(*, finding, attempt_path, change_contract, attempt_number):
    del finding, change_contract
    (attempt_path / "marker.txt").write_text(f"still-broken-{attempt_number}\n")
    return f"fix attempt {attempt_number} for {FINDING_ID}"


class LocalCommitRepoTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        init_repo(self.repo)


class ImmediateConvergenceTests(LocalCommitRepoTestCase):
    def test_clean_candidate_converges_without_any_fix_cycle(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "converged")
        self.assertNotIn("reason", result)
        self.assertEqual(result["head"]["initial"], head_sha)
        self.assertEqual(result["head"]["final"], head_sha)
        self.assertEqual(result["created_commits"], [])
        self.assertEqual(result["budget"]["consumed_cycles"], 0)
        self.assertFalse(result["acceptance_reconciliation_required"])
        self.assertEqual(
            result["publication"],
            {
                "policy": "local_commit",
                "status": "not_applicable",
                "non_converged_exposure": False,
            },
        )
        self.assertEqual(len(result["review_records"]), 1)
        self.assertEqual(result["review_records"][0]["aggregate_verdict"], "clean")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])


class FixCycleTests(LocalCommitRepoTestCase):
    def test_one_fix_cycle_converges(self):
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "converged")
        self.assertEqual(result["head"]["initial"], head_sha)
        self.assertNotEqual(result["head"]["final"], head_sha)
        self.assertEqual(len(result["created_commits"]), 1)
        self.assertEqual(result["budget"]["consumed_cycles"], 1)
        self.assertEqual(result["budget"]["remaining_cycles"], 2)
        self.assertTrue(result["acceptance_reconciliation_required"])
        self.assertEqual(result["unpushed_commits"], result["created_commits"])
        self.assertEqual(
            result["finding_dispositions"],
            [
                {
                    "finding_id": FINDING_ID,
                    "disposition": "selected",
                    "rationale": f"{FINDING_ID} is tractable",
                    "fix_commit_sha": result["created_commits"][0],
                }
            ],
        )
        # Two review passes: the initial non-clean one and the post-fix clean one.
        self.assertEqual(len(result["review_records"]), 2)
        self.assertEqual(
            result["review_records"][0]["aggregate_verdict"], "changes_required"
        )
        self.assertEqual(result["review_records"][1]["aggregate_verdict"], "clean")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])

        # The canonical worktree actually advanced to the promoted commit.
        self.assertEqual(LE.current_head(self.repo), result["head"]["final"])
        self.assertEqual((self.repo / "marker.txt").read_text().strip(), "fixed")
        self.assertTrue(LE.is_clean(LE.worktree_status(self.repo)))

    def test_multiple_fix_cycles_before_convergence(self):
        """The fake reviewer only reports `clean` once marker.txt reads
        'fixed'; a fixer that takes two attempts to actually write that
        content demonstrates more than one committed fix cycle."""
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            max_fix_cycles=5,
        )

        attempts_seen: list[int] = []

        def two_step_apply_fix(
            *, finding, attempt_path, change_contract, attempt_number
        ):
            del finding, change_contract
            attempts_seen.append(attempt_number)
            content = "fixed" if len(attempts_seen) >= 2 else "getting-there"
            (attempt_path / "marker.txt").write_text(content + "\n")
            return f"fix attempt {attempt_number}"

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=two_step_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "converged")
        self.assertEqual(len(result["created_commits"]), 2)
        self.assertEqual(result["budget"]["consumed_cycles"], 2)
        self.assertEqual(len(result["review_records"]), 3)
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])


class BudgetExhaustionTests(LocalCommitRepoTestCase):
    def test_ineffective_fixes_exhaust_the_budget(self):
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            max_fix_cycles=2,
        )
        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=ineffective_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "changes_remaining")
        self.assertEqual(result["reason"], "cycle_budget_exhausted")
        self.assertEqual(result["budget"]["consumed_cycles"], 2)
        self.assertEqual(result["budget"]["remaining_cycles"], 0)
        self.assertEqual(len(result["created_commits"]), 2)
        self.assertEqual(result["unpushed_commits"], result["created_commits"])
        self.assertEqual(result["publication"]["status"], "not_applicable")
        self.assertIn(FINDING_ID, result["unresolved_or_deferred_findings"][0])
        self.assertTrue(result["operator_action"])
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])
        # The candidate itself is preserved at its last committed head, not lost.
        self.assertEqual(LE.current_head(self.repo), result["head"]["final"])


FINDING_ID_2 = "correctness-002"


def _finding2() -> dict[str, Any]:
    return {
        "id": FINDING_ID_2,
        "lens": "correctness",
        "severity": "blocking",
        "confidence": "high",
        "rule": "example rule",
        "evidence": [
            {"location": "other_file.txt:1", "detail": "other_file.txt reads 'broken'"}
        ],
        "concern": "other_file.txt does not read 'ok'",
        "impact": "a second defect is present",
        "proposed_change": "write 'ok' into other_file.txt",
        "expected_effect": "other_file.txt reads 'ok'",
    }


def make_two_finding_reviewer(repo: Path):
    """A fake reviewer gating on two independent tracked files: `marker.txt`
    (finding `correctness-001`) and `other_file.txt` (finding
    `correctness-002`, treated as absent/resolved when the file does not yet
    exist at the reviewed head). Lets a test drive expanding or oscillating
    finding sets across cycles by controlling both files independently.
    """

    def reviewer(
        *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
    ) -> LC.ReviewPass:
        del packet, briefing, independence, sequence
        marker = LE.git("show", f"{head_sha}:marker.txt", cwd=repo).stdout.strip()
        other = LE.git("show", f"{head_sha}:other_file.txt", cwd=repo, check=False)
        other_content = other.stdout.strip() if other.returncode == 0 else "ok"
        findings = []
        if marker != "fixed":
            findings.append(_finding())
        if other_content == "broken":
            findings.append(_finding2())
        candidate = {"head_sha": head_sha, "comparison_base_sha": comparison_base_sha}
        if not findings:
            result = {
                **CLEAN_TEMPLATE,
                "candidate": candidate,
                "lens_executions": [
                    {
                        "lens": lens,
                        "head_sha": head_sha,
                        "comparison_base_sha": comparison_base_sha,
                        "verdict": "clean",
                        "freshly_executed": True,
                    }
                    for lens in (
                        "solution_simplicity",
                        "correctness",
                        "code_simplicity",
                    )
                ],
            }
        else:
            result = {
                **CLEAN_TEMPLATE,
                "candidate": candidate,
                "verdict": "changes_required",
                "findings": findings,
                "lens_executions": [
                    {
                        "lens": "solution_simplicity",
                        "head_sha": head_sha,
                        "comparison_base_sha": comparison_base_sha,
                        "verdict": "clean",
                        "freshly_executed": True,
                    }
                ],
                "next_action": "Fix the reported findings.",
            }
        return LC.ReviewPass(result=result)

    return reviewer


class StopConditionTests(LocalCommitRepoTestCase):
    def test_a_fix_that_introduces_a_new_finding_stops_as_expanding_findings(self):
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            max_fix_cycles=3,
        )

        def apply_fix(*, finding, attempt_path, change_contract, attempt_number):
            del finding, change_contract, attempt_number
            # Leave marker.txt (correctness-001) unresolved and additionally
            # introduce a second, independent defect.
            (attempt_path / "other_file.txt").write_text("broken\n")
            return "fix: (ineffectively) touch other_file.txt too"

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_two_finding_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=apply_fix,
        )
        self.assertEqual(result["terminal_state"], "changes_remaining")
        self.assertEqual(result["reason"], "expanding_findings")
        self.assertEqual(result["budget"]["consumed_cycles"], 1)
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])

    def test_oscillating_finding_sets_stop_as_oscillation(self):
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            max_fix_cycles=5,
        )

        def apply_fix(*, finding, attempt_path, change_contract, attempt_number):
            del finding, change_contract
            if attempt_number % 2 == 1:
                (attempt_path / "marker.txt").write_text("fixed\n")
                (attempt_path / "other_file.txt").write_text("broken\n")
            else:
                (attempt_path / "marker.txt").write_text("broken\n")
                (attempt_path / "other_file.txt").write_text("ok\n")
            return f"fix attempt {attempt_number}: swap which defect is present"

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_two_finding_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=apply_fix,
        )
        self.assertEqual(result["terminal_state"], "changes_remaining")
        self.assertEqual(result["reason"], "oscillation")
        self.assertEqual(result["budget"]["consumed_cycles"], 2)
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])

    def test_two_consecutive_failed_attempts_stop_as_repeated_failed_attempt(self):
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            max_fix_cycles=3,
            validation=NOT_TRIGGER_FAIL_VALIDATION,
        )

        def always_fails_validation_apply_fix(
            *, finding, attempt_path, change_contract, attempt_number
        ):
            del finding, change_contract, attempt_number
            (attempt_path / "marker.txt").write_text("trigger-fail\n")
            return "fix attempt that never actually validates"

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=always_fails_validation_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "changes_remaining")
        self.assertEqual(result["reason"], "repeated_failed_attempt")
        self.assertEqual(result["budget"]["consumed_cycles"], 2)
        self.assertEqual(result["created_commits"], [])
        self.assertEqual(len(result["preserved_failed_attempts"]), 2)
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])
        # Canonical candidate untouched: both attempts failed validation and
        # were discarded rather than promoted.
        self.assertEqual(LE.current_head(self.repo), head_sha)
        self.assertTrue(LE.is_clean(LE.worktree_status(self.repo)))


class RegressionTests(LocalCommitRepoTestCase):
    def test_resumed_acceptance_replaces_a_stale_declined_disposition(self):
        """A finding declined on one pass and later accepted-and-fixed after
        a resumed run with a different decision must not leave both a stale
        `declined` entry and the real `selected` entry in the same result."""
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        branch = "fix/99-example"
        invocation_id = "local-commit-regression-test"
        invocation = make_invocation(
            self.repo,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            invocation_id=invocation_id,
        )

        def declining_decide(*, finding, change_contract, attempt_number):
            del change_contract, attempt_number
            return LC.FixDecision(
                disposition="rejected",
                rationale=f"{finding['id']} looked out of scope on first review",
            )

        first = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=declining_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(first["terminal_state"], "blocked")
        self.assertEqual(first["reason"], "operator_input_required")

        common_dir = LE.git_common_dir(self.repo)
        checkpoint_path = LE.checkpoint_path(common_dir, invocation_id)
        checkpoint = LE.read_checkpoint(checkpoint_path)

        second = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
            resume_checkpoint=checkpoint,
        )
        self.assertEqual(second["terminal_state"], "converged")
        self.assertEqual(second["resume_status"], "resumed")
        # Exactly one disposition for this finding_id, and it is the real,
        # current one — not both a stale `declined` and the new `selected`.
        matching = [
            entry
            for entry in second["finding_dispositions"]
            if entry["finding_id"] == FINDING_ID
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["disposition"], "selected")
        self.assertIn("fix_commit_sha", matching[0])
        # No longer reported as unresolved/deferred now that it was fixed.
        self.assertEqual(second["unresolved_or_deferred_findings"], [])
        self.assertEqual(VALIDATE.validate_terminal_result(second), [])


class SourceBindingTests(LocalCommitRepoTestCase):
    def test_bound_source_reports_ahead_behind_counts_instead_of_unavailable(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        invocation["candidate"]["source_binding"] = {
            "repository": "shaug/compris",
            "remote_url": "git@github.com:shaug/compris.git",
            "ref": "refs/heads/fix/99-example",
            "observed_object_id": base_sha,
        }
        del invocation["candidate"]["source_unavailable_reason"]

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "converged")
        self.assertEqual(result["source"]["status"], "bound")
        self.assertEqual(result["source"]["initial_head"], base_sha)
        self.assertEqual(result["source"]["final_head"], base_sha)
        # The candidate head is exactly one commit ahead of the source
        # (the "start candidate" commit) and zero behind.
        self.assertEqual(result["source"]["ahead_by"], 1)
        self.assertEqual(result["source"]["behind_by"], 0)
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])

    def test_source_unavailable_reason_preserved_without_a_binding(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["source"]["status"], "unavailable")
        self.assertEqual(
            result["source"]["unavailable_reason"],
            "standalone invocation has no recorded pushable source",
        )


class ValidationFailureTests(LocalCommitRepoTestCase):
    def test_untractable_validation_failure_reports_changes_remaining(self):
        base_sha, head_sha = start_candidate(
            self.repo, marker="fixed", validation_flag="fail"
        )
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            validation=FLAG_GATED_VALIDATION,
        )
        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "changes_remaining")
        self.assertEqual(result["reason"], "current_candidate_validation_failure")
        self.assertEqual(result["budget"]["consumed_cycles"], 0)
        self.assertEqual(result["review_records"], [])
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])

    def test_unavailable_validation_command_blocks(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )

        def unavailable_run_validation(*, name, command, scope, cwd):
            if scope == "full":
                return LC.ValidationOutcome(
                    status="unavailable", reason="the full-gate tool is not installed"
                )
            return LC.default_run_validation(
                name=name, command=command, scope=scope, cwd=cwd
            )

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
            run_validation=unavailable_run_validation,
        )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "validation_unavailable")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])

    def test_tractable_validation_failure_is_fixed_via_synthetic_finding(self):
        base_sha, head_sha = start_candidate(
            self.repo, marker="fixed", validation_flag="fail"
        )
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            validation=FLAG_GATED_VALIDATION,
        )

        def classify(*, outcome, invocation):
            del outcome, invocation
            return {
                "id": "validation-flag-001",
                "lens": "validation",
                "severity": "blocking",
                "confidence": "high",
                "rule": "validation must pass",
                "evidence": [
                    {"location": "validation_flag.txt:1", "detail": "reads 'fail'"}
                ],
                "concern": "validation_flag.txt disables the focused check",
                "impact": "the focused validation command fails",
                "proposed_change": "write 'pass' into validation_flag.txt",
                "expected_effect": "the focused validation command passes",
            }

        def apply_fix(*, finding, attempt_path, change_contract, attempt_number):
            del finding, change_contract, attempt_number
            (attempt_path / "validation_flag.txt").write_text("pass\n")
            return "fix: repair validation_flag.txt"

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=apply_fix,
            classify_validation_failure=classify,
        )
        self.assertEqual(result["terminal_state"], "converged")
        self.assertEqual(result["budget"]["consumed_cycles"], 1)
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])


class OperatorInputTests(LocalCommitRepoTestCase):
    def test_declined_finding_blocks_on_operator_input_and_stays_visible(self):
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )

        def declining_decide(*, finding, change_contract, attempt_number):
            del change_contract, attempt_number
            return LC.FixDecision(
                disposition="rejected",
                rationale=f"{finding['id']} is already addressed upstream",
            )

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=declining_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "operator_input_required")
        self.assertEqual(result["budget"]["consumed_cycles"], 0)
        self.assertEqual(
            result["unresolved_or_deferred_findings"],
            [f"{FINDING_ID}: {FINDING_ID} is already addressed upstream"],
        )
        # The decline and its rationale are visible in the per-review record too.
        self.assertEqual(
            result["review_records"][0]["finding_dispositions"],
            [
                {
                    "finding_id": FINDING_ID,
                    "disposition": "rejected",
                    "rationale": f"{FINDING_ID} is already addressed upstream",
                }
            ],
        )
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])

    def test_scope_expanding_fix_blocks_on_scope_decision(self):
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )

        def expanding_decide(*, finding, change_contract, attempt_number):
            del change_contract, attempt_number
            return LC.FixDecision(
                disposition="accepted",
                rationale=f"{finding['id']} needs a broader change",
                expands_scope=True,
            )

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=expanding_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "scope_decision_required")
        self.assertEqual(result["budget"]["consumed_cycles"], 0)
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])


class RecoveryTests(LocalCommitRepoTestCase):
    def test_resumes_and_discards_an_interrupted_attempt_then_converges(self):
        base_sha, head_sha = start_candidate(self.repo, marker="broken")
        branch = "fix/99-example"
        invocation_id = "local-commit-recovery-test"
        invocation = make_invocation(
            self.repo,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            invocation_id=invocation_id,
        )
        common_dir = LE.git_common_dir(self.repo)
        attempts_root = LE.default_attempts_root(common_dir)

        # Simulate a crash: an isolated attempt was created and committed but
        # never promoted, and no checkpoint ever recorded its reservation.
        interrupted = LE.create_attempt(
            repo=self.repo,
            attempts_root=attempts_root,
            base_sha=head_sha,
            invocation_id=invocation_id,
            sequence=1,
        )
        (interrupted.path / "marker.txt").write_text("half-fixed\n")
        LE.commit_attempt(interrupted, "in-flight fix, never promoted")
        self.assertEqual(LE.current_head(self.repo), head_sha)  # canonical untouched

        checkpoint = {
            "schema_version": "1.0",
            "invocation_id": invocation_id,
            "repository": invocation["repository"],
            "branch": branch,
            "worktree": LE.worktree_status(self.repo),
            "initial_head": head_sha,
            "current_head": head_sha,
            "comparison_base": {"ref": "main", "sha": base_sha},
            "publication": {"policy": "local_commit"},
            "original_cycle_budget": 3,
            "cycle_attempts": [],
            "head_history": [head_sha],
            "base_revision_history": [{"ref": "main", "sha": base_sha}],
            "review_records": [],
            "validation_outcomes": [],
            "preserved_failed_attempts": [],
            "source": {
                "status": "unavailable",
                "unavailable_reason": "standalone invocation has no recorded pushable source",
            },
            "current_phase": "fix",
            "expected_next_action": "recover the interrupted attempt",
        }
        self.assertEqual(VALIDATE.validate_checkpoint(checkpoint), [])

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
            resume_checkpoint=checkpoint,
        )
        self.assertEqual(result["resume_status"], "resumed")
        self.assertEqual(result["terminal_state"], "converged")
        # The leftover attempt was discarded (preserved for inspection) and
        # recorded as one interrupted cycle attempt, then a fresh committed
        # attempt fixed the candidate for real.
        self.assertEqual(len(result["preserved_failed_attempts"]), 1)
        self.assertEqual(
            result["budget"]["consumed_cycles"], 2
        )  # interrupted + committed
        self.assertEqual(len(result["created_commits"]), 1)
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])

        # The interrupted attempt's branch and worktree were cleaned up by
        # `discard_attempt`'s caller responsibility is NOT implied — only the
        # canonical worktree's cleanliness matters here.
        self.assertTrue(LE.is_clean(LE.worktree_status(self.repo)))


class InputValidationTests(LocalCommitRepoTestCase):
    def test_rejects_invalid_invocation(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        del invocation["fix_cycle_budget"]
        with self.assertRaises(LC.LocalCommitError):
            LC.run_local_commit(
                invocation,
                repo=self.repo,
                reviewer=make_marker_reviewer(self.repo),
                decide=accepting_decide,
                apply_fix=fixing_apply_fix,
            )

    def test_rejects_update_pr_policy(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        invocation["publication"] = {
            "policy": "update_pr",
            "pull_request": {
                "head_repository": "shaug/compris",
                "head_ref": "refs/heads/fix/99-example",
                "expected_old_head_sha": head_sha,
                "base_ref": "main",
                "base_sha": base_sha,
            },
        }
        invocation["candidate"]["source_binding"] = {
            "repository": "shaug/compris",
            "remote_url": "git@github.com:shaug/compris.git",
            "ref": "refs/heads/fix/99-example",
            "observed_object_id": head_sha,
        }
        del invocation["candidate"]["source_unavailable_reason"]
        with self.assertRaises(LC.LocalCommitError):
            LC.run_local_commit(
                invocation,
                repo=self.repo,
                reviewer=make_marker_reviewer(self.repo),
                decide=accepting_decide,
                apply_fix=fixing_apply_fix,
            )

    def test_candidate_busy_when_lock_already_held(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        common_dir = LE.git_common_dir(self.repo)
        with LE.acquire_candidate_locks(common_dir, "refs/heads/fix/99-example"):
            result = LC.run_local_commit(
                invocation,
                repo=self.repo,
                reviewer=make_marker_reviewer(self.repo),
                decide=accepting_decide,
                apply_fix=fixing_apply_fix,
            )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "candidate_busy")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])


class ReviewerMutationTests(LocalCommitRepoTestCase):
    def test_reviewer_mutation_attempt_blocks_with_reviewer_integrity_failure(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )

        def mutating_reviewer(
            *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
        ):
            del packet, briefing, independence, sequence
            (self.repo / "sneaky.txt").write_text(
                "a reviewer should never write this\n"
            )
            LE.git("add", "-A", cwd=self.repo)
            candidate = {
                "head_sha": head_sha,
                "comparison_base_sha": comparison_base_sha,
            }
            result = {
                **CLEAN_TEMPLATE,
                "candidate": candidate,
                "lens_executions": [
                    {
                        "lens": lens,
                        "head_sha": head_sha,
                        "comparison_base_sha": comparison_base_sha,
                        "verdict": "clean",
                        "freshly_executed": True,
                    }
                    for lens in (
                        "solution_simplicity",
                        "correctness",
                        "code_simplicity",
                    )
                ],
            }
            return LC.ReviewPass(result=result)

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=mutating_reviewer,
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "reviewer_integrity_failure")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])
        # Preserved for operator inspection, not silently cleaned up.
        LE.git("reset", "-q", "--hard", "HEAD", cwd=self.repo)
        LE.git("clean", "-fdq", cwd=self.repo)


def _clean_review_pass(head_sha, comparison_base_sha, **kwargs):
    candidate = {"head_sha": head_sha, "comparison_base_sha": comparison_base_sha}
    result = {
        **CLEAN_TEMPLATE,
        "candidate": candidate,
        "lens_executions": [
            {
                "lens": lens,
                "head_sha": head_sha,
                "comparison_base_sha": comparison_base_sha,
                "verdict": "clean",
                "freshly_executed": True,
            }
            for lens in ("solution_simplicity", "correctness", "code_simplicity")
        ],
    }
    return LC.ReviewPass(result=result, **kwargs)


class CandidateRefIntegrityTests(LocalCommitRepoTestCase):
    """Tier 1 (issue #245): a change to `HEAD`, the candidate branch ref, or
    this invocation's own attempt namespace invalidates the candidate itself
    — `blocked/candidate_integrity_failure` — regardless of who caused it."""

    def test_candidate_branch_ref_move_during_review_blocks_candidate_integrity(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )

        def reviewer(
            *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
        ):
            del packet, briefing, independence, sequence
            # Simulate a concurrent advance of the very branch this candidate
            # is defined by — e.g. a background `pull --ff-only` of the
            # checked-out branch.
            LE.git(
                "update-ref",
                "refs/heads/fix/99-example",
                base_sha,
                cwd=self.repo,
            )
            return _clean_review_pass(head_sha, comparison_base_sha)

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=reviewer,
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "candidate_integrity_failure")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])
        # Restore for cleanup.
        LE.git("update-ref", "refs/heads/fix/99-example", head_sha, cwd=self.repo)

    def test_own_attempt_namespace_change_during_review_blocks_candidate_integrity(
        self,
    ):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            invocation_id="lc-attempt-ns-test",
        )

        def reviewer(
            *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
        ):
            del packet, briefing, independence, sequence
            LE.git(
                "update-ref",
                "refs/heads/review-fix-loop/attempt/lc-attempt-ns-test/1",
                head_sha,
                cwd=self.repo,
            )
            return _clean_review_pass(head_sha, comparison_base_sha)

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=reviewer,
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "candidate_integrity_failure")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])


class UnattributedRefAdvanceTests(LocalCommitRepoTestCase):
    """Tier 2 (issue #245): an unattributed local ref change — one that is
    not the candidate branch ref, not `HEAD`, and not this invocation's own
    attempt namespace — is a non-gating observation by default, since the
    ref store may be shared with other worktrees or background automation."""

    def test_unrelated_local_branch_advance_still_converges(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        LE.git("branch", "background/automation", base_sha, cwd=self.repo)

        def reviewer(
            *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
        ):
            del packet, briefing, independence, sequence
            # A concurrent process — not this reviewer pass — advances an
            # unrelated branch while the review runs.
            LE.git(
                "update-ref",
                "refs/heads/background/automation",
                head_sha,
                cwd=self.repo,
            )
            return _clean_review_pass(head_sha, comparison_base_sha)

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=reviewer,
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "converged")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])
        final_record = result["review_records"][-1]
        self.assertEqual([], final_record["mutation_attempts"])
        self.assertEqual("enforced", final_record["write_isolation"])
        self.assertTrue(
            any(
                "background/automation" in change
                for change in final_record.get("observed_ref_changes", [])
            )
        )

    def test_another_invocations_attempt_namespace_advance_still_converges(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo,
            branch="fix/99-example",
            base_sha=base_sha,
            head_sha=head_sha,
            invocation_id="lc-this-invocation",
        )

        def reviewer(
            *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
        ):
            del packet, briefing, independence, sequence
            LE.git(
                "update-ref",
                "refs/heads/review-fix-loop/attempt/other-invocation/1",
                head_sha,
                cwd=self.repo,
            )
            return _clean_review_pass(head_sha, comparison_base_sha)

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=reviewer,
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "converged")
        final_record = result["review_records"][-1]
        self.assertTrue(
            any(
                "other-invocation" in change
                for change in final_record.get("observed_ref_changes", [])
            )
        )


class IntegrityEvidenceTests(LocalCommitRepoTestCase):
    """`integrity_evidence` (issue #245) distinguishes host-supplied
    tool-trace inspection from a surface-only (snapshot-only) pass; either
    way a clean pass converges."""

    def test_no_tool_trace_supplied_records_surface_only_and_converges(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )

        def reviewer(
            *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
        ):
            del packet, briefing, independence, sequence
            return _clean_review_pass(head_sha, comparison_base_sha)

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=reviewer,
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "converged")
        self.assertEqual(
            "surface_only", result["review_records"][-1]["integrity_evidence"]
        )

    def test_tool_trace_supplied_and_clean_records_tool_trace_and_converges(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )

        def reviewer(
            *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
        ):
            del packet, briefing, independence, sequence
            return _clean_review_pass(
                head_sha, comparison_base_sha, tool_trace_available=True
            )

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=reviewer,
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "converged")
        self.assertEqual(
            "tool_trace", result["review_records"][-1]["integrity_evidence"]
        )

    def test_tool_trace_mutation_blocks_even_with_no_snapshot_change(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )

        def reviewer(
            *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
        ):
            del packet, briefing, independence, sequence
            return _clean_review_pass(
                head_sha,
                comparison_base_sha,
                tool_trace_available=True,
                mutation_attempts=["tool trace: attempted `git push origin main`"],
            )

        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=reviewer,
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
        )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "reviewer_integrity_failure")
        final_record = result["review_records"][-1]
        self.assertEqual("violated", final_record["write_isolation"])
        self.assertEqual("tool_trace", final_record["integrity_evidence"])


class MissingCapabilityTests(LocalCommitRepoTestCase):
    def test_no_fresh_subagent_and_no_override_blocks_with_missing_capability(self):
        base_sha, head_sha = start_candidate(self.repo, marker="fixed")
        invocation = make_invocation(
            self.repo, branch="fix/99-example", base_sha=base_sha, head_sha=head_sha
        )
        result = LC.run_local_commit(
            invocation,
            repo=self.repo,
            reviewer=make_marker_reviewer(self.repo),
            decide=accepting_decide,
            apply_fix=fixing_apply_fix,
            host_supports_fresh_subagent=False,
        )
        self.assertEqual(result["terminal_state"], "blocked")
        self.assertEqual(result["reason"], "missing_capability")
        self.assertEqual(VALIDATE.validate_terminal_result(result), [])


if __name__ == "__main__":
    unittest.main()
