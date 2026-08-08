# Compaction-resilient ledger

`.implement-epic/` already holds the per-child brief and report files
[Run the graph loop](../SKILL.md#run-the-graph-loop) describes. This ledger is a
third artifact in that same workspace: a durable, machine-readable record of
what each session already dispatched and what it got back, so a session resumed
after a compaction, a crash, or a fresh context does not have to reconstruct
that history from recollection or from re-reading every brief and report file in
full.

## Workspace layout

The workspace is keyed by the epic being orchestrated this run — a tracker
prefix plus its id, for example `github-119` or `linear-eng-119`. `unit_key_for`
folds an 8-hex-digit digest of the exact epic key into the key before
slugifying, because slugifying alone collapses any `/` or other punctuation an
epic key might contain to a single `-`, which could otherwise let two distinct
epic identities alias onto the same slug. With the digest, a resumed session
finds the prior workspace deterministically without guessing a path, and two
distinct epics can never collide on one:

```text
.implement-epic/
  github-119-3c59fbe3/
    ledger.jsonl
    .gitignore          # written by ensure_workspace(); contains "*"
    brief-133.md
    report-133.md
    brief-134.md
    report-134.md
```

(`3c59fbe3` above is `sha256("github-119")`'s first 8 hex digits — deterministic
for that exact epic key, so the same epic always produces the same workspace
path.)

`scripts/ledger.py` derives this path from `(root, epic_key)` via
`workspace_dir`/`ledger_path`, composing `unit_key_for(epic_key)` and slugifying
the result, and creates the directory plus its own self-excluding `.gitignore`
the first time anything is recorded (`ensure_workspace`). The brief/report
naming and per-child pairing are unchanged from
[Run the graph loop](../SKILL.md#run-the-graph-loop); only the containing
directory moves from the workspace root to the epic-keyed subdirectory, and the
ledger lives beside them.

## Ledger format

`ledger.jsonl` is append-only JSON Lines — one JSON object per line, never
rewritten or truncated. Two kinds of line:

- **`session`**: written once at the start of a session that will dispatch or
  verify work for this epic.

  ```json
  {"kind": "session", "schema_version": 1, "session_id": "<opaque>", "started_at": "2026-08-07T22:10:00Z"}
  ```

- **`entry`**: written once per child-dispatch outcome — after
  [Verify the terminal result](../SKILL.md#4-verify-the-terminal-result)
  confirms what `implement-ticket` actually returned, not before.

  ```json
  {
    "kind": "entry",
    "schema_version": 1,
    "child_id": "133",
    "action": "child_dispatch",
    "terminal_result": "ready_pr",
    "head_sha": "4f2c9a1d",
    "evidence": {"pr": 181, "repo": "shaug/compris"},
    "recorded_at": "2026-08-07T22:41:12Z"
  }
  ```

  `child_id` is the child ticket's own tracker identity — a GitHub issue number
  or Linear identifier — not the epic's; the workspace is already keyed by the
  epic, so entries only need to disambiguate within it. `terminal_result` is
  `implement-ticket`'s own returned state (`ready_pr`, `ready_prs`, `merged`,
  `blocked`, or `requires_epic`) or `null` for an entry recorded before a
  terminal result exists. `evidence` carries whatever identifiers let a later
  reader verify the claim against live state — PR number, merge SHA, tracker
  transition outcome — never a substitute for that verification.

Record one `session` line per session, then one `entry` line per verified child
result — append after verification, not before dispatch, so a mid-dispatch
interruption never leaves a false completion claim in the ledger.

## Recovery rule

On resume, or after a context compaction, trust the ledger plus live
tracker/git/PR state over recollection. Read the ledger for the epic key before
reading old graph-loop iterations from memory:

1. Read `.implement-epic/<epic-key>-<digest>/ledger.jsonl` with `read_ledger` —
   the same `slugify(unit_key_for(epic_key))` workspace path shown in
   [Workspace layout](#workspace-layout) above.
2. For each candidate child, call
   `already_recorded_complete(entries, child_id)`. This is a **dedup guard, not
   proof**: it returns the ledger's own latest claim, filtered to the terminal
   results
   [Verify the terminal result](../SKILL.md#4-verify-the-terminal-result) treats
   as forward progress (`ready_pr`, `ready_prs`, `merged`) — `blocked` never
   counts as complete, so a blocked child is never suppressed from re-selection
   by this guard alone.
3. Verify that claim against live state before trusting it: the PR is still
   open/merged as recorded, the tracker reflects the recorded transition, and
   the recorded head SHA is represented on the base when the claim is `merged`.
   This is the same verification
   [Verify the terminal result](../SKILL.md#4-verify-the-terminal-result)
   already requires for a freshly returned result; the ledger only tells this
   session where to look, it does not replace the look.
4. Never re-dispatch a child whose completed terminal result is ledger-recorded
   and verified against live state. A ledger claim that fails live verification
   is stale, not authoritative — treat the child as unresolved and let the
   ordinary graph-loop selection in
   [Select one child](../SKILL.md#2-select-one-child) decide what happens next,
   exactly as it would for a child this session never touched.

The ledger is orientation plus a dedup guard; live remote state remains the
execution source of truth, unchanged from every other precedence rule this skill
already states. It does not replace
[Verify the terminal result](../SKILL.md#4-verify-the-terminal-result) or
[Refresh or stop at the requested boundary](../SKILL.md#5-refresh-or-stop-at-the-requested-boundary),
and it is never itself acceptance, delivery, or closeout evidence.

## Helper reference

`scripts/ledger.py` (unittest-covered in `scripts/tests/test_ledger.py`)
provides both a library API and a CLI. Its shared mechanics — workspace
derivation and self-exclusion, append-only JSON Lines I/O, and the recovery-path
dedup guard — live in `scripts/ledger_core.py`, a bundled, byte-identical copy
of this repository's own `ledger/core.py` kept in sync by `just sync-contracts`,
the same canonical-source-plus-bundled-copy convention already used for the
review lenses' shared contract. `ledger.py` itself is a thin wrapper fixing that
core to this skill's own vocabulary (`.implement-epic/`, `child_id`,
`ready_pr`/`ready_prs`/`merged`):

```bash
python3 scripts/ledger.py session-start --epic github-119
python3 scripts/ledger.py record --epic github-119 --child 133 \
  --action child_dispatch --terminal-result ready_pr \
  --head-sha 4f2c9a1d --evidence-json '{"pr": 181}'
python3 scripts/ledger.py read --epic github-119
python3 scripts/ledger.py find --epic github-119 --child 133   # exit 0 iff complete
```

Pass `--root <coordinator-working-root>` when not invoking from that directory;
every path is resolved from it, never from this script's own installed location.
