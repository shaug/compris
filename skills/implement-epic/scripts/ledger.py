#!/usr/bin/env python3
"""Append-only, compaction-resilient ledger for `implement-epic`'s workspace.

See `references/ledger.md` for the workspace layout, ledger format, and
recovery rule this module implements. Summary: one workspace directory per
epic (the target unit), keyed by tracker + epic id so a resumed session finds
it deterministically; one append-only `ledger.jsonl` inside it; a `session`
line recorded once per session start; and one `entry` line per child-ticket
dispatch outcome. The ledger is orientation plus a dedup guard — live tracker,
git, and PR state remain the execution source of truth, exactly as
`implement-epic`'s own precedence rules already require. Recovery here means
answering "does the ledger already claim this child is done", not verifying
that claim against live state; the caller still owes that verification before
trusting it.

Usable as a library (`import ledger`) or as a CLI:

    python3 scripts/ledger.py session-start --epic github-119
    python3 scripts/ledger.py record --epic github-119 --child 133 \\
        --action child_dispatch --terminal-result ready_pr \\
        --head-sha 4f2c9a1d --evidence-json '{"pr": 181}'
    python3 scripts/ledger.py read --epic github-119
    python3 scripts/ledger.py find --epic github-119 --child 133

All paths are resolved relative to an explicit `--root` (defaulting to the
current working directory), never to this script's own installed location —
the workspace lives in the coordinator's working root, not inside the skill.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
WORKSPACE_DIRNAME = ".implement-epic"
LEDGER_FILENAME = "ledger.jsonl"

# Terminal results implement-epic's own child-verification step (SKILL.md,
# "Verify the terminal result") treats as forward progress rather than a stop.
# `blocked` is deliberately excluded: a blocked child is not done, and the
# recovery rule only guards against re-dispatching a completed unit.
DEFAULT_COMPLETED_TERMINAL_RESULTS = frozenset({"ready_pr", "ready_prs", "merged"})


def slugify(value: str) -> str:
    """Derive a filesystem-safe, case-insensitive workspace key.

    Keeps the slug readable (unlike a bare hash) so a resumed session or a
    human inspecting the worktree can tell which epic a workspace belongs to
    without decoding it.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    if not slug:
        raise ValueError(f"cannot derive a workspace slug from {value!r}")
    return slug.lower()


def workspace_dir(root: Path, epic_key: str) -> Path:
    """Return the epic-keyed workspace directory under `root`."""
    return Path(root) / WORKSPACE_DIRNAME / slugify(epic_key)


def ledger_path(root: Path, epic_key: str) -> Path:
    return workspace_dir(root, epic_key) / LEDGER_FILENAME


def ensure_workspace(root: Path, epic_key: str) -> Path:
    """Create the workspace directory and self-exclude it from git.

    Writes a `.gitignore` containing `*` directly inside the workspace so it
    stays out of history regardless of where the coordinator's working root
    happens to sit relative to any repository-level `.gitignore` — the
    workspace excludes itself rather than depending on external
    configuration.
    """
    directory = workspace_dir(root, epic_key)
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
    epic_key: str,
    *,
    session_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one session-identity line at the start of a session."""
    ensure_workspace(root, epic_key)
    record = {
        "kind": "session",
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id or uuid.uuid4().hex,
        "started_at": now or _now_iso(),
    }
    return _append_line(ledger_path(root, epic_key), record)


def record_entry(
    root: Path,
    epic_key: str,
    *,
    child_id: str,
    action: str,
    terminal_result: str | None = None,
    head_sha: str | None = None,
    evidence: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one per-child entry recording a dispatch outcome.

    `child_id` carries the child ticket's own tracker identity (e.g. a GitHub
    issue number or Linear identifier), not the epic's — the workspace is
    already keyed by the epic, so entries only need to disambiguate within it.
    """
    ensure_workspace(root, epic_key)
    record = {
        "kind": "entry",
        "schema_version": SCHEMA_VERSION,
        "child_id": str(child_id),
        "action": action,
        "terminal_result": terminal_result,
        "head_sha": head_sha,
        "evidence": evidence or {},
        "recorded_at": now or _now_iso(),
    }
    return _append_line(ledger_path(root, epic_key), record)


