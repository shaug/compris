# Compaction-resilient ledger

`.carve-changesets/plan.json` is the ephemeral proposal truth for changesets not
yet materialized (`references/plan-schema.md`). This ledger is a separate,
append-only record of what has already happened to each materialized changeset —
reviewed, published, merged — so a session resumed after a compaction, a crash,
or a fresh context does not have to replay `review-fix-loop` or re-open a PR for
a changeset it already finished.

## Workspace layout

The workspace is keyed by the source branch being carved, so a resumed session
finds the prior workspace deterministically without guessing a path:

```text
.carve-changesets/
  plan.json                              # unchanged: the ephemeral proposal
  feature-cloud-host-migration/
    ledger.jsonl
    .gitignore                           # written by ensure_workspace(); contains "*"
```

`scripts/ledger.py` derives this path from `(root, source_branch)` via
`workspace_dir`/`ledger_path`, slugifying the branch name (`/` becomes `-`) so
it is a safe single path component, and creates the directory plus its own
self-excluding `.gitignore` the first time anything is recorded
(`ensure_workspace`). `.carve-changesets/` itself is already required to be
ignored by the consuming repository — `scripts/preflight.py` fails closed
otherwise — so this workspace's own `.gitignore` is a second, self-contained
guarantee, not a replacement for that check.

## Ledger format

`ledger.jsonl` is append-only JSON Lines — one JSON object per line, never
rewritten or truncated. Two kinds of line:

- **`session`**: written once at the start of a session that will materialize,
  review, publish, or merge changesets for this source branch.

  ```json
  {"kind": "session", "schema_version": 1, "session_id": "<opaque>", "started_at": "2026-08-07T22:10:00Z"}
  ```

- **`entry`**: written once per changeset action, after the action's own
  terminal result is known — a `review-fix-loop` `converged` result from
  [Materialize and prove equivalence](../SKILL.md#2-materialize-and-prove-equivalence),
  a `babysit-pr` result from [Publish](../SKILL.md#3-publish), or a merge
  outcome from [Merge and propagate](../SKILL.md#4-merge-and-propagate).

  ```json
  {
    "kind": "entry",
    "schema_version": 1,
    "changeset_slug": "rename-config-types",
    "action": "review_fix_loop",
    "terminal_result": "converged",
    "head_sha": "4f2c9a1d",
    "evidence": {"base": "7be044c2"},
    "recorded_at": "2026-08-07T22:41:12Z"
  }
  ```

  `changeset_slug` is the plan's own `slug` field (`references/plan-schema.md`),
  already carried into commit trailers and PR titles — using it here means a
  ledger entry lines up with live git and GitHub state without a translation
  step. `action` names which phase produced the entry (`review_fix_loop`,
  `publish`, `merge`); `terminal_result` is that phase's own returned state
  (`converged`, `prs_open`, `all_merged`, `blocked`, and so on). `evidence`
  carries whatever identifiers let a later reader verify the claim against live
  state — the comparison base, the PR number, the merge SHA — never a substitute
  for that verification.

Record one `session` line per session, then one `entry` line per verified
changeset outcome — append after verification, not before starting the phase, so
an interrupted phase never leaves a false completion claim in the ledger.

## Recovery rule

On resume, or after a context compaction, trust the ledger plus live git/GitHub
state over recollection. Read the ledger for the source branch before assuming
which changesets already converged, published, or merged:

1. Read `.carve-changesets/<source-branch-slug>/ledger.jsonl` with
   `read_ledger`.
2. For each changeset in the plan, call
   `already_recorded_complete(entries, changeset_slug)`. This is a **dedup
   guard, not proof**: it returns the ledger's own latest claim, filtered to the
   terminal results this skill's phase workflow treats as forward progress
   (`converged`, `chain_ready`, `prs_open`, `all_merged`, `merged`) — `blocked`
   never counts as complete, so a blocked changeset is never suppressed from a
   fresh attempt by this guard alone.
3. Verify that claim against live state before trusting it: the materialized
   branch still exists with the recorded head, the PR is open or merged as
   recorded, and the merged position is represented on the base when the claim
   covers a merge. This is the same verification
   [Merge and propagate](../SKILL.md#4-merge-and-propagate) and
   [Return one terminal handoff](../SKILL.md#return-one-terminal-handoff)
   already require; the ledger only tells this session where to look, it does
   not replace the look.
4. Never re-run `review-fix-loop`, republish, or re-merge a changeset whose
   completed terminal result is ledger-recorded and verified against live state.
   A ledger claim that fails live verification is stale, not authoritative —
   treat the changeset as unresolved and let the ordinary phase workflow decide
   what happens next, exactly as it would for a changeset this session never
   touched.

The ledger is orientation plus a dedup guard; live git and GitHub state remain
the execution source of truth, unchanged from every other precedence rule this
skill already states — "stronger live truth conflicts with the plan or other
weaker records" in [Stop conditions](../SKILL.md#stop-conditions) applies to the
ledger exactly as it applies to `plan.json`. It never overrides
`.carve-changesets/plan.json` for an unmaterialized changeset, and it is never
itself equivalence, review, or merge evidence.

## Helper reference

`scripts/ledger.py` (unittest-covered in `scripts/tests/test_ledger.py`)
provides both a library API and a CLI. Its shared mechanics — workspace
derivation and self-exclusion, append-only JSON Lines I/O, and the recovery-path
dedup guard — live in `scripts/ledger_core.py`, a bundled, byte-identical copy
of this repository's own `ledger/core.py` kept in sync by `just sync-contracts`,
the same canonical-source-plus-bundled-copy convention already used for the
review lenses' shared contract. `ledger.py` itself is a thin wrapper fixing that
core to this skill's own vocabulary (`.carve-changesets/`, `changeset_slug`,
`converged`/`prs_open`/`chain_ready`/`all_merged`/`merged`):

```bash
python3 scripts/ledger.py session-start --source feature/cloud-host-migration
python3 scripts/ledger.py record \
  --source feature/cloud-host-migration --changeset rename-config-types \
  --action review_fix_loop --terminal-result converged --head-sha 4f2c9a1d
python3 scripts/ledger.py read --source feature/cloud-host-migration
python3 scripts/ledger.py find \
  --source feature/cloud-host-migration --changeset rename-config-types
```

Pass `--root <repository-root>` when not invoking from that directory; every
path is resolved from it, never from this script's own installed location.
