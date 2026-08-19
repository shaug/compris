"""The reusable, result-blind review-fix-loop evaluation corpus (issue #101).

Each scenario function below drives the real `local_commit.run_local_commit`
or `update_pr.run_update_pr` entry point end to end against a real temporary
Git repository (and, for `update_pr`, a real disposable local bare
repository), then reports a `checks` mapping of
`name -> (expected, observed)` pairs for `grader.grade_case` to diff.
`observed` values are computed independently of the returned terminal-result
document wherever the design's "Validation strategy" calls for externally
observable evidence — reading `marker.txt`'s content at a specific commit via
`git show`, reading a ref directly via `git rev-parse`/`git ls-remote`,
checking object reachability via `git cat-file -e` — never by re-deriving the
same field the code under test already reported. See `grader.py`'s module
docstring for the full rationale.

Corpus scope mirrors this ticket's own "Scope" bullet list exactly:
convergence, repeated findings, invalid reviews, declined findings, budget
exhaustion, interruption, recovery, validation failure, reviewer mutation,
publication races, plus fresh-subagent defaults and the explicit in-agent
override. It deliberately does not re-cover `oscillation` or
`repeated_failed_attempt`: those `changes_remaining` reasons are already
exercised by `scripts/tests/test_local_commit.py`, the capability-owned unit
suite this ticket's own body says not to duplicate. Issue #245 adds one
scenario beyond #101's original list, alongside the existing reviewer-mutation
one: an unattributed third-party ref advance
(`lc_unattributed_ref_advance_converges`) that must converge rather than
block, per the tiered write-isolation attribution that issue introduces.

Every scenario is a plain function `(tmp_dir: Path) -> dict` so `runner.py`
can execute each one inside its own disposable temporary directory and so
`scripts/tests/test_evals.py` can call any single scenario directly for the
seeded-fault demonstration required by this ticket's Validation section.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import grader as G  # noqa: E402
import helpers as H  # noqa: E402

LC = H.LC
UP = H.UP
LE = H.LE
VALIDATE = H.VALIDATE


def _schema_check(result: dict[str, Any]) -> tuple[list[str], list[str]]:
    return ([], VALIDATE.validate_terminal_result(result))


def _terminal_checks(
    result: dict[str, Any], *, terminal_state: str, reason: str | None
) -> dict[str, tuple[Any, Any]]:
    return {
        "terminal_state": (terminal_state, result.get("terminal_state")),
        "reason": (reason, result.get("reason")),
        "schema_valid": _schema_check(result),
    }


def _case(
    id: str,
    *,
    category: str,
    policy: str,
    result: dict[str, Any],
    checks: dict[str, tuple[Any, Any]],
) -> dict[str, Any]:
    return {
        "id": id,
        "category": category,
        "policy": policy,
        "result": result,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# local_commit: convergence
# ---------------------------------------------------------------------------


def lc_converged_clean_initial(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/clean", marker="fixed")
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/clean",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-converged-clean-initial",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_clean_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    branch_head = G.rev_parse(repo, "lc/clean")
    checks = _terminal_checks(result, terminal_state="converged", reason=None)
    checks.update(
        {
            "no_new_commit_on_canonical_branch": (
                0,
                G.rev_list_count(repo, head_sha, branch_head),
            ),
            "marker_at_final_head": (
                H.MARKER_FIXED,
                G.show_file(repo, branch_head, "marker.txt"),
            ),
            "worktree_clean": (True, G.worktree_is_clean(repo)),
        }
    )
    return _case(
        "lc-converged-clean-initial",
        category="convergence",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_converged_after_one_fix(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/one-fix", marker="broken")
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/one-fix",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-converged-after-one-fix",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    branch_head = G.rev_parse(repo, "lc/one-fix")
    checks = _terminal_checks(result, terminal_state="converged", reason=None)
    checks.update(
        {
            "exactly_one_new_commit": (
                1,
                G.rev_list_count(repo, head_sha, branch_head),
            ),
            "canonical_branch_matches_reported_final_head": (
                result.get("head", {}).get("final"),
                branch_head,
            ),
            "marker_at_final_head": (
                H.MARKER_FIXED,
                G.show_file(repo, branch_head, "marker.txt"),
            ),
            "worktree_clean": (True, G.worktree_is_clean(repo)),
            "default_review_independence": (
                "fresh_subagent",
                (result.get("review_records") or [{}])[-1].get("review_independence"),
            ),
        }
    )
    return _case(
        "lc-converged-after-one-fix",
        category="convergence",
        policy="local_commit",
        result=result,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# local_commit: repeated findings + budget exhaustion
# ---------------------------------------------------------------------------


def lc_budget_exhausted_persistent_finding(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/budget", marker="broken")
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/budget",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-budget-exhausted",
        max_fix_cycles=1,
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.accepting_decide,
        apply_fix=H.make_never_fixing_apply_fix(),
    )
    branch_head = G.rev_parse(repo, "lc/budget")
    checks = _terminal_checks(
        result, terminal_state="changes_remaining", reason="cycle_budget_exhausted"
    )
    checks.update(
        {
            "exactly_one_attempt_committed": (
                1,
                G.rev_list_count(repo, head_sha, branch_head),
            ),
            "finding_genuinely_unresolved_at_final_head": (
                False,
                G.show_file(repo, branch_head, "marker.txt") == H.MARKER_FIXED,
            ),
            "worktree_clean": (True, G.worktree_is_clean(repo)),
        }
    )
    return _case(
        "lc-budget-exhausted-persistent-finding",
        category="budget_exhaustion",
        policy="local_commit",
        result=result,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# local_commit: declined findings
# ---------------------------------------------------------------------------


def lc_declined_finding_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/declined", marker="broken")
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/declined",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-declined-finding",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.make_rejecting_decide("not a genuine defect for this scenario"),
        apply_fix=H.fixing_apply_fix,
    )
    branch_head = G.rev_parse(repo, "lc/declined")
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="operator_input_required"
    )
    checks.update(
        {
            "no_commit_was_made": (head_sha, branch_head),
            "worktree_clean": (True, G.worktree_is_clean(repo)),
        }
    )
    return _case(
        "lc-declined-finding-blocked",
        category="declined_findings",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_scope_expanding_finding_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/scope", marker="broken")
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/scope",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-scope-expanding",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.make_scope_expanding_decide(),
        apply_fix=H.fixing_apply_fix,
    )
    branch_head = G.rev_parse(repo, "lc/scope")
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="scope_decision_required"
    )
    checks["no_commit_was_made"] = (head_sha, branch_head)
    return _case(
        "lc-scope-expanding-finding-blocked",
        category="declined_findings",
        policy="local_commit",
        result=result,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# local_commit: validation failure
# ---------------------------------------------------------------------------


def lc_validation_unavailable_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(
        repo, branch="lc/val-unavailable", marker="fixed"
    )
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/val-unavailable",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-validation-unavailable",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_clean_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
        run_validation=H.make_unavailable_validation_runner(),
    )
    branch_head = G.rev_parse(repo, "lc/val-unavailable")
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="validation_unavailable"
    )
    checks["no_commit_was_made"] = (head_sha, branch_head)
    return _case(
        "lc-validation-unavailable-blocked",
        category="validation_failure",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_validation_failure_not_tractable(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(
        repo, branch="lc/val-intractable", marker="fixed", validation_flag="fail"
    )
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/val-intractable",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-validation-intractable",
        validation=H.FLAG_GATED_VALIDATION,
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_clean_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
        classify_validation_failure=H.classify_validation_failure_as_intractable,
    )
    branch_head = G.rev_parse(repo, "lc/val-intractable")
    checks = _terminal_checks(
        result,
        terminal_state="changes_remaining",
        reason="current_candidate_validation_failure",
    )
    checks["no_commit_was_made"] = (head_sha, branch_head)
    return _case(
        "lc-validation-failure-not-tractable",
        category="validation_failure",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_validation_failure_tractable_converges(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(
        repo, branch="lc/val-tractable", marker="fixed", validation_flag="fail"
    )
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/val-tractable",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-validation-tractable",
        validation=H.FLAG_GATED_VALIDATION,
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_clean_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.make_flag_fixing_apply_fix(),
        classify_validation_failure=H.classify_validation_failure_as_tractable,
    )
    branch_head = G.rev_parse(repo, "lc/val-tractable")
    checks = _terminal_checks(result, terminal_state="converged", reason=None)
    checks.update(
        {
            "exactly_one_new_commit": (
                1,
                G.rev_list_count(repo, head_sha, branch_head),
            ),
            "validation_flag_actually_repaired": (
                "pass",
                G.show_file(repo, branch_head, "validation_flag.txt"),
            ),
        }
    )
    return _case(
        "lc-validation-failure-tractable-converges",
        category="validation_failure",
        policy="local_commit",
        result=result,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# local_commit: invalid/incomplete review + reviewer mutation
# ---------------------------------------------------------------------------


def lc_reviewer_mutation_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/mutation", marker="broken")
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/mutation",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-reviewer-mutation",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_mutating_reviewer(repo, H.make_marker_reviewer(repo)),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    branch_head = G.rev_parse(repo, "lc/mutation")
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="reviewer_integrity_failure"
    )
    checks.update(
        {
            "candidate_never_advanced": (head_sha, branch_head),
            "mutation_attempt_preserved_for_inspection": (
                True,
                "reviewer-attempted-write.txt" in G.untracked_paths(repo),
            ),
        }
    )
    return _case(
        "lc-reviewer-mutation-blocked",
        category="reviewer_mutation",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_unattributed_ref_advance_converges(tmp_dir: Path) -> dict[str, Any]:
    """The unattributed third-party ref advance this ticket (#245) adds
    alongside `lc_reviewer_mutation_blocked`: a local ref unrelated to the
    candidate — not the candidate branch, not `HEAD`, not this invocation's
    own attempt namespace — force-advances mid-review, the way a concurrent
    worktree's own branch or an unattended background `pull --ff-only` would
    in a checkout where several worktrees share one ref store. The review
    must still converge, and the change must be recorded verbatim in the
    final review record's `observed_ref_changes` — non-gating, never a
    reviewer-integrity failure."""
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(
        repo, branch="lc/unattributed-ref", marker="fixed"
    )
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/unattributed-ref",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-unattributed-ref",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_third_party_ref_advancing_reviewer(
            repo, H.make_marker_reviewer(repo)
        ),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    checks = _terminal_checks(result, terminal_state="converged", reason=None)
    final_records = [
        record
        for record in result.get("review_records", [])
        if record.get("head_sha") == head_sha
    ]
    final_record = final_records[-1] if final_records else {}
    third_party_ref_sha = G.rev_parse(repo, "background/automation")
    candidate_branch_sha = G.rev_parse(repo, "lc/unattributed-ref")
    checks.update(
        {
            "write_isolation_enforced": (
                "enforced",
                final_record.get("write_isolation"),
            ),
            "no_mutation_attempts": ([], final_record.get("mutation_attempts")),
            "third_party_ref_observed": (
                True,
                any(
                    "background/automation" in change
                    for change in final_record.get("observed_ref_changes", [])
                ),
            ),
            # Independent Git evidence: the third-party ref genuinely
            # advanced (the mutation really happened, not merely un-reported)
            # while the candidate branch itself never moved.
            "third_party_ref_actually_advanced": (head_sha, third_party_ref_sha),
            "candidate_branch_unaffected": (head_sha, candidate_branch_sha),
        }
    )
    return _case(
        "lc-unattributed-ref-advance-converges",
        category="reviewer_mutation",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_incomplete_review_blocked_verdict(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(
        repo, branch="lc/incomplete", marker="broken"
    )
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/incomplete",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-incomplete-review",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_blocked_reviewer("aggregate lens coverage is incomplete"),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    branch_head = G.rev_parse(repo, "lc/incomplete")
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="missing_capability"
    )
    checks["candidate_never_advanced"] = (head_sha, branch_head)
    return _case(
        "lc-incomplete-review-blocked-verdict",
        category="invalid_review",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_invalid_stale_review_result_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(
        repo, branch="lc/stale-review", marker="broken"
    )
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/stale-review",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-stale-review-result",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_malformed_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    branch_head = G.rev_parse(repo, "lc/stale-review")
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="reviewer_integrity_failure"
    )
    checks["candidate_never_advanced"] = (head_sha, branch_head)
    return _case(
        "lc-invalid-stale-review-result-blocked",
        category="invalid_review",
        policy="local_commit",
        result=result,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# local_commit: fresh-subagent default vs. explicit in-agent override
# ---------------------------------------------------------------------------


def lc_missing_capability_without_override(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(
        repo, branch="lc/no-fresh-host", marker="fixed"
    )
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/no-fresh-host",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-missing-capability",
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_clean_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
        host_supports_fresh_subagent=False,
    )
    branch_head = G.rev_parse(repo, "lc/no-fresh-host")
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="missing_capability"
    )
    checks["candidate_never_advanced"] = (head_sha, branch_head)
    return _case(
        "lc-missing-capability-without-override",
        category="review_mode",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_in_agent_override_bypasses_missing_capability(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/override", marker="broken")
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/override",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="lc-in-agent-override",
        review_execution={
            "mode": "in_agent_override",
            "override_authorization": "user-explicit-2026-07-31",
        },
    )
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
        # No host in this process can honor `fresh_subagent`; the override
        # must still be honored per design ("An explicit override is always
        # honored, regardless of host capability").
        host_supports_fresh_subagent=False,
    )
    branch_head = G.rev_parse(repo, "lc/override")
    checks = _terminal_checks(result, terminal_state="converged", reason=None)
    checks.update(
        {
            "exactly_one_new_commit": (
                1,
                G.rev_list_count(repo, head_sha, branch_head),
            ),
            "marker_at_final_head": (
                H.MARKER_FIXED,
                G.show_file(repo, branch_head, "marker.txt"),
            ),
            "review_independence_is_in_agent_override": (
                "in_agent_override",
                (result.get("review_records") or [{}])[-1].get("review_independence"),
            ),
        }
    )
    return _case(
        "lc-in-agent-override-bypasses-missing-capability",
        category="review_mode",
        policy="local_commit",
        result=result,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# local_commit: checkpoint mismatch + interruption/recovery
# ---------------------------------------------------------------------------


def lc_checkpoint_mismatch_resume_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/mismatch", marker="broken")
    invocation_id = "lc-checkpoint-mismatch"
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/mismatch",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id=invocation_id,
    )
    # First run: stops at "decide" (declined finding) so a real checkpoint is
    # persisted without ever advancing the canonical head.
    LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.make_rejecting_decide(),
        apply_fix=H.fixing_apply_fix,
    )
    common_dir = LE.git_common_dir(repo)
    checkpoint_path = LC.LE.checkpoint_path(common_dir, invocation_id)
    checkpoint = LC.LE.read_checkpoint(checkpoint_path)
    # Corrupt the one field `reconcile_checkpoint_for_resume` checks last: a
    # real, well-formed, but wrong `current_head`.
    tampered = dict(checkpoint)
    tampered["current_head"] = base_sha
    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
        resume_checkpoint=tampered,
    )
    branch_head = G.rev_parse(repo, "lc/mismatch")
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="checkpoint_mismatch"
    )
    checks["candidate_never_advanced"] = (head_sha, branch_head)
    return _case(
        "lc-checkpoint-mismatch-resume-blocked",
        category="recovery",
        policy="local_commit",
        result=result,
        checks=checks,
    )


def lc_interrupted_attempt_recovered_without_losing_commit(
    tmp_dir: Path,
) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    base_sha, head_sha = H.start_candidate(repo, branch="lc/recovery", marker="broken")
    invocation_id = "lc-recovery"
    invocation = H.make_invocation(
        repo,
        policy="local_commit",
        branch="lc/recovery",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id=invocation_id,
    )
    # First run: stops at "decide" (declined) so a real checkpoint exists
    # with no promoted commit yet.
    LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.make_rejecting_decide(),
        apply_fix=H.fixing_apply_fix,
    )
    common_dir = LE.git_common_dir(repo)
    checkpoint_path = LC.LE.checkpoint_path(common_dir, invocation_id)
    checkpoint = LC.LE.read_checkpoint(checkpoint_path)

    # Simulate a crash between `commit_attempt` and `promote_attempt`: create
    # and commit an attempt branch by hand, but never promote it.
    attempts_root = LC.LE.default_attempts_root(common_dir)
    handle = LC.LE.create_attempt(
        repo=repo,
        attempts_root=attempts_root,
        base_sha=head_sha,
        invocation_id=invocation_id,
        sequence=1,
    )
    (handle.path / "marker.txt").write_text("fixed\n")
    interrupted_sha = LC.LE.commit_attempt(handle, "manually interrupted commit")
    attempt_branch_ref = f"refs/heads/{handle.branch}"

    result = LC.run_local_commit(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
        resume_checkpoint=checkpoint,
    )
    branch_head = G.rev_parse(repo, "lc/recovery")
    checks = _terminal_checks(result, terminal_state="converged", reason=None)
    checks.update(
        {
            # Only the fresh, post-recovery attempt was ever promoted onto
            # the canonical branch.
            "exactly_one_promoted_commit": (
                1,
                G.rev_list_count(repo, head_sha, branch_head),
            ),
            "marker_at_final_head": (
                H.MARKER_FIXED,
                G.show_file(repo, branch_head, "marker.txt"),
            ),
            # The interrupted commit's object was never lost: its attempt
            # branch still points at it even though it was never promoted.
            "interrupted_commit_object_preserved": (
                True,
                G.object_exists(repo, interrupted_sha),
            ),
            "interrupted_attempt_branch_still_points_at_it": (
                interrupted_sha,
                G.rev_parse(repo, attempt_branch_ref),
            ),
            "interrupted_attempt_recorded_as_preserved": (
                True,
                any(
                    entry.get("attempt_ref") == handle.branch
                    for entry in result.get("preserved_failed_attempts", [])
                ),
            ),
        }
    )
    return _case(
        "lc-interrupted-attempt-recovered-without-losing-commit",
        category="recovery",
        policy="local_commit",
        result=result,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# update_pr: convergence + publication
# ---------------------------------------------------------------------------


def up_converged_published(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    bare = H.init_bare_remote(tmp_dir)
    base_sha, head_sha = H.start_candidate(
        repo, branch="up/converge", marker="broken", bare=bare
    )
    head_ref = "refs/heads/up/converge"
    remote_before = G.ls_remote(bare, head_ref)
    invocation = H.make_invocation(
        repo,
        policy="update_pr",
        branch="up/converge",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="up-converged-published",
        bare=bare,
    )
    result = UP.run_update_pr(
        invocation,
        repo=repo,
        reviewer=H.make_marker_reviewer(repo),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    branch_head = G.rev_parse(repo, "up/converge")
    remote_after = G.ls_remote(bare, head_ref)
    checks = _terminal_checks(result, terminal_state="converged", reason=None)
    checks.update(
        {
            "remote_started_at_expected_old_head": (head_sha, remote_before),
            "remote_advanced_to_exact_local_head": (branch_head, remote_after),
            "marker_at_published_head": (
                H.MARKER_FIXED,
                G.show_file(repo, remote_after or "", "marker.txt"),
            ),
        }
    )
    return _case(
        "up-converged-published",
        category="convergence",
        policy="update_pr",
        result=result,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# update_pr: stale target / remote already advanced
# ---------------------------------------------------------------------------


def up_remote_advanced_stale_target_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    bare = H.init_bare_remote(tmp_dir)
    base_sha, head_sha = H.start_candidate(
        repo, branch="up/stale", marker="fixed", bare=bare
    )
    head_ref = "refs/heads/up/stale"

    # Someone else's clone advances the remote before this invocation runs.
    other_clone = tmp_dir / "other-clone"
    LE.git("clone", "-q", str(repo), str(other_clone))
    LE.git("checkout", "-q", "up/stale", cwd=other_clone)
    (other_clone / "marker.txt").write_text("someone-else-fixed-it\n")
    LE.git("add", "-A", cwd=other_clone)
    LE.git(
        "-c",
        "user.email=other@example.com",
        "-c",
        "user.name=Other",
        "commit",
        "-q",
        "-m",
        "a competing fix",
        cwd=other_clone,
    )
    LE.git("push", str(bare), "up/stale:refs/heads/up/stale", cwd=other_clone)
    competing_head = LE.current_head(other_clone)

    invocation = H.make_invocation(
        repo,
        policy="update_pr",
        branch="up/stale",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="up-remote-advanced",
        bare=bare,
    )
    result = UP.run_update_pr(
        invocation,
        repo=repo,
        reviewer=H.make_clean_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    remote_after = G.ls_remote(bare, head_ref)
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="remote_advanced"
    )
    checks.update(
        {
            "remote_untouched_by_the_losing_invocation": (competing_head, remote_after),
            "local_converged_commit_not_lost": (
                True,
                G.object_exists(repo, result.get("head", {}).get("final", "")),
            ),
        }
    )
    return _case(
        "up-remote-advanced-stale-target-blocked",
        category="publication_race",
        policy="update_pr",
        result=result,
        checks=checks,
    )


def up_sequential_publication_race_second_clone_loses(tmp_dir: Path) -> dict[str, Any]:
    """Two independent local clones of the same PR branch/head both converge
    locally; the first to publish wins, and the second is deterministically
    interleaved (via its own reviewer callback, never real concurrency) to
    attempt publication only after the first has already landed."""
    canonical = tmp_dir / "repo"
    H.init_repo(canonical)
    bare = H.init_bare_remote(tmp_dir)
    base_sha, head_sha = H.start_candidate(
        canonical, branch="up/race", marker="broken", bare=bare
    )
    head_ref = "refs/heads/up/race"

    def _clone_with_identity(name: str) -> Path:
        # `git clone` never copies the source repository's local
        # `user.name`/`user.email` config, and a CI runner (unlike a
        # developer machine) typically has no global git identity
        # configured either — the engine's own `commit_attempt` relies on
        # ambient git identity exactly as production code does, so each
        # clone needs its own explicit local config, matching what
        # `H.init_repo` already does for every non-cloned fixture repo.
        clone_path = tmp_dir / name
        LE.git("clone", "-q", str(canonical), str(clone_path))
        LE.git("checkout", "-q", "up/race", cwd=clone_path)
        LE.git("config", "user.email", "test@example.com", cwd=clone_path)
        LE.git("config", "user.name", "Eval", cwd=clone_path)
        return clone_path

    repo_a = _clone_with_identity("clone-a")
    repo_b = _clone_with_identity("clone-b")

    invocation_a = H.make_invocation(
        repo_a,
        policy="update_pr",
        branch="up/race",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="up-race-a",
        bare=bare,
    )
    invocation_b = H.make_invocation(
        repo_b,
        policy="update_pr",
        branch="up/race",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="up-race-b",
        bare=bare,
    )

    base_reviewer_b = H.make_marker_reviewer(repo_b)
    result_a_box: dict[str, Any] = {}

    def reviewer_b(**kwargs):
        pass_result = base_reviewer_b(**kwargs)
        if pass_result.result.get("verdict") == "clean":
            # Deterministically interleave: clone A completes its entire
            # converge-and-publish run right before clone B's own clean
            # review would let it proceed to publish.
            result_a_box["result"] = UP.run_update_pr(
                invocation_a,
                repo=repo_a,
                reviewer=H.make_marker_reviewer(repo_a),
                decide=H.accepting_decide,
                apply_fix=H.fixing_apply_fix,
            )
        return pass_result

    def apply_fix_b(*, finding, attempt_path, change_contract, attempt_number):
        del finding, change_contract, attempt_number
        (attempt_path / "marker.txt").write_text(H.MARKER_FIXED + "\n")
        # A distinct commit message from clone A's `fixing_apply_fix`, so the
        # two clones' fix commits never collide on identical tree, parent,
        # message, *and* same-second timestamp — which git would otherwise
        # hash to the exact same commit object, defeating this scenario's
        # "the loser's own distinct local commit is not lost" evidence.
        return f"fix: resolve {H.FINDING_ID} (clone B)"

    result_b = UP.run_update_pr(
        invocation_b,
        repo=repo_b,
        reviewer=reviewer_b,
        decide=H.accepting_decide,
        apply_fix=apply_fix_b,
    )
    result_a = result_a_box["result"]

    remote_final = G.ls_remote(bare, head_ref)
    branch_head_a = G.rev_parse(repo_a, "up/race")
    branch_head_b = G.rev_parse(repo_b, "up/race")

    checks: dict[str, tuple[Any, Any]] = {
        "winner_terminal_state": ("converged", result_a.get("terminal_state")),
        "loser_terminal_state": ("blocked", result_b.get("terminal_state")),
        "loser_reason": ("remote_advanced", result_b.get("reason")),
        "remote_equals_winners_local_head": (branch_head_a, remote_final),
        "remote_does_not_equal_losers_local_head": (
            True,
            remote_final != branch_head_b,
        ),
        # The loser's own local fix commit is not lost, merely unpublished.
        "losers_local_commit_exists": (True, branch_head_b != head_sha),
        "losers_local_commit_object_preserved": (
            True,
            G.object_exists(repo_b, branch_head_b),
        ),
        "loser_publication_status": (
            "failed",
            result_b.get("publication", {}).get("status"),
        ),
    }
    return _case(
        "up-sequential-publication-race-second-clone-loses",
        category="publication_race",
        policy="update_pr",
        result=result_b,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# update_pr: publication target / grant validation (fail closed before any lock)
# ---------------------------------------------------------------------------


def up_missing_authority_target_mismatch_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    bare = H.init_bare_remote(tmp_dir)
    base_sha, head_sha = H.start_candidate(
        repo, branch="up/mismatch", marker="fixed", bare=bare
    )
    head_ref = "refs/heads/up/mismatch"
    invocation = H.make_invocation(
        repo,
        policy="update_pr",
        branch="up/mismatch",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="up-target-mismatch",
        bare=bare,
        source_repository="someone-else/a-fork",
    )
    result = UP.run_update_pr(
        invocation,
        repo=repo,
        reviewer=H.make_clean_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    remote_after = G.ls_remote(bare, head_ref)
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="missing_authority"
    )
    checks.update(
        {
            "remote_untouched_before_any_lock": (head_sha, remote_after),
            "no_cycle_was_ever_consumed": (
                0,
                result.get("budget", {}).get("consumed_cycles"),
            ),
        }
    )
    return _case(
        "up-missing-authority-target-mismatch-blocked",
        category="publication_target",
        policy="update_pr",
        result=result,
        checks=checks,
    )


def up_mismatched_grant_blocked(tmp_dir: Path) -> dict[str, Any]:
    repo = tmp_dir / "repo"
    H.init_repo(repo)
    bare = H.init_bare_remote(tmp_dir)
    base_sha, head_sha = H.start_candidate(
        repo, branch="up/bad-grant", marker="fixed", bare=bare
    )
    head_ref = "refs/heads/up/bad-grant"
    invocation = H.make_invocation(
        repo,
        policy="update_pr",
        branch="up/bad-grant",
        base_sha=base_sha,
        head_sha=head_sha,
        invocation_id="up-bad-grant",
        bare=bare,
        grants=[
            {
                "mechanism_id": "ci-check",
                "kind": "external_ci",
                "repository": "shaug/compris",
                "ref": "refs/heads/some-other-branch",
                "origin_only_evidence": "CI only evaluates the pushed remote ref",
            }
        ],
    )
    result = UP.run_update_pr(
        invocation,
        repo=repo,
        reviewer=H.make_clean_reviewer(),
        decide=H.accepting_decide,
        apply_fix=H.fixing_apply_fix,
    )
    remote_after = G.ls_remote(bare, head_ref)
    checks = _terminal_checks(
        result, terminal_state="blocked", reason="missing_authority"
    )
    checks["remote_untouched_before_any_lock"] = (head_sha, remote_after)
    return _case(
        "up-mismatched-grant-blocked",
        category="publication_target",
        policy="update_pr",
        result=result,
        checks=checks,
    )


SCENARIOS: list[Callable[[Path], dict[str, Any]]] = [
    lc_converged_clean_initial,
    lc_converged_after_one_fix,
    lc_budget_exhausted_persistent_finding,
    lc_declined_finding_blocked,
    lc_scope_expanding_finding_blocked,
    lc_validation_unavailable_blocked,
    lc_validation_failure_not_tractable,
    lc_validation_failure_tractable_converges,
    lc_reviewer_mutation_blocked,
    lc_unattributed_ref_advance_converges,
    lc_incomplete_review_blocked_verdict,
    lc_invalid_stale_review_result_blocked,
    lc_missing_capability_without_override,
    lc_in_agent_override_bypasses_missing_capability,
    lc_checkpoint_mismatch_resume_blocked,
    lc_interrupted_attempt_recovered_without_losing_commit,
    up_converged_published,
    up_remote_advanced_stale_target_blocked,
    up_sequential_publication_race_second_clone_loses,
    up_missing_authority_target_mismatch_blocked,
    up_mismatched_grant_blocked,
]

SCENARIOS_BY_ID: dict[str, Callable[[Path], dict[str, Any]]] = {
    scenario.__name__: scenario for scenario in SCENARIOS
}
