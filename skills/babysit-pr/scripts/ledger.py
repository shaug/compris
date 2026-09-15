#!/usr/bin/env python3
"""Append-only, compaction-resilient ledger for `babysit-pr`'s workspace.

See `references/ledger.md` for the workspace layout, ledger format, and
recovery rule this module implements. Summary: one workspace directory per PR
(the target unit), keyed by repository + PR number so a resumed session finds
it deterministically; one append-only `ledger.jsonl` inside it; a `session`
line recorded once per session start; and one `entry` line per feedback
disposition, retry, fix pushed, or terminal lifecycle observation during this
skill's watch loop.

The shared mechanics (workspace derivation and self-exclusion, append-only
JSON Lines I/O, the recovery-path dedup guard) live in `ledger_core.py`, a
byte-identical bundled copy of this repository's `ledger/core.py`, refreshed
by `just sync-contracts` — mirroring the same canonical-source-plus-bundled-
copy convention already used for the review lenses' shared contract. This
module fixes that shared core's generic parameters to this skill's own
vocabulary (`.babysit-pr/`, `item_id`,
`fixed`/`rejected`/`not_applicable` dispositions) and adds this skill's own
watcher-state reconciliation and CLI, neither of which has an analog in the
other two skills' ledgers.

This is a distinct store from `scripts/gh_pr_watch.py`'s own state file (which
lives outside the repository, under the system temp directory, and tracks
per-head retry counts and seen-feedback IDs for the watcher's own budget
enforcement — see `default_state_file_for`/`load_state` below). The two are
never merged: the watcher state file remains authoritative for retry-budget
enforcement exactly as it already is, and this ledger exists so a resumed or
post-compaction session can recover *what this skill itself decided* —
which feedback item got which disposition, which fix commit addressed it —
without re-reading transcript history. `reconcile_with_watcher_state` below
compares the two only to surface drift, never to override either one; live
PR and watcher state remain the execution source of truth per this skill's
own precedence rules.

Usable as a library (`import ledger`) or as a CLI:

    python3 scripts/ledger.py session-start --repo example/project --pr 482
    python3 scripts/ledger.py record \\
        --repo example/project --pr 482 --item review-comment-9001 \\
        --action feedback_disposition --terminal-result fixed \\
        --head-sha 4f2c9a1d --evidence-json '{"disposition": "fixed"}'
    python3 scripts/ledger.py read --repo example/project --pr 482
    python3 scripts/ledger.py find \\
        --repo example/project --pr 482 --item review-comment-9001

All paths are resolved relative to an explicit `--root` (defaulting to the
current working directory) so the workspace sits in the ticket's own
worktree, not inside this installed skill.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Iterable

WORKSPACE_DIRNAME = ".babysit-pr"
ID_FIELD = "item_id"

# Dispositions this skill's own workflow (SKILL.md, "Diagnose CI and
# feedback") treats as a closed, non-repeatable action. `deferred` is
# deliberately excluded: a deferred finding is preserved, not resolved, and
# recovery must still be able to see it as outstanding rather than treat it
# as done.
DEFAULT_COMPLETED_FEEDBACK_DISPOSITIONS = frozenset(
    {"fixed", "rejected", "not_applicable"}
)
DELIVERY_STATES = ("ready_to_merge", "merged", "closed", "blocked")
IMPLEMENTATION_OUTCOMES = ("held", "falsified", "missing", "unavailable")
OBSERVATION_STATUSES = ("observed", "uncertain", "missing")


def _load_sibling_module(name: str, filename: str):
    """Load a same-directory script by path and register it in `sys.modules`.

    Matches this repository's own test-loader convention rather than
    assuming package-relative import resolution regardless of how this
    script is invoked. Shared by `_load_core` (this module's own bundled
    `ledger_core.py`) and `_load_watcher_module` (the sibling
    `gh_pr_watch.py`) so the load-by-path mechanic exists once, not twice.
    """
    module_path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_core():
    """Load the bundled `ledger_core.py` by path."""
    return _load_sibling_module("ledger_core", "ledger_core.py")


core = _load_core()


def unit_key_for(repo: str, pr_number: int | str) -> str:
    """Compose the workspace key from repo + PR number.

    Mirrors `gh_pr_watch.default_state_file_for`'s own keying (case-folded
    repo, explicit PR number) so the two stores are trivially correlatable by
    a human or a script even though they live in different locations.

    `slugify` collapses every run of non-identifier characters — including
    both `/` (common inside a repo owner/name) and `#` (the join point below)
    — to a single `-`, which would otherwise let two distinct repos alias
    onto the same slug purely by where their own `/` happens to fall (e.g.
    `octocat/hello-world#482` and `octocat-hello/world#482` both slugify to
    `octocat-hello-world-482`). `core.collision_safe_digest` breaks that
    collision — the same fix `gh_pr_watch.default_state_file_for` already
    applies to its own identically-shaped keying, for the identical reason
    (see its own comment there: "the digest of the exact repository string
    guarantees distinct repositories can never collide").
    """
    repo_normalized = repo.lower()
    return (
        f"{repo_normalized}#{core.collision_safe_digest(repo_normalized)}#{pr_number}"
    )


def slugify(value: str) -> str:
    """Derive a filesystem-safe workspace key from `owner/repo#number`."""
    return core.slugify(value)


def workspace_dir(root: Path, repo: str, pr_number: int | str) -> Path:
    """Return the repo+PR-keyed workspace directory under `root`."""
    return core.workspace_dir(root, WORKSPACE_DIRNAME, unit_key_for(repo, pr_number))


def ledger_path(root: Path, repo: str, pr_number: int | str) -> Path:
    return core.ledger_path(root, WORKSPACE_DIRNAME, unit_key_for(repo, pr_number))


def ensure_workspace(root: Path, repo: str, pr_number: int | str) -> Path:
    """Create the workspace directory and self-exclude it from git.

    Writes a `.gitignore` containing `*` directly inside the workspace so it
    stays out of history regardless of where the ticket worktree sits — the
    workspace excludes itself rather than depending on the target
    repository's own `.gitignore`.
    """
    return core.ensure_workspace(root, WORKSPACE_DIRNAME, unit_key_for(repo, pr_number))


def record_session_start(
    root: Path,
    repo: str,
    pr_number: int | str,
    *,
    session_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one session-identity line at the start of a session."""
    return core.record_session_start(
        root,
        WORKSPACE_DIRNAME,
        unit_key_for(repo, pr_number),
        session_id=session_id,
        now=now,
    )


def record_entry(
    root: Path,
    repo: str,
    pr_number: int | str,
    *,
    item_id: str,
    action: str,
    terminal_result: str | None = None,
    head_sha: str | None = None,
    evidence: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one entry recording a feedback disposition, retry, or fix.

    `item_id` names the thing this entry is about, whose shape depends on
    `action`: a review comment or thread id for `feedback_disposition`, the
    exact head SHA for `retry` (retry budget is tracked per head SHA, matching
    `gh_pr_watch`'s own `retries_by_sha`), or the new commit SHA for
    `fix_pushed`.
    """
    return core.record_entry(
        root,
        WORKSPACE_DIRNAME,
        unit_key_for(repo, pr_number),
        id_field=ID_FIELD,
        id_value=item_id,
        action=action,
        terminal_result=terminal_result,
        head_sha=head_sha,
        evidence=evidence,
        now=now,
    )


def _validate_predicted_shape(value: dict[str, Any]) -> dict[str, Any]:
    """Validate the caller-owned predicted-shape identity without inventing it."""
    if not isinstance(value, dict):
        raise TypeError("predicted shape must be a JSON object")
    if set(value) != {"status", "identity", "source"}:
        raise ValueError(
            "predicted shape must contain exactly status, identity, and source"
        )
    if value["status"] == "available":
        if not all(
            isinstance(value[field], str) and value[field].strip()
            for field in ("identity", "source")
        ):
            raise ValueError(
                "available predicted shape requires non-empty identity and source"
            )
    elif value["status"] == "missing":
        if value["identity"] is not None or value["source"] is not None:
            raise ValueError(
                "missing predicted shape requires null identity and source"
            )
    else:
        raise ValueError("predicted shape status must be available or missing")
    return value


def _predicted_shape(raw: str) -> dict[str, Any]:
    """Parse the CLI's predicted-shape JSON before shared validation."""
    return _validate_predicted_shape(json.loads(raw))


def _observation(status: str, evidence: str | None) -> dict[str, str | None]:
    """Keep observation absence and uncertainty distinct from an observation."""
    if status not in OBSERVATION_STATUSES:
        raise ValueError(
            "lifecycle telemetry status must be observed, uncertain, or missing"
        )
    if status in {"observed", "uncertain"} and not (evidence or "").strip():
        raise ValueError(f"{status} lifecycle telemetry requires evidence")
    if status == "missing" and evidence is not None:
        raise ValueError("missing lifecycle telemetry cannot carry evidence")
    return {"status": status, "evidence": evidence}


def record_lifecycle_observation(
    root: Path,
    repo: str,
    pr_number: int | str,
    *,
    head_sha: str,
    delivery_state: str,
    predicted_shape: dict[str, Any],
    implementation_outcome: str,
    fired_trigger: str | None,
    reviewability_status: str,
    reviewability_evidence: str | None,
    operator_effort_status: str,
    operator_effort_evidence: str | None,
) -> dict[str, Any]:
    """Append non-gating terminal telemetry bound to one exact PR head."""
    if delivery_state not in DELIVERY_STATES:
        raise ValueError(f"unsupported delivery state: {delivery_state}")
    if implementation_outcome not in IMPLEMENTATION_OUTCOMES:
        raise ValueError(
            f"unsupported implementation outcome: {implementation_outcome}"
        )
    predicted_shape = _validate_predicted_shape(predicted_shape)
    prediction_missing = predicted_shape["status"] == "missing"
    outcome_missing = implementation_outcome == "missing"
    if prediction_missing != outcome_missing:
        raise ValueError("predicted shape and implementation outcome disagree")
    evidence = {
        "non_gating": True,
        "predicted_shape": predicted_shape,
        "implementation_outcome": implementation_outcome,
        "fired_trigger": fired_trigger,
        "reviewability": _observation(reviewability_status, reviewability_evidence),
        "operator_effort": _observation(
            operator_effort_status, operator_effort_evidence
        ),
    }
    return record_entry(
        root,
        repo,
        pr_number,
        item_id=head_sha,
        action="lifecycle_observation",
        terminal_result=delivery_state,
        head_sha=head_sha,
        evidence=evidence,
    )


def read_ledger(root: Path, repo: str, pr_number: int | str):
    """Parse the ledger, tolerating a malformed or partially written line."""
    return core.read_ledger(root, WORKSPACE_DIRNAME, unit_key_for(repo, pr_number))


def already_dispositioned(
    entries: Iterable[dict[str, Any]],
    item_id: str,
    completed_dispositions: frozenset[str] = DEFAULT_COMPLETED_FEEDBACK_DISPOSITIONS,
) -> dict[str, Any] | None:
    """Recovery-path dedup guard for feedback: the ledger's own claim.

    Returns the latest `feedback_disposition` entry for `item_id` when it
    already records a closed disposition (`fixed`, `rejected`, or
    `not_applicable`), else None. `deferred` never counts as dispositioned
    here, matching this skill's own rule that a deferred finding stays
    outstanding rather than resolved. This answers only what the ledger
    claims; the caller still must verify the item's live thread/comment state
    before treating a reply as already posted.
    """
    return core.already_recorded_complete(
        entries,
        ID_FIELD,
        item_id,
        completed_dispositions,
        action_filter=lambda entry: entry.get("action") == "feedback_disposition",
    )


def recorded_retry_counts(entries: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count ledger-recorded `retry` entries per head SHA.

    Used only for reconciliation against the watcher's own `retries_by_sha`;
    the watcher state file remains the authoritative budget enforcement, per
    `gh_pr_watch.current_retry_count`.
    """
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.get("action") != "retry":
            continue
        sha = entry.get("head_sha")
        if not sha:
            continue
        counts[sha] = counts.get(sha, 0) + 1
    return counts


def reconcile_with_watcher_state(
    entries: Iterable[dict[str, Any]], watcher_state: dict[str, Any] | None
) -> dict[str, Any]:
    """Compare this ledger's record against the watcher's own state file.

    Returns a report, never a mutation: `retry_mismatches` flags any head SHA
    where the ledger recorded more retries than the watcher state shows —
    the signal that a recorded retry never reached the watcher's own budget
    accounting and needs investigation before spending another — and
    `dispositioned_feedback_ids` is the closed-disposition set recovery must
    not re-disposition. The watcher's `retries_by_sha` remains authoritative
    for budget enforcement; this function only detects drift between the two
    stores, exactly as the recovery rule requires reconciling against "the
    existing watcher state file plus live PR state" rather than trusting the
    ledger alone.
    """
    entries = list(entries)
    watcher_retries = (watcher_state or {}).get("retries_by_sha") or {}
    ledger_retries = recorded_retry_counts(entries)
    mismatches = {}
    for sha, ledger_count in ledger_retries.items():
        watcher_count = int(watcher_retries.get(sha, 0) or 0)
        if watcher_count < ledger_count:
            mismatches[sha] = {
                "ledger_recorded": ledger_count,
                "watcher_recorded": watcher_count,
            }
    # Latest-entry-per-item semantics, matching `already_dispositioned`: an
    # item re-dispositioned more than once (e.g. `fixed` then later
    # `deferred`, after a regression) must report its *current* state, not
    # "closed at some point in its history" — an existential OR across the
    # full history would report a genuinely reopened item as still closed.
    candidate_ids = {
        entry.get("item_id")
        for entry in entries
        if entry.get("action") == "feedback_disposition" and entry.get("item_id")
    }
    dispositioned = sorted(
        item_id
        for item_id in candidate_ids
        if already_dispositioned(entries, item_id) is not None
    )
    return {"retry_mismatches": mismatches, "dispositioned_feedback_ids": dispositioned}


def _load_watcher_module():
    """Load `gh_pr_watch.py` by path so this module never assumes CWD.

    Deferred to call time (rather than a module-level import, unlike
    `_load_core`) so unit tests can exercise `reconcile_with_watcher_state`
    against a plain dict without requiring the watcher module or its
    `fcntl` dependency to be importable in every test environment.
    """
    return _load_sibling_module("gh_pr_watch", "gh_pr_watch.py")


def load_watcher_state(repo: str, pr_number: int | str) -> dict[str, Any]:
    """Read the live watcher state file for this repo + PR, if any exists."""
    watcher = _load_watcher_module()
    state_path = watcher.default_state_file_for({"repo": repo, "number": pr_number})
    state, _ = watcher.load_state(state_path)
    return state


# --- CLI -------------------------------------------------------------------

# Re-exported for the CLI below and for callers/tests that reach for it
# directly.
_parse_evidence = core.parse_evidence_json


def _cmd_session_start(args: argparse.Namespace) -> int:
    record = record_session_start(
        Path(args.root), args.repo, args.pr, session_id=args.session_id
    )
    print(json.dumps(record, sort_keys=True))
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    record = record_entry(
        Path(args.root),
        args.repo,
        args.pr,
        item_id=args.item,
        action=args.action,
        terminal_result=args.terminal_result,
        head_sha=args.head_sha,
        evidence=_parse_evidence(args.evidence_json),
    )
    print(json.dumps(record, sort_keys=True))
    return 0


def _cmd_observe(args: argparse.Namespace) -> int:
    record = record_lifecycle_observation(
        Path(args.root),
        args.repo,
        args.pr,
        head_sha=args.head_sha,
        delivery_state=args.delivery_state,
        predicted_shape=_predicted_shape(args.predicted_shape_json),
        implementation_outcome=args.implementation_outcome,
        fired_trigger=args.fired_trigger,
        reviewability_status=args.reviewability_status,
        reviewability_evidence=args.reviewability_evidence,
        operator_effort_status=args.operator_effort_status,
        operator_effort_evidence=args.operator_effort_evidence,
    )
    print(json.dumps(record, sort_keys=True))
    return 0


def _cmd_read(args: argparse.Namespace) -> int:
    result = read_ledger(Path(args.root), args.repo, args.pr)
    payload = {
        "sessions": result.sessions,
        "entries": result.entries,
        "skipped_lines": result.skipped_lines,
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


def _cmd_find(args: argparse.Namespace) -> int:
    result = read_ledger(Path(args.root), args.repo, args.pr)
    entry = already_dispositioned(result.entries, args.item)
    print(json.dumps(entry, sort_keys=True, indent=2) if entry else "null")
    return 0 if entry else 1


def _cmd_reconcile(args: argparse.Namespace) -> int:
    result = read_ledger(Path(args.root), args.repo, args.pr)
    watcher_state = load_watcher_state(args.repo, args.pr)
    report = reconcile_with_watcher_state(result.entries, watcher_state)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 1 if report["retry_mismatches"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="ticket worktree root the .babysit-pr/ workspace lives under",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    session = subparsers.add_parser(
        "session-start", help="append a session-identity line"
    )
    session.add_argument("--repo", required=True)
    session.add_argument("--pr", required=True)
    session.add_argument("--session-id", default=None)
    session.set_defaults(func=_cmd_session_start)

    record = subparsers.add_parser(
        "record", help="append a feedback-disposition, retry, or fix entry"
    )
    record.add_argument("--repo", required=True)
    record.add_argument("--pr", required=True)
    record.add_argument("--item", required=True)
    record.add_argument("--action", required=True)
    record.add_argument("--terminal-result", default=None)
    record.add_argument("--head-sha", default=None)
    record.add_argument("--evidence-json", default=None)
    record.set_defaults(func=_cmd_record)

    observe = subparsers.add_parser(
        "observe", help="append non-gating telemetry for one completed PR lifecycle"
    )
    observe.add_argument("--repo", required=True)
    observe.add_argument("--pr", required=True)
    observe.add_argument("--head-sha", required=True)
    observe.add_argument("--delivery-state", required=True, choices=DELIVERY_STATES)
    observe.add_argument("--predicted-shape-json", required=True)
    observe.add_argument(
        "--implementation-outcome", required=True, choices=IMPLEMENTATION_OUTCOMES
    )
    observe.add_argument("--fired-trigger", default=None)
    observe.add_argument(
        "--reviewability-status", required=True, choices=OBSERVATION_STATUSES
    )
    observe.add_argument("--reviewability-evidence", default=None)
    observe.add_argument(
        "--operator-effort-status", required=True, choices=OBSERVATION_STATUSES
    )
    observe.add_argument("--operator-effort-evidence", default=None)
    observe.set_defaults(func=_cmd_observe)

    read = subparsers.add_parser("read", help="print the parsed ledger as JSON")
    read.add_argument("--repo", required=True)
    read.add_argument("--pr", required=True)
    read.set_defaults(func=_cmd_read)

    find = subparsers.add_parser(
        "find", help="print the ledger's closed disposition for a feedback item, if any"
    )
    find.add_argument("--repo", required=True)
    find.add_argument("--pr", required=True)
    find.add_argument("--item", required=True)
    find.set_defaults(func=_cmd_find)

    reconcile = subparsers.add_parser(
        "reconcile", help="compare the ledger against the live watcher state file"
    )
    reconcile.add_argument("--repo", required=True)
    reconcile.add_argument("--pr", required=True)
    reconcile.set_defaults(func=_cmd_reconcile)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
