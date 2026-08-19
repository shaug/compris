# Reviewer isolation and complete-review orchestration

This document implements
[`design/review-fix-loop.md`](../../../design/review-fix-loop.md)'s "Review
execution" and "Reviewer write prevention" sections (under "Invocation
contract") and workflow step 3 ("Review"), for the executing agent that follows
[`SKILL.md`](../SKILL.md). It does not define locking, isolated attempts,
worktree management, or publication — those belong to the sibling children this
document links to below. It also does not define the "Decide" (step 4) or "Fix"
(step 5) workflow steps: choosing which finding to accept, reject, or defer, and
applying the resulting edit, remain a later child's responsibility (see design's
"Compatibility and rollout").

Load [`scripts/reviewer_orchestration.py`](../scripts/reviewer_orchestration.py)
for the deterministic decisions and data transformations this document
describes; it is dependency-free like every other script in this skill, and its
docstrings cross-reference the specific acceptance criterion or design
requirement each function satisfies.

## Lens resolution

`review-fix-loop` has no selectable lens subset. The complete repository review
suite — `review-code-change`, which in turn sequences
`review-solution-simplicity`, `review-correctness`, and `review-code-simplicity`
— is the sole initial review mode for every cycle. Do not invoke an individual
lens directly, and do not accept an invocation field that tries to request a
narrower set; the invocation schema has none, and
`scripts/reviewer_orchestration.py`'s `resolve_review_lenses()` returns this
fixed set from the same constant the bundled review-suite contract uses to
enforce it (`REQUIRED_AGGREGATE_LENSES`), so no caller or test hand-copies the
three lens names and risks drifting from the contract that actually enforces
them.

"Resolving" a review therefore means: confirm `review-code-change` and its three
lens skills are available (fail closed per its own `SKILL.md` if not), and
require every review pass's result to demonstrate it actually covered all three
— see "Rejecting an incomplete result" below.

## Review execution

The default execution mode is `fresh_subagent`. Every review pass:

