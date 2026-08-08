#!/usr/bin/env python3
"""Append-only, compaction-resilient ledger for `babysit-pr`'s workspace.

See `references/ledger.md` for the workspace layout, ledger format, and
recovery rule this module implements. Summary: one workspace directory per PR
(the target unit), keyed by repository + PR number so a resumed session finds
it deterministically; one append-only `ledger.jsonl` inside it; a `session`
line recorded once per session start; and one `entry` line per feedback
disposition, retry, or fix pushed during this skill's watch loop.

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
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
WORKSPACE_DIRNAME = ".babysit-pr"
LEDGER_FILENAME = "ledger.jsonl"

# Terminal results / dispositions this skill's own workflow (SKILL.md,
# "Diagnose CI and feedback") treats as a closed, non-repeatable action.
# `deferred` is deliberately excluded from the disposition set below: a
# deferred finding is preserved, not resolved, and recovery must still be able
# to see it as outstanding rather than treat it as done.
DEFAULT_COMPLETED_FEEDBACK_DISPOSITIONS = frozenset(
    {"fixed", "rejected", "not_applicable"}
)


def unit_key_for(repo: str, pr_number: int | str) -> str:
    """Compose the workspace key from repo + PR number.

    Mirrors `gh_pr_watch.default_state_file_for`'s own keying (case-folded
    repo, explicit PR number) so the two stores are trivially correlatable by
    a human or a script even though they live in different locations.
    """
    return f"{repo.lower()}#{pr_number}"


def slugify(value: str) -> str:
    """Derive a filesystem-safe workspace key from `owner/repo#number`."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    if not slug:
        raise ValueError(f"cannot derive a workspace slug from {value!r}")
    return slug.lower()


def workspace_dir(root: Path, repo: str, pr_number: int | str) -> Path:
    """Return the repo+PR-keyed workspace directory under `root`."""
    return Path(root) / WORKSPACE_DIRNAME / slugify(unit_key_for(repo, pr_number))


def ledger_path(root: Path, repo: str, pr_number: int | str) -> Path:
    return workspace_dir(root, repo, pr_number) / LEDGER_FILENAME


def ensure_workspace(root: Path, repo: str, pr_number: int | str) -> Path:
    """Create the workspace directory and self-exclude it from git.

    Writes a `.gitignore` containing `*` directly inside the workspace so it
    stays out of history regardless of where the ticket worktree sits — the
    workspace excludes itself rather than depending on the target
    repository's own `.gitignore`.
    """
    directory = workspace_dir(root, repo, pr_number)
    directory.mkdir(parents=True, exist_ok=True)
    gitignore = directory / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")
    return directory


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_line(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    line = json.dumps(record, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return record


def record_session_start(
    root: Path,
    repo: str,
    pr_number: int | str,
    *,
    session_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one session-identity line at the start of a session."""
    ensure_workspace(root, repo, pr_number)
    record = {
        "kind": "session",
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id or uuid.uuid4().hex,
        "started_at": now or _now_iso(),
    }
    return _append_line(ledger_path(root, repo, pr_number), record)


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
    ensure_workspace(root, repo, pr_number)
    record = {
        "kind": "entry",
        "schema_version": SCHEMA_VERSION,
        "item_id": str(item_id),
        "action": action,
        "terminal_result": terminal_result,
        "head_sha": head_sha,
        "evidence": evidence or {},
        "recorded_at": now or _now_iso(),
    }
    return _append_line(ledger_path(root, repo, pr_number), record)


@dataclass
class LedgerReadResult:
    sessions: list[dict[str, Any]] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)
    skipped_lines: list[int] = field(default_factory=list)


def read_ledger(root: Path, repo: str, pr_number: int | str) -> LedgerReadResult:
    """Parse the ledger, tolerating a malformed or partially written line.

    An append-only log can be interrupted mid-write (a crash, a killed
    process, a compaction boundary landing mid-flush); a partial trailing line
    must not make the rest of the ledger unreadable. Skipped line numbers are
    reported so a caller can decide whether to investigate, not silently lose
    them.
    """
    path = ledger_path(root, repo, pr_number)
    result = LedgerReadResult()
    if not path.exists():
        return result
    for lineno, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            result.skipped_lines.append(lineno)
            continue
        kind = record.get("kind")
        if kind == "session":
            result.sessions.append(record)
        elif kind == "entry":
            result.entries.append(record)
        else:
            result.skipped_lines.append(lineno)
    return result


def latest_entry(
    entries: Iterable[dict[str, Any]], item_id: str
) -> dict[str, Any] | None:
    """Return the most recent entry recorded for `item_id`, or None."""
    matches = [entry for entry in entries if entry.get("item_id") == str(item_id)]
    return matches[-1] if matches else None


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
    entry = latest_entry(entries, item_id)
    if (
        entry is not None
        and entry.get("action") == "feedback_disposition"
        and entry.get("terminal_result") in completed_dispositions
    ):
        return entry
    return None


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
    dispositioned = sorted(
        {
            entry.get("item_id")
            for entry in entries
            if entry.get("action") == "feedback_disposition"
            and entry.get("terminal_result") in DEFAULT_COMPLETED_FEEDBACK_DISPOSITIONS
            and entry.get("item_id")
        }
    )
    return {"retry_mismatches": mismatches, "dispositioned_feedback_ids": dispositioned}


def _load_watcher_module():
    """Load `gh_pr_watch.py` by path so this module never assumes CWD.

    Deferred to call time (rather than a module-level import) so unit tests
    can exercise `reconcile_with_watcher_state` against a plain dict without
    requiring the watcher module or its `fcntl` dependency to be importable
    in every test environment.
    """
    module_path = Path(__file__).resolve().parent / "gh_pr_watch.py"
    spec = importlib.util.spec_from_file_location("gh_pr_watch", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_watcher_state(repo: str, pr_number: int | str) -> dict[str, Any]:
    """Read the live watcher state file for this repo + PR, if any exists."""
    watcher = _load_watcher_module()
    state_path = watcher.default_state_file_for({"repo": repo, "number": pr_number})
    state, _ = watcher.load_state(state_path)
    return state


# --- CLI -------------------------------------------------------------------


def _parse_evidence(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--evidence-json must decode to a JSON object")
    return parsed


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
