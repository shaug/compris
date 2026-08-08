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

The shared mechanics (workspace derivation and self-exclusion, append-only
JSON Lines I/O, the recovery-path dedup guard) live in `ledger_core.py`, a
byte-identical bundled copy of this repository's `ledger/core.py`, refreshed
by `just sync-contracts` — mirroring the same canonical-source-plus-bundled-
copy convention already used for the review lenses' shared contract. This
module fixes that shared core's generic parameters to this skill's own
vocabulary (`.carve-changesets/`, `changeset_slug`,
`converged`/`prs_open`/`chain_ready`/`all_merged`/`merged`) and adds the CLI.

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
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

WORKSPACE_DIRNAME = ".carve-changesets"
ID_FIELD = "changeset_slug"

# Terminal results this skill's own phase workflow (SKILL.md) treats as
# forward progress for one changeset. `blocked` is deliberately excluded: a
# blocked changeset is not done, and the recovery rule only guards against
# redoing work the ledger shows is already finished.
DEFAULT_COMPLETED_TERMINAL_RESULTS = frozenset(
    {"converged", "prs_open", "chain_ready", "all_merged", "merged"}
)


def _load_core():
    """Load the bundled `ledger_core.py` by path, matching this repository's
    own test-loader convention rather than assuming package-relative import
    resolution regardless of how this script is invoked."""
    core_path = Path(__file__).resolve().parent / "ledger_core.py"
    spec = importlib.util.spec_from_file_location("ledger_core", core_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


core = _load_core()

# Re-exported for callers/tests that reach for the shared primitives directly.
slugify = core.slugify
LedgerReadResult = core.LedgerReadResult


def workspace_dir(root: Path, source_branch: str) -> Path:
    return core.workspace_dir(root, WORKSPACE_DIRNAME, source_branch)


def ledger_path(root: Path, source_branch: str) -> Path:
    return core.ledger_path(root, WORKSPACE_DIRNAME, source_branch)


def ensure_workspace(root: Path, source_branch: str) -> Path:
    return core.ensure_workspace(root, WORKSPACE_DIRNAME, source_branch)


def record_session_start(
    root: Path,
    source_branch: str,
    *,
    session_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one session-identity line at the start of a session."""
    return core.record_session_start(
        root, WORKSPACE_DIRNAME, source_branch, session_id=session_id, now=now
    )


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
    return core.record_entry(
        root,
        WORKSPACE_DIRNAME,
        source_branch,
        id_field=ID_FIELD,
        id_value=changeset_slug,
        action=action,
        terminal_result=terminal_result,
        head_sha=head_sha,
        evidence=evidence,
        now=now,
    )


def read_ledger(root: Path, source_branch: str):
    """Parse the ledger, tolerating a malformed or partially written line."""
    return core.read_ledger(root, WORKSPACE_DIRNAME, source_branch)


def latest_entry(entries, changeset_slug: str) -> dict[str, Any] | None:
    """Return the most recent entry recorded for `changeset_slug`, or None."""
    return core.latest_entry(entries, ID_FIELD, changeset_slug)


def already_recorded_complete(
    entries,
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
    return core.already_recorded_complete(
        entries, ID_FIELD, changeset_slug, completed_terminal_results
    )


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