@dataclass
class LedgerReadResult:
    sessions: list[dict[str, Any]] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)
    skipped_lines: list[int] = field(default_factory=list)


def read_ledger(root: Path, epic_key: str) -> LedgerReadResult:
    """Parse the ledger, tolerating a malformed or partially written line.

    An append-only log can be interrupted mid-write (a crash, a killed
    process, a compaction boundary landing mid-flush); a partial trailing line
    must not make the rest of the ledger unreadable. Skipped line numbers are
    reported so a caller can decide whether to investigate, not silently lose
    them.
    """
    path = ledger_path(root, epic_key)
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
    entries: Iterable[dict[str, Any]], child_id: str
) -> dict[str, Any] | None:
    """Return the most recent entry recorded for `child_id`, or None."""
    matches = [entry for entry in entries if entry.get("child_id") == str(child_id)]
    return matches[-1] if matches else None


def already_recorded_complete(
    entries: Iterable[dict[str, Any]],
    child_id: str,
    completed_terminal_results: frozenset[str] = DEFAULT_COMPLETED_TERMINAL_RESULTS,
) -> dict[str, Any] | None:
    """Recovery-path dedup guard: the ledger's own claim, not live proof.

    Returns the latest entry for `child_id` when the ledger already records a
    completed terminal result for it, else None. This answers only what the
    ledger claims; `implement-epic`'s recovery rule still requires verifying
    that claim against live tracker/git/PR state before skipping a
    re-dispatch — a ledger entry alone is never sufficient.
    """
    entry = latest_entry(entries, child_id)
    if entry is not None and entry.get("terminal_result") in completed_terminal_results:
        return entry
    return None


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
        Path(args.root), args.epic, session_id=args.session_id
    )
    print(json.dumps(record, sort_keys=True))
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    record = record_entry(
        Path(args.root),
        args.epic,
        child_id=args.child,
        action=args.action,
        terminal_result=args.terminal_result,
        head_sha=args.head_sha,
        evidence=_parse_evidence(args.evidence_json),
    )
    print(json.dumps(record, sort_keys=True))
    return 0


def _cmd_read(args: argparse.Namespace) -> int:
    result = read_ledger(Path(args.root), args.epic)
    payload = {
        "sessions": result.sessions,
        "entries": result.entries,
        "skipped_lines": result.skipped_lines,
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


def _cmd_find(args: argparse.Namespace) -> int:
    result = read_ledger(Path(args.root), args.epic)
    entry = already_recorded_complete(result.entries, args.child)
    print(json.dumps(entry, sort_keys=True, indent=2) if entry else "null")
    return 0 if entry else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="coordinator working root the .implement-epic/ workspace lives under",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    session = subparsers.add_parser(
        "session-start", help="append a session-identity line"
    )
    session.add_argument("--epic", required=True, help="epic key, e.g. github-119")
    session.add_argument("--session-id", default=None)
    session.set_defaults(func=_cmd_session_start)

    record = subparsers.add_parser("record", help="append a per-child entry")
    record.add_argument("--epic", required=True)
    record.add_argument("--child", required=True, help="child ticket identity")
    record.add_argument("--action", required=True)
    record.add_argument("--terminal-result", default=None)
    record.add_argument("--head-sha", default=None)
    record.add_argument("--evidence-json", default=None)
    record.set_defaults(func=_cmd_record)

    read = subparsers.add_parser("read", help="print the parsed ledger as JSON")
    read.add_argument("--epic", required=True)
    read.set_defaults(func=_cmd_read)

    find = subparsers.add_parser(
        "find", help="print the ledger's completed entry for a child, if any"
    )
    find.add_argument("--epic", required=True)
    find.add_argument("--child", required=True)
    find.set_defaults(func=_cmd_find)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
