---
name: review-fix-loop
description: 'Use when an existing committed candidate should be driven to review convergence — reviewed and remediated repeatedly until the complete repository-owned review comes back clean or a bounded stop condition is reached — or when a review-fix-loop document should be checked against the shared contracts. Two publication policies decide what reaches the remote: local_commit keeps every fix local, and update_pr publishes exactly once after convergence. Scope is one locked candidate: it never selects a ticket or opens a pull request. See design/review-fix-loop.md and references/CONTRACT.md.'
allowed-tools: Read, Grep, Glob, Bash, Agent, Task, Skill
---

# Review Fix Loop

`review-fix-loop` will become a repository-owned skill that takes cooperative
ownership of an existing committed candidate, runs the complete repository
review suite, applies material ticket-scoped fixes, and repeats until review
converges or a bounded stop condition is reached. The full design is
[`design/review-fix-loop.md`](../../design/review-fix-loop.md).

Six of its children are implemented so far:

- [Issue #96](https://github.com/shaug/compris/issues/96) (the first of epic
  [#95](https://github.com/shaug/compris/issues/95)) defines and validates the
  contracts every later child builds on:
  - the **invocation** a caller or standalone operator supplies to start or
    resume a loop;
  - the **durable checkpoint** the loop would record between phases; and
  - the **terminal result** the loop returns.
- [Issue #98](https://github.com/shaug/compris/issues/98) implements **reviewer
  isolation and complete-review orchestration**: resolving the fixed lens set a
  complete review must cover, running that review in a fresh read-only subagent
  by default (or, only through an explicit invocation override, in-agent),
  detecting an attempted reviewer mutation and failing that cycle closed, and
  normalizing findings into one deterministic order. See
  [`references/reviewer-orchestration.md`](references/reviewer-orchestration.md)
  and [`scripts/reviewer_orchestration.py`](scripts/reviewer_orchestration.py).
- [Issue #97](https://github.com/shaug/compris/issues/97) adds the local
  execution substrate those contracts describe: common-Git-common-directory
  locking, isolated attempt worktrees, durable checkpoint persistence and resume
  reconciliation, verified fast-forward-only canonical promotion, and recovery
  of an interrupted attempt. See [Local execution](#local-execution) below.
- [Issue #99](https://github.com/shaug/compris/issues/99) composes all three of
  the above into the actual standalone `local_commit` workflow: the full
  Resolve/Establish evidence/Review/Decide/Fix/Validate and commit/Invalidate
  and repeat/Publish/Return loop, fix-cycle budget enforcement, the automatic
  non-convergence stops, and terminal-result assembly — with no remote write in
  any path. See
  [Run the standalone `local_commit` workflow](#run-the-standalone-local_commit-workflow)
  below.
- [Issue #100](https://github.com/shaug/compris/issues/100) adds and evaluates
  `update_pr`: the same review/fix/converge machinery as `local_commit` — every
  intermediate fix commit stays local — plus one expected-old, fast-forward-only
  Git publish immediately after convergence. Resolves and cross-validates the
  fork/remote publication target (never assuming "origin" ownership), validates
  `remote_iteration_grants`, and preserves the converged local commit with an
  actionable recovery path when the publication race is lost or the remote is
  unavailable. See
  [Run the standalone `update_pr` workflow](#run-the-standalone-update_pr-workflow)
  below.
- [Issue #101](https://github.com/shaug/compris/issues/101) adds the
  cross-cutting, result-blind evaluation corpus that establishes this skill's
  behavioral contract across both execution modes from externally observable Git
  evidence, not the returned terminal-result document's own claims. See
  [Evaluation](#evaluation) below.

Use [`scripts/local_commit.py`](scripts/local_commit.py)'s
`run_local_commit(...)` to run a complete standalone `local_commit` invocation
end to end, and [`scripts/update_pr.py`](scripts/update_pr.py)'s
`run_update_pr(...)` for `update_pr`; use the lower-level modules directly only
when you need just one of their individual behaviors (validating a document,
running one review pass, or acquiring a lock and running one isolated attempt)
outside the full loop.

## Load the contracts

Read [`references/CONTRACT.md`](references/CONTRACT.md) and the three schemas
beside it before authoring or trusting any invocation, checkpoint, or
terminal-result document:

- [`references/invocation.schema.json`](references/invocation.schema.json)
- [`references/checkpoint.schema.json`](references/checkpoint.schema.json)
- [`references/terminal-result.schema.json`](references/terminal-result.schema.json)

[`references/examples/`](references/examples) contains complete, valid documents
for both the `local_commit` and `update_pr` publication policies, including a
`changes_remaining` and a `blocked` terminal result, each already in the
canonical serialized form `scripts/validate.py` produces.

## Validate a document

`scripts/validate.py` is dependency-free, matching the convention used by the
bundled `review-code-change` review-suite contract, so it works wherever this
skill is installed:

```bash
python3 skills/review-fix-loop/scripts/validate.py invocation path/to/invocation.json
python3 skills/review-fix-loop/scripts/validate.py checkpoint path/to/checkpoint.json
python3 skills/review-fix-loop/scripts/validate.py terminal-result path/to/result.json
```

Each prints `valid <kind>: <path>` and exits `0` on success, or prints one
diagnostic per violation to stderr and exits `1`. A malformed document exits
`2`.

The module also exposes importable functions for a caller that already holds
parsed documents in memory: `validate_invocation`, `validate_checkpoint`,
`validate_terminal_result`, `reconstruct_cycle_accounting` (derive consumed and
remaining fix cycles from a checkpoint's recorded attempts),
`validate_checkpoint_against_invocation` (confirm a checkpoint's initial head,
original base, cycle budget, invocation ID, repository, and publication policy
match the invocation it derives from), and
`validate_terminal_against_checkpoint` (confirm a terminal result's budget and
head/base identities match the checkpoint it derives from). See
[`references/CONTRACT.md`](references/CONTRACT.md) for the cross-field semantics
these functions enforce beyond plain JSON Schema, and
`scripts/tests/test_validate.py` for the complete valid, invalid, boundary, and
round-trip case coverage.

## Run a complete review

Read
[`references/reviewer-orchestration.md`](references/reviewer-orchestration.md)
in full before running a review pass; it implements design's "Review execution"
and "Reviewer write prevention" sections and workflow step 3 ("Review"). In
summary:

1. Confirm `review-code-change` and its three lens skills are available; fail
   closed (`blocked/missing_capability`) if not.
2. Resolve this invocation's review-execution mode with
   `resolve_review_execution_mode` — `fresh_subagent` by default, or the
   invocation's explicit `in_agent_override` when authorized. There is no
   automatic fallback between them.
3. Build the raw review-code-change packet bound to the exact current head and
   comparison base, prepend `build_reviewer_briefing`'s literal prohibitions,
   and invoke `review-code-change` in a fresh subagent (or, only under the
   explicit override, in-agent) restricted to
   `Read, Grep, Glob, Bash, Agent, Task, Skill` — never a file-editing or
   remote-write tool.
4. Capture worktree state, including local refs (excluding `refs/remotes/*`),
   immediately before and after the pass and run `detect_worktree_mutation` on
   the two snapshots, passing `candidate_branch_ref`, `attempt_namespace_prefix`
   (from `local_execution.attempt_namespace_ref_prefix`), and
   `review_execution.exclusive_ref_store` (it raises if either snapshot is
   missing a required capture key, rather than silently treating an uncaptured
   dimension as unchanged). It returns a `WorktreeMutationReport`, not a flat
   list: a Tier 1 `candidate_mutations` entry (`head_sha`, the candidate branch
   ref, or this invocation's own attempt namespace) means the candidate itself
   moved — stop immediately and return `blocked/candidate_integrity_failure`
   without building a `review_records` entry, since the packet's expected head
   and base are now stale. Everything else — worktree path state plus, under
   `exclusive_ref_store`, every other local ref — lands in `mutation_attempts`;
   every remaining local ref lands in non-gating `observed_ref_changes`. See
   [`references/reviewer-orchestration.md`](references/reviewer-orchestration.md)'s
   "Reviewer write prevention" tier 4 for the full attribution rationale.
5. Build one `review_records` entry with `build_review_record`, passing both the
   exact packet handed to the reviewer (`packet=...`, required) and its result,
   feeding in `mutation_attempts` (worktree state plus any tool-trace evidence),
   `observed_ref_changes`, and `integrity_evidence` (`"tool_trace"` when the
   host performed tool-trace inspection for this pass, `"surface_only"`
   otherwise). This validates the packet and result together — including
   catching a `clean` verdict paired with a packet whose own required validation
   entry was `failed` or `unavailable`, which a result-only check cannot see —
   and raises `ReviewIntegrityError` instead of returning a partially trusted
   record. A non-empty `mutation_attempts` always yields
   `write_isolation: "violated"`, even when the aggregate verdict itself looked
   clean — stop immediately and return `blocked/reviewer_integrity_failure`
   rather than continuing to iterate on that pass's findings.
   `observed_ref_changes` never affects `write_isolation`; a `surface_only`
   `integrity_evidence` still reaches `converged`.
6. When the verdict is not `clean`, use `normalize_findings` and
   `select_next_finding` to identify the next finding in one deterministic order
   — selecting a finding is not disposing or fixing it; that remains a later
   child's "Decide"/"Fix" responsibility.

`scripts/reviewer_orchestration.py` is dependency-free, matching
`scripts/validate.py`'s convention, and bundles the same
`references/review-suite/` contract copy and `scripts/review_gate.py` gate
`implement-ticket` and `babysit-pr` already ship (kept in sync via the
repository's `just sync-contracts`) — it does not reimplement candidate/
lens-execution binding, only reuses the canonical `review_gate.evaluate_bound`.
See `scripts/tests/test_reviewer_orchestration.py` for complete coverage of lens
resolution, rejection of an incomplete or stale-bound result, default
fresh-reviewer selection with no automatic fallback, the explicit in-agent
override, reviewer-identity freshness, mutation detection that fails a cycle
closed, and deterministic finding normalization/selection.

## Local execution

`scripts/local_execution.py` is dependency-free and loads `scripts/validate.py`
from this same directory via `importlib` rather than duplicating any schema or
cross-field check, so a caller always resumes and promotes against the exact
contract `references/CONTRACT.md` defines. It implements the parts of
`design/review-fix-loop.md`'s "Local ownership and checkpointing" section this
repository can exercise without a selected fix:

- `acquire_candidate_locks` — the non-blocking, common-Git-common-directory
  local-ref lock plus the optional `update_pr` remote-target lock, acquired in
  that fixed order and released in reverse, so conflicting local invocations can
  never both own the same target and lock ordering cannot self-deadlock.
- `write_checkpoint_atomic`, `read_checkpoint`, and
  `reconcile_checkpoint_for_resume` — durable, schema-validated checkpoint
  persistence and the complete design-required resume precondition set (no
  active lock holder, matching cross-document identity, a clean candidate, and
  live head/base agreement).
- `create_attempt`, `commit_attempt`, `promote_attempt`, `discard_attempt`, and
  `cleanup_attempt` — an isolated attempt worktree and branch created from the
  exact canonical head, a verified fast-forward-only promotion that leaves the
  canonical candidate untouched on any failure, and cleanup that only ever acts
  on the `review-fix-loop/attempt/` namespace it created.
- `recover_interrupted_attempts` — reconciles attempt branches an interrupted
  invocation left behind against a checkpoint's own history, returning each
  uniquely identifiable leftover for the caller to retry or discard, and raising
  rather than guessing when reconciliation is ambiguous.

See the module's own docstrings and
[`scripts/tests/test_local_execution.py`](scripts/tests/test_local_execution.py)
for the complete contention, interruption, stale-state, dirty-worktree,
promotion-race, and cleanup-safety coverage. Selecting which finding to fix,
writing the fix's content, and publishing to a remote remain out of scope here;
a caller supplies the fix content and invokes these primitives around it.

## Run the standalone `local_commit` workflow

Read [`references/local-commit.md`](references/local-commit.md) in full before
running an end-to-end invocation; it implements every remaining "Workflow" step
design describes plus "Convergence and stop conditions" and the `local_commit`
half of "Publication policy". In summary:
[`scripts/local_commit.py`](scripts/local_commit.py)'s `run_local_commit(...)`
composes `validate.py`, `local_execution.py`, and `reviewer_orchestration.py`
into the complete loop: resolve the invocation and acquire the candidate lock;
establish and classify validation evidence; run a complete review and detect any
reviewer mutation; decide each selected finding's disposition; fix, validate,
and commit an accepted finding in an isolated attempt, promoting only on
success; repeat with a fresh review after every promotion; and return one
schema-valid, candidate-bound terminal result (`converged`, `changes_remaining`,
or `blocked`) — never performing a remote write. The three genuinely
host-boundary actions (running one review pass, deciding a finding's
disposition, and writing a fix's content) are supplied by the caller as small
callables; every other action — locking, Git, checkpointing, promotion,
review-result evaluation — happens for real, matching this skill's existing "no
mocked Git state" testing convention.

See [`scripts/tests/test_local_commit.py`](scripts/tests/test_local_commit.py)
for complete end-to-end coverage: immediate convergence, one and multiple fix
cycles, budget exhaustion, a validation failure that is unavailable,
untractable, and tractable, a declined finding and a scope-expanding fix (both
surfaced as operator input), a fix that introduces a new finding, an oscillating
finding set, two consecutive failed attempts, recovery from an interrupted
attempt, an already-held candidate lock, an attempted reviewer mutation, and a
host without fresh-subagent support.

## Run the standalone `update_pr` workflow

Read [`references/update-pr.md`](references/update-pr.md) in full before running
an end-to-end `update_pr` invocation; it implements design's "Publication
policy" > `update_pr`, "Origin-visible exception", workflow step 8 "Publish
after convergence", and the `update_pr` parts of "Local ownership and
checkpointing" > "Cooperative ownership". In summary:
[`scripts/update_pr.py`](scripts/update_pr.py)'s `run_update_pr(...)` composes
the exact same review/fix/converge engine `local_commit.py` already implements —
it never reimplements Resolve/Establish evidence/Review/Decide/Fix/Validate and
commit/Invalidate and repeat, and every intermediate fix commit stays local
exactly as under `local_commit`. Only the publication tail differs:

1. Resolve and cross-validate the publication target from
   `candidate.source_binding` (the actual pushable remote — never assumed to be
   this repository's own `origin`, so a fork's own remote is handled identically
   to a same-repository branch) and `publication.pull_request` (the PR's own
   head-repository/head-ref/expected-old identity); a mismatch between the two
   fails closed with `blocked/missing_authority` before any lock, review, or
   mutation. Validate every `remote_iteration_grants` entry against that same
   resolved target the same way.
2. Acquire the same local candidate lock as `local_commit` plus the
   `update_pr`-only remote-target lock (already implemented by
   [Local execution](#local-execution)'s `acquire_candidate_locks`).
3. Run the identical loop, with one added check at the two points
   `local_commit`'s engine already calls a policy hook from (before establishing
   evidence for a fresh review, and before starting a fix attempt): reread the
   live remote head and stop with `blocked/remote_advanced` if it no longer
   matches the invocation's recorded `expected_old_head_sha`.
4. The instant the aggregate review is clean, and only then: fetch and reread
   the exact remote head; require it to equal `expected_old_head_sha`; prove the
   local candidate is a non-rewriting descendant of it; perform one
   `--force-with-lease=<head_ref>:<expected_old_head_sha>` push; and read the
   ref back to confirm it now equals the converged local head. Any failure at
   any of those steps returns `blocked` (`remote_advanced`,
   `candidate_integrity_failure`, or `publication_failed`) and preserves the
   converged local commit exactly as `local_commit` always would — this never
   merges, rebases, force-updates, or otherwise supersedes a competing
   candidate.

See [`scripts/tests/test_update_pr.py`](scripts/tests/test_update_pr.py) for
complete disposable-remote coverage (every test drives a real temporary Git
repository and a real disposable local bare repository as the publication remote
— never this repository's actual `origin`): a successful converge-then-publish
run with and without a fix cycle, a fork target resolved without assuming origin
ownership, a competing remote update that cannot be overwritten, local
non-fast-forward history relative to the recorded expected-old head, a
misconfigured publication target, a mismatched remote-iteration grant, an
unreachable remote, the remote-target lock actually being exercised through
`run_update_pr`, and rejection of an invalid invocation or a `local_commit`
invocation at the API boundary.

## Publication policy and retained commits

Both standalone workflows keep every intermediate fix commit strictly local
until the aggregate review converges. Neither workflow ever publishes a fix as
it is made; there is no partial-publication path.

- `local_commit` never writes to a remote at all, converged or not. A converged
  result reports `publication.status: not_applicable` and lists every commit it
  made in `unpushed_commits` — this is the expected, non-error shape of success,
  and `operator_action` names how the operator publishes those commits through
  their own workflow.
- `update_pr` publishes exactly once, only in the instant the aggregate review
  first comes back clean, via one expected-old, fast-forward-only Git push (see
  [Run the standalone `update_pr` workflow](#run-the-standalone-update_pr-workflow)
  above). Before that instant, and on every non-`converged` exit
  (`changes_remaining` or `blocked`, including `remote_advanced` and
  `publication_failed`), the commits this invocation made remain local and
  unpushed.
- **Every non-converged terminal result — under either policy — reports its
  retained, unpushed commits explicitly in `unpushed_commits` and names the
  concrete next step in `operator_action`.** A caller must not assume "no error"
  means "nothing to do": read `terminal_state`, `unpushed_commits`, and
  `operator_action` together before treating an invocation as finished, and see
  [`references/CONTRACT.md`](references/CONTRACT.md)'s "Terminal result" section
  for the complete per-state publication and retained-commit rules the validator
  enforces.

## Evaluation

[`evals/README.md`](evals/README.md) documents the cross-cutting, result-blind
evaluation corpus in [`scripts/evals/`](scripts/evals): twenty scenarios,
covering convergence, repeated findings, invalid/incomplete reviews, declined
findings, budget exhaustion, interruption and recovery, validation failure,
reviewer mutation, and publication races across both `local_commit` and
`update_pr`, plus the fresh-subagent default and the explicit in-agent override.
Every scenario drives the real engine against a real disposable Git repository
(and, for `update_pr`, a real disposable bare remote) and is graded against
independently derived Git evidence — a real commit count, a real file's content
at a real commit, a real remote ref, a real object's reachability — never the
returned terminal-result document's own claims, so a result that only *asserts*
success cannot pass. No subprocess boundary and no model call is involved, so
the whole corpus runs deterministically under `just test` (via
[`scripts/tests/test_evals.py`](scripts/tests/test_evals.py)) and standalone via
`just eval-review-fix-loop`.

## Non-goals

- Creating, merging, closing, or otherwise managing a pull request.
- Force-pushing or rewriting remote history — `update_pr` performs only one
  expected-old, fast-forward-only Git update.
- Migrating `implement-ticket`, `babysit-pr`, `carve-changesets`, or any other
  existing caller.
- Owning acceptance criteria or a caller-specific acceptance ledger — the
  contract records `acceptance_reconciliation_required` but the caller always
  retains its own ledger.
- Distributed coordination beyond this skill's local locks and Git
  compare-and-swap (no distributed lease, fencing token, or coordinator
  service).
