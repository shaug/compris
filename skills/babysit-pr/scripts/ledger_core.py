#!/usr/bin/env python3
"""Canonical core for every skill's compaction-resilient ledger.

This is the single source of truth for the mechanics shared by
`implement-epic`, `carve-changesets`, and `babysit-pr`'s compaction ledgers:
workspace derivation and self-exclusion, append-only JSON Lines I/O, and the
recovery-path dedup guard. `just sync-contracts` copies this file byte-for-byte
into each of the three skills as `scripts/ledger_core.py`, mirroring the
existing `review-suite/` → bundled-copy convention this repository already
uses for the review lenses' shared contract — a skill installed standalone
outside this monorepo still needs its own copy, so this is copied rather than
imported across skill boundaries.

Each consuming skill's own `scripts/ledger.py` is a thin, skill-specific
wrapper: it fixes this module's generic parameters (the workspace dirname, the
per-entry identity field name, that skill's own completed-terminal-results
vocabulary, and its own CLI flag names/help text) and adds whatever is
genuinely skill-specific — `carve-changesets`'s chain-order semantics live in
its `SKILL.md`, not here; `babysit-pr`'s watcher-state reconciliation
(`reconcile_with_watcher_state`, `load_watcher_state`) has no analog in the
other two skills and stays in its own `ledger.py`.

See each skill's `references/ledger.md` for the workspace layout, ledger
format, and recovery rule this module implements.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA_VERSION = 1
LEDGER_FILENAME = "ledger.jsonl"


def collision_safe_digest(value: str) -> str:
    """Return an 8-hex-digit sha256 digest of `value`.

    Every skill's `unit_key_for` folds this into its workspace key before
    slugifying, because `slugify` collapses any run of non-identifier
    characters — including `/`, common in branch names and `owner/repo`
    strings — to a single `-`, which would otherwise let two distinct unit
    identities alias onto the same slug purely by where such a character
    happens to fall. Centralized here (rather than each skill hand-writing
    the same formula) so the collision-avoidance guarantee depends on one
    maintained implementation, not three independently kept in sync —
    mirroring `gh_pr_watch.default_state_file_for`'s own pre-existing use of
    the identical formula for the identical reason.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def parse_evidence_json(raw: str | None) -> dict[str, Any]:
    """Decode a CLI `--evidence-json` argument into a JSON object.

    Shared by every skill's CLI `record` subcommand: `None` (the flag was
    omitted) becomes `{}`; otherwise the raw string must decode to a JSON
    object, or a `ValueError` names the requirement.
    """
    if raw is None:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--evidence-json must decode to a JSON object")
    return parsed


def slugify(value: str) -> str:
    """Derive a filesystem-safe, case-insensitive workspace key.

    Keeps the slug readable (unlike a bare hash) so a resumed session or a
    human inspecting the worktree can tell which unit a workspace belongs to
    without decoding it. Collapses any run of non-identifier characters
    (including `/`, common in branch names and `owner/repo#number` keys) to a
    single `-`.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    if not slug:
        raise ValueError(f"cannot derive a workspace slug from {value!r}")
    return slug.lower()


def workspace_dir(root: Path, workspace_dirname: str, unit_key: str) -> Path:
    """Return the unit-keyed workspace directory under `root`."""
    return Path(root) / workspace_dirname / slugify(unit_key)


def ledger_path(root: Path, workspace_dirname: str, unit_key: str) -> Path:
    return workspace_dir(root, workspace_dirname, unit_key) / LEDGER_FILENAME


def ensure_workspace(root: Path, workspace_dirname: str, unit_key: str) -> Path:
    """Create the workspace directory and self-exclude it from git.

    Writes a `.gitignore` containing `*` directly inside the workspace so it
    stays out of history regardless of where the workspace happens to sit
    relative to any repository-level `.gitignore` — the workspace excludes
    itself rather than depending on external configuration.
    """
    directory = workspace_dir(root, workspace_dirname, unit_key)
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
    workspace_dirname: str,
    unit_key: str,
    *,
    session_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one session-identity line at the start of a session."""
    ensure_workspace(root, workspace_dirname, unit_key)
    record = {
        "kind": "session",
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id or uuid.uuid4().hex,
        "started_at": now or _now_iso(),
    }
    return _append_line(ledger_path(root, workspace_dirname, unit_key), record)


def record_entry(
    root: Path,
    workspace_dirname: str,
    unit_key: str,
    *,
    id_field: str,
    id_value: str,
    action: str,
    terminal_result: str | None = None,
    head_sha: str | None = None,
    evidence: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Append one per-unit entry under the field name the caller supplies.

    `id_field` names the entry's own identity field (`child_id`,
    `changeset_slug`, `item_id`, ...) so each skill's own ledger reads exactly
    the vocabulary its `references/ledger.md` documents, even though this
    function is shared.
    """
    ensure_workspace(root, workspace_dirname, unit_key)
    record = {
        "kind": "entry",
        "schema_version": SCHEMA_VERSION,
        id_field: str(id_value),
        "action": action,
        "terminal_result": terminal_result,
        "head_sha": head_sha,
        "evidence": evidence or {},
        "recorded_at": now or _now_iso(),
    }
    return _append_line(ledger_path(root, workspace_dirname, unit_key), record)


@dataclass
class LedgerReadResult:
    sessions: list[dict[str, Any]] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)
    skipped_lines: list[int] = field(default_factory=list)


def read_ledger(root: Path, workspace_dirname: str, unit_key: str) -> LedgerReadResult:
    """Parse the ledger, tolerating a malformed or partially written line.

    An append-only log can be interrupted mid-write (a crash, a killed
    process, a compaction boundary landing mid-flush); a partial trailing line
    must not make the rest of the ledger unreadable. Skipped line numbers are
    reported so a caller can decide whether to investigate, not silently lose
    them.
    """
    path = ledger_path(root, workspace_dirname, unit_key)
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


def already_recorded_complete(
    entries: Iterable[dict[str, Any]],
    id_field: str,
    id_value: str,
    completed_terminal_results: frozenset[str],
    *,
    action_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any] | None:
    """Recovery-path dedup guard: the ledger's own claim, not live proof.

    Returns the latest entry matching both `id_value` and (when supplied)
    `action_filter`, when it records a terminal result the caller treats as
    complete, else None. `action_filter` scopes the search itself — not just
    a check on whichever entry happens to be globally latest for `id_value` —
    because a unit accumulates one entry per phase as it progresses (a
    `carve-changesets` changeset gets `review_fix_loop`, then `publish`, then
    `merge` entries; a `babysit-pr` feedback item's `item_id` space can also
    carry `retry`/`fix_pushed` entries). Without scoping the search itself, a
    later entry from a *different* phase or action would mask an earlier
    completed one purely by being more recent, causing needless re-work on
    resume — filtering only the already-selected latest entry does not fix
    this, since the correct answer may be an earlier entry the naive latest
    lookup skipped past. `babysit-pr` uses this to require
    `action == "feedback_disposition"` so a `retry` or `fix_pushed` entry
    sharing the same `item_id` space never satisfies the disposition guard;
    `carve-changesets` scopes to one of `review_fix_loop`/`publish`/`merge`
    per phase. This answers only what the ledger claims; the caller still
    must verify that claim against live state before trusting it — a ledger
    entry alone is never sufficient.
    """
    matches = [entry for entry in entries if entry.get(id_field) == str(id_value)]
    if action_filter is not None:
        matches = [entry for entry in matches if action_filter(entry)]
    if not matches:
        return None
    entry = matches[-1]
    if entry.get("terminal_result") in completed_terminal_results:
        return entry
    return None
