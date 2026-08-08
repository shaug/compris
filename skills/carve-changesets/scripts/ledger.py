#!/usr/bin/env python3
"""Append-only, compaction-resilient ledger for `carve-changesets`'s workspace.

See `references/ledger.md` for the workspace layout, ledger format, and
recovery rule this module implements. Summary: one workspace directory per
source branch (the target unit) under `.carve-changesets/`, keyed so a resumed
session finds it deterministically; one append-only `ledger.jsonl` inside it; a
`session` line recorded once per session start; and one `entry` line per
changeset's review/publish/merge action. The ledger is orientation plus a
dedup guard — `.carve-changesets/plan.json`, live git, and live GitHub state
remain the execution source of truth exactly as this skill's own precedence
rules already require (`references/SPEC.md`: "stronger live truth conflicts
with the plan or other weaker records"). This module never reads or writes
`plan.json`; it only tracks what has already happened to each materialized
changeset.

Usable as a library (`import ledger`) or as a CLI:

    python3 scripts/ledger.py session-start --source feature/cloud-host-migration
    python3 scripts/ledger.py record \\
        --source feature/cloud-host-migration --changeset rename-config-types \\
        --action review_fix_loop --terminal-result converged \\
        --head-sha 4f2c9a1d
    python3 scripts/ledger.py read --source feature/cloud-host-migration
    python3 scripts/ledger.py find \\
        --source feature/cloud-host-migration --changeset rename-config-types

All paths are resolved relative to an explicit `--root` (defaulting to the
current working directory) so the workspace sits beside `.carve-changesets/`
in the repository being carved, not inside this installed skill.
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
WORKSPACE_DIRNAME = ".carve-changesets"
LEDGER_FILENAME = "ledger.jsonl"

# Terminal results this skill's own phase workflow (SKILL.md) treats as
# forward progress for one changeset. `blocked` is deliberately excluded: a
# blocked changeset is not done, and the recovery rule only guards against
# redoing work the ledger shows is already finished.
DEFAULT_COMPLETED_TERMINAL_RESULTS = frozenset(
    {"converged", "prs_open", "chain_ready", "all_merged", "merged"}
)


def slugify(value: str) -> str:
    """Derive a filesystem-safe workspace key from a branch name.

    A source branch name commonly contains `/`, which is not a safe path
    segment; this collapses any run of non-identifier characters to `-` so
    `feature/cloud-host-migration` and similar names produce one clean,
    readable directory component.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    if not slug:
        raise ValueError(f"cannot derive a workspace slug from {value!r}")
    return slug.lower()


def workspace_dir(root: Path, source_branch: str) -> Path:
    """Return the source-branch-keyed workspace directory under `root`."""
    return Path(root) / WORKSPACE_DIRNAME / slugify(source_branch)


def ledger_path(root: Path, source_branch: str) -> Path:
    return workspace_dir(root, source_branch) / LEDGER_FILENAME


def ensure_workspace(root: Path, source_branch: str) -> Path:
    """Create the workspace directory and self-exclude it from git.

    `.carve-changesets/` is already required to be ignored by the consuming
    repository (`scripts/preflight.py` fails closed otherwise); this adds a
    second, self-contained `.gitignore` directly inside the per-branch
    workspace so the ledger stays excluded even when that outer check is
    bypassed or the workspace is copied elsewhere.
    """
    directory = workspace_dir(root, source_branch)
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
    source_branch: str,
    *,
    session_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one session-identity line at the start of a session."""
    ensure_workspace(root, source_branch)
    record = {
        "kind": "session",
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id or uuid.uuid4().hex,
        "started_at": now or _now_iso(),
    }
    return _append_line(ledger_path(root, source_branch), record)


def record_entry(
    root: Path,
    source_branch: str,
    *,
    changeset_slug: str,
    action: str,
    terminal_result: str | None = None,
    head_sha: str | None = None,
    evidence: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one per-changeset entry recording a review/publish/merge action.

    `changeset_slug` is the plan's own `slug` field, carried into commit and
    PR metadata by `references/plan-schema.md` — the same stable identifier
    already used elsewhere, so ledger entries line up with live trailers and
    PR titles without a translation step.
    """
    ensure_workspace(root, source_branch)
    record = {
        "kind": "entry",
        "schema_version": SCHEMA_VERSION,
        "changeset_slug": str(changeset_slug),
        "action": action,
        "terminal_result": terminal_result,
        "head_sha": head_sha,
        "evidence": evidence or {},
        "recorded_at": now or _now_iso(),
    }
    return _append_line(ledger_path(root, source_branch), record)


