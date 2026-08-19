#!/usr/bin/env python3
"""End-to-end standalone `local_commit` workflow for `review-fix-loop` (issue #99),
and the shared engine issue #100's `update_pr.py` composes its publication tail
onto.

Composes the three already-merged children of epic #95 into the actual loop
`design/review-fix-loop.md`'s "Workflow" section describes (steps 1 "Resolve"
through 9 "Return"):

- `validate.py` (#96) — the invocation/checkpoint/terminal-result contract and
  its cross-field semantics.
- `local_execution.py` (#97) — common-directory locking, isolated attempt
  worktrees, durable checkpointing, verified fast-forward-only promotion, and
  interrupted-attempt recovery.
- `reviewer_orchestration.py` (#98) — fixed lens resolution, review-result
  evaluation/binding, mutation detection, and deterministic finding ordering.

This module does not reimplement any of that logic; it sequences calls into
the three modules above and owns only what issue #99 itself is responsible
for: the loop's control flow (Resolve, Establish evidence, Review, Decide,
Fix, Validate and commit, Invalidate and repeat, Publish, Return), fix-cycle
budget enforcement, and terminal-result assembly.

`run_local_commit` is a thin wrapper around the private `_run_engine`, bound to
the trivial `local_commit` `_Policy` (every hook `None` — the engine's
behavior is exactly what it always was before this policy abstraction
existed). `update_pr.py` (issue #100) is the only other caller of
`_run_engine`; it supplies a populated `_Policy` built from its own resolved
publication target instead of reimplementing this loop. `_run_engine`,
`_Policy`, `_PublishOutcome`, `_State`, `_finalize`, `_minimal_blocked_result`,
and `_validate_and_require_policy` are shared, private, cross-module surface
between the two files in this same skill directory — never a public API for
anything outside it.

## Host boundary

Three actions in the design are inherently host/runtime actions that this
dependency-free module cannot perform itself — spawning a review subagent,
writing a fix's actual content, and running an arbitrary validation command —
so they are supplied by the caller as small callables ("ports"):

- `reviewer(*, packet, briefing, head_sha, comparison_base_sha, independence,
  sequence) -> ReviewPass` — run one complete `review-code-change` pass
  (fresh subagent by default) and return its raw result.
- `decide(*, finding, change_contract, attempt_number) -> FixDecision` —
  verify a selected finding's evidence, confirm it is within
  `allowed_remediation_scope`, and accept, reject, or defer it.
- `apply_fix(*, finding, attempt_path, change_contract, attempt_number) ->
  str` — write the smallest coherent remediation into the isolated attempt
  worktree and return a commit message. Only called after `decide` accepts.
- `run_validation(*, name, command, scope, cwd) -> ValidationOutcome` — run one
  recorded validation command. Defaults to a real subprocess runner.
- `classify_validation_failure(*, outcome, invocation) -> SyntheticFinding |
  None` — called only when validation fails for a head no fix cycle just
  produced (i.e., the failure was not itself just re-checked by a promotion).
  Returning `None` (the default) means the failure is not tractable per the
  design ("no tractable correction remains"); returning a finding-shaped dict
  routes it through the same decide/fix pipeline as a review finding.

Every other action (git, locking, checkpointing, promotion, review-result
evaluation) happens for real against the repository at `repo`, matching the
testing convention already used by `local_execution.py` and its tests: no
mocked Git state.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

HERE = Path(__file__).resolve().parent


def _load_bundled_module(name: str, path: Path):
    spec = importlib_util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib_util.module_from_spec(spec)
    # Registered before exec_module: local_execution.py's dataclasses use
    # `from __future__ import annotations`, and this mirrors the same
    # precaution `scripts/tests/test_local_execution.py` takes so Python's
    # dataclass machinery can resolve string type hints via
    # `sys.modules[cls.__module__]` if it ever needs to.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VALIDATE = _load_bundled_module("review_fix_loop_validate", HERE / "validate.py")
LE = _load_bundled_module(
    "review_fix_loop_local_execution", HERE / "local_execution.py"
)
ORCH = _load_bundled_module(
    "review_fix_loop_reviewer_orchestration", HERE / "reviewer_orchestration.py"
)


class LocalCommitError(RuntimeError):
    """A precondition this module requires of its caller was not met.

    Raised only for a caller/programming error (an invalid invocation, or an
    invocation whose `publication.policy` is not `local_commit`) — never for
    an ordinary runtime stop condition, which is always a structured terminal
    result instead.
    """


# ---------------------------------------------------------------------------
# Ports (host-boundary callables the caller supplies)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ReviewPass:
    """One raw review-code-change pass and its isolation evidence.

    `mutation_attempts` is host-supplied tool-trace evidence of an attempted
    write (tier 5 of the write-prevention ladder) — leave it empty when the
    host observed no attempt. `tool_trace_available` is `True` only when the
    host actually performed tool-trace inspection for this pass (whether or
    not it found anything); the default `False` means no tool trace was
    supplied at all, distinct from "inspected and clean."
    """

    result: Mapping[str, Any]
    reviewer_identity: str | None = None
    mutation_attempts: Sequence[str] = ()
    tool_trace_available: bool = False


@dataclasses.dataclass
class FixDecision:
    """The result of the design's "Decide" workflow step for one finding."""

    disposition: str  # "accepted" | "rejected" | "deferred"
    rationale: str
    expands_scope: bool = False
    operator_input_required: bool = False


@dataclasses.dataclass
class ValidationOutcome:
    status: str  # "passed" | "failed" | "unavailable"
    result: str | None = None
    reason: str | None = None


ReviewerPort = Callable[..., ReviewPass]
DeciderPort = Callable[..., FixDecision]
FixerPort = Callable[..., str]
ValidationRunnerPort = Callable[..., ValidationOutcome]
ValidationClassifierPort = Callable[..., dict[str, Any] | None]


def default_run_validation(
    *, name: str, command: str, scope: str, cwd: Path
) -> ValidationOutcome:
    """Real subprocess validation runner: the default `run_validation` port.

    A caller invoking this against a repository-instructed command (never
    interpolating untrusted text into it) may use this directly; tests
    supply their own deterministic port instead, per this module's
    docstring.
    """
    del name, scope  # only the command and cwd matter to execute it
    try:
        completed = subprocess.run(
            command, shell=True, cwd=str(cwd), text=True, capture_output=True
        )
    except OSError as exc:
        return ValidationOutcome(status="unavailable", reason=str(exc))
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode == 0:
        return ValidationOutcome(status="passed", result=output.strip() or "OK")
    return ValidationOutcome(
        status="failed", result=output.strip() or f"exit code {completed.returncode}"
    )


