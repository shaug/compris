"""Shared fixture plumbing for review-fix-loop's cross-cutting evaluation
corpus (issue #101).

This mirrors the module-loading and "no mocked Git state" conventions
`scripts/tests/helpers.py` already established for the capability-owned unit
suites (`test_local_commit.py`, `test_update_pr.py`): every scenario drives
the real `local_commit.run_local_commit` / `update_pr.run_update_pr` entry
points against a real temporary Git repository (and, for `update_pr`, a real
disposable local bare repository used as the publication remote — never this
repository's actual `origin`).

It imports the identical subset of `scripts/tests/helpers.py`'s own fixtures
(`init_repo`, `CLEAN_TEMPLATE`, `ALWAYS_PASS_VALIDATION`, `finding`,
`make_clean_reviewer`, `fixing_apply_fix`, `accepting_decide`) rather than
redefining them, following this repository's own `carve-changesets` precedent
of one skill's `scripts/tests/`/`scripts/evals/` fixture modules importing
across that boundary
(`skills/carve-changesets/scripts/tests/test_evals.py` imports directly from
its sibling `scripts/evals/`). Every fixture below —
imported or defined here — is duck-typed (attribute access only, never
`isinstance`), matching `scripts/tests/helpers.py`'s own documented
convention: constructing a `ReviewPass`/`FixDecision` from one module's
separately loaded `local_commit.py` is exactly as valid to another module's
separately loaded engine as one built from that engine's own load. Only the
fixtures genuinely specific to this corpus (more reviewer/decide/apply_fix
shapes than any one capability's unit tests need, because this corpus
exercises the full cross-cutting scenario list from
`design/review-fix-loop.md`'s "Validation strategy" section rather than one
module's own contract) are defined here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

SKILL_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, filename: str, *, subdir: str = "scripts"):
    spec = importlib.util.spec_from_file_location(name, SKILL_ROOT / subdir / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# One dedicated load, shared by every scenario builder in `corpus.py`. Every
# fixture below is duck-typed (attribute access only), matching the existing
# convention documented in `scripts/tests/helpers.py`.
UP = load_module("review_fix_loop_eval_update_pr", "update_pr.py")
LC = UP.LC
LE = LC.LE
VALIDATE = LC.VALIDATE

# The capability unit suites' own shared fixture module — see this module's
# docstring for why importing across the tests/evals boundary is safe here.
TESTS = load_module(
    "review_fix_loop_eval_tests_helpers", "helpers.py", subdir="scripts/tests"
)
init_repo = TESTS.init_repo
CLEAN_TEMPLATE = TESTS.CLEAN_TEMPLATE
ALWAYS_PASS_VALIDATION = TESTS.ALWAYS_PASS_VALIDATION
FINDING_ID = TESTS.FINDING_ID
finding = TESTS.finding
make_clean_reviewer = TESTS.make_clean_reviewer
fixing_apply_fix = TESTS.fixing_apply_fix
accepting_decide = TESTS.accepting_decide

MARKER_FIXED = "fixed"
MARKER_BROKEN = "broken"

# Fails exactly while `validation_flag.txt` reads anything other than `pass`,
# matching `scripts/tests/test_local_commit.py`'s established flag-gated
# validation convention.
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


# ---------------------------------------------------------------------------
# Repository + disposable remote fixtures
# ---------------------------------------------------------------------------


def init_bare_remote(root: Path, *, name: str = "remote.git") -> Path:
    bare = root / name
    LE.git("init", "-q", "--bare", str(bare))
    return bare


def start_candidate(
    repo: Path,
    *,
    branch: str,
    marker: str = MARKER_BROKEN,
    validation_flag: str = "pass",
    bare: Path | None = None,
) -> tuple[str, str]:
    """Create `branch` off `main` with one commit, optionally pushing it to
    `bare` at the same ref name. Returns `(base_sha, head_sha)`."""
    base_sha = LE.current_head(repo)
    LE.git("checkout", "-q", "-b", branch, cwd=repo)
    (repo / "marker.txt").write_text(marker + "\n")
    (repo / "validation_flag.txt").write_text(validation_flag + "\n")
    LE.git("add", "-A", cwd=repo)
    LE.git("commit", "-q", "-m", "start candidate", cwd=repo)
    head_sha = LE.current_head(repo)
    if bare is not None:
        LE.git("push", str(bare), f"{branch}:refs/heads/{branch}", cwd=repo)
    return base_sha, head_sha


def make_invocation(
    repo: Path,
    *,
    policy: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    invocation_id: str,
    bare: Path | None = None,
    max_fix_cycles: int = 3,
    validation: list[dict[str, str]] | None = None,
    grants: list[dict[str, str]] | None = None,
    review_execution: dict[str, str] | None = None,
    head_repository: str = "shaug/compris",
    source_repository: str | None = None,
    remote_url: str | None = None,
    expected_old_head_sha: str | None = None,
) -> dict[str, Any]:
    """Build one schema-shaped invocation document for either publication
    policy, mirroring `scripts/tests/test_local_commit.py` and
    `scripts/tests/test_update_pr.py`'s own `make_invocation` builders (kept
    as one parameterized function here since this corpus, unlike either unit
    suite, exercises both policies from a single scenario registry)."""
    common_dir = LE.git_common_dir(repo)
    diff = LE.git("diff", base_sha, head_sha, cwd=repo).stdout
    worktree = LE.worktree_status(repo)
    document: dict[str, Any] = {
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
        "review_execution": review_execution or {"mode": "fresh_subagent"},
        "fix_cycle_budget": {"max_fix_cycles": max_fix_cycles},
        "validation": validation or ALWAYS_PASS_VALIDATION,
    }

    if policy == "local_commit":
        document["candidate"]["source_unavailable_reason"] = (
            "standalone invocation has no recorded pushable source"
        )
        document["publication"] = {"policy": "local_commit"}
        return document

    if policy != "update_pr":
        raise ValueError(f"unknown policy: {policy!r}")

    assert bare is not None, "update_pr scenarios require a bare remote"
    head_ref = f"refs/heads/{branch}"
    document["candidate"]["pull_request"] = {
        "repository": "shaug/compris",
        "number": 123,
    }
    document["candidate"]["source_binding"] = {
        "repository": source_repository or head_repository,
        "remote_url": remote_url or str(bare),
        "ref": head_ref,
        "observed_object_id": head_sha,
    }
    publication: dict[str, Any] = {
        "policy": "update_pr",
        "pull_request": {
            "head_repository": head_repository,
            "head_ref": head_ref,
            "expected_old_head_sha": expected_old_head_sha or head_sha,
            "base_ref": "main",
            "base_sha": base_sha,
        },
    }
    if grants is not None:
        publication["remote_iteration_grants"] = grants
    document["publication"] = publication
    return document


# ---------------------------------------------------------------------------
# Reviewer fixtures
# ---------------------------------------------------------------------------


def _lens_executions(head_sha: str, comparison_base_sha: str) -> list[dict[str, Any]]:
    return [
        {
            "lens": lens,
            "head_sha": head_sha,
            "comparison_base_sha": comparison_base_sha,
            "verdict": "clean",
            "freshly_executed": True,
        }
        for lens in ("solution_simplicity", "correctness", "code_simplicity")
    ]


def make_marker_reviewer(repo: Path) -> Callable[..., Any]:
    """`clean` iff `marker.txt` reads 'fixed' at the exact reviewed head,
    `changes_required` with one blocking finding otherwise. A real function
    of real repository content, never a call counter."""

    def reviewer(
        *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
    ):
        del packet, briefing, independence, sequence
        content = LE.git("show", f"{head_sha}:marker.txt", cwd=repo).stdout.strip()
        candidate = {"head_sha": head_sha, "comparison_base_sha": comparison_base_sha}
        if content == MARKER_FIXED:
            result = {
                **CLEAN_TEMPLATE,
                "candidate": candidate,
                "lens_executions": _lens_executions(head_sha, comparison_base_sha),
            }
        else:
            result = {
                **CLEAN_TEMPLATE,
                "candidate": candidate,
                "verdict": "changes_required",
                "findings": [finding()],
                "lens_executions": [
                    {
                        "lens": "correctness",
                        "head_sha": head_sha,
                        "comparison_base_sha": comparison_base_sha,
                        "verdict": "changes_required",
                        "freshly_executed": True,
                    }
                ],
                "next_action": f"Fix {FINDING_ID}.",
            }
        return LC.ReviewPass(result=result)

    return reviewer


def make_blocked_reviewer(reason: str = "coverage gap") -> Callable[..., Any]:
    """The complete aggregate review itself returns `blocked` (design:
    "the review pass itself returned blocked"), simulating incomplete review
    evidence rather than a normal changes_required/clean verdict."""

    def reviewer(
        *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
    ):
        del packet, briefing, independence, sequence
        candidate = {"head_sha": head_sha, "comparison_base_sha": comparison_base_sha}
        result = {
            "schema_version": "1.4",
            "lens": "aggregate",
            "verdict": "blocked",
            "candidate": candidate,
            "findings": [],
            "blocking_reasons": [reason],
            "validation_limitations": [],
            "next_action": f"Resolve: {reason}.",
        }
        return LC.ReviewPass(result=result)

    return reviewer


def make_malformed_reviewer() -> Callable[..., Any]:
    """Returns a result bound to the wrong head — an "incomplete/invalid
    review" that `evaluate_review_result` must reject before it can ever
    certify anything, regardless of its claimed verdict."""

    def reviewer(
        *, packet, briefing, head_sha, comparison_base_sha, independence, sequence
    ):
        del packet, briefing, independence, sequence
        # Deliberately bound to a fabricated, non-matching head: a stale or
        # cross-candidate result.
        candidate = {
            "head_sha": "0" * 40,
            "comparison_base_sha": comparison_base_sha,
        }
        result = {
            **CLEAN_TEMPLATE,
            "candidate": candidate,
            "lens_executions": _lens_executions("0" * 40, comparison_base_sha),
        }
        return LC.ReviewPass(result=result)

    return reviewer


def make_mutating_reviewer(repo: Path, inner: Callable[..., Any]) -> Callable[..., Any]:
    """Wraps `inner` but also writes an untracked file into the canonical
    worktree before returning — a reviewer attempting a prohibited mutation.
    `_run_engine`'s before/after worktree snapshot around the reviewer call
    must detect this regardless of the wrapped verdict."""

    def reviewer(**kwargs):
        (repo / "reviewer-attempted-write.txt").write_text("i should not be here\n")
        return inner(**kwargs)

    return reviewer


def make_third_party_ref_advancing_reviewer(
    repo: Path,
    inner: Callable[..., Any],
    *,
    ref: str = "refs/heads/background/automation",
) -> Callable[..., Any]:
    """Wraps `inner` but also force-advances an unrelated local ref before
    returning — simulating background automation (a concurrent worktree's own
    branch, an unattended `pull --ff-only`) sharing this checkout's ref store,
    never the reviewer itself. `ref` is neither the candidate branch, `HEAD`,
    nor this invocation's own attempt namespace, so this is Tier 2 by design
    (issue #245): unattributable from the ref map alone, and must not gate a
    clean review the way `make_mutating_reviewer`'s Tier 1/worktree mutation
    does."""

    def reviewer(**kwargs):
        LE.git("update-ref", ref, kwargs["head_sha"], cwd=repo)
        return inner(**kwargs)

    return reviewer


# ---------------------------------------------------------------------------
# Decide fixtures
# ---------------------------------------------------------------------------


def make_rejecting_decide(
    rationale: str = "not a genuine defect",
) -> Callable[..., Any]:
    def decide(*, finding, change_contract, attempt_number):
        del change_contract, attempt_number
        return LC.FixDecision(disposition="rejected", rationale=rationale)

    return decide


def make_scope_expanding_decide() -> Callable[..., Any]:
    def decide(*, finding, change_contract, attempt_number):
        del change_contract, attempt_number
        return LC.FixDecision(
            disposition="accepted",
            rationale=f"{finding['id']} is real but only fixable outside scope",
            expands_scope=True,
        )

    return decide


# ---------------------------------------------------------------------------
# Apply-fix fixtures
# ---------------------------------------------------------------------------


def make_never_fixing_apply_fix(content: str = "still-broken") -> Callable[..., Any]:
    """A deliberately incomplete fix: commits real progress but never writes
    the content the reviewer actually requires, so the same finding persists
    across every subsequent review. Used for the budget-exhaustion scenario,
    and (unmodified) for this ticket's own seeded-faulty-fixture
    demonstration."""

    def apply_fix(*, finding, attempt_path, change_contract, attempt_number):
        del finding, change_contract
        (attempt_path / "marker.txt").write_text(f"{content}-{attempt_number}\n")
        return f"fix: partial attempt {attempt_number}"

    return apply_fix


def make_flag_fixing_apply_fix() -> Callable[..., Any]:
    """Fixes `validation_flag.txt` (not `marker.txt`) — pairs with a
    synthetic validation-failure finding rather than a review finding."""

    def apply_fix(*, finding, attempt_path, change_contract, attempt_number):
        del finding, change_contract, attempt_number
        (attempt_path / "validation_flag.txt").write_text("pass\n")
        return "fix: repair validation_flag.txt"

    return apply_fix


# ---------------------------------------------------------------------------
# Validation-classification fixtures
# ---------------------------------------------------------------------------


def classify_validation_failure_as_tractable(*, outcome, invocation):
    del invocation
    return {
        "id": "validation-001",
        "lens": "validation",
        "severity": "blocking",
        "confidence": "high",
        "rule": "validation must pass",
        "evidence": [{"location": "validation_flag.txt", "detail": outcome.result}],
        "concern": "the focused validation command fails",
        "impact": "the candidate is not demonstrably correct",
        "proposed_change": "repair validation_flag.txt",
        "expected_effect": "the focused validation command passes",
    }


def classify_validation_failure_as_intractable(*, outcome, invocation):
    del outcome, invocation
    return None


def make_unavailable_validation_runner(
    reason: str = "the validation environment is unreachable from this sandbox",
) -> Callable[..., Any]:
    """A `run_validation` port that unconditionally reports its command as
    unavailable — a deterministic stand-in for an environment failure (a
    missing tool, an unreachable CI runner) distinct from an ordinary command
    failure (`status: "failed"`), which `default_run_validation` only reports
    when the command itself cannot even be spawned."""

    def run_validation(*, name, command, scope, cwd):
        del name, command, scope, cwd
        return LC.ValidationOutcome(status="unavailable", reason=reason)

    return run_validation
