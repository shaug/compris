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

The shared mechanics (workspace derivation and self-exclusion, append-only
JSON Lines I/O, the recovery-path dedup guard) live in `ledger_core.py`, a
byte-identical bundled copy of this repository's `ledger/core.py`, refreshed
by `just sync-contracts` — mirroring the same canonical-source-plus-bundled-
copy convention already used for the review lenses' shared contract. This
module fixes that shared core's generic parameters to this skill's own
vocabulary (`.implement-epic/`, `child_id`, `ready_pr`/`ready_prs`/`merged`)
and adds the CLI.

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
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

WORKSPACE_DIRNAME = ".implement-epic"
ID_FIELD = "child_id"

# Terminal results implement-epic's own child-verification step (SKILL.md,
# "Verify the terminal result") treats as forward progress rather than a stop.
# `blocked` is deliberately excluded: a blocked child is not done, and the
# recovery rule only guards against re-dispatching a completed unit.
DEFAULT_COMPLETED_TERMINAL_RESULTS = frozenset({"ready_pr", "ready_prs", "merged"})


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


def unit_key_for(epic_key: str) -> str:
    """Compose the workspace key from the epic key.

    `slugify` collapses any run of non-identifier characters — including `/`
    — to a single `-`, which would otherwise let two distinct epic
    identities alias onto the same slug purely by where such a character
    happens to fall. `core.collision_safe_digest` breaks that collision — the
    same fix `carve-changesets`'s and `babysit-pr`'s own `unit_key_for`
    already apply to their identically-shaped keying, for the identical
    reason.
    """
    return f"{epic_key}#{core.collision_safe_digest(epic_key)}"


def workspace_dir(root: Path, epic_key: str) -> Path:
    return core.workspace_dir(root, WORKSPACE_DIRNAME, unit_key_for(epic_key))


def ledger_path(root: Path, epic_key: str) -> Path:
    return core.ledger_path(root, WORKSPACE_DIRNAME, unit_key_for(epic_key))


def ensure_workspace(root: Path, epic_key: str) -> Path:
    return core.ensure_workspace(root, WORKSPACE_DIRNAME, unit_key_for(epic_key))


def record_session_start(
    root: Path, epic_key: str, *, session_id: str | None = None, now: str | None = None
) -> dict[str, Any]:
    """Append one session-identity line at the start of a session."""
    return core.record_session_start(
        root, WORKSPACE_DIRNAME, unit_key_for(epic_key), session_id=session_id, now=now
    )


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
    return core.record_entry(
        root,
        WORKSPACE_DIRNAME,
        unit_key_for(epic_key),
        id_field=ID_FIELD,
        id_value=child_id,
        action=action,
        terminal_result=terminal_result,
        head_sha=head_sha,
        evidence=evidence,
        now=now,
    )


def read_ledger(root: Path, epic_key: str):
    """Parse the ledger, tolerating a malformed or partially written line."""
    return core.read_ledger(root, WORKSPACE_DIRNAME, unit_key_for(epic_key))


def latest_entry(entries, child_id: str) -> dict[str, Any] | None:
    """Return the most recent entry recorded for `child_id`, or None."""
    return core.latest_entry(entries, ID_FIELD, child_id)


def already_recorded_complete(
    entries,
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
    return core.already_recorded_complete(
        entries, ID_FIELD, child_id, completed_terminal_results
    )


# --- CLI -------------------------------------------------------------------

# Re-exported for the CLI below and for callers/tests that reach for it
# directly.
_parse_evidence = core.parse_evidence_json


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