@dataclass
class LedgerReadResult:
    sessions: list[dict[str, Any]] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)
    skipped_lines: list[int] = field(default_factory=list)


def read_ledger(root: Path, source_branch: str) -> LedgerReadResult:
    """Parse the ledger, tolerating a malformed or partially written line.

    An append-only log can be interrupted mid-write (a crash, a killed
    process, a compaction boundary landing mid-flush); a partial trailing line
    must not make the rest of the ledger unreadable. Skipped line numbers are
    reported so a caller can decide whether to investigate, not silently lose
    them.
    """
    path = ledger_path(root, source_branch)
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
    entries: Iterable[dict[str, Any]], changeset_slug: str
) -> dict[str, Any] | None:
    """Return the most recent entry recorded for `changeset_slug`, or None."""
    matches = [
        entry for entry in entries if entry.get("changeset_slug") == str(changeset_slug)
    ]
    return matches[-1] if matches else None


def already_recorded_complete(
    entries: Iterable[dict[str, Any]],
    changeset_slug: str,
    completed_terminal_results: frozenset[str] = DEFAULT_COMPLETED_TERMINAL_RESULTS,
) -> dict[str, Any] | None:
    """Recovery-path dedup guard: the ledger's own claim, not live proof.

    Returns the latest entry for `changeset_slug` when the ledger already
    records a completed terminal result for it, else None. This answers only
    what the ledger claims; the caller still must verify it against live git
    and GitHub state (materialized branch, correct ancestry, merged PR) before
    skipping re-review or re-publication of that changeset.
    """
    entry = latest_entry(entries, changeset_slug)
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
        Path(args.root), args.source, session_id=args.session_id
    )
    print(json.dumps(record, sort_keys=True))
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    record = record_entry(
        Path(args.root),
        args.source,
        changeset_slug=args.changeset,
        action=args.action,
        terminal_result=args.terminal_result,
        head_sha=args.head_sha,
        evidence=_parse_evidence(args.evidence_json),
    )
    print(json.dumps(record, sort_keys=True))
    return 0


def _cmd_read(args: argparse.Namespace) -> int:
    result = read_ledger(Path(args.root), args.source)
    payload = {
        "sessions": result.sessions,
        "entries": result.entries,
        "skipped_lines": result.skipped_lines,
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


def _cmd_find(args: argparse.Namespace) -> int:
    result = read_ledger(Path(args.root), args.source)
    entry = already_recorded_complete(result.entries, args.changeset)
    print(json.dumps(entry, sort_keys=True, indent=2) if entry else "null")
    return 0 if entry else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="repository root the .carve-changesets/ workspace lives under",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    session = subparsers.add_parser(
        "session-start", help="append a session-identity line"
    )
    session.add_argument(
        "--source", required=True, help="source branch, e.g. feature/x"
    )
    session.add_argument("--session-id", default=None)
    session.set_defaults(func=_cmd_session_start)

    record = subparsers.add_parser("record", help="append a per-changeset entry")
    record.add_argument("--source", required=True)
    record.add_argument(
        "--changeset", required=True, help="changeset slug from the plan"
    )
    record.add_argument("--action", required=True)
    record.add_argument("--terminal-result", default=None)
    record.add_argument("--head-sha", default=None)
    record.add_argument("--evidence-json", default=None)
    record.set_defaults(func=_cmd_record)

    read = subparsers.add_parser("read", help="print the parsed ledger as JSON")
    read.add_argument("--source", required=True)
    read.set_defaults(func=_cmd_read)

    find = subparsers.add_parser(
        "find", help="print the ledger's completed entry for a changeset, if any"
    )
    find.add_argument("--source", required=True)
    find.add_argument("--changeset", required=True)
    find.set_defaults(func=_cmd_find)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