def _default_classify_validation_failure(
    *, outcome: ValidationOutcome, invocation: Mapping[str, Any]
) -> dict[str, Any] | None:
    del outcome, invocation
    return None


# ---------------------------------------------------------------------------
# Publication policy (shared engine hook; issue #100's `update_pr` is the only
# non-trivial policy so far)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _PublishOutcome:
    """The result of one attempted publication, returned by a `_Policy.publish`
    hook. `status` is either `"published"` (the exact expected-old fast-forward
    update landed and read back correctly) or `"failed"` (nothing was
    published; `blocked_reason` names why, and the caller's already-converged
    local commit is preserved exactly as-is)."""

    status: str  # "published" | "failed"
    operator_action: str
    non_converged_exposure: bool = False
    remote_head_before: str | None = None
    remote_head_after: str | None = None
    blocked_reason: str | None = None  # required when status == "failed"


@dataclasses.dataclass(frozen=True)
class _Policy:
    """What distinguishes one publication policy's effect on the shared engine.

    `local_commit` (this module's own default) never sets `remote_target`,
    `check_remote`, or `publish` — every hook stays `None`, so the engine's
    behavior for `local_commit` is unchanged from before this policy
    abstraction existed. `update_pr.py` supplies a populated `_Policy` built
    from its own resolved publication target; the engine never constructs one
    itself for `update_pr`.
    """

    name: str  # "local_commit" | "update_pr"
    remote_target: tuple[str, str] | None = None
    checkpoint_pull_request: Mapping[str, str] | None = None
    # Returns `None` when the remote has not observably advanced, or
    # `{"reason": <blocked reason>, "remote_head": <sha> | None}` when it
    # has — `remote_head` is the live value observed, when the check could
    # determine one, for the resulting terminal result's
    # `publication.remote_head_before`/`remote_head_after`.
    check_remote: Callable[["_State"], dict[str, Any] | None] | None = None
    publish: Callable[["_State"], _PublishOutcome] | None = None


_LOCAL_COMMIT_POLICY = _Policy(name="local_commit")


def _default_publication(
    policy_name: str, *, terminal_state: str, reason: str | None
) -> dict[str, Any]:
    """The policy-appropriate `publication` dict for every ordinary return path
    that never attempts a remote write itself (every `blocked`/
    `changes_remaining` reason except the dedicated publish step's own
    outcome, which always supplies its own explicit `publication_override`).

    `local_commit` is always `not_applicable`, exactly as before this
    function existed. `update_pr` mirrors `validate.py`'s own
    `BLOCKED_REASONS_IMPLYING_PUBLICATION_FAILED` rule instead of duplicating
    it: `withheld` for every ordinary stop, `failed` only for the two reasons
    that mean a publication attempt did not land (`remote_advanced`,
    `publication_failed`).
    """
    if policy_name == "local_commit":
        return {
            "policy": "local_commit",
            "status": "not_applicable",
            "non_converged_exposure": False,
        }
    status = (
        "failed"
        if terminal_state == "blocked"
        and reason in VALIDATE.BLOCKED_REASONS_IMPLYING_PUBLICATION_FAILED
        else "withheld"
    )
    return {"policy": policy_name, "status": status, "non_converged_exposure": False}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _worktree_snapshot(repo: Path) -> dict[str, Any]:
    """Capture the `REQUIRED_SNAPSHOT_KEYS`-shaped before/after snapshot
    `detect_worktree_mutation` compares."""
    status = LE.worktree_status(repo)
    refs_output = LE.git(
        "for-each-ref", "--format=%(refname) %(objectname)", cwd=repo
    ).stdout
    refs: dict[str, str] = {}
    for line in refs_output.splitlines():
        if not line:
            continue
        ref_name, _, object_id = line.partition(" ")
        refs[ref_name] = object_id
    return {"head_sha": LE.current_head(repo), "refs": refs, **status}


