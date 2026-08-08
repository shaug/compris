# Compaction-resilient ledger

`scripts/gh_pr_watch.py` already persists its own state — seen-feedback IDs and
per-head retry counts — but that state file lives outside the repository, under
the system temp directory (`default_state_directory`/ `default_state_file_for`),
keyed only by repository and PR number. It records *that* the watcher observed
something, not *what this skill decided to do about it*. This ledger is a
second, repository-local store for that decision: which feedback item got which
disposition, which retry was spent and why, which commit fixed what — so a
session resumed after a compaction, a crash, or a fresh context recovers those
decisions without re-reading transcript history, and without re-dispositioning a
finding or re-spending a retry the prior session already accounted for.

The two stores are never merged and neither is authoritative over the other for
what it alone tracks: the watcher state file remains authoritative for
retry-*budget enforcement* (`gh_pr_watch.current_retry_count` refuses a retry
beyond the configured maximum regardless of what this ledger says), and this
ledger remains the only record of *disposition* — the watcher has no concept of
"fixed" versus "rejected" versus "deferred". `reconcile_with_watcher_state`
below compares the two only to surface drift between them, never to override
either.

## Workspace layout

The workspace is keyed by repository and PR number, mirroring
`gh_pr_watch.default_state_file_for`'s own keying, so a resumed session finds
the prior workspace deterministically without guessing a path:

```text
.babysit-pr/
  example-project-482/
    ledger.jsonl
    .gitignore          # written by ensure_workspace(); contains "*"
```

`scripts/ledger.py` derives this path from `(root, repo, pr_number)` via
`workspace_dir`/`ledger_path`, and creates the directory plus its own
self-excluding `.gitignore` the first time anything is recorded
(`ensure_workspace`). The workspace lives in the ticket's own worktree (the
`root` this skill was invoked against), not inside this installed skill.

## Ledger format

`ledger.jsonl` is append-only JSON Lines — one JSON object per line, never
rewritten or truncated. Two kinds of line:

- **`session`**: written once at the start of a session that will watch,
  diagnose, or fix this PR.

  ```json
  {"kind": "session", "schema_version": 1, "session_id": "<opaque>", "started_at": "2026-08-07T22:10:00Z"}
  ```

