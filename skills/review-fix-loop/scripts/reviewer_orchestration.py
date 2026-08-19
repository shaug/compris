#!/usr/bin/env python3
"""Reviewer isolation and complete-review orchestration for `review-fix-loop`.

Implements the deterministic decisions and data transformations behind
design's "Review execution" and "Reviewer write prevention" sections
(`design/review-fix-loop.md`) and workflow step 3 ("Review"): fixed lens
resolution, review-execution mode resolution, before/after mutation
detection, checkpoint-shaped `review_records` construction, and finding
normalization. See `references/reviewer-orchestration.md` for the full
rationale behind each function; this module states it once each, briefly,
and does not restate it.

It does not run a subagent, spawn a process, or shell out to Git — those are
host/runtime actions the executing agent performs by following
`references/reviewer-orchestration.md`. It also does not decide which
finding to fix or apply a fix (design's "Decide"/"Fix" steps 4-5, a later
child's responsibility); `select_next_finding` only identifies the next
candidate in a stable order.

Dependency-free, like every other script in this skill: it loads the
bundled `references/review-suite/validate.py` and `scripts/review_gate.py`
(kept in sync via `just sync-contracts`) rather than duplicating their
candidate/lens-execution binding logic.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple, Sequence

HERE = Path(__file__).resolve().parent
REVIEW_SUITE_VALIDATE_PATH = HERE.parent / "references" / "review-suite" / "validate.py"
REVIEW_GATE_PATH = HERE / "review_gate.py"


def _load_bundled_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REVIEW_SUITE = _load_bundled_module(
    "review_fix_loop_bundled_review_suite_validate", REVIEW_SUITE_VALIDATE_PATH
)
GATE = _load_bundled_module("review_fix_loop_bundled_review_gate", REVIEW_GATE_PATH)

# Sourced from the bundled validator's own constant so this cannot drift from
# the schema/semantics that enforce it.
REQUIRED_LENSES: tuple[str, ...] = REVIEW_SUITE.REQUIRED_AGGREGATE_LENSES

SEVERITY_ORDER = {"blocking": 0, "strong_recommendation": 1, "defer": 2}
GATING_SEVERITIES = frozenset({"blocking", "strong_recommendation"})

# Compared for mutation. `ignored` is captured (REQUIRED_SNAPSHOT_KEYS) but
# never compared — see references/reviewer-orchestration.md, "Reviewer write
# prevention" tier 4.
COMPARED_WORKTREE_CATEGORIES = ("tracked", "staged", "unstaged", "untracked")
REQUIRED_SNAPSHOT_KEYS = ("head_sha", "refs", *COMPARED_WORKTREE_CATEGORIES, "ignored")

# Acceptance criterion: "Reviewer instructions explicitly prohibit worktree
# mutation and implementation." One shared tuple so a fresh subagent and an
# in-agent override get identical wording, and a test can assert on it.
REVIEWER_PROHIBITIONS: tuple[str, ...] = (
    "Report findings only; do not implement, edit, or otherwise change any "
    "file in this worktree or any other.",
    "Never stage, commit, amend, rebase, or push any ref in this worktree or "
    "any other.",
    "Never run a tool or command that writes to the working tree, the index, "
    "or any Git ref; use read-only inspection and validation commands only.",
    "Do not resolve conflicts, run formatters or codemods, or apply any "
    "proposed fix, including one you propose yourself.",
)


class ReviewIntegrityError(ValueError):
    """A raw review-code-change packet/result pair cannot be trusted this cycle.

    Raised by `build_review_record` when `evaluate_review_result` finds
    either document untrustworthy. Treat like any other incomplete-evidence
    stop; there is no partially-trusted fallback record.
    """

    def __init__(self, errors: Sequence[str]):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def resolve_review_lenses() -> tuple[str, ...]:
    """Return the fixed set of lenses a complete review must cover.

    `review-fix-loop` has no selectable lens subset (design: the complete
    suite is its "sole initial review mode"); this is the one canonical
    source for that fixed set.
    """
    return REQUIRED_LENSES


def evaluate_review_result(
    packet: Mapping[str, Any],
    result: Mapping[str, Any],
    expected_head: str,
    expected_base: str,
) -> list[str]:
    """Return rejection reasons for a raw review-code-change result and its packet.

    Empty means the result is trustworthy evidence for exactly this cycle:
    schema-valid, cross-field consistent, bound to `expected_head`/
    `expected_base` at the candidate and every lens execution, and backed by
    a packet bound to the same candidate whose own validation entries can
    support the verdict. `changes_required` and `blocked` are ordinary
    outcomes, not failures — see references/reviewer-orchestration.md,
    "Rejecting an incomplete result", for why both the result and the packet
    must be checked and why this does not simply call the bundled
    `validate_pair`.

    `packet` is required, not optional: review-fix-loop's own
    checkpoint/terminal-result contract never persists one without the
    other, so there is no legitimate packet-less caller.
    """
    packet = dict(packet)
    result = dict(result)
    result_errors = [
        f"result: {error}" for error in REVIEW_SUITE.validate_result(result)
    ]
    packet_errors = []
    for error in REVIEW_SUITE.validate_packet(packet):
        if result.get(
            "verdict"
        ) != "blocked" or not REVIEW_SUITE.is_blockable_packet_error(error):
            packet_errors.append(f"packet: {error}")
    errors = result_errors + packet_errors
    if errors:
        return errors

    packet_candidate = packet.get("candidate") or {}
    if (
        packet_candidate.get("head_sha") != expected_head
        or packet_candidate.get("comparison_base_sha") != expected_base
    ):
        return [
            "packet.candidate: packet is not bound to the current candidate "
            f"(expected head {expected_head} / base {expected_base}, got "
            f"head {packet_candidate.get('head_sha')!r} / "
            f"base {packet_candidate.get('comparison_base_sha')!r})"
        ]

    errors = [
        f"pair: {error}"
        for error in REVIEW_SUITE._check_clean_requires_passing_validation(
            packet, result
        )
    ]
    if errors:
        return errors

    return GATE.evaluate_bound(result, expected_head, expected_base)


def resolve_review_execution_mode(
    mode: str,
    *,
    override_authorization: str | None = None,
    host_supports_fresh_subagent: bool = True,
) -> dict[str, Any]:
    """Resolve the review-execution mode this host actually grants.

    Assumes `mode`/`override_authorization` already satisfy
    `validate_invocation`'s invariant (`in_agent_override` requires
    authorization; `fresh_subagent` must not carry one) and resolves the one
    thing schema validation cannot: whether this host can honor
    `fresh_subagent`.

    Returns `independence` (`"fresh_subagent"`, `"in_agent_override"`, or
    `None`), `authorized_by`, and `blocked_reason` (`None` or
    `"missing_capability"`). An explicit override is always honored,
    regardless of host capability. An unsupported `fresh_subagent` host with
    no override is `missing_capability` — no automatic fallback to in-agent
    (acceptance criterion: in-agent execution occurs only when explicitly
    requested).
    """
    if mode == "in_agent_override":
        return {
            "independence": "in_agent_override",
            "authorized_by": override_authorization,
            "blocked_reason": None,
        }
    if mode == "fresh_subagent":
        if host_supports_fresh_subagent:
            return {
                "independence": "fresh_subagent",
                "authorized_by": None,
                "blocked_reason": None,
            }
        return {
            "independence": None,
            "authorized_by": None,
            "blocked_reason": "missing_capability",
        }
    raise ValueError(f"unknown review_execution mode: {mode!r}")


def generate_reviewer_identity(
    independence: str, sequence: int, *, explicit: str | None = None
) -> str:
    """Return this review pass's reviewer identity.

    Default `<independence>-review-<sequence>` (matching
    `references/examples/*`, e.g. `fresh-subagent-review-1`) makes freshness
    per head observable; an explicit identity (a real subagent/session ID)
    always wins.
    """
    if explicit:
        return explicit
    if sequence < 1:
        raise ValueError(f"sequence must be >= 1, got {sequence}")
    return f"{independence.replace('_', '-')}-review-{sequence}"


class WorktreeMutationReport(NamedTuple):
    """Tiered result of `detect_worktree_mutation`.

    `candidate_mutations` (Tier 1: `head_sha`, the candidate branch ref, and
    this invocation's own attempt namespace) invalidates the candidate itself
    regardless of who caused it — callers map a non-empty list to
    `blocked/candidate_integrity_failure`, not `write_isolation`.

    `mutation_attempts` (worktree path state — `tracked`/`staged`/`unstaged`/
    `untracked`) is attributable to this reviewer pass exactly as before this
    tiering existed: feed it into `build_review_record`'s `mutation_attempts`
    to force `write_isolation: "violated"`.

    `observed_ref_changes` (Tier 2: every other local ref) is a non-gating
    observation only — a ref this check cannot attribute to the reviewer
    because the ref store may be shared with other worktrees or background
    automation.
    """

    candidate_mutations: list[str]
    mutation_attempts: list[str]
    observed_ref_changes: list[str]


def _format_ref_detail(
    *, added: Sequence[str], removed: Sequence[str], changed: Sequence[str]
) -> str:
    detail = []
    if added:
        detail.append(f"added {list(added)}")
    if removed:
        detail.append(f"removed {list(removed)}")
    if changed:
        detail.append(f"changed {list(changed)}")
    return "refs: " + "; ".join(detail)


def detect_worktree_mutation(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    candidate_branch_ref: str | None = None,
    attempt_namespace_prefix: str | None = None,
) -> WorktreeMutationReport:
    """Return a tiered `WorktreeMutationReport` between two worktree snapshots.

    `before`/`after` must each carry every `REQUIRED_SNAPSHOT_KEYS` entry:
    `head_sha`, a `refs` mapping (ref name to object ID), and the
    tracked/staged/unstaged/untracked/ignored path lists. Raises
    `ValueError` if either is missing a key — fails closed rather than
    treating an uncaptured dimension as unchanged.

    `head_sha` and every `COMPARED_WORKTREE_CATEGORIES` path list are
    compared exactly as before this tiering existed; `head_sha` lands in
    `candidate_mutations` (it is always candidate-bound — Tier 1), and the
    path lists land in `mutation_attempts` (worktree state is never shared
    across worktrees, so it stays fully attributable to this pass). `ignored`
    is captured but never compared. See references/reviewer-orchestration.md
    for the full rationale.

    Local `refs` (excluding `refs/remotes/*`, since an unattributed
    remote-tracking-ref advance is the ordinary `remote_advanced`
    publication-race contract, not reviewer misconduct — issue #97/#100's
    scope) are classified Tier 1 when the ref is `candidate_branch_ref` or
    starts with `attempt_namespace_prefix`, and Tier 2 otherwise. A Tier 2 ref
    change is unattributable by construction — the ref store may be shared
    with other worktrees or unrelated background automation — so it is
    always recorded in `observed_ref_changes` rather than gating.

    Every list empty means no attributable change per *this* check; design
    also requires the stronger filesystem-boundary and tool-surface controls
    this function cannot see. A non-empty `candidate_mutations` invalidates
    the candidate itself; a non-empty `mutation_attempts` must fail the cycle
    closed: `build_review_record` forces `write_isolation: "violated"`, and
    `validate.py`'s `_check_converged_requires_clean_evidence` rejects
    `converged` for any review record with a non-empty `mutation_attempts`.
    """
    missing_before = [key for key in REQUIRED_SNAPSHOT_KEYS if key not in before]
    missing_after = [key for key in REQUIRED_SNAPSHOT_KEYS if key not in after]
    if missing_before or missing_after:
        raise ValueError(
            "detect_worktree_mutation requires a complete before/after "
            f"snapshot; before is missing {missing_before!r}, after is "
            f"missing {missing_after!r}"
        )

    candidate_mutations: list[str] = []
    mutation_attempts: list[str] = []
    observed_ref_changes: list[str] = []

    before_head = before["head_sha"]
    after_head = after["head_sha"]
    if before_head != after_head:
        candidate_mutations.append(
            f"head_sha advanced from {before_head!r} to {after_head!r}"
        )
    for category in COMPARED_WORKTREE_CATEGORIES:
        before_paths = set(before[category] or [])
        after_paths = set(after[category] or [])
        if before_paths != after_paths:
            added = sorted(after_paths - before_paths)
            removed = sorted(before_paths - after_paths)
            detail = []
            if added:
                detail.append(f"added {added}")
            if removed:
                detail.append(f"removed {removed}")
            mutation_attempts.append(f"{category}: " + "; ".join(detail))

    def _local_refs(snapshot: Mapping[str, Any]) -> dict[str, str]:
        refs = snapshot["refs"] or {}
        return {
            name: value
            for name, value in refs.items()
            if not name.startswith("refs/remotes/")
        }

    def _is_candidate_bound(ref_name: str) -> bool:
        if candidate_branch_ref is not None and ref_name == candidate_branch_ref:
            return True
        if attempt_namespace_prefix and ref_name.startswith(attempt_namespace_prefix):
            return True
        return False

    before_refs = _local_refs(before)
    after_refs = _local_refs(after)
    if before_refs != after_refs:
        added = sorted(set(after_refs) - set(before_refs))
        removed = sorted(set(before_refs) - set(after_refs))
        changed = sorted(
            name
            for name in set(before_refs) & set(after_refs)
            if before_refs[name] != after_refs[name]
        )

        tier1_added = [name for name in added if _is_candidate_bound(name)]
        tier1_removed = [name for name in removed if _is_candidate_bound(name)]
        tier1_changed = [name for name in changed if _is_candidate_bound(name)]
        if tier1_added or tier1_removed or tier1_changed:
            candidate_mutations.append(
                _format_ref_detail(
                    added=tier1_added, removed=tier1_removed, changed=tier1_changed
                )
            )

        tier2_added = [name for name in added if not _is_candidate_bound(name)]
        tier2_removed = [name for name in removed if not _is_candidate_bound(name)]
        tier2_changed = [name for name in changed if not _is_candidate_bound(name)]
        if tier2_added or tier2_removed or tier2_changed:
            observed_ref_changes.append(
                _format_ref_detail(
                    added=tier2_added, removed=tier2_removed, changed=tier2_changed
                )
            )

    return WorktreeMutationReport(
        candidate_mutations=candidate_mutations,
        mutation_attempts=mutation_attempts,
        observed_ref_changes=observed_ref_changes,
    )


def build_review_record(
    *,
    sequence: int,
    packet: Mapping[str, Any],
    result: Mapping[str, Any],
    expected_head: str,
    expected_base: str,
    independence: str,
    reviewer_identity: str,
    mutation_attempts: Sequence[str] = (),
    observed_ref_changes: Sequence[str] = (),
    integrity_evidence: str = "surface_only",
) -> dict[str, Any]:
    """Build one checkpoint-shaped `review_records` entry from a raw result.

    Fails closed: raises `ReviewIntegrityError` (never returns a partially
    trusted record) when `evaluate_review_result` rejects `packet`/`result`.

    Any non-empty `mutation_attempts` forces `write_isolation: "violated"`
    regardless of the aggregate verdict — an attempted prohibited mutation
    invalidates the review even if the runtime blocked it. `mutation_attempts`
    is the attributable channel only (worktree path state plus host-supplied
    tool-trace evidence) — an unattributed Tier 2 ref change belongs in
    `observed_ref_changes` instead and never affects `write_isolation`.

    `observed_ref_changes` is recorded verbatim when non-empty and omitted
    otherwise — a non-gating record of every local ref this pass could not
    attribute to the reviewer.

    `integrity_evidence` is `"tool_trace"` when the host supplied tool-trace
    inspection for this pass (whether or not it found anything) and
    `"surface_only"` (the default) when it did not, so a reader can tell
    "inspected and clean" from "never inspected." Always recorded — a
    `surface_only` run still reaches `converged`.

    `finding_dispositions` starts empty: disposing a finding
    (`accepted`/`rejected`/`deferred`) is design's "Decide" step, a later
    child's responsibility; this record reserves the field's shape for it.
    """
    errors = evaluate_review_result(packet, result, expected_head, expected_base)
    if errors:
        raise ReviewIntegrityError(errors)

    record: dict[str, Any] = {
        "sequence": sequence,
        "head_sha": expected_head,
        "comparison_base_sha": expected_base,
        "review_independence": independence,
        "reviewer_identity": reviewer_identity,
        "write_isolation": "violated" if mutation_attempts else "enforced",
        "aggregate_verdict": result["verdict"],
        "finding_dispositions": [],
        "mutation_attempts": list(mutation_attempts),
        "integrity_evidence": (
            "tool_trace" if integrity_evidence == "tool_trace" else "surface_only"
        ),
    }
    if observed_ref_changes:
        record["observed_ref_changes"] = list(observed_ref_changes)
    return record


def normalize_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return `findings` in one deterministic, input-order-independent order.

    Sorted by severity (`blocking`, `strong_recommendation`, `defer`), then
    lens, then finding `id`. `review-code-change` guarantees no particular
    ordering; without a canonical one, finding-to-fix linkage and checkpoint
    replay could disagree run to run given identical evidence.

    Pure reordering: every entry is shallow-copied, never mutated or dropped.
    """

    def sort_key(finding: Mapping[str, Any]) -> tuple[int, str, str]:
        return (
            SEVERITY_ORDER.get(finding.get("severity"), len(SEVERITY_ORDER)),
            str(finding.get("lens", "")),
            str(finding.get("id", "")),
        )

    return [dict(finding) for finding in sorted(findings, key=sort_key)]


def select_next_finding(findings: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Return the one finding a fix cycle would target next, or `None`.

    The first gating (`blocking`/`strong_recommendation`) entry of
    `normalize_findings`'s canonical order; `defer` findings are never
    selected. Selecting is not disposing or fixing — see
    `build_review_record`'s docstring.
    """
    for finding in normalize_findings(findings):
        if finding.get("severity") in GATING_SEVERITIES:
            return finding
    return None


def build_reviewer_briefing(
    *, independence: str, head_sha: str, comparison_base_sha: str
) -> str:
    """Return the literal instruction text handed to one review pass.

    Acceptance criterion: "Reviewer instructions explicitly prohibit
    worktree mutation and implementation" — the actual prompt text prepended
    before invoking `review-code-change`, so the prohibition travels with
    every pass rather than living only in a document.
    """
    lines = [
        "You are running the complete repository-owned review-code-change "
        f"sequence for candidate {head_sha} against comparison base "
        f"{comparison_base_sha}.",
        f"Execution context: {independence}.",
        *REVIEWER_PROHIBITIONS,
        "Invoke review-code-change with only the supplied raw evidence "
        "packet; do not consult any implementation transcript, intended fix, "
        "prior conclusion, or suspected finding.",
    ]
    return "\n".join(lines)