def _run_validation_suite(
    invocation: Mapping[str, Any], *, cwd: Path, run_validation: ValidationRunnerPort
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for entry in invocation["validation"]:
        outcome = run_validation(
            name=entry["name"], command=entry["command"], scope=entry["scope"], cwd=cwd
        )
        record: dict[str, Any] = {
            "name": entry["name"],
            "command": entry["command"],
            "scope": entry["scope"],
            "status": outcome.status,
        }
        if outcome.result is not None:
            record["result"] = outcome.result
        if outcome.reason is not None:
            record["reason"] = outcome.reason
        outcomes.append(record)
    return outcomes


def _unavailable_scope(outcomes: Sequence[Mapping[str, Any]]) -> str | None:
    for outcome in outcomes:
        if outcome["status"] == "unavailable":
            return outcome["scope"]
    return None


def _failed_outcome(
    outcomes: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for outcome in outcomes:
        if outcome["status"] == "failed":
            return outcome
    return None


def _build_packet(
    invocation: Mapping[str, Any],
    *,
    head_sha: str,
    comparison_base_sha: str,
    diff: Mapping[str, Any],
    validation_outcomes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    change_contract = invocation["change_contract"]
    return {
        "schema_version": "1.0",
        "repository": {
            "identity": invocation["repository"]["identity"],
            "base_branch": invocation["candidate"]["comparison_base"]["ref"],
        },
        "candidate": {
            "head_sha": head_sha,
            "comparison_base_sha": comparison_base_sha,
            "diff": dict(diff),
        },
        "change_contract": {
            "goal": change_contract["goal"],
            "acceptance_criteria": list(change_contract["acceptance_criteria"]),
            "non_goals": list(change_contract["non_goals"]),
            "preserved_behaviors": list(change_contract["preserved_behaviors"]),
        },
        "sources": {
            "repository_instructions": list(
                change_contract["sources"]["repository_instructions"]
            ),
            "named_documents": list(change_contract["sources"]["named_documents"]),
            "nearby_patterns": list(change_contract["sources"]["nearby_patterns"]),
        },
        "validation": list(validation_outcomes),
    }


def _current_diff(repo: Path, base_sha: str, head_sha: str) -> dict[str, Any]:
    content = LE.git("diff", base_sha, head_sha, cwd=repo).stdout
    return {"format": "unified_diff", "complete": True, "content": content}


def _commits_between(repo: Path, old: str, new: str) -> int:
    return int(LE.git("rev-list", "--count", f"{old}..{new}", cwd=repo).stdout.strip())


def _checkpoint_source_status(
    candidate: Mapping[str, Any], *, repo: Path, current_head: str
) -> dict[str, Any]:
    """Build this checkpoint's `source` status.

    A `local_commit` invocation may still carry an optional read-only
    `source_binding` purely for comparison (design: "An optional read-only
    source binding ... required when the candidate has a known pushable
    source"; "A read-only source binding grants comparison authority only;
    it never implies permission to push"). When one is present, report
    `bound` with the exact ahead/behind counts relative to its
    `observed_object_id`; otherwise report the invocation's own
    `source_unavailable_reason` verbatim.
    """
    source_binding = candidate.get("source_binding")
    if source_binding is None:
        return {
            "status": "unavailable",
            "unavailable_reason": candidate.get(
                "source_unavailable_reason", "no recorded pushable source"
            ),
        }
    source_sha = source_binding["observed_object_id"]
    return {
        "status": "bound",
        "last_verified_head": source_sha,
        "ahead_by": _commits_between(repo, source_sha, current_head),
        "behind_by": _commits_between(repo, current_head, source_sha),
    }


def _terminal_source_status(
    candidate: Mapping[str, Any], *, repo: Path, current_head: str
) -> dict[str, Any]:
    """Terminal-result equivalent of `_checkpoint_source_status`.

    `local_commit` never re-fetches or advances a bound source (that
    remains `update_pr`-only, per this ticket's non-goals); `initial_head`
    and `final_head` are therefore both this invocation's one observed
    source object, and only the local ahead/behind counts relative to the
    final candidate head can change.
    """
    source_binding = candidate.get("source_binding")
    if source_binding is None:
        return {
            "status": "unavailable",
            "unavailable_reason": candidate.get(
                "source_unavailable_reason", "no recorded pushable source"
            ),
        }
    source_sha = source_binding["observed_object_id"]
    return {
        "status": "bound",
        "initial_head": source_sha,
        "final_head": source_sha,
        "ahead_by": _commits_between(repo, source_sha, current_head),
        "behind_by": _commits_between(repo, current_head, source_sha),
    }


def _checkpoint_preserved(preserved: Mapping[str, Any]) -> dict[str, str]:
    """Narrow `discard_attempt`'s `{attempt_ref, patch_path, reason}` return
    to the `{attempt_ref, reason}` shape `checkpoint.schema.json` and
    `terminal-result.schema.json` both actually declare (`additionalProperties:
    false`); `patch_path` is on-disk-only operator-inspection detail, not part
    of either document contract."""
    return {"attempt_ref": preserved["attempt_ref"], "reason": preserved["reason"]}


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _State:
    invocation: Mapping[str, Any]
    repo: Path
    common_dir: Path
    branch: str
    initial_head: str
    current_head: str
    base_ref: str
    current_base_sha: str
    original_budget: int
    policy: _Policy
    cycle_attempts: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    head_history: list[str] = dataclasses.field(default_factory=list)
    base_revision_history: list[dict[str, str]] = dataclasses.field(
        default_factory=list
    )
    review_records: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    validation_outcomes: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    preserved_failed_attempts: list[dict[str, str]] = dataclasses.field(
        default_factory=list
    )
    finding_dispositions: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    unresolved_or_deferred: list[str] = dataclasses.field(default_factory=list)
    resume_status: str = "not_resumed"

    def consumed_cycles(self) -> int:
        return len(self.cycle_attempts)

    def remaining_cycles(self) -> int:
        return self.original_budget - self.consumed_cycles()

    def record_finding_disposition(
        self,
        *,
        finding_id: str,
        disposition: str,
        rationale: str,
        fix_commit_sha: str | None = None,
    ) -> None:
        """Record (or replace) this finding's one current top-level
        disposition (`selected` or `declined`).

        A `finding_id` can legitimately gain more than one disposition
        across an invocation's lifetime — declined on one pass, then
        accepted and fixed once resumed with a different decision, or
        reconstructed from an older checkpoint entry and then superseded by
        a fresh live decision in this same run. Only the most recent one is
        meaningful evidence, so this always removes any prior entry for the
        same `finding_id` from both `finding_dispositions` and
        `unresolved_or_deferred_findings` before appending the new one,
        rather than letting a `converged` result carry stale, contradictory
        history for a finding that was in fact fixed (or vice versa).
        """
        self.finding_dispositions = [
            entry
            for entry in self.finding_dispositions
            if entry["finding_id"] != finding_id
        ]
        self.unresolved_or_deferred = [
            entry
            for entry in self.unresolved_or_deferred
            if not entry.startswith(f"{finding_id}:")
        ]
        entry: dict[str, Any] = {
            "finding_id": finding_id,
            "disposition": disposition,
            "rationale": rationale,
        }
        if fix_commit_sha is not None:
            entry["fix_commit_sha"] = fix_commit_sha
        self.finding_dispositions.append(entry)
        if disposition == "declined":
            self.unresolved_or_deferred.append(f"{finding_id}: {rationale}")


def _checkpoint_document(
    state: _State, *, phase: str, next_action: str
) -> dict[str, Any]:
    invocation = state.invocation
    publication: dict[str, Any] = {"policy": state.policy.name}
    if state.policy.checkpoint_pull_request is not None:
        publication["pull_request"] = dict(state.policy.checkpoint_pull_request)
    document = {
        "schema_version": "1.0",
        "invocation_id": invocation["invocation_id"],
        "repository": dict(invocation["repository"]),
        "branch": state.branch,
        "worktree": LE.worktree_status(state.repo),
        "initial_head": state.initial_head,
        "current_head": state.current_head,
        "comparison_base": {"ref": state.base_ref, "sha": state.current_base_sha},
        "publication": publication,
        "original_cycle_budget": state.original_budget,
        "cycle_attempts": list(state.cycle_attempts),
        "head_history": list(state.head_history),
        "base_revision_history": list(state.base_revision_history),
        "review_records": list(state.review_records),
        "validation_outcomes": list(state.validation_outcomes),
        "preserved_failed_attempts": list(state.preserved_failed_attempts),
        "source": _checkpoint_source_status(
            invocation["candidate"], repo=state.repo, current_head=state.current_head
        ),
        "current_phase": phase,
        "expected_next_action": next_action,
    }
    if "pull_request" in invocation["candidate"]:
        document["pull_request"] = invocation["candidate"]["pull_request"]
    return document


def _persist_checkpoint(
    state: _State, *, phase: str, next_action: str
) -> dict[str, Any]:
    document = _checkpoint_document(state, phase=phase, next_action=next_action)
    path = LE.checkpoint_path(state.common_dir, state.invocation["invocation_id"])
    LE.write_checkpoint_atomic(path, document)
    return document


def _terminal_result(
    state: _State,
    *,
    terminal_state: str,
    reason: str | None,
    operator_action: str,
    publication_override: Mapping[str, Any] | None = None,
    source_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    invocation = state.invocation
    consumed = state.consumed_cycles()
    remaining = state.remaining_cycles()
    created_commits = state.head_history[1:]
    identity_changed = (
        state.current_head != state.initial_head
        or state.current_base_sha != state.base_revision_history[0]["sha"]
    )
    publication = (
        dict(publication_override)
        if publication_override is not None
        else _default_publication(
            state.policy.name, terminal_state=terminal_state, reason=reason
        )
    )
    source = (
        dict(source_override)
        if source_override is not None
        else _terminal_source_status(
            invocation["candidate"], repo=state.repo, current_head=state.current_head
        )
    )
    unpushed_commits = (
        [] if publication.get("status") == "published" else list(created_commits)
    )
    document: dict[str, Any] = {
        "schema_version": "1.0",
        "invocation_id": invocation["invocation_id"],
        "terminal_state": terminal_state,
        "budget": {
            "original_max_fix_cycles": state.original_budget,
            "consumed_cycles": consumed,
            "remaining_cycles": remaining,
        },
        "resume_status": state.resume_status,
        "repository": dict(invocation["repository"]),
        "branch": state.branch,
        "worktree": LE.worktree_status(state.repo),
        "head": {"initial": state.initial_head, "final": state.current_head},
        "comparison_base": {
            "initial": dict(state.base_revision_history[0]),
            "final": {"ref": state.base_ref, "sha": state.current_base_sha},
        },
        "head_history": list(state.head_history),
        "base_revision_history": list(state.base_revision_history),
        "review_records": list(state.review_records),
        "validation_summary": list(state.validation_outcomes),
        "finding_dispositions": list(state.finding_dispositions),
        "created_commits": list(created_commits),
        "preserved_failed_attempts": list(state.preserved_failed_attempts),
        "source": source,
        "unpushed_commits": unpushed_commits,
        "publication": publication,
        "acceptance_reconciliation_required": bool(identity_changed),
        "unresolved_or_deferred_findings": list(state.unresolved_or_deferred),
        "operator_action": operator_action,
    }
    if reason is not None:
        document["reason"] = reason
    if "pull_request" in invocation["candidate"]:
        document["pull_request"] = invocation["candidate"]["pull_request"]
    return document


def _finalize(
    state: _State,
    *,
    terminal_state: str,
    reason: str | None,
    operator_action: str,
    phase: str,
    publication_override: Mapping[str, Any] | None = None,
    source_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _persist_checkpoint(state, phase=phase, next_action=operator_action)
    result = _terminal_result(
        state,
        terminal_state=terminal_state,
        reason=reason,
        operator_action=operator_action,
        publication_override=publication_override,
        source_override=source_override,
    )
    errors = VALIDATE.validate_terminal_result(result)
    if errors:
        raise LocalCommitError(
            "internal error: assembled an invalid terminal result: " + "; ".join(errors)
        )
    return result


def _remote_check_publication_override(
    state: _State, remote_check: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the `publication` dict for a mid-loop `check_remote` stop, reusing
    `_default_publication`'s exact status rule and attaching the observed
    remote head (when the check could determine one) as both
    `remote_head_before` and `remote_head_after` — nothing was pushed, so the
    remote's live value is unchanged by this invocation either way."""
    publication = dict(
        _default_publication(
            state.policy.name, terminal_state="blocked", reason=remote_check["reason"]
        )
    )
    remote_head = remote_check.get("remote_head")
    if remote_head is not None:
        publication["remote_head_before"] = remote_head
        publication["remote_head_after"] = remote_head
    return publication


def _minimal_blocked_result(
    invocation: Mapping[str, Any],
    *,
    repo: Path,
    reason: str,
    operator_action: str,
    policy_name: str = "local_commit",
) -> dict[str, Any]:
    """Build a `blocked` terminal result for a stop that occurs before this
    invocation could acquire its candidate lock — nothing has been
    checkpointed or mutated yet, so this reports only the invocation's own
    static candidate identity rather than any live-derived progress. A
    read-only source-binding ahead/behind comparison is still safe and
    meaningful here (it never touches the candidate lock or worktree)."""
    candidate = invocation["candidate"]
    base = dict(candidate["comparison_base"])
    head = candidate["head_sha"]
    budget = invocation["fix_cycle_budget"]["max_fix_cycles"]
    document: dict[str, Any] = {
        "schema_version": "1.0",
        "invocation_id": invocation["invocation_id"],
        "terminal_state": "blocked",
        "reason": reason,
        "budget": {
            "original_max_fix_cycles": budget,
            "consumed_cycles": 0,
            "remaining_cycles": budget,
        },
        "resume_status": "not_resumed",
        "repository": dict(invocation["repository"]),
        "branch": candidate["branch"],
        "worktree": dict(candidate["worktree"]),
        "head": {"initial": head, "final": head},
        "comparison_base": {"initial": base, "final": base},
        "head_history": [head],
        "base_revision_history": [base],
        "review_records": [],
        "validation_summary": [],
        "finding_dispositions": [],
        "created_commits": [],
        "preserved_failed_attempts": [],
        "source": _terminal_source_status(candidate, repo=repo, current_head=head),
        "unpushed_commits": [],
        "publication": _default_publication(
            policy_name, terminal_state="blocked", reason=reason
        ),
        "acceptance_reconciliation_required": False,
        "unresolved_or_deferred_findings": [],
        "operator_action": operator_action,
    }
    if "pull_request" in candidate:
        document["pull_request"] = candidate["pull_request"]
    errors = VALIDATE.validate_terminal_result(document)
    if errors:
        raise LocalCommitError(
            "internal error: assembled an invalid terminal result: " + "; ".join(errors)
        )
    return document


def _validate_and_require_policy(
    invocation: Mapping[str, Any], expected_policy: str
) -> None:
    """Shared entry-point guard for both `run_local_commit` and
    `update_pr.run_update_pr`: validate the invocation against the complete
    contract and require its exact `publication.policy`. Raises
    `LocalCommitError` for a caller/programming error — an invalid invocation
    or one whose policy does not match the entry point invoked — never for an
    ordinary runtime stop condition, matching this module's existing
    convention."""
    errors = VALIDATE.validate_invocation(dict(invocation))
    if errors:
        raise LocalCommitError(
            "invocation failed contract validation: " + "; ".join(errors)
        )
    policy = invocation["publication"]["policy"]
    if policy != expected_policy:
        raise LocalCommitError(
            f"expected publication.policy {expected_policy!r}, got {policy!r}"
        )


def run_local_commit(
    invocation: Mapping[str, Any],
    *,
    repo: Path,
    reviewer: ReviewerPort,
    decide: DeciderPort,
    apply_fix: FixerPort,
    run_validation: ValidationRunnerPort = default_run_validation,
    classify_validation_failure: ValidationClassifierPort = _default_classify_validation_failure,
    host_supports_fresh_subagent: bool = True,
    attempts_root: Path | None = None,
    resume_checkpoint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run (or resume) one standalone `local_commit` review-fix-loop invocation.

    Returns a schema-valid terminal-result document (`converged`,
    `changes_remaining`, or `blocked`). Every successful fix is committed
    locally and promoted through the canonical worktree at `repo`; no remote
    write ever occurs, per this invocation's `local_commit` policy.

    A thin wrapper around `_run_engine` bound to the trivial `local_commit`
    policy (every hook `None`); see `update_pr.run_update_pr` for the other
    entry point that shares this same engine with a populated `_Policy`.
    """
    _validate_and_require_policy(invocation, "local_commit")
    return _run_engine(
        invocation,
        repo=repo,
        reviewer=reviewer,
        decide=decide,
        apply_fix=apply_fix,
        run_validation=run_validation,
        classify_validation_failure=classify_validation_failure,
        host_supports_fresh_subagent=host_supports_fresh_subagent,
        attempts_root=attempts_root,
        resume_checkpoint=resume_checkpoint,
        policy=_LOCAL_COMMIT_POLICY,
    )


def _run_engine(
    invocation: Mapping[str, Any],
    *,
    repo: Path,
    reviewer: ReviewerPort,
    decide: DeciderPort,
    apply_fix: FixerPort,
    run_validation: ValidationRunnerPort,
    classify_validation_failure: ValidationClassifierPort,
    host_supports_fresh_subagent: bool,
    attempts_root: Path | None,
    resume_checkpoint: Mapping[str, Any] | None,
    policy: _Policy,
) -> dict[str, Any]:
    """The shared review/fix/converge engine both publication policies use.

    Composes `validate.py`, `local_execution.py`, and
    `reviewer_orchestration.py` exactly as `run_local_commit` always has; the
    only new behavior `policy` can add is an additional remote-target lock,
    an optional remote-staleness check at two boundaries (before establishing
    evidence for a fresh review, and before starting a fix attempt), and a
    publish step that runs only once, immediately after a clean review, in
    place of `local_commit`'s unconditional "publish nothing" return. Callers
    never construct `_Policy` themselves except `run_local_commit`
    (`_LOCAL_COMMIT_POLICY`, every hook `None`) and `update_pr.run_update_pr`
    (a populated `_Policy` built from its own resolved publication target).
    """
    candidate = invocation["candidate"]
    branch = candidate["branch"]
    common_dir = LE.git_common_dir(repo)
    local_ref = f"refs/heads/{branch}"
    attempts_root = attempts_root or LE.default_attempts_root(common_dir)

    lock_cm = LE.acquire_candidate_locks(
        common_dir, local_ref, remote_target=policy.remote_target
    )
    try:
        lock_cm.__enter__()
    except LE.CandidateBusyError as exc:
        return _minimal_blocked_result(
            invocation,
            repo=repo,
            reason="candidate_busy",
            operator_action=f"the candidate lock is already held: {exc}",
            policy_name=policy.name,
        )

    try:
        live_head = LE.current_head(repo)
        live_status = LE.worktree_status(repo)
        if not LE.is_clean(live_status):
            raise LocalCommitError(
                f"worktree must be clean before a {policy.name} invocation"
            )

        state = _State(
            invocation=invocation,
            repo=repo,
            common_dir=common_dir,
            branch=branch,
            initial_head=candidate["head_sha"],
            current_head=live_head,
            base_ref=candidate["comparison_base"]["ref"],
            current_base_sha=candidate["comparison_base"]["sha"],
            original_budget=invocation["fix_cycle_budget"]["max_fix_cycles"],
            policy=policy,
        )

        if resume_checkpoint is not None:
            try:
                LE.reconcile_checkpoint_for_resume(
                    invocation=dict(invocation),
                    checkpoint=dict(resume_checkpoint),
                    live_head=live_head,
                    live_base_sha=state.current_base_sha,
                    live_worktree_status=live_status,
                    lock_busy=False,
                )
            except LE.LocalExecutionError as exc:
                reason = (
                    "candidate_busy"
                    if isinstance(exc, LE.CandidateBusyError)
                    else "checkpoint_mismatch"
                )
                state.resume_status = "resume_unavailable"
                state.head_history = [state.initial_head]
                state.base_revision_history = [
                    {"ref": state.base_ref, "sha": state.current_base_sha}
                ]
                return _finalize(
                    state,
                    terminal_state="blocked",
                    reason=reason,
                    operator_action=f"resume failed: {exc}",
                    phase="resolve",
                )
            state.resume_status = "resumed"
            state.current_head = resume_checkpoint["current_head"]
            state.cycle_attempts = list(resume_checkpoint["cycle_attempts"])
            state.head_history = list(resume_checkpoint["head_history"])
            state.base_revision_history = list(
                resume_checkpoint["base_revision_history"]
            )
            state.review_records = list(resume_checkpoint["review_records"])
            state.validation_outcomes = list(resume_checkpoint["validation_outcomes"])
            state.preserved_failed_attempts = list(
                resume_checkpoint["preserved_failed_attempts"]
            )
            # Reconstruct the terminal result's top-level `finding_dispositions`
            # from checkpoint history, oldest review pass first. An "accepted"
            # review-record disposition only becomes a reportable "selected"
            # entry once a matching `committed` cycle attempt actually
            # produced a fix commit for it (schema requires `selected` to
            # carry `fix_commit_sha`); an accepted-but-not-yet-committed
            # finding was interrupted before it resolved, so this run will
            # decide and attempt it again rather than reporting it
            # prematurely. `record_finding_disposition` always replaces any
            # prior entry for the same finding_id, so iterating oldest first
            # naturally leaves the most recent disposition per finding as the
            # final reconstructed state — a finding declined on an earlier
            # pass and later accepted-and-fixed is never left carrying both a
            # stale `declined` entry and its real `selected` one.
            committed_fix_by_finding = {
                attempt["finding_id"]: attempt["resulting_head"]
                for attempt in state.cycle_attempts
                if attempt.get("outcome") == "committed" and attempt.get("finding_id")
            }
            for record in state.review_records:
                for disposition in record["finding_dispositions"]:
                    finding_id = disposition["finding_id"]
                    if disposition["disposition"] == "accepted":
                        fix_commit_sha = committed_fix_by_finding.get(finding_id)
                        if fix_commit_sha is None:
                            continue
                        state.record_finding_disposition(
                            finding_id=finding_id,
                            disposition="selected",
                            rationale=disposition["rationale"],
                            fix_commit_sha=fix_commit_sha,
                        )
                    else:
                        state.record_finding_disposition(
                            finding_id=finding_id,
                            disposition="declined",
                            rationale=disposition["rationale"],
                        )

            recovered = LE.recover_interrupted_attempts(
                repo=repo,
                invocation_id=invocation["invocation_id"],
                checkpoint=dict(resume_checkpoint),
            )
            for leftover in recovered:
                if leftover.already_promoted:
                    continue
                handle = LE.AttemptHandle(
                    path=leftover.worktree_path or (attempts_root / leftover.branch),
                    branch=leftover.branch,
                    base_sha=leftover.base_sha,
                )
                preserved = LE.discard_attempt(
                    common_dir=common_dir,
                    handle=handle,
                    attempt_sha=leftover.attempt_sha,
                    reason="recovered interrupted attempt from a prior invocation run",
                )
                state.preserved_failed_attempts.append(_checkpoint_preserved(preserved))
                state.cycle_attempts.append(
                    {
                        "sequence": len(state.cycle_attempts) + 1,
                        "started_from_head": leftover.base_sha,
                        "outcome": "interrupted",
                    }
                )
        else:
            if state.current_head != state.initial_head:
                return _finalize(
                    state,
                    terminal_state="blocked",
                    reason="candidate_integrity_failure",
                    operator_action=(
                        f"live head {state.current_head} does not match invocation "
                        f"candidate.head_sha {state.initial_head}"
                    ),
                    phase="resolve",
                )
            state.head_history = [state.initial_head]
            state.base_revision_history = [
                {"ref": state.base_ref, "sha": state.current_base_sha}
            ]

        _persist_checkpoint(
            state,
            phase="establish_evidence",
            next_action="run the next complete review",
        )

        review_sequence = len(state.review_records) + 1
        attempt_sequence = state.consumed_cycles() + 1
        # Only reconstructable from checkpoint `finding_dispositions` on resume
        # (the checkpoint schema does not retain a pass's full raw finding
        # set), so expanding/oscillation detection is best-effort across a
        # resume boundary and exact within one continuous run.
        previous_gating_ids: list[frozenset[str]] = [
            frozenset(
                disposition["finding_id"]
                for disposition in record["finding_dispositions"]
            )
            for record in state.review_records
        ]

        pending_finding: dict[str, Any] | None = None
        pending_from_review = False
        pending_decision: FixDecision | None = None

        while True:
            if pending_finding is None:
                if state.policy.check_remote is not None:
                    remote_check = state.policy.check_remote(state)
                    if remote_check is not None:
                        return _finalize(
                            state,
                            terminal_state="blocked",
                            reason=remote_check["reason"],
                            operator_action=(
                                "the remote head for this candidate advanced before "
                                "this invocation could converge; reconcile the two "
                                "candidates manually before retrying"
                            ),
                            phase="establish_evidence",
                            publication_override=_remote_check_publication_override(
                                state, remote_check
                            ),
                        )
                validation_outcomes = _run_validation_suite(
                    invocation, cwd=state.repo, run_validation=run_validation
                )
                unavailable_scope = _unavailable_scope(validation_outcomes)
                if unavailable_scope is not None:
                    state.validation_outcomes = validation_outcomes
                    return _finalize(
                        state,
                        terminal_state="blocked",
                        reason="validation_unavailable",
                        operator_action=(
                            f"the {unavailable_scope} validation command is unavailable; "
                            "an operator must repair the environment before this "
                            "invocation can continue"
                        ),
                        phase="establish_evidence",
                    )

                failed = _failed_outcome(validation_outcomes)
                if failed is not None:
                    synthetic = classify_validation_failure(
                        outcome=ValidationOutcome(
                            status="failed", result=failed.get("result")
                        ),
                        invocation=invocation,
                    )
                    state.validation_outcomes = validation_outcomes
                    if synthetic is None:
                        return _finalize(
                            state,
                            terminal_state="changes_remaining",
                            reason="current_candidate_validation_failure",
                            operator_action=(
                                f"the {failed['scope']} validation command "
                                f"{failed['command']!r} fails and no tractable "
                                "correction was identified; an operator must repair it"
                            ),
                            phase="decide",
                        )
                    pending_finding = synthetic
                    pending_from_review = False
                else:
                    state.validation_outcomes = validation_outcomes
                    diff = _current_diff(
                        state.repo, state.current_base_sha, state.current_head
                    )
                    packet = _build_packet(
                        invocation,
                        head_sha=state.current_head,
                        comparison_base_sha=state.current_base_sha,
                        diff=diff,
                        validation_outcomes=validation_outcomes,
                    )
                    mode = ORCH.resolve_review_execution_mode(
                        invocation["review_execution"]["mode"],
                        override_authorization=invocation["review_execution"].get(
                            "override_authorization"
                        ),
                        host_supports_fresh_subagent=host_supports_fresh_subagent,
                    )
                    if mode["blocked_reason"] is not None:
                        return _finalize(
                            state,
                            terminal_state="blocked",
                            reason="missing_capability",
                            operator_action=(
                                "this host cannot run a fresh read-only reviewer "
                                "subagent and the invocation carries no explicit "
                                "in_agent_override"
                            ),
                            phase="review",
                        )
                    independence = mode["independence"]
                    briefing = ORCH.build_reviewer_briefing(
                        independence=independence,
                        head_sha=state.current_head,
                        comparison_base_sha=state.current_base_sha,
                    )
                    before = _worktree_snapshot(state.repo)
                    review_pass = reviewer(
                        packet=packet,
                        briefing=briefing,
                        head_sha=state.current_head,
                        comparison_base_sha=state.current_base_sha,
                        independence=independence,
                        sequence=review_sequence,
                    )
                    after = _worktree_snapshot(state.repo)
                    mutation_report = ORCH.detect_worktree_mutation(
                        before,
                        after,
                        candidate_branch_ref=f"refs/heads/{state.branch}",
                        attempt_namespace_prefix=LE.attempt_namespace_ref_prefix(
                            invocation["invocation_id"]
                        ),
                    )
                    if mutation_report.candidate_mutations:
                        return _finalize(
                            state,
                            terminal_state="blocked",
                            reason="candidate_integrity_failure",
                            operator_action=(
                                "the candidate's own refs moved during the review "
                                "pass, regardless of attribution: "
                                + "; ".join(mutation_report.candidate_mutations)
                            ),
                            phase="review",
                        )
                    mutation_attempts = list(mutation_report.mutation_attempts) + list(
                        review_pass.mutation_attempts
                    )
                    integrity_evidence = (
                        "tool_trace"
                        if review_pass.tool_trace_available
                        else "surface_only"
                    )
                    reviewer_identity = ORCH.generate_reviewer_identity(
                        independence,
                        review_sequence,
                        explicit=review_pass.reviewer_identity,
                    )
                    try:
                        record = ORCH.build_review_record(
                            sequence=review_sequence,
                            packet=packet,
                            result=review_pass.result,
                            expected_head=state.current_head,
                            expected_base=state.current_base_sha,
                            independence=independence,
                            reviewer_identity=reviewer_identity,
                            mutation_attempts=mutation_attempts,
                            observed_ref_changes=mutation_report.observed_ref_changes,
                            integrity_evidence=integrity_evidence,
                        )
                    except ORCH.ReviewIntegrityError as exc:
                        return _finalize(
                            state,
                            terminal_state="blocked",
                            reason="reviewer_integrity_failure",
                            operator_action=f"the review pass could not be trusted: {exc}",
                            phase="review",
                        )

                    if mutation_attempts:
                        state.review_records.append(record)
                        return _finalize(
                            state,
                            terminal_state="blocked",
                            reason="reviewer_integrity_failure",
                            operator_action=(
                                "the reviewer attempted a prohibited mutation: "
                                + "; ".join(mutation_attempts)
                            ),
                            phase="review",
                        )

                    result = review_pass.result
                    if record["aggregate_verdict"] == "blocked":
                        state.review_records.append(record)
                        return _finalize(
                            state,
                            terminal_state="blocked",
                            reason="missing_capability",
                            operator_action=(
                                "the review pass itself returned blocked: "
                                f"{result.get('next_action', '')}"
                            ),
                            phase="review",
                        )

                    if record["aggregate_verdict"] == "clean":
                        state.review_records.append(record)
                        converged_created_commits = state.head_history[1:]
                        if state.policy.publish is None:
                            _persist_checkpoint(
                                state, phase="return", next_action="none; converged"
                            )
                            return _finalize(
                                state,
                                terminal_state="converged",
                                reason=None,
                                operator_action=(
                                    "publish the retained local commit(s) through your "
                                    "existing PR or merge workflow; review-fix-loop "
                                    "performs no remote write under local_commit"
                                    if converged_created_commits
                                    else "no changes were required; nothing to publish"
                                ),
                                phase="return",
                            )

                        # `update_pr`: the review/fix/converge machinery above is
                        # identical to `local_commit`'s; only the publication tail
                        # differs. Every ordinary iteration cycle stayed local —
                        # this is the one and only remote write this invocation
                        # ever attempts, and only now that review is clean.
                        outcome = policy.publish(state)
                        if outcome.status == "published":
                            publication_override: dict[str, Any] = {
                                "policy": policy.name,
                                "status": "published",
                                "non_converged_exposure": outcome.non_converged_exposure,
                            }
                        else:
                            # Mirror `_default_publication`'s own
                            # blocked-reason rule rather than trusting
                            # `outcome.status` directly: only
                            # `remote_advanced`/`publication_failed` mean a
                            # publication attempt itself did not land
                            # (`failed`); every other blocked reason this
                            # publish step can return (for example a local
                            # `candidate_integrity_failure` ancestry check
                            # that never even attempted a push) is
                            # `withheld`, exactly like every other blocked
                            # reason the engine returns.
                            publication_override = dict(
                                _default_publication(
                                    policy.name,
                                    terminal_state="blocked",
                                    reason=outcome.blocked_reason,
                                )
                            )
                            publication_override["non_converged_exposure"] = (
                                outcome.non_converged_exposure
                            )
                        if outcome.remote_head_before is not None:
                            publication_override["remote_head_before"] = (
                                outcome.remote_head_before
                            )
                        if outcome.remote_head_after is not None:
                            publication_override["remote_head_after"] = (
                                outcome.remote_head_after
                            )

                        if outcome.status == "published":
                            source_override = None
                            if outcome.remote_head_after is not None:
                                original_source_sha = invocation["candidate"][
                                    "source_binding"
                                ]["observed_object_id"]
                                source_override = {
                                    "status": "bound",
                                    "initial_head": original_source_sha,
                                    "final_head": outcome.remote_head_after,
                                    "ahead_by": 0,
                                    "behind_by": 0,
                                }
                            _persist_checkpoint(
                                state,
                                phase="return",
                                next_action="none; converged and published",
                            )
                            return _finalize(
                                state,
                                terminal_state="converged",
                                reason=None,
                                operator_action=outcome.operator_action,
                                phase="return",
                                publication_override=publication_override,
                                source_override=source_override,
                            )

                        _persist_checkpoint(
                            state, phase="publish", next_action=outcome.operator_action
                        )
                        return _finalize(
                            state,
                            terminal_state="blocked",
                            reason=outcome.blocked_reason,
                            operator_action=outcome.operator_action,
                            phase="publish",
                            publication_override=publication_override,
                        )

                    gating_ids = frozenset(
                        finding["id"]
                        for finding in ORCH.normalize_findings(result["findings"])
                        if finding["severity"] in ORCH.GATING_SEVERITIES
                    )
                    if (
                        previous_gating_ids
                        and len(gating_ids) > len(previous_gating_ids[-1])
                        and previous_gating_ids[-1] <= gating_ids
                    ):
                        state.review_records.append(record)
                        return _finalize(
                            state,
                            terminal_state="changes_remaining",
                            reason="expanding_findings",
                            operator_action=(
                                "a prior fix introduced additional gating findings; "
                                "an operator must review the remaining scope before "
                                "further automatic remediation"
                            ),
                            phase="decide",
                        )
                    # A genuine A,B,A oscillation: the set changed from the
                    # immediately preceding pass but matches the pass before
                    # that. A finding set that simply survives unchanged
                    # (A,A,A) is not oscillation — it is the ordinary
                    # "repeated finding" case the design tolerates within
                    # budget, not an early stop.
                    if (
                        len(previous_gating_ids) >= 2
                        and previous_gating_ids[-1] != gating_ids
                        and previous_gating_ids[-2] == gating_ids
                    ):
                        state.review_records.append(record)
                        return _finalize(
                            state,
                            terminal_state="changes_remaining",
                            reason="oscillation",
                            operator_action=(
                                "the same finding set is oscillating across review "
                                "passes without converging; an operator must break "
                                "the cycle"
                            ),
                            phase="decide",
                        )
                    previous_gating_ids.append(gating_ids)

                    selected = ORCH.select_next_finding(result["findings"])
                    state.review_records.append(record)
                    review_sequence += 1

                    if selected is None:
                        _persist_checkpoint(
                            state, phase="decide", next_action="operator input required"
                        )
                        return _finalize(
                            state,
                            terminal_state="blocked",
                            reason="operator_input_required",
                            operator_action=(
                                "only deferred findings remain; an operator must "
                                "decide whether to accept, escalate, or authorize "
                                "further work"
                            ),
                            phase="decide",
                        )
                    pending_finding = selected
                    pending_from_review = True

            finding = pending_finding

            if pending_decision is None:
                decision = decide(
                    finding=finding,
                    change_contract=invocation["change_contract"],
                    attempt_number=attempt_sequence,
                )
                disposition_record = {
                    "finding_id": finding["id"],
                    "disposition": decision.disposition,
                    "rationale": decision.rationale,
                }
                if pending_from_review and state.review_records:
                    state.review_records[-1]["finding_dispositions"].append(
                        disposition_record
                    )

                if decision.disposition != "accepted":
                    state.record_finding_disposition(
                        finding_id=finding["id"],
                        disposition="declined",
                        rationale=decision.rationale,
                    )
                    _persist_checkpoint(
                        state, phase="decide", next_action="operator input required"
                    )
                    return _finalize(
                        state,
                        terminal_state="blocked",
                        reason="operator_input_required",
                        operator_action=(
                            f"finding {finding['id']} was {decision.disposition} "
                            f"({decision.rationale}); an operator must decide how "
                            "to proceed since it was not fixed"
                        ),
                        phase="decide",
                    )

                if decision.expands_scope:
                    _persist_checkpoint(
                        state, phase="decide", next_action="scope decision required"
                    )
                    return _finalize(
                        state,
                        terminal_state="blocked",
                        reason="scope_decision_required",
                        operator_action=(
                            f"fixing {finding['id']} would expand beyond "
                            f"{invocation['change_contract']['allowed_remediation_scope']!r}; "
                            "an operator must authorize the expanded scope"
                        ),
                        phase="decide",
                    )
                if decision.operator_input_required:
                    _persist_checkpoint(
                        state, phase="decide", next_action="operator input required"
                    )
                    return _finalize(
                        state,
                        terminal_state="blocked",
                        reason="operator_input_required",
                        operator_action=(
                            f"finding {finding['id']} requires operator input "
                            "before a fix can be attempted"
                        ),
                        phase="decide",
                    )
                pending_decision = decision

            decision = pending_decision

            if state.remaining_cycles() <= 0:
                state.unresolved_or_deferred.append(
                    f"{finding['id']}: accepted but the fix-cycle budget is exhausted"
                )
                _persist_checkpoint(
                    state,
                    phase="fix",
                    next_action="operator must authorize a new budget",
                )
                return _finalize(
                    state,
                    terminal_state="changes_remaining",
                    reason="cycle_budget_exhausted",
                    operator_action=(
                        f"{finding['id']} remains after consuming every fix cycle; "
                        "an operator must resolve it directly or authorize a new "
                        "invocation with a fresh budget"
                    ),
                    phase="fix",
                )

            if state.policy.check_remote is not None:
                remote_check = state.policy.check_remote(state)
                if remote_check is not None:
                    return _finalize(
                        state,
                        terminal_state="blocked",
                        reason=remote_check["reason"],
                        operator_action=(
                            "the remote head for this candidate advanced before "
                            "this fix attempt could start; reconcile the two "
                            "candidates manually before retrying"
                        ),
                        phase="fix",
                        publication_override=_remote_check_publication_override(
                            state, remote_check
                        ),
                    )

            started_from_head = state.current_head
            sequence = attempt_sequence
            attempt_sequence += 1
            attempt = LE.create_attempt(
                repo=state.repo,
                attempts_root=attempts_root,
                base_sha=started_from_head,
                invocation_id=invocation["invocation_id"],
                sequence=sequence,
            )
            commit_message = apply_fix(
                finding=finding,
                attempt_path=attempt.path,
                change_contract=invocation["change_contract"],
                attempt_number=sequence,
            )
            attempt_validation = _run_validation_suite(
                invocation, cwd=attempt.path, run_validation=run_validation
            )
            attempt_failed = bool(
                _failed_outcome(attempt_validation)
                or _unavailable_scope(attempt_validation)
            )

            if attempt_failed:
                preserved = LE.discard_attempt(
                    common_dir=common_dir,
                    handle=attempt,
                    attempt_sha=None,
                    reason=f"validation failed while fixing {finding['id']}",
                )
                state.preserved_failed_attempts.append(_checkpoint_preserved(preserved))
                previous_attempt = (
                    state.cycle_attempts[-1] if state.cycle_attempts else None
                )
                consecutive_failure = (
                    previous_attempt is not None
                    and previous_attempt["outcome"] == "failed"
                    and previous_attempt["started_from_head"] == started_from_head
                )
                state.cycle_attempts.append(
                    {
                        "sequence": sequence,
                        "started_from_head": started_from_head,
                        "outcome": "failed",
                        "finding_id": finding["id"],
                    }
                )
                if consecutive_failure:
                    _persist_checkpoint(
                        state, phase="fix", next_action="operator input required"
                    )
                    return _finalize(
                        state,
                        terminal_state="changes_remaining",
                        reason="repeated_failed_attempt",
                        operator_action=(
                            f"two consecutive fix attempts for {finding['id']} both "
                            "failed validation without any progress; an operator "
                            "must intervene"
                        ),
                        phase="fix",
                    )
                _persist_checkpoint(
                    state, phase="fix", next_action="retry the fix from the same head"
                )
                # Retry the same accepted finding from the same head: no head
                # change occurred, so no fresh review is needed before retrying.
                continue

            new_sha = LE.commit_attempt(attempt, commit_message)
            new_head = LE.promote_attempt(
                canonical_worktree=state.repo,
                canonical_branch=state.branch,
                attempt_sha=new_sha,
                expected_old_head=started_from_head,
            )
            state.cycle_attempts.append(
                {
                    "sequence": sequence,
                    "started_from_head": started_from_head,
                    "outcome": "committed",
                    "resulting_head": new_head,
                    "finding_id": finding["id"],
                }
            )
            state.record_finding_disposition(
                finding_id=finding["id"],
                disposition="selected",
                rationale=decision.rationale,
                fix_commit_sha=new_head,
            )
            state.current_head = new_head
            state.head_history.append(new_head)
            pending_finding = None
            pending_decision = None
            _persist_checkpoint(
                state,
                phase="invalidate_and_repeat",
                next_action="run a fresh complete review",
            )
    finally:
        lock_cm.__exit__(None, None, None)