1. **Creates a new aggregate-review context.** In a runtime that supports
   subagents (for example Claude Code's Agent/Task tool), spawn one new subagent
   scoped to this pass only. Never reuse a subagent from a prior pass, and never
   reuse the implementation/mutation context itself as the reviewer.
2. **Supplies only raw evidence.** Build the shared review-code-change packet
   (goal, acceptance criteria, non-goals, preserved behaviors, sources,
   candidate diff, worktree state, and exact focused/full validation evidence)
   bound to the exact current head and comparison base. Withhold the
   implementation transcript, the intended fix, prior conclusions, suspected
   findings, and the expected result.
3. **Grants no mutation authority.** The reviewer subagent's tool surface must
   exclude file-editing, commit, push, communication, merge, and
   tracker-mutation tools. In Claude Code, restrict it to
   `Read, Grep, Glob, Bash, Agent, Task, Skill` — the same tool set
   `review-code-change` itself declares — never `Edit`, `Write`, `NotebookEdit`,
   or any tool capable of a remote write.
4. **Discards the reviewer context after the result.** Do not carry a reviewer
   subagent's working notes, intermediate reasoning, or session state into the
   next pass or into the fix cycle that follows.
5. **States no conclusion.** The reviewer receives evidence and contracts and
   never the answer. If the prompt being written steers the verdict — "do not
   flag", "this is fine", a pre-judged severity, or the result expected back —
   stop and rewrite it. This is the dispatch-side counterpart of step 2's
   withholding rule: step 2 keeps the intended fix out of the packet, and this
   keeps it out of the prompt wrapped around the packet. A steered reviewer
   returns confirmation, and a loop that converges on confirmation reports
   convergence it never earned.

Give each review pass a capability tier adequate for judgment: it inherits the
session's tier by default rather than the cheapest one, and a pass that missed a
defect a later pass surfaces escalates one tier instead of rerunning
identically. Prefer one well-briefed pass to several thin ones — every pass
spends from the cycle budget, and the budget is what bounds this loop.

`review-code-change` runs its own complete lens sequence
(`review-solution-simplicity`, `review-correctness`, `review-code-simplicity`)
inside that one aggregate-review subagent. Those nested lens invocations may
share the aggregate-review subagent's context — `review-fix-loop` does not spawn
a second subagent per lens itself, and this sharing does not weaken
completeness: `review-code-change`'s own aggregate `clean` verdict still
requires a fresh, current-head, `clean` execution from each of the three lenses
(enforced independently by the bundled contract's
`_check_aggregate_clean_lens_executions`, which `evaluate_review_result` below
reuses). Sharing a context changes *where* the lenses run, not whether each one
actually ran fresh against the exact candidate.

### The explicit in-agent override

`in_agent_override` runs the same complete aggregate review in the
implementation agent's own context instead of a fresh subagent. Use it only when
the invocation carries a non-empty `review_execution.override_authorization`
(already required by `validate_invocation`); there is no automatic fallback.

- Call
  `resolve_review_execution_mode(mode, override_authorization=..., host_supports_fresh_subagent=...)`
  to resolve what this specific host and invocation actually grant. An explicit
  override is honored regardless of whether the host could have run
  `fresh_subagent` — the override does not require the fresh path to be
  unavailable first.
- When `mode` is `fresh_subagent` and the host cannot spawn an isolated context,
  `resolve_review_execution_mode` returns
  `blocked_reason: "missing_capability"`. Return `blocked/missing_capability`;
  never silently run in-agent instead.
- Record the resolved `independence` (`fresh_subagent` or `in_agent_override`)
  in every `review_records` entry's `review_independence` field — this is what
  makes "in-agent execution occurs only when explicitly requested and is
  recorded in the result" true in the actual checkpoint/terminal-result
  documents, not just in this document's prose.

## Reviewer write prevention

"Read-only" is a capability boundary, not merely prompt language. Apply every
tier the runtime supports, strongest first:

1. **Immutable snapshot or deny-write filesystem boundary**, when the runtime
   can provide one.
2. **A restricted reviewer tool surface** without edit, patch, file-write,
   commit, push, or remote-write operations (see "Review execution" step 3
   above).
3. **Read-only inspection commands only** inside the reviewer context —
   validation and diagnostic commands the invocation already recorded, never an
   ad hoc write.
4. **Before/after state capture, attributed by tier**: snapshot `head_sha`,
   local `refs` (for example via `git for-each-ref`), and
   tracked/staged/unstaged/untracked/ignored worktree state immediately before
   spawning the reviewer and immediately after it returns — every key
   `REQUIRED_SNAPSHOT_KEYS` names. Pass both snapshots to
   `detect_worktree_mutation(before, after, candidate_branch_ref=..., attempt_namespace_prefix=..., exclusive_ref_store=...)`,
   which raises `ValueError` if either snapshot is missing a required key (fails
   closed rather than silently treating an uncaptured dimension as unchanged)
   and otherwise returns a `WorktreeMutationReport` that separates *what
   changed* from *what can be attributed to this pass* — a single before/after
   diff cannot itself tell a candidate-defining ref moving under the reviewer
   from an unrelated ref moving beside it, so this function classifies rather
   than flattening both into one undifferentiated mutation list:
   - **Tier 1 — candidate-bound refs** (`candidate_mutations`): `head_sha`, the
     candidate branch ref (`candidate_branch_ref`), and this invocation's own
     `refs/heads/review-fix-loop/attempt/<invocation_id>/*` namespace
     (`attempt_namespace_prefix`, from
     `local_execution.attempt_namespace_ref_prefix(invocation_id)`). A change
     here invalidates the candidate itself regardless of who caused it — the
     evidence this pass reviewed no longer describes the live candidate. Stop
     immediately and return `blocked/candidate_integrity_failure`, the same
     reason the "resolve" workflow step already uses when a resumed live head
     doesn't match its checkpoint, without building or appending a
     `review_records` entry: the packet's `expected_head`/`expected_base` are
     now stale, so a record bound to them would misrepresent the live candidate
     rather than describe it.
   - **Tier 2 — every other local ref** (`observed_ref_changes` by default,
     including the comparison base ref and another invocation's own attempt
     namespace): unattributable from the ref map alone — the ref store may be
     shared across several worktrees, or unrelated background automation (a
     `pull --ff-only` of `main`, a sibling worktree's own branch) may be running
     concurrently. Non-gating: record it verbatim on the review record's
     `observed_ref_changes` and continue — `write_isolation` stays `enforced`
     and the pass can still reach `converged`. Set
     `review_execution.exclusive_ref_store: true` on the invocation only for a
     dedicated clone this invocation genuinely owns exclusively; that folds
     every Tier 2 ref change back into `mutation_attempts` below, reproducing
     the flat behavior this tiering replaces.
   - Worktree path state — `tracked`/`staged`/`unstaged`/`untracked`
     (`mutation_attempts`) — is compared exactly as before this tiering existed
     and is never subject to Tier 1/Tier 2 attribution: a worktree's index and
     working directory are never shared across worktrees the way a ref store can
     be, so a path-state change stays fully attributable to this pass.
     `refs/remotes/*` entries are excluded from every tier: an unattributed
     remote-tracking-ref advance is the ordinary `remote_advanced`
     publication-race contract (issue #97/#100's scope), not reviewer
     misconduct. `ignored` is captured (required above) but deliberately not
     compared: authorized recorded validation commands legitimately create or
     change ignored build artifacts (`__pycache__/`, `.ruff_cache/`, `.venv/`),
     so comparing it would make every review pass that runs validation falsely
     report a mutation — this mirrors the invocation-cleanliness contract's own
     rule that ignored files "do not represent an uncommitted change and are not
     part of what 'clean' means here."
5. **Tool-trace inspection**, when the runtime exposes one, for an attempted
   mutation that a capability boundary already blocked. This is the only channel
   that can attribute a Tier 2-shaped observation (a mutation the before/after
   ref diff alone could not pin on this pass) to the reviewer: feed it through
   `ReviewPass.mutation_attempts`, and set
   `ReviewPass.tool_trace_available = True` whenever the host actually performed
   this inspection for the pass — whether or not it found anything — so
   `build_review_record`'s `integrity_evidence` can record `"tool_trace"` rather
   than the default `"surface_only"`. A reader can then tell "inspected and
   clean" from "never inspected"; a `surface_only` pass still reaches
   `converged` when otherwise clean.

Certification requires enforced write isolation; before/after verification alone
is not sufficient by itself — it is tier 4 of five, not a replacement for tiers
1–3 where the runtime supports them.

An attempted prohibited mutation invalidates the review even when the runtime
blocked it. Feed `detect_worktree_mutation`'s `mutation_attempts` (Tier 1 refs
are handled separately, above) plus any tool-trace evidence into
`build_review_record`'s own `mutation_attempts` parameter, and its
`observed_ref_changes` into the same-named parameter. A non-empty
`mutation_attempts` always sets `write_isolation: "violated"`, regardless of the
aggregate verdict, and `scripts/validate.py`'s
`_check_converged_requires_clean_evidence` already rejects `converged` for *any*
`review_records` entry with a non-empty `mutation_attempts` — not only the
final-head-bound one. `observed_ref_changes` never affects `write_isolation` —
an unattributed Tier 2 ref advance by itself is not proof of reviewer
misconduct, exactly as an unattributed remote-ref advance already wasn't; that
is the ordinary `remote_advanced` publication-race contract (issue #97/#100's
scope) or unrelated concurrent activity in a shared ref store (issue #245's
scope), not a reviewer-integrity failure.

**Stop immediately on a mutation attributable to this pass.** Design assigns
that judgment to "the phase that observed it" — this phase, the moment
`detect_worktree_mutation`'s `mutation_attempts` (or tool-trace evidence)
returns non-empty for a pass this cycle just ran. Do not keep iterating on that
pass's findings, and do not wait for a later phase to notice the tainted
`review_records` entry indirectly. Stop the invocation and return
`blocked/reviewer_integrity_failure` immediately, preserving the unexpected
worktree/ref state for operator inspection rather than resetting or repairing
it. The `mutation_attempts`/`write_isolation: "violated"` chain into
`_check_converged_requires_clean_evidence` is a backstop that keeps a stale
checkpoint from ever certifying `converged` later — it is not a substitute for
this immediate stop. A Tier 1 `candidate_mutations` change stops the invocation
the same way, but with `blocked/candidate_integrity_failure` instead: that
judgment is about the candidate's own identity, not about what the reviewer
attempted, so it never touches `write_isolation` or `mutation_attempts` at all.

### The reviewer briefing

Call
`build_reviewer_briefing(independence=..., head_sha=..., comparison_base_sha=...)`
and prepend its return value to the raw evidence handed to the reviewer context,
before the review-code-change invocation itself. It states the exact execution
context, the exact candidate, and the literal prohibitions
(`REVIEWER_PROHIBITIONS`): report findings only; never stage, commit, amend,
rebase, or push any ref; never run a tool or command that writes to the working
tree, index, or any ref; never resolve conflicts, run formatters or codemods, or
apply any proposed fix, including one the reviewer itself proposes. This is the
acceptance criterion "Reviewer instructions explicitly prohibit worktree
mutation and implementation" made literal: the same wording travels with every
review pass instead of living only in this document.

## Rejecting an incomplete result

The acceptance criterion "Reviewer output is rejected if required lenses or
evidence are incomplete" has two distinct halves, both enforced by the single
`evaluate_review_result(packet, result, expected_head, expected_base)`:

- **Lenses**: an empty return means `result` is schema-valid, cross-field
  consistent, and bound to the exact head and comparison base this cycle
  captured — including every `lens_executions` entry, not only the result's own
  `candidate`.
  - A `clean` verdict must demonstrate a fresh, current-head, `clean` execution
    for all three required lenses; a result missing one, reusing a stale head,
    or reusing an old base is rejected, not silently treated as complete.
  - A `changes_required` verdict is not required to carry all three lens
    executions: the orchestration protocol stops at the first gating finding, so
    a partial `lens_executions` list there is expected and valid.
  - A `blocked` verdict may omit candidate identity entirely when the caller
    could not establish it; this is not treated as a stale-candidate mismatch.
- **Evidence**: the function also validates `packet` — the raw evidence packet
  review-fix-loop actually handed to the reviewer — against `result` and against
  `expected_head`/`expected_base` directly. A single-document check on the
  result alone cannot see this: the shared review-suite contract's "validation
  must back a clean verdict" rule (`_check_clean_requires_passing_validation`)
  needs the packet's own `validation` array.

`packet` is required, not optional: review-fix-loop's own checkpoint/
terminal-result contract (from #96) never persists a raw packet or raw result on
its own, so no caller can legitimately hold one without the other, and a
packet-less evaluation could let a `clean` verdict with actually-failed packet
validation slip through undetected.

Treat any non-empty return as a failed review pass: do not build a
`review_records` entry from it. `build_review_record` enforces this directly —
it raises `ReviewIntegrityError` instead of returning a partially trusted
record.

## Building the review record

Once a raw result and its packet pass evaluation, call:

```python
build_review_record(
    sequence=<next cycle_attempts/review sequence number>,
    packet=<the exact packet handed to the reviewer>,
    result=<raw review-code-change aggregate result>,
    expected_head=<exact current head SHA>,
    expected_base=<exact current comparison-base SHA>,
    independence=<"fresh_subagent" or "in_agent_override">,
    reviewer_identity=<generate_reviewer_identity(independence, sequence)>,
    mutation_attempts=<detect_worktree_mutation(before, after) + any tool-trace evidence>,
)
```

The returned dict matches `checkpoint.schema.json`'s `review_records` item
exactly — append it to the checkpoint's `review_records` array (and, at return
time, the terminal result's own `review_records`). It leaves
`finding_dispositions` empty: disposing a finding as `accepted`, `rejected`, or
`deferred` is workflow step 4 ("Decide"), which this document and its script do
not implement. Populate that field only once a later child (or caller) actually
runs Decide for this exact head/base pair.

## Normalizing findings for deterministic selection

`review-code-change` does not guarantee any particular ordering of findings
across lenses or review passes. Call `normalize_findings(result["findings"])` to
get one deterministic order — sorted by severity (`blocking` before
`strong_recommendation` before `defer`), then lens, then stable finding `id` —
regardless of the input order the raw result happened to produce. This is what
makes finding-to-fix linkage and checkpoint replay reproducible given
byte-identical review evidence, instead of depending on incidental lens or
dict-insertion order.

`select_next_finding(result["findings"])` returns the one finding a fix cycle
would target next: the first gating (`blocking` or `strong_recommendation`)
entry of that canonical order, or `None` when only `defer` findings remain.
Selecting a finding is not disposing or fixing it; a later child's Decide step
still verifies the selected finding's evidence against the candidate, confirms
it is within `change_contract.allowed_remediation_scope`, and only then accepts,
rejects, or defers it.

## Related documents

- [`design/review-fix-loop.md`](../../../design/review-fix-loop.md) — the
  authoritative design this document implements a slice of.
- [`references/CONTRACT.md`](CONTRACT.md) — the invocation, checkpoint, and
  terminal-result schemas' cross-field semantics `build_review_record`'s output
  must satisfy.
- [`skills/review-code-change/references/orchestration-protocol.md`](../../review-code-change/references/orchestration-protocol.md)
  — the lens sequencing and aggregation this document's "aggregate-review
  subagent" invokes; this document does not redefine or duplicate it.