- **`entry`**: written once per feedback disposition, retry, or fix — after
  [Diagnose CI and feedback](../SKILL.md#diagnose-ci-and-feedback) or
  [Delegate repository review and remediation](../SKILL.md#delegate-repository-review-and-remediation)
  confirms the outcome, not before acting.

  ```json
  {
    "kind": "entry",
    "schema_version": 1,
    "item_id": "review-comment-9001",
    "action": "feedback_disposition",
    "terminal_result": "fixed",
    "head_sha": "4f2c9a1d",
    "evidence": {"disposition": "fixed", "reply_url": "https://github.com/.../c9001"},
    "recorded_at": "2026-08-07T22:41:12Z"
  }
  ```

  `item_id` names what the entry is about, and its shape depends on `action`:

  | `action`               | `item_id` names                                                                             | `terminal_result` vocabulary                      |
  | ---------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------- |
  | `feedback_disposition` | the review comment/thread id being dispositioned                                            | `fixed`, `rejected`, `not_applicable`, `deferred` |
  | `retry`                | the exact head SHA the retry ran against (matches `gh_pr_watch`'s own `retries_by_sha` key) | `rerun`, or the diagnosed classification          |
  | `fix_pushed`           | the new commit SHA                                                                          | `pushed`                                          |

  `evidence` carries whatever identifiers let a later reader verify the claim
  against live state — the reply URL, the diagnosed run id, the commit — never a
  substitute for that verification.

Record one `session` line per session, then one `entry` line per completed
action — append after the disposition is posted, the retry is spent, or the fix
is pushed, not before, so an interrupted action never leaves a false completion
claim in the ledger.

## Recovery rule

On resume, or after a context compaction, trust the ledger plus live PR and
watcher state over recollection. This skill's recovery rule is explicit about
two categories the ticket calls out because getting them wrong is costly:
re-dispositioning already-addressed feedback wastes review cycles and can post a
duplicate or contradictory reply, and re-spending retry budget the watcher
already accounted for can exhaust the configured maximum without ever running a
genuinely new attempt.

1. Read `.babysit-pr/<repo-slug>-pr<number>/ledger.jsonl` with `read_ledger`.
2. For each currently open feedback item, call
   `already_dispositioned(entries, item_id)`. This is a **dedup guard, not
   proof**: it returns the ledger's own latest `feedback_disposition` entry,
   filtered to closed dispositions (`fixed`, `rejected`, `not_applicable`) —
   `deferred` never counts as dispositioned, matching
   [Diagnose CI and feedback](../SKILL.md#diagnose-ci-and-feedback)'s own rule
   that a deferred finding stays outstanding, not resolved.
3. Verify that claim against live state before trusting it: the thread is still
   resolved/replied as recorded, and the recorded head SHA matches or precedes
   the PR's current head. Never re-disposition an item the ledger shows closed
   and live state confirms; recovery through
   [Process each snapshot](../SKILL.md#process-each-snapshot) still surfaces any
   *new* feedback normally.
4. Call `load_watcher_state(repo, pr_number)` to read the watcher's own state
   file, then `reconcile_with_watcher_state(entries, watcher_state)`. Its
   `retry_mismatches` flags any head SHA where this ledger recorded more retries
   than the watcher's `retries_by_sha` shows — investigate before spending
   another retry against that head, since the mismatch means a recorded retry
   never reached the watcher's own accounting. Its `dispositioned_feedback_ids`
   is the same closed-disposition set step 2 already computes, offered as one
   call for a caller that wants both at once.
5. Never re-spend retry budget the watcher state file already shows consumed for
   the current head. The watcher itself enforces this
   (`gh_pr_watch.current_retry_count`/`--retry-failed-now` refuses a retry past
   `--max-flaky-retries`); this ledger's role is orientation for *why* a given
   head is near or at budget, not a second enforcement point.

The ledger is orientation plus a dedup guard; live PR state and the watcher's
own state file remain the execution source of truth, unchanged from every other
precedence rule this skill already states — "Bind every gate to the candidate it
evaluated ... invalidate and rebuild every affected head-bound gate" in
[Establish candidate identity](../SKILL.md#establish-candidate-identity) applies
to ledger-recorded dispositions and retries exactly as it applies to validation
and review evidence. It is never itself a substitute for the final gate in
[Apply the final gate](../SKILL.md#apply-the-final-gate).

## Helper reference

`scripts/ledger.py` (unittest-covered in `scripts/tests/test_ledger.py`)
provides both a library API and a CLI. Its shared mechanics — workspace
derivation and self-exclusion, append-only JSON Lines I/O, and the recovery-path
dedup guard — live in `scripts/ledger_core.py`, a bundled, byte-identical copy
of this repository's own `ledger/core.py` kept in sync by `just sync-contracts`,
the same canonical-source-plus-bundled-copy convention already used for the
review lenses' shared contract. `ledger.py` itself is a thin wrapper fixing that
core to this skill's own vocabulary (`.babysit-pr/`, `item_id`,
`fixed`/`rejected`/`not_applicable` dispositions) and adds this skill's own
watcher-state reconciliation, which has no analog in the other two skills:

```bash
python3 scripts/ledger.py session-start --repo example/project --pr 482
python3 scripts/ledger.py record \
  --repo example/project --pr 482 --item review-comment-9001 \
  --action feedback_disposition --terminal-result fixed \
  --head-sha 4f2c9a1d --evidence-json '{"disposition": "fixed"}'
python3 scripts/ledger.py read --repo example/project --pr 482
python3 scripts/ledger.py find --repo example/project --pr 482 \
  --item review-comment-9001                    # exit 0 iff dispositioned
python3 scripts/ledger.py reconcile --repo example/project --pr 482
```

Pass `--root <ticket-worktree-root>` when not invoking from that directory;
every ledger path is resolved from it, never from this script's own installed
location. `reconcile` locates the watcher's own state file the same way
`gh_pr_watch.py` does, via `default_state_file_for` — it needs no `--root` for
that half of the comparison.
